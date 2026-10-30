"""Shared helpers for the evals: scripted run of the graph (auto-answers HITL) and the LLM judge."""
import csv
import os
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import find_dotenv, load_dotenv  # noqa: E402
from langgraph.types import Command  # noqa: E402

from agent import llm  # noqa: E402
from agent.graph import build_graph  # noqa: E402
from agent.arch import check_brief  # noqa: E402

load_dotenv(find_dotenv(usecwd=True))

PROJECT = str(ROOT / "evals" / "sample_project")
RESULTS = ROOT / "evals" / "results"
CRITERIA = ("relevance", "factual_accuracy", "completeness", "format", "scope_control", "assumption_handling")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini")
TASKS = {
    "alerts_tab": "Add an alerts tab to the sensor details screen that lists the alerts of a sensor.",
    "table_filter": "Add a reusable filter bar to the sensors list table.",
    "api_retry": "Add retry with exponential backoff to the API client for failed requests.",
}


def run_auto(task: str, model: str, project: str = PROJECT) -> tuple[dict, float, dict]:
    """Run the full graph with a 'junior who needs guidance': says "I don't know" first, then answers with the real files the guidance pointed to;
    takes the recommended option and declines file writes."""
    llm.CONFIG["model"] = model
    llm.TRACKER.reset()
    graph = build_graph()
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    inp = {"task": task, "project_root": project, "attachments": [], "run_id": "eval"}
    t0 = time.time()
    for _ in range(200):  # hard bound: an eval must never loop forever
        graph.invoke(inp, cfg)
        snap = graph.get_state(cfg)
        if not snap.next:
            return snap.values, time.time() - t0, llm.TRACKER.total()
        p = snap.tasks[0].interrupts[0].value
        if p["type"] == "text":
            g = p.get("guidance")
            ans = " ".join((g or {}).get("files", [])[:2]) if g else "לא יודע"
        else:
            ans = {"choice": "המלצה", "save": "n"}[p["type"]]
        inp = Command(resume=ans)
    raise RuntimeError("graph did not terminate within 200 steps")


def deterministic_metrics(state: dict) -> dict:
    """Judge-independent reliability metrics computed from the state and the final prompt."""
    issues = check_brief(state.get("final_prompt", ""), set(state.get("project_files", [])), state.get("topics", []), state.get("decisions", []))
    topics = state.get("topics", [])
    return {"outcome": state.get("outcome"), "brief_accepted": state.get("brief_accepted"), "topics": len(topics),
            "verified": sum(t["status"] == "verified" for t in topics), "open_items": sum(t["status"] in {"suspected", "unknown", "open"} for t in topics),
            "decisions": len(state.get("decisions", [])), "corrections": state.get("correction_round", 0),
            "invented_paths": sum(i["type"] == "invented_file_path" for i in issues)}


def project_text() -> str:
    files = [p for p in sorted(Path(PROJECT).rglob("*")) if p.is_file()]
    return "\n\n".join(f"### {p.relative_to(PROJECT).as_posix()}\n{p.read_text(encoding='utf-8')}" for p in files)


def judge(task: str, brief: str) -> dict:
    """LLM-as-judge: one fixed model for all comparisons, rubric from rubric.md."""
    system = "You are a strict evaluator. Score the brief using this rubric.\n\n" + (ROOT / "evals" / "rubric.md").read_text(encoding="utf-8")
    user = f"## TASK\n{task}\n\n## PROJECT FILES\n{project_text()}\n\n## BRIEF\n{brief}"
    res = llm.invoke_json("judge", system, user, model=JUDGE_MODEL)
    out = {}
    for k in CRITERIA:
        try:
            out[k] = max(1, min(5, int(res.get(k, 1))))
        except (TypeError, ValueError):
            out[k] = 1
    out["comment"] = str(res.get("comment", ""))
    return out


def write_csv(name: str, rows: list[dict]):
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / name
    fields = list({k: None for r in rows for k in r})
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"[eval] wrote {path}")
