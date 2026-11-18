"""OpenRouter client, JSON helper and cost tracking."""
import json
import os
import re
import time

try:  # trust the Windows/macOS certificate store (needed behind HTTPS-inspecting filters/proxies/antivirus)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from langchain_openai import ChatOpenAI

OPENROUTER_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

# USD per 1M tokens (input, output). APPROXIMATE - verify at openrouter.ai/models and edit.
PRICES = {
    "openai/gpt-4o-mini": (0.15, 0.60),
    "meta-llama/llama-3.3-70b-instruct": (0.10, 0.25),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "deepseek/deepseek-chat": (0.2574, 1.029),  # openrouter.ai/deepseek/deepseek-chat, 2026-11-18 (cheapest standard-routed provider)
    "anthropic/claude-sonnet-5.5": (2.00, 10.00),  # openrouter.ai/anthropic/claude-sonnet-5-5
}
# Rate used for the "theoretical" cost of a model that is not in PRICES.
THEORETICAL_DEFAULT = (0.15, 0.60)

CONFIG = {"model": None}


def current_model() -> str:
    return CONFIG["model"] or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL


def _rates(model: str) -> tuple[float, float]:
    return PRICES.get(model.removesuffix(":free"), THEORETICAL_DEFAULT)


class CostTracker:
    def __init__(self):
        self.rows: list[dict] = []

    def reset(self):
        self.rows = []

    def add(self, node, model, tin, tout, seconds):
        rin, rout = _rates(model)
        theoretical = (tin * rin + tout * rout) / 1_000_000
        actual = 0.0 if model.endswith(":free") else theoretical
        self.rows.append(dict(node=node, model=model, input_tokens=tin, output_tokens=tout,
                              actual_usd=actual, theoretical_usd=theoretical, seconds=seconds))

    def by_node(self) -> list[dict]:
        agg: dict[str, dict] = {}
        for r in self.rows:
            a = agg.setdefault(r["node"], dict(node=r["node"], calls=0, input_tokens=0, output_tokens=0,
                                               actual_usd=0.0, theoretical_usd=0.0, seconds=0.0))
            a["calls"] += 1
            for k in ("input_tokens", "output_tokens", "actual_usd", "theoretical_usd", "seconds"):
                a[k] += r[k]
        return list(agg.values())

    def total(self) -> dict:
        keys = ("input_tokens", "output_tokens", "actual_usd", "theoretical_usd", "seconds")
        t = {k: sum(r[k] for r in self.rows) for k in keys}
        t["calls"] = len(self.rows)
        return t

    def table(self) -> str:
        head = f"{'node':<22}{'calls':>6}{'tokens in/out':>16}{'actual $':>11}{'theoretical $':>15}"
        lines = [head]
        for r in self.by_node():
            lines.append(f"{r['node']:<22}{r['calls']:>6}{r['input_tokens']:>8}/{r['output_tokens']:<7}"
                         f"{r['actual_usd']:>11.5f}{r['theoretical_usd']:>15.5f}")
        t = self.total()
        lines.append(f"{'TOTAL':<22}{t['calls']:>6}{t['input_tokens']:>8}/{t['output_tokens']:<7}"
                     f"{t['actual_usd']:>11.5f}{t['theoretical_usd']:>15.5f}")
        return "\n".join(lines)


TRACKER = CostTracker()


def invoke(node: str, system: str, user: str, model: str | None = None, temperature: float = 0.2) -> str:
    model = model or current_model()
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set (see .env.example)")
    # Without max_tokens OpenRouter reserves the model's maximum (16384 for deepseek) against the
    # credit balance and answers 402 when the balance is lower. Our outputs are short JSON/prompts.
    max_out = int(os.getenv("MAX_OUTPUT_TOKENS", "3000"))
    llm = ChatOpenAI(model=model, base_url=OPENROUTER_URL, api_key=key, max_tokens=max_out,
                     temperature=temperature, timeout=90, max_retries=2)
    t0 = time.time()
    try:
        msg = llm.invoke([("system", system), ("user", user)], config={"run_name": node})
    except Exception as e:
        if "402" in str(e):
            raise RuntimeError("OpenRouter 402: אין מספיק קרדיט בחשבון (או MAX_OUTPUT_TOKENS גבוה מדי). "
                               "הוסיפי קרדיט ב-openrouter.ai/credits או הורידי MAX_OUTPUT_TOKENS ב-.env.") from e
        raise
    text = msg.content if isinstance(msg.content, str) else "".join(
        p.get("text", "") for p in msg.content if isinstance(p, dict))
    usage = getattr(msg, "usage_metadata", None) or {}
    tin = usage.get("input_tokens") or (len(system) + len(user)) // 4
    tout = usage.get("output_tokens") or len(text) // 4
    TRACKER.add(node, model, tin, tout, time.time() - t0)
    return text


def _extract_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        s, e = text.find(opener), text.rfind(closer)
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no valid JSON in model output")


def invoke_json(node: str, system: str, user: str, model: str | None = None):
    """Call the model and parse JSON; one retry with a stricter reminder."""
    reminder = "\n\nReturn ONLY valid JSON, no prose and no markdown fences."
    try:
        return _extract_json(invoke(node, system + reminder, user, model))
    except ValueError:
        return _extract_json(invoke(node, system + reminder, user, model, temperature=0))
