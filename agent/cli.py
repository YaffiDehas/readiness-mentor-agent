"""Interactive CLI: streams the current node, handles HITL prompts, shows cost, errors and help."""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime

from dotenv import find_dotenv, load_dotenv
from langgraph.types import Command

from agent import llm, tools
from agent.graph import build_graph

HELP = """\
Readiness Mentor Agent - makes sure you know how the project is built BEFORE you implement a task.

  <text>          describe the development task you are about to implement
  /file <path>    attach a local file (task description / spec: txt, md, docx, code) to the next task
  /summary        export this session's summary to a local text file
  help | ?        show this help
  exit | quit     leave

Flow: I read the project myself, then ask you a few ARCHITECTURE questions about it (where similar screens live, which components/libraries/API layer exist...).
Answer in your own words with real paths. "I don't know" -> I tell you where to look. After looking you can answer: a path / "אין" (nothing like it exists - a new one will be created) /
"יש חשד" (you think it exists - the prompt will say: search before creating) / "לא יודע" (for architecture questions I decide from what the project already has, and say so).
Facts I cannot find in the code - the exact REST endpoint (method + URL), auth - I never invent: you get precise questions for your mentor and NO prompt.
After the mentor answers, continue with:  python main.py --resume <session file>  (only the open questions are asked again).
Backend not ready: work continues against a labeled mock. Section H of the prompt tells you what to pay attention to before coding. Q = quit. I ask Y/N before writing any file.
Use Windows Terminal for correct Hebrew display."""


def friendly_error(e: Exception) -> str:
    s = f"{type(e).__name__}: {e}"
    chain, x = [], e
    while x is not None and len(chain) < 8:  # the real cause is often hidden in __cause__ (e.g. SSL behind "Connection error")
        chain.append(f"{type(x).__name__}: {x}")
        x = x.__cause__ or x.__context__
    low = " | ".join(chain).lower()
    if "certificate" in low or "ssl" in low:
        return (f"{s}\n  -> SSL certificate problem: your network/antivirus inspects HTTPS with its own certificate. "
                "Run: pip install truststore (already in requirements.txt), then retry. Cause: " + chain[-1][:200])
    if "401" in s or "unauthorized" in low or "api_key" in low or "not set" in low:
        return f"{s}\n  -> Check OPENROUTER_API_KEY in your .env file."
    if "404" in s or "no endpoints" in low:
        return f"{s}\n  -> The model is not available on OpenRouter right now. Set OPENROUTER_MODEL to another model (see openrouter.ai/models)."
    if "429" in s or "rate" in low:
        return f"{s}\n  -> Rate limit (common on free models). Wait a minute or switch model via OPENROUTER_MODEL."
    if "connection" in low or "timeout" in low:
        return f"{s}\n  -> Network problem - check your internet connection and retry."
    if isinstance(e, FileNotFoundError):
        return f"{s}\n  -> Check the path."
    return s


def _show_error(p: dict):
    if p.get("error"):
        print(f"  ! {p['error']}")


def ask_human(p: dict) -> str:
    """One prompt per interrupt. Validation is done by the graph (invalid input re-asks the same question), not here."""
    _show_error(p)
    t = p["type"]
    if t == "text":
        if p["kind"] == "mentor":
            print(f"\n[{p['id']}] תשובת המנטור לשאלה: {p['question']}")
            return input("תשובת המנטור (או 'אין' אם עוד אין): ")
        if p.get("note"):
            print(f"\n  ? {p['note']}")
        g = p.get("guidance")
        if g:
            print("\n  איפה לחפש (הצעות מהפרויקט - לא עובדות מאומתות):")
            if g.get("why"):
                print(f"   למה זה חשוב: {g['why']}")
            if g.get("files"):
                print(f"   קבצים שאולי קשורים: {', '.join(g['files'])}")
            if g.get("terms"):
                print(f"   מילות חיפוש: {', '.join(g['terms'])}")
            if g.get("dirs"):
                print(f"   תיקיות ראשיות: {', '.join(g['dirs'])}")
            if g.get("dependencies"):
                print(f"   ספריות בפרויקט: {', '.join(g['dependencies'])}")
        else:
            print(f"\n[{p['n']}/{p['total']}] {p['title']}\n  {p['question']}")
            if p.get("why"):
                print(f"  למה זה חשוב: {p['why']}")
        return input("Your answer (path / free text, 'אין', 'יש חשד', 'לא יודע', Q = quit): ")
    if t == "choice":
        print(f"\n[{p['n']}/{p['total']}] {p['title']}\n  {p['question']}")
        for o in p["options"]:
            ev = f" | based on: {', '.join(o['evidence'])}" if o["evidence"] else (f" | uses: {o['dependency']}" if o.get("dependency") else "")
            print(f"  {o['id']}) {o['label']}{'  (מומלץ)' if o['recommended'] else ''}{'  [NEW DEPENDENCY]' if o['new_dependency'] else ''}{ev}")
            print(f"       + {o['pros']}   - {o['cons']}")
        return input("Choose a number, write your own option, or 'המלצה' for the recommended one: ")
    if t == "save":
        return input(f"\nSave the {'session (to continue after the mentor answers)' if p['kind'] == 'session' else 'prompt'} to {p['path']}? [Y/N]: ")
    raise ValueError(f"unknown interrupt: {p}")


def run_task(graph, task: str, project: str, attachments: list[dict], log: list[dict], session: dict | None = None):
    cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
    llm.TRACKER.reset()
    payload = {"task": task, "project_root": project, "attachments": attachments,
               "run_id": datetime.now().strftime("%Y%m%d-%H%M%S")}
    if session:
        payload["session"] = session
    last_node = None
    if not project:
        print("[INFO] No project folder given (--project): nothing will be scanned and every finding will be marked as your own statement.")
    try:
        while True:
            for _mode, chunk in graph.stream(payload, cfg, stream_mode=["debug"]):
                if chunk["type"] == "task" and chunk["payload"]["name"] != last_node:
                    last_node = chunk["payload"]["name"]
                    print(f"[INFO] Entering Node: {last_node}")
            snap = graph.get_state(cfg)
            if not snap.next:
                break
            payload = Command(resume=ask_human(snap.tasks[0].interrupts[0].value))
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Cancelled. Nothing was saved.")
        return
    st = snap.values
    for w in st.get("warnings", []):
        print(f"[WARN] {w}")
    for line in st.get("retrieval_log", []):
        if "no " in line and ("found" in line or "matched" in line):
            print(f"[INFO] {line}")
    if st.get("final_prompt"):
        print("\n" + "=" * 20 + " IMPLEMENTATION PROMPT " + "=" * 20 + "\n" + st["final_prompt"] + "\n" + "=" * 63)
    print("\n" + st.get("final_message", ""))
    if st.get("saved_path"):
        print(f"[INFO] Saved to {st['saved_path']}")
    print("\nUsage and cost (actual = billed, theoretical = at paid-equivalent rate):")
    print(llm.TRACKER.table())
    log.append({"task": task, "in_scope": st.get("in_scope"), "outcome": st.get("outcome") or ("cancelled" if st.get("cancelled") else "out_of_scope"),
                "blocked": [b["title"] for b in st.get("blocked", [])], "open": [t["title"] for t in st.get("topics", []) if t["status"] in {"suspected", "unknown", "open"}], "message": st.get("final_message", ""),
                "saved": st.get("saved_path", ""), "cost": llm.TRACKER.total()})


def export_summary(log: list[dict]) -> str:
    path = f"summary-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
    lines = []
    for i, e in enumerate(log, 1):
        lines += [f"Task {i}: {e['task']}", f"  in scope: {e['in_scope']} | outcome: {e['outcome']}",
                  f"  to clarify with the mentor (blocking): {', '.join(e['blocked']) or 'none'}", f"  open items: {', '.join(e['open']) or 'none'}", f"  result: {e['message']}",
                  f"  saved: {e['saved'] or '-'}", f"  cost (actual/theoretical USD): {e['cost']['actual_usd']:.5f}/{e['cost']['theoretical_usd']:.5f}", ""]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) or "No tasks in this session.")
    return path


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Readiness Mentor Agent")
    ap.add_argument("--project", default=None, help="path of YOUR project (the one the task belongs to). Without it nothing is scanned and every finding is your own statement")
    ap.add_argument("--model", help="OpenRouter model id (overrides OPENROUTER_MODEL)")
    ap.add_argument("--resume", help="session file saved when the agent asked you to clarify something with the mentor")
    args = ap.parse_args(argv)

    load_dotenv(find_dotenv(usecwd=True))
    if args.model:
        llm.CONFIG["model"] = args.model
    if not os.getenv("OPENROUTER_API_KEY"):
        print("[ERROR] OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in.")
        return 2
    traced = os.getenv("LANGSMITH_TRACING", "").lower() == "true" and os.getenv("LANGSMITH_API_KEY")
    print(f"Readiness Mentor Agent | model: {llm.current_model()} | LangSmith tracing: {'on' if traced else 'off'}")
    print("Type 'help' for usage.\n")

    graph, attachments, log = build_graph(), [], []
    if args.resume:
        try:
            with open(args.resume, encoding="utf-8") as f:
                session = json.load(f)
            project = args.project or session.get("project", "")
            print(f"[INFO] Continuing: {session['task'][:80]}")
            run_task(graph, session["task"], project, [], log, session)
        except Exception as e:
            print(f"[ERROR] {friendly_error(e)}")
        return 0
    while True:
        try:
            line = input("task> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        low = line.lower()
        if low in {"exit", "quit"}:
            break
        if low in {"help", "?"}:
            print(HELP)
        elif low == "/summary":
            print(f"[INFO] Summary written to {export_summary(log)}")
        elif low.startswith("/file"):
            try:
                path = line[5:].strip()
                attachments.append({"name": os.path.basename(path.strip('"')), "text": tools.read_attachment(path)})
                print(f"[INFO] Attached {attachments[-1]['name']} ({len(attachments)} file(s) for the next task)")
            except Exception as e:
                print(f"[ERROR] {friendly_error(e)}")
        else:
            try:
                run_task(graph, line, args.project, attachments, log)
                attachments = []
            except Exception as e:
                print(f"\n[ERROR] {friendly_error(e)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
