"""Test harness. The LLM is scripted (including deliberately BAD outputs) so the tests exercise the deterministic logic:
labeling of the developer's answers, guidance, option grounding and brief checks. They do not measure model quality."""
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from langgraph.types import Command

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import llm  # noqa: E402
from agent.graph import build_graph  # noqa: E402

SENSORS = str(ROOT / "evals" / "sample_project")
PARKING = str(ROOT / "evals" / "fixtures" / "parking_app")
SHOP = str(ROOT / "evals" / "fixtures" / "shop_app")


def topic(title, question="Where in the project is this done?", category="similar_implementation", terms=(), **kw):
    """A raw (LLM-shaped) checklist topic."""
    return {"title": title, "question": question, "why": f"the implementation depends on: {title}", "category": category,
            "search_terms": list(terms), **kw}


def checklist(*topics, requirements=("show a list",)):
    return {"requirements": list(requirements), "topics": list(topics)}


def option(label, evidence=(), dep=None, new=False, **kw):
    return {"label": label, "description": f"{label} description", "pros": "fits the project", "cons": "more code", "evidence": list(evidence),
            "uses_dependency": dep, "new_dependency": new, **kw}


def decision(title, *options, recommended=0, **kw):
    return {"title": title, "question": f"{title}?", "options": list(options), "recommended": recommended, **kw}


GOOD_BODY = ("=== A ===\nTask and requirements listed.\n=== D ===\nExtend existing files first.\n=== F ===\nUNKNOWN: no test convention found.\n"
             "=== G ===\nImplement the task; do not change unrelated files.")


class Script:
    """Per-node scripted responses: a value, a list (one per call; last repeats) or a callable (user_text, call_no) -> value."""

    def __init__(self, **responses):
        self.r = {"guardrails": {"in_scope": True}, "build_checklist": checklist(), "propose_options": {"decisions": []},
                  "compose_prompt": GOOD_BODY, "eval_prompt": {"issues": []}}
        self.r.update(responses)
        self.calls = []

    def count(self, node):
        return self.calls.count(node)

    def get(self, node, user):
        self.calls.append(node)
        if node not in self.r:
            raise AssertionError(f"LLM node {node!r} was called but not scripted")
        v, n = self.r[node], self.calls.count(node)
        if callable(v):
            return v(user, n)
        return v[min(n, len(v)) - 1] if isinstance(v, list) else v

    def install(self, monkeypatch):
        monkeypatch.setattr(llm, "invoke_json", lambda node, system, user, model=None: self.get(node, user))
        monkeypatch.setattr(llm, "invoke", lambda node, system, user, model=None, temperature=0.2: self.get(node, user))


class Human:
    """Scripted developer. text={"t1": [answer, ...]} answers topic prompts in order (asking more often than scripted fails the test);
    mentor={"t1": answer} answers resumed mentor prompts; choice=[...] answers option prompts; save answers the 'save ...?' prompts."""

    def __init__(self, text=None, mentor=None, choice=None, save="n"):
        self.text = {k: list(v) for k, v in (text or {}).items()}
        self.mentor = dict(mentor or {})
        self.choice = list(choice or [])
        self.save = list(save) if isinstance(save, list) else [save]

    def __call__(self, p, st):
        t = p["type"]
        if t == "text":
            if p["kind"] == "mentor":
                return self.mentor.get(p["id"], "אין")
            q = self.text.get(p["id"])
            assert q, f"unexpected extra question for {p['id']} (kind={p['kind']})"
            return q.pop(0)
        if t == "choice":
            assert self.choice, f"unexpected choice prompt {p['id']}"
            return self.choice.pop(0)
        if t == "save":
            return self.save.pop(0) if len(self.save) > 1 else self.save[0]
        raise AssertionError(f"unknown prompt {p}")


@dataclass
class Result:
    values: dict
    prompts: list
    script: Script
    nodes: list = field(default_factory=list)


def run_graph(monkeypatch, tmp_path, project, task, script, human=None, session=None, max_steps=120):
    monkeypatch.chdir(tmp_path)
    script.install(monkeypatch)
    human = human or Human()
    g = build_graph()
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    inp, prompts, nodes = {"task": task, "project_root": project, "attachments": [], "run_id": "t"}, [], []
    if session is not None:
        inp["session"] = session
    for _ in range(max_steps):
        for _mode, ch in g.stream(inp, cfg, stream_mode=["debug"]):
            if ch["type"] == "task" and (not nodes or nodes[-1] != ch["payload"]["name"]):
                nodes.append(ch["payload"]["name"])
        snap = g.get_state(cfg)
        if not snap.next:
            return Result(snap.values, prompts, script, nodes)
        p = snap.tasks[0].interrupts[0].value
        prompts.append(p)
        inp = Command(resume=human(p, snap.values))
    raise AssertionError("graph did not terminate (possible infinite loop)")


@pytest.fixture
def run(monkeypatch, tmp_path):
    return lambda project, task, script, human=None, session=None: run_graph(monkeypatch, tmp_path, project, task, script, human, session)
