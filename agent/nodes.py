"""Graph nodes and routers. LLM output is always treated as untrusted: arch.py decides. Nodes that talk to the developer (ask_topic, choose_option)
contain no LLM call, so they can safely re-run from their start after every interrupt resume.
The agent is a guide, not a gatekeeper: it asks, points to where to look, records what the developer says (with its source) and ALWAYS ends with a prompt;
whatever stays unknown or suspected is written into the prompt as an open item.
Two kinds of gaps: ARCHITECTURE (where to put it, which component, how data is kept) - the agent decides from the project itself when the developer does not know;
BLOCKING FACTS (the endpoint URL, auth, a business rule) - never invented: the developer gets precise questions for the mentor and NO prompt until they are answered."""
import json
import os
import re
from datetime import datetime
from pathlib import Path

from langgraph.types import interrupt

from agent import arch, llm, prompts as P, tools

MAX_CORRECTIONS = int(os.getenv("READINESS_MAX_CORRECTIONS", "2") or 2)
MAX_INVALID = 5                                   # consecutive empty/invalid inputs before the run is cancelled
MENTOR = os.getenv("MENTOR_NAME", "המנטור/ית")
INJECTION = re.compile(
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)|disregard .{0,30}instructions|"
    r"reveal .{0,20}system prompt|התעלם מ(כל )?ההוראות", re.I)
CANCEL_MESSAGE = "ההרצה בוטלה - לא הופק פרומפט. / Session cancelled - no prompt was produced."
LABEL = {"verified": "VERIFIED (found in the project)", "reported": "DEVELOPER-REPORTED (not verified)",
         "mock_ok": "MOCK (provisional - ASSUMPTION)", "mentor_answered": "MENTOR-CONFIRMED (not verified in the project)",
         "mentor_needed": "BLOCKED (unknown - must be clarified with the mentor)", "absent": "DEVELOPER-CONFIRMED: DOES NOT EXIST (new to create; not verified)",
         "suspected": "SUSPECTED EXISTING (search before creating anything new)", "unknown": "UNKNOWN to the developer (decided from the project - see section C)",
         "open": "UNKNOWN"}


def _section(**parts: str) -> str:
    return "\n\n".join(f"## {k.upper().replace('_', ' ')}\n{v}" for k, v in parts.items())


def task_block(state) -> str:
    parts = [state["task"].strip()]
    for a in state.get("attachments", []):
        parts.append(f"[ATTACHMENT {a['name']}]\n{a['text'][:4000]}")
    return "\n\n".join(parts)


def _cancel():
    return {"cancelled": True, "final_message": CANCEL_MESSAGE}


def _text(payload: dict) -> str | None:
    """Free-text prompt. An empty answer is rejected and the same prompt is shown again; None = too many invalid inputs."""
    error = None
    for _ in range(MAX_INVALID):
        raw = str(interrupt({**payload, "error": error})).strip()
        if raw:
            return raw
        error = "התשובה ריקה. כתבו תשובה, 'לא יודע/ת', או Q ליציאה."
    return None


# ---------------------------------------------------------------- guardrails
def guardrails(state):
    task = state.get("task", "").strip()
    refuse = {"in_scope": False,
              "final_message": "אני עוזר/ת רק להכנה לפני מימוש משימת פיתוח בפרויקט שלך. "
                               "נסו לתאר משימת פיתוח. / I only help prepare software-development tasks."}
    if not task or INJECTION.search(task):
        return refuse
    res = llm.invoke_json("guardrails", P.GUARD, f"TASK:\n{task_block(state)}")
    return {"in_scope": True} if res.get("in_scope") is True else refuse


def route_after_guard(state):
    return "context_retrieval" if state.get("in_scope") else "end"


# ------------------------------------------------------- project scan (RAG)
def context_retrieval(state):
    """The agent reads the project BEFORE asking the developer anything."""
    root, was_agent_repo = tools.resolve_root(state.get("project_root"))      # "" = no project: nothing is scanned, nothing may be claimed about the code
    scan = tools.scan_project(root)
    hits = tools.get_index(root).search(task_block(state), k=8)
    files = sorted({h["path"] for h in hits})
    warnings = list(state.get("warnings", []))
    if not root:
        log = ["no project was provided - nothing was scanned; every finding will be the developer's own statement"]
        if was_agent_repo:
            warnings.append("התיקייה שנבחרה היא תיקיית הסוכן עצמו, לא הפרויקט שלכם - לא נסרקה. ציינו את תיקיית הפרויקט (--project) כדי שהסוכן יסרוק אותו.")
    else:
        log = [f"searched {scan['n_files']} project files for the task"]
        if not files:
            log.append("no project file matched the task - evidence unavailable")
        if not scan["api"]:
            log.append("no API contract files found (swagger/openapi/graphql/proto)")
    out = {"project_root": root, "no_project": not root, "warnings": warnings, "project_facts": tools.facts_text(scan), "project_files": scan["files"], "dependencies": arch.dep_names(scan["tech"]), "scan": scan,
           "evidence_files": files, "retrieval_log": log, "topic_idx": 0, "decision_idx": 0, "correction_round": 0, "prompt_round": 0}
    sess = state.get("session")
    if isinstance(sess, dict) and isinstance(sess.get("topics"), list) and sess["topics"]:     # continue where the developer stopped
        out["topics"] = [dict(t) for t in sess["topics"] if isinstance(t, dict) and "id" in t and "status" in t]
        out["requirements"] = arch.clean_requirements(sess.get("requirements"))
    return out


# ------------------------------------------------- task-specific checklist
def build_checklist(state):
    if state.get("topics"):                                   # resumed session: the checklist already exists
        return {}
    hits = tools.get_index(state["project_root"]).search(task_block(state), k=8)
    # the task may be written in another language than the code (Hebrew task, English project): the model also sees the real file list
    user = _section(task=task_block(state), project_facts=state["project_facts"], project_files="\n".join(state["project_files"][:150]) or "(none)",
                    evidence=tools.evidence_text(hits, 700))
    res = llm.invoke_json("build_checklist", P.CHECKLIST, user)
    res = res if isinstance(res, dict) else {}
    return {"topics": arch.clean_topics(res.get("topics")), "requirements": arch.clean_requirements(res.get("requirements"))}


# ------------------------------------------------- ask the developer (HITL)
_MENU = ("אם מצאתם - כתבו נתיב או שם ספרייה. אם אחרי החיפוש אתם בטוחים שאין - כתבו 'אין' ונוסיף רכיב חדש. "
         "אם יש חשד שקיים אבל לא מצאתם - כתבו 'יש חשד' ונציין בפרומפט לחפש לפני שיוצרים. אם לא ברור - כתבו 'לא יודע/ת' והסוכן יחליט לפי מה שקיים בפרויקט ויציין זאת.")
_NOTES = {"idk": "אין בעיה - הנה איפה לחפש. " + _MENU,
          "absent": "אתם אומרים שאין, אבל בחיפוש בפרויקט מצאתי קבצים שאולי קשורים (למטה). בטוחים שאין? " + _MENU,
          "suspect": "יש חשד שקיים - הנה איפה לחפש. " + _MENU, "empty": "לא התקבלה תשובה. " + _MENU}
_FACT_NOTE = ("זו עובדה שאי אפשר להסיק מהקוד, ואני לא ממציא אותה. הנה איפה לחפש (שירותים, תיעוד API). אם מצאתם - כתבו שיטה ונתיב (למשל GET /api/...) או נתיב לקובץ. "
              "אם ה-Backend עדיין לא מוכן - כתבו 'ה-API עדיין לא מוכן'. אחרת תקבלו שאלה מדויקת למנטור.")


def _record(t: dict, status: str, answer: str, res: dict | None = None, cands: list[str] | None = None, note: str = "") -> dict:
    t = dict(t)
    t.update(status=status, answer=answer[:500])
    if res:
        t.update(paths=res["paths"], deps=res["deps"])
        if res["note"]:
            t["notes"] = t["notes"] + [res["note"]]
    if cands and status in {"absent", "suspected", "unknown"}:
        t["candidates"] = cands
    if note:
        t["notes"] = t["notes"] + [note]
    return t


def _mentor_branch(state, t, head, i, topics):
    """Resumed session: the developer brings the mentor's answer for a blocked fact. A statement of the mentor is recorded as such - never as repository evidence."""
    raw = _text({**head, "kind": "mentor", "question": t["mentor_question"] or t["question"]})
    if raw is None or arch.QUIT_RE.match(raw):
        return _cancel()
    if arch.classify_text(raw) == "idk" or arch.NO_ANSWER_RE.match(raw):          # still no answer: stays blocked
        topics[i] = _record(t, "mentor_needed", "", note="עדיין אין תשובה מהמנטור")
    else:
        res = arch.verify_answer(t, raw, state["project_root"], set(state["project_files"]), state["dependencies"])
        t = _record(t, "mentor_answered", raw, res)
        t["mentor"] = {"answer": raw[:500], "scope": f"{t['id']}: {t['title']}", "found_in_project": res["paths"], "not_in_project": res["missing"]}
        topics[i] = t
    return {"topics": topics, "topic_idx": i + 1}


def ask_topic(state):
    """One topic per run of this node. ARCHITECTURE topic: ask -> (if unsure) show where to look -> record what the developer says; whatever stays unknown is decided later
    from the project. BLOCKING FACT (endpoint URL, auth...): never invented - after one round of guidance an unknown goes to the mentor (the run then stops, see gate)."""
    topics, i = [dict(t) for t in state["topics"]], state["topic_idx"]
    t = topics[i]
    root, files, deps, scan = state["project_root"], set(state["project_files"]), state["dependencies"], state["scan"]
    head = {"type": "text", "id": t["id"], "n": i + 1, "total": len(topics), "title": t["title"], "question": t["question"], "why": t["why"],
            "category": t["category"], "blocker": t["blocker"]}
    if t["status"] not in {"open", "mentor_needed"}:           # resumed session: already settled, never asked twice
        return {"topic_idx": i + 1}
    if t["status"] == "mentor_needed":
        return _mentor_branch(state, t, head, i, topics)

    cands = arch.related_candidates(t, root, files)
    guide, note, final = None, None, None                      # final = (status, answer, res, why_open)
    earlier = [x["answer"] for x in topics[:i] if x["answer"]]
    set_aside = []                                             # an answer asked again as off-topic is still kept in the record - nothing the developer wrote is lost
    for attempt in (0, 1):
        raw = _text({**head, "kind": "topic" if attempt == 0 else "guidance", "note": note, "guidance": guide})
        if raw is None or arch.QUIT_RE.match(raw):
            return _cancel()
        off = arch.off_topic(t, raw, earlier)                  # a URL for a design question, the same text as the previous answer...
        if off and attempt == 0:
            set_aside.append(raw)
            guide, note = arch.guidance(t, root, scan), off
            continue
        res = arch.verify_answer(t, raw, root, files, deps)
        if off:
            res = {**res, "note": (res["note"] + " " if res["note"] else "") + "התשובה נראית לא קשורה לשאלה - לא נבדקה."}
        kind = arch.classify_text(raw, res, t["category"])
        if kind == "no_api":                                   # the backend/API does not exist yet
            final = ("mock_ok", raw, res, "") if t["mockable"] else ("mentor_needed", raw, res, "ה-API חסר והנושא רגיש - אין Mock")
            break
        if t["blocker"]:
            concrete = arch.has_endpoint(raw) or res["paths"] or res["deps"]
            if kind == "answer" and (t["category"] != "api_dependency" or concrete):
                final = ("verified" if res["paths"] or res["deps"] else "reported", raw, res, "")
                break
            if attempt == 1:                                   # one round of guidance did not settle it: no invention - the mentor
                why = "לא נמסרו שיטה ונתיב/כתובת" if kind == "answer" else "הג'וניור לא הצליח לאתר"
                final = ("mentor_needed", raw if kind == "answer" else "", res, why)
                break
            guide, note = arch.guidance(t, root, scan), _FACT_NOTE
            continue
        if kind == "answer":
            final = ("verified" if res["status"] == "verified" else "reported", raw, res, "")
            break
        if kind == "absent" and (attempt == 1 or not cands):
            final = ("absent", raw, res, "")
            break
        if attempt == 1:
            final = ("suspected" if kind == "suspect" else "unknown", raw if kind != "idk" else "", res, "")
            break
        guide = arch.guidance(t, root, scan)                   # "where to look": real files, search terms, directories - suggestions, never facts
        note = _NOTES.get(kind, _NOTES["idk"])
    status, answer, res, why_open = final
    t = _record(t, status, answer, res if status in {"verified", "reported", "mock_ok", "mentor_needed"} else None, cands,
                note=("הוגדרה בצד כלא קשורה לשאלה, ונשמרה לתיעוד: " + " | ".join(set_aside)) if set_aside else "")
    if status == "mentor_needed":
        t["mentor_question"] = arch.mentor_question(t, why_open)
    topics[i] = t
    return {"topics": topics, "topic_idx": i + 1}


def route_after_topic(state):
    if state.get("cancelled"):
        return "end"
    return "ask_topic" if state["topic_idx"] < len(state["topics"]) else "gate"


# ----------------------------------------------------------- stop or continue
def gate(state):
    return {"blocked": [{"id": t["id"], "title": t["title"], "question": t["mentor_question"] or arch.mentor_question(t)} for t in arch.blocking(state["topics"])]}


def route_after_gate(state):
    return "stop_report" if state["blocked"] else "propose_options"


def _save(kind: str, path: Path, text: str) -> str:
    error, save = None, False
    for _ in range(3):
        ans, error = arch.parse_yes_no(interrupt({"type": "save", "kind": kind, "path": str(path), "error": error}))   # HITL before writing a file
        if ans is not None:
            save = ans
            break
    if not save:
        return ""
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def stop_report(state):
    """A fact the task cannot do without (the endpoint, auth...) is missing and the agent will not invent it: NO prompt. The developer gets the precise
    questions for the mentor and a session file; after the mentor answers they continue and only these questions are asked again."""
    topics = state["topics"]
    lines = [f"לא הופק פרומפט: חסר מידע שהמשימה תלויה בו, ואני לא ממציא אותו. יש לברר מול {MENTOR} לפני שמתחילים לממש.", "", f"לברר מול {MENTOR}:"]
    lines += [f"{n}. [{b['id']}] {b['question']}" for n, b in enumerate(state["blocked"], 1)]
    done = [t for t in topics if t["status"] not in {"open", "mentor_needed"}]
    if done:
        lines += ["", "מה שכבר נקבע (לא תצטרכו לענות עליו שוב):"]
        lines += [f"- {t['title']}: {LABEL[t['status']]}" for t in done]
    session = {"version": 2, "task": state["task"], "project": state["project_root"], "requirements": state.get("requirements", []), "topics": topics,
               "created": datetime.now().isoformat(timespec="seconds")}
    path = Path("briefs") / f"session-{state.get('run_id', 'run')}.json"
    saved = _save("session", path, json.dumps(session, ensure_ascii=False, indent=2))
    lines += ["", f"אחרי שהתקבלה תשובה: הריצו שוב עם `--resume {path}` (או \"המשך מקובץ\" בממשק) והסוכן ימשיך מהנקודה הזו ויבקש רק את תשובות המנטור."
              if saved else "לא נשמר קובץ המשך. כדי להמשיך, הריצו את המשימה שוב אחרי שהתקבלו תשובות."]
    return {"outcome": "needs_mentor", "final_message": "\n".join(lines), "session_out": session, "saved_path": saved}


# ------------------------------------------------------------ solution options
def propose_options(state):
    if state.get("no_project"):                                # nothing to ground an option on: the agent proposes no architecture of its own
        return {"decisions": [], "decision_idx": 0}
    findings = [{"id": t["id"], "title": t["title"], "status": t["status"], "answer": t["answer"], "paths": t["paths"], "dependencies": t["deps"],
                 "possible_matches": t["candidates"]}
                for t in state["topics"]]
    user = _section(task=task_block(state), requirements="\n".join(state.get("requirements", [])) or "(none extracted)",
                    findings=json.dumps(findings, ensure_ascii=False), project_files="\n".join(state["project_files"][:200]),
                    dependencies=", ".join(state["dependencies"]) or "(none)")
    res = llm.invoke_json("propose_options", P.OPTIONS, user)
    unknown_ids = {t["id"] for t in state["topics"] if t["status"] == "unknown" and not t["blocker"]}
    decisions = arch.clean_decisions(res.get("decisions") if isinstance(res, dict) else None, state["project_root"], set(state["project_files"]), state["dependencies"], unknown_ids)
    for d in decisions:                                        # the developer did not know -> the agent decides, from what the project already has, and says so
        if d["topic"]:
            o = next(x for x in d["options"] if x["recommended"])
            d["chosen"], d["status"] = {**o, "custom": False, "accepted_recommendation": False, "agent_decided": True}, "agent_decided"
    return {"decisions": decisions, "decision_idx": _next_open(decisions, 0)}


def _next_open(decisions: list[dict], i: int) -> int:
    while i < len(decisions) and decisions[i]["status"] != "open":
        i += 1
    return i


def route_after_options(state):
    return "choose_option" if state["decision_idx"] < len(state["decisions"]) else "compose_prompt"


def choose_option(state):
    decisions, i = [dict(d) for d in state["decisions"]], state["decision_idx"]
    d = decisions[i]
    error, choice = None, None
    asked = [k for k, x in enumerate(decisions) if x["status"] != "agent_decided"]           # the developer is asked only about real choices
    for _ in range(MAX_INVALID):
        raw = interrupt({"type": "choice", "id": d["id"], "n": asked.index(i) + 1, "total": len(asked), "title": d["title"], "question": d["question"],
                         "options": d["options"], "error": error})
        choice, error = arch.parse_choice(raw, len(d["options"]))
        if choice:
            break
    if choice is None or choice[0] == "quit":
        return _cancel()
    kind, val = choice
    if kind == "custom":
        d["chosen"] = {"label": val, "custom": True, "evidence": [], "recommended": False}   # the developer's own option: kept, flagged as not grounded
    else:
        o = d["options"][(val - 1) if kind == "option" else next(k for k, x in enumerate(d["options"]) if x["recommended"])]
        d["chosen"] = {**o, "custom": False, "accepted_recommendation": kind == "recommended"}
    d["status"] = "chosen"
    decisions[i] = d
    return {"decisions": decisions, "decision_idx": _next_open(decisions, i + 1)}


def route_after_choice(state):
    if state.get("cancelled"):
        return "end"
    return "choose_option" if state["decision_idx"] < len(state["decisions"]) else "compose_prompt"


# --------------------------------------------------- prompt builder + evaluator
def _conflicts(t: dict) -> bool:
    """The developer says it does not exist, but searching the project found files that may be it: two sources disagree and nobody has decided."""
    return t["status"] == "absent" and bool(t["candidates"])


def _section_b(state) -> str:
    lines = ["## B. Architecture findings", ""]
    if state.get("no_project"):
        lines += ["**NO PROJECT WAS SCANNED.** Every item below is the developer's own statement; nothing was checked against code, and no file, convention or dependency is claimed.", ""]
    lines += ["Status legend: VERIFIED = found in the project | UNVERIFIED = developer / mentor statement, mock, unknown | CONFLICTING = the sources disagree - resolve before building.", ""]
    for t in state["topics"]:
        lines.append(f"- [{t['id']}] {t['title']} - {LABEL[t['status']]}" + (" - CONFLICTING with the project search (see possible matches)" if _conflicts(t) else ""))
        if t["paths"]:
            lines.append(f"  files: {', '.join(t['paths'])}")
        if t["deps"]:
            lines.append(f"  dependencies (from the manifests): {', '.join(t['deps'])}")
        if t["answer"]:
            lines.append(f"  {'mentor' if t['status'] == 'mentor_answered' else 'developer'} said: {t['answer']}")
        if t["mentor"] and t["mentor"]["not_in_project"]:
            lines.append(f"  NOTE: the mentor named {', '.join(t['mentor']['not_in_project'])}, which does not exist in the project - confirm before relying on it")
        if t["candidates"]:
            lines.append(f"  possible matches found by searching the project (not verified): {', '.join(t['candidates'])}")
        lines += [f"  note: {n}" for n in t["notes"]]
    return "\n".join(lines) if state["topics"] else "## B. Architecture findings\n\n- none (the task needed no architecture checks)"


def _section_c(state) -> str:
    lines = ["## C. Decisions", ""]
    for d in state["decisions"]:
        c = d["chosen"]
        how = ("DECIDED BY THE AGENT from what the project already has (the developer did not know) - the developer should review it" if c.get("agent_decided") else
               "developer's own option - not grounded in the project" if c["custom"] else
               ("recommended option, accepted by the developer" if c.get("accepted_recommendation") else "chosen by the developer"))
        ev = f" (based on: {', '.join(c['evidence'])})" if c.get("evidence") else (f" (existing dependency: {c['dependency']})" if c.get("dependency") else "")
        new = " NEW DEPENDENCY - not in the project today" if c.get("new_dependency") else ""
        lines.append(f"- [{d['id']}] {d['title']}: {c['label']} - {how}{ev}{new}")
    return "\n".join(lines) if state["decisions"] else "## C. Decisions\n\n- none: no open implementation choice was found"


def _endpoints(state) -> list[str]:
    """Every endpoint the developer wrote anywhere (task text, attachments, any answer - including answers that were set aside). Code collects them: the model cannot drop one."""
    text = task_block(state) + "\n" + "\n".join(t["answer"] + "\n" + "\n".join(t["notes"]) for t in state["topics"])
    return arch.find_endpoints(text)


def _section_e(state) -> str:
    lines = ["## E. Provisional work and open items", ""]
    ask = []          # questions for the mentor: (text)
    eps = _endpoints(state)
    if eps:
        lines += [f"- ENDPOINTS GIVEN BY THE DEVELOPER (unverified): {', '.join(eps)}. Use exactly these, call them and inspect the real response; never guess another address.", ""]
    by_topic = {d["topic"]: d for d in state["decisions"] if d.get("topic") and d.get("chosen")}
    for t in state["topics"]:
        tid, ttl, st = t["id"], t["title"], t["status"]
        if st == "mock_ok":
            lines += [f"- [{tid}] {ttl}: the backend/API does not exist yet. Work proceeds against a MOCK behind an interface.",
                      "  ASSUMPTION: the real contract (method, path, parameters, field names and types, permissions) is NOT known. Use only the fields the task itself names;",
                      "  every other field is a guess - mark it ASSUMPTION and do not build logic on it. The real contract must be agreed before integration, and the mock replaced then."]
            ask.append(f"What is the real contract of '{ttl}' (method, path, parameters, response fields and types, permissions), and who approves it? Until then the mock stays labeled ASSUMPTION.")
        elif st == "reported":
            if not t["blocker"]:
                extra = " Confirm while implementing."
            elif eps:
                extra = (f" Endpoint(s) given by the developer (see above) - confirm with the backend before integrating. Their response shape (field names, types) is NOT documented here: "
                         "call the endpoint and inspect the real response before typing the data; never guess field names.")
            else:
                extra = " NO endpoint (method + path) was given for it. Do not invent one: ask the mentor for it, or work against a labeled MOCK."
            lines.append(f"- [{tid}] {ttl}: DEVELOPER-REPORTED, not verified in the project.{extra}")
            if t["blocker"]:
                ask.append(f"Is the contract of '{ttl}' documented anywhere (method, parameters, response fields, permissions)? The developer gave only the address." if eps else
                           f"What is the exact endpoint (method + path) behind '{ttl}', its parameters and its response? None was given.")
        elif st == "mentor_answered":
            lines.append(f"- [{tid}] {ttl}: MENTOR-CONFIRMED (a statement, not repository evidence) - re-check it against the code while implementing.")
        elif st == "suspected":
            where = f" Look first at: {', '.join(t['candidates'])}." if t["candidates"] else ""
            lines.append(f"- [{tid}] {ttl}: SUSPECTED EXISTING - the developer believes it already exists but did not find it.{where} "
                         "Search the project before creating anything new, and reuse it if it exists.")
            ask.append(t["question"])
        elif st == "absent":
            maybe = f" Possible matches found by search: {', '.join(t['candidates'])} - rule them out." if t["candidates"] else ""
            lines.append(f"- [{tid}] {ttl}: the developer confirmed it does not exist, so a new one may be created (not verified).{maybe}"
                         + (" CONFLICTING: rule the matches out before creating anything." if maybe else ""))
        elif st in {"unknown", "open"}:
            d = by_topic.get(tid)
            if d:
                lines.append(f"- [{tid}] {ttl}: UNKNOWN to the developer. DECIDED BY THE AGENT from what the project already has: {d['chosen']['label']} (section C). "
                             "Treat it as provisional and review it before relying on it.")
            else:
                near = f" Closest existing patterns: {', '.join(t['candidates'])}." if t["candidates"] else ""
                what = ("UNKNOWN - the developer did not know and no project was scanned, so the agent cannot suggest an answer. Look it up in the project (or ask) before building on it."
                        if state.get("no_project") else "UNKNOWN - the developer did not know and no grounded option was found.")
                lines.append(f"- [{tid}] {ttl}: {what}{near}" + ("" if state.get("no_project") else " Follow the closest existing pattern; do not invent a new one."))
            if not d:
                ask.append(t["question"])
    if ask:
        lines += ["", f"Questions to clarify with {MENTOR} (do not block the work, but do not assume the answer):"]
        lines += [f"- {q}" for q in ask]
    return "\n".join(lines) if len(lines) > 2 else "## E. Provisional work and open items\n\n- none"


def _decided_topics(state) -> set:
    return {d["topic"] for d in state["decisions"] if d.get("topic")}


def _section_ready(state) -> str:
    """The readiness decision (spec step 8): proceed / proceed with limits. A blocked task never reaches this point (stop_report)."""
    topics, decided = state["topics"], _decided_topics(state)
    limits = []
    if state.get("no_project"):
        limits.append("No project was scanned: every finding is the developer's own statement and nothing was checked against code.")
    for t in topics:
        tid, ttl, st = t["id"], t["title"], t["status"]
        if st == "mock_ok":
            limits.append(f"[{tid}] {ttl}: build only against a labeled MOCK; the real contract is not agreed.")
        elif st == "reported" and t["blocker"]:
            limits.append(f"[{tid}] {ttl}: the endpoint was given by the developer and is unverified; confirm it with the backend before integrating.")
        elif st == "mentor_answered":
            limits.append(f"[{tid}] {ttl}: the mentor's statement, not repository evidence; re-check it in the code.")
        elif st == "suspected":
            limits.append(f"[{tid}] {ttl}: suspected to exist; search the project before creating anything new.")
        elif st in {"unknown", "open"}:
            limits.append(f"[{tid}] {ttl}: " + ("decided by the agent from the project; review it." if tid in decided else "unknown; do not build on an assumption."))
        elif _conflicts(t):
            limits.append(f"[{tid}] {ttl}: CONFLICTING - the developer says it does not exist, the project search found possible matches; rule them out first.")
    eps = _endpoints(state)
    if eps:
        limits.append(f"Endpoint(s) given by the developer, unverified: {', '.join(eps)}. Confirm with the backend; inspect the real response before typing the data.")
    reported = [t["id"] for t in topics if t["status"] == "reported" and not t["blocker"]]
    lines = ["## R. Readiness decision", "", f"**Decision: {'PROCEED WITH LIMITS' if limits else 'PROCEED'}**"]
    if limits:
        lines += ["", "Limits - do not write code that depends on these until they are confirmed:", *[f"- {x}" for x in limits],
                  "", "Work that does not depend on the items above can start now."]
    if reported:
        lines += ["", f"Developer-reported and not verified ({', '.join(reported)}): confirm each in the code while implementing."]
    if not limits and not reported:
        lines += ["", "Everything the brief relies on was found in the project."]
    return "\n".join(lines)


def _section_i(state) -> str | None:
    """What changes when the real dependency replaces the mock / the reported endpoint is confirmed (spec section 7). None when no such dependency exists."""
    api = [t for t in state["topics"] if t["category"] == "api_dependency" and t["status"] in {"mock_ok", "reported", "verified", "mentor_answered"}]
    if not api:
        return None
    L = ["## I. What changes when the real dependency connects", ""]
    if any(t["status"] == "mock_ok" for t in api):
        L += ["- Keep the mock behind ONE interface (the data-access function or service the screen calls). Only that place changes when the real client arrives; the screen must not know where the data comes from.",
              "- Replace every field marked ASSUMPTION with the real contract's field names and types; the real contract must come from the backend / the mentor.",
              "- Delete the mock data and the ASSUMPTION labels, then add real loading / error handling for the request.",
              "- Re-run the tests against the real client; confirm authentication and permissions with the mentor."]
    if any(t["status"] in {"reported", "verified", "mentor_answered"} for t in api):
        L += ["- Call the endpoint and inspect the real response (method, parameters, field names, types, error shape) before typing the data. If it differs from this brief, the real response wins - update the brief, not the data."]
    return "\n".join(L)


def _section_j(state) -> str:
    """Risks, approvals and tests (spec section 7) - built from the statuses, never invented."""
    topics, scan = state["topics"], state["scan"]
    L = ["## J. Risks, approvals and tests", "", "**Risks**"]
    risks = []
    for t in topics:
        if t["status"] == "mock_ok":
            risks.append(f"A mock can hide the real contract: {t['title']}.")
        elif t["status"] == "reported" and t["blocker"]:
            risks.append(f"Unverified endpoint / fact: {t['title']}.")
        elif t["status"] in {"suspected", "unknown", "open"} or _conflicts(t):
            risks.append(f"Duplicating or contradicting existing code: {t['title']}.")
    if state.get("no_project"):
        risks.append("Nothing was checked against code: conventions, reuse and architecture are the developer's word.")
    L += [f"- {r}" for r in dict.fromkeys(risks)] or ["- No specific risk was identified from the findings."]
    L += ["", f"**Needs approval from {MENTOR} before building the affected part**"]
    need = [f"- The contract of '{t['title']}'." for t in topics if t["status"] in {"mock_ok", "reported"} and t["blocker"]]
    need += [f"- Whether '{t['title']}' should be a generic shared component." for t in topics if t["category"] == "future_reuse" and t["status"] in {"unknown", "open"}]
    L += need or ["- Nothing specific; ask if a finding in section B is contradicted by the code."]
    L += ["", "**Tests**"]
    if scan.get("tests") or any(c["what"] == "test setup" for c in scan.get("conventions", [])):
        L.append("- Follow the project's existing tests (see section F) and add tests for the new behavior.")
    else:
        L.append(f"- No test convention is known ({'no project was scanned' if state.get('no_project') else 'none was found'}): ask {MENTOR} which tests are required. At minimum cover the main flow and the loading, empty and error states.")
    return "\n".join(L)


def _status_footer(state) -> str:
    """Code-built tail of the implementation prompt: it must survive even if only this section is pasted into the coding agent."""
    short = {"verified": "VERIFIED", "reported": "DEVELOPER-REPORTED (unverified)", "mock_ok": "MOCK (ASSUMPTION)", "mentor_answered": "MENTOR-CONFIRMED (unverified)",
             "mentor_needed": "BLOCKED", "absent": "NEW (developer says it does not exist)", "suspected": "SUSPECTED EXISTING - search first",
             "unknown": "UNKNOWN", "open": "UNKNOWN"}
    L = ["", "Status of every fact above (do not treat anything as verified unless it says VERIFIED):"]
    L += [f"- {t['title']}: {short[t['status']]}" + (" - CONFLICTING" if _conflicts(t) else "") for t in state["topics"]]
    eps = _endpoints(state)
    if eps:
        L.append(f"Endpoints given by the developer (unverified - the only ones you may use): {', '.join(eps)}")
    if state.get("no_project"):
        L.append("- No project was scanned: the files, conventions and dependencies are NOT known to this brief.")
    L += ["Rules: never invent an endpoint, a payload field, a permission or a file name; for anything not VERIFIED, check it in the code or ask before building on it;",
          "follow the project's own conventions (section H); read the risks and approvals in section J."]
    return "\n".join(L)


_YES_REUSE = re.compile(r"^\s*(כן|בטח|יכול|ייתכן|yes|y)\b|עוד מסכ|בעתיד|מסכים נוספים|שימוש חוזר|גנרי|generic|reus", re.I)


def _section_h(state) -> str:
    """What the junior must pay attention to BEFORE writing code. Facts come from the scan and the answers; general reminders are labeled as such."""
    scan, topics = state["scan"], state["topics"]
    L = ["## H. Before you start - what to pay attention to", "", "**Follow this project's own way of writing code**"]
    conv = scan.get("conventions", [])
    if state.get("no_project"):
        L.append("- Project conventions were NOT checked (no project was scanned). Before writing code, find the lint / formatting / TypeScript / test configuration and any style guide in YOUR project and follow them; mirror the naming, structure and styling of the closest existing file.")
    elif conv:
        L += [f"- {c['what']}: {', '.join(c['files'])} (found in the project) - follow it; do not add rules of your own." for c in conv]
    else:
        L.append("- No lint / formatting / style-guide / test-config files were found in the project. Mirror the naming, structure and styling of the existing files listed below instead of choosing your own.")
    found = sorted({p for t in topics if t["status"] in {"verified", "mentor_answered"} and t["category"] != "api_dependency" for p in t["paths"]})
    if found:
        L += ["", "**Existing code to read first and reuse** (found in the project)", *[f"- {p}" for p in found]]
    maybe = sorted({p for t in topics if t["status"] in {"suspected", "absent"} for p in t["candidates"]})
    if maybe:
        L += ["", "**Search these before creating anything new** (possible matches, not verified)", *[f"- {p}" for p in maybe]]
    elif state.get("no_project"):
        terms = list(dict.fromkeys(w for t in topics if t["status"] in {"suspected", "absent", "unknown", "open"} for w in t["search_terms"]))[:10]
        L += ["", "**Search your project before creating anything new**",
              "- No project was scanned, so the agent cannot name files. Search for: " + (", ".join(terms) if terms else "similar screens, shared components, services") + "."]
    fr = next((t for t in topics if t["category"] == "future_reuse"), None)
    L += ["", "**Components other screens may need later**"]
    shared = next((str(Path(p).parent).replace("\\", "/") for t in topics if t["category"] == "reusable_components" for p in t["paths"]), "")
    where = f" in the shared components folder ({shared})" if shared else ""
    if fr and fr["status"] in {"verified", "reported"} and _YES_REUSE.search(fr["answer"]):
        L.append(f"- The developer said it will be reused: build it as a generic, props-driven component{where}, with no hard-coded texts, endpoints or screen-specific logic.")
    elif fr and fr["status"] in {"verified", "reported"}:
        L.append("- The developer said it is local to this feature: keep it simple and next to the feature; do not build a framework for it.")
    else:
        L.append(f"- Reuse is not known: keep the UI part presentational and props-driven{where or ', next to the feature'}, so it can be promoted to a shared component later (agent default - not a project rule).")
    L += ["", "**Quality (general reminders, not project facts)**",
          "- Handle loading, empty and error states; type the data you receive; do not hard-code URLs or texts that the project keeps in one place.",
          "- Write the tests the project's convention asks for (see section F); if none was found, say so instead of inventing a test setup.",
          "", "**Be careful**",
          "- Do not write code just because it looks right. If something in sections B or E is UNKNOWN, SUSPECTED or DEVELOPER-REPORTED, check it in the code or ask before building on it.",
          "- Never invent an endpoint, a payload field, a permission or a file name. Missing facts go back to the mentor."]
    return "\n".join(L)


_HEADINGS = {"A": "Task, requirements and acceptance criteria", "D": "Implementation plan", "F": "Testing", "G": "Implementation prompt"}


def compose_prompt(state):
    allowed = sorted({p for t in state["topics"] for p in t["paths"]} | {p for d in state["decisions"] for o in d["options"] for p in o["evidence"]}
                     | set(state["evidence_files"]))
    findings = [{k: t[k] for k in ("id", "title", "status", "answer", "paths", "deps", "candidates")} for t in state["topics"]]
    decisions = [{"id": d["id"], "question": d["question"], "chosen": d["chosen"]["label"] if d["chosen"] else None,
                  "custom": bool(d["chosen"] and d["chosen"]["custom"])} for d in state["decisions"]]
    user = _section(task=task_block(state), project_status=state["project_facts"] if state.get("no_project") else "a project was scanned",
                    endpoints_given="\n".join(_endpoints(state)) or "(none)",
                    requirements="\n".join(state.get("requirements", [])) or "(none extracted)", findings=json.dumps(findings, ensure_ascii=False),
                    decisions=json.dumps(decisions, ensure_ascii=False), allowed_paths="\n".join(allowed) or "(none)",
                    corrections=state.get("final_prompt_eval_text", "") if state.get("prompt_round") else "(none)")
    text = llm.invoke("compose_prompt", P.COMPOSE, user, temperature=0.3)
    parts = {m.group(1): m.group(2).strip() for m in re.finditer(r"^===\s*([ADFG])\s*===\s*\n(.*?)(?=^===\s*[ADFG]\s*===|\Z)", text, re.S | re.M)}

    def sec(k):
        return f"## {k}. {_HEADINGS[k]}\n\n{parts.get(k) or 'UNKNOWN: this section was not generated.'}"
    if not any(t["status"] == "verified" for t in state["topics"]):          # nothing was verified: the prompt must not say so
        parts["G"] = re.sub(r"verified architecture", "Architecture findings", parts.get("G", ""), flags=re.I)
    parts["G"] = (parts.get("G") or "UNKNOWN: this section was not generated.").rstrip() + "\n" + _status_footer(state)
    ordered = [_section_ready(state), sec("A"), _section_b(state), _section_c(state), sec("D"), _section_e(state), _section_i(state), _section_h(state), sec("F"), _section_j(state), sec("G")]
    brief = "\n\n".join(x for x in ordered if x)
    return {"final_prompt": brief, "prompt_round": state.get("prompt_round", 0) + 1}


def eval_prompt(state):
    det = arch.check_brief(state["final_prompt"], set(state["project_files"]), state["topics"], state["decisions"],
                           known_text=(task_block(state) + "\n" + "\n".join(t["answer"] for t in state["topics"])) if state.get("no_project") else "",
                           known_endpoints=tuple(_endpoints(state)))
    findings = [f"{t['id']} {t['title']}: {t['status']} {t['answer'][:80]}" for t in state["topics"]]
    decisions = [f"{d['id']} {d['question']} -> {d['chosen']['label'] if d['chosen'] else None}" for d in state["decisions"]]
    user = _section(task=task_block(state), findings="\n".join(findings) or "(none)", decisions="\n".join(decisions) or "(none)", prompt=state["final_prompt"])
    llm_issues, warnings = [], state.get("warnings", [])
    try:
        llm_issues = arch.clean_llm_issues(llm.invoke_json("eval_prompt", P.EVAL, user).get("issues"))
    except Exception as e:
        warnings = warnings + [f"semantic evaluation unavailable ({type(e).__name__}); deterministic checks only"]
    issues = det + llm_issues
    crit = [i for i in issues if i["severity"] == "critical"]
    text = "\n".join(f"- [{i['severity']}] {i['type']} ({i['section']}): {i['explanation']} -> {i['action']}" for i in issues if i["severity"] != "minor")
    return {"eval_issues": issues, "final_prompt_eval_text": text, "brief_accepted": not crit,
            "correction_round": state.get("correction_round", 0) + (1 if crit else 0), "warnings": warnings}


def route_after_eval_prompt(state):
    return "compose_prompt" if not state["brief_accepted"] and state["correction_round"] <= MAX_CORRECTIONS else "deliver"


def deliver(state):
    accepted = state.get("brief_accepted", False)
    lines = ["הפרומפט המקצועי מוכן. הממצאים וההחלטות מסומנים לפי מקורם (VERIFIED / DEVELOPER-REPORTED / MOCK / SUSPECTED...).",
             "לפני שמתחילים לכתוב קוד: קראו את סעיף H בפרומפט - איך כותבים בפרויקט הזה, מה כבר קיים ומה לבדוק."]
    if not accepted:
        crit = [i for i in state["eval_issues"] if i["severity"] == "critical"]
        lines = [f"הפרומפט לא עבר את הבדיקה: נותרו {len(crit)} בעיות קריטיות ({', '.join(sorted({i['type'] for i in crit}))}). אין להסתמך עליו בלי בדיקה עם {MENTOR}."]
    decided = {d["topic"] for d in state["decisions"] if d.get("topic")}
    open_items = [t["title"] for t in state["topics"] if t["status"] == "suspected" or (t["status"] in {"unknown", "open"} and t["id"] not in decided)]
    if open_items:
        lines.append(f"נשארו נושאים פתוחים ({', '.join(open_items)}): הם מופיעים בפרומפט (סעיף E) כשאלות לבירור מול {MENTOR}.")
    path = Path("briefs") / f"prompt-{state.get('run_id', 'run')}{'' if accepted else '-unaccepted'}.md"
    saved = _save("prompt", path, state["final_prompt"])
    return {"outcome": "prompt", "final_message": "\n".join(lines), "saved_path": saved}
