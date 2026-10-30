"""Deterministic logic of the architecture-first workflow. Everything the agent must never get wrong lives here (no LLM), so it is unit-tested:

- cleaning of the LLM's checklist / options (untrusted drafts)
- a light check of the developer's free-text answers against the real project (paths that exist, dependencies in the manifests) - a hint, not a gate
- classification of free text (quit / "I don't know" / "none exists" / "I suspect it exists" / answer), yes-no and option choices
- the two kinds of topics: ARCHITECTURE topics (where to put it, which component, how data is kept...) - when the developer does not know, the agent decides
  from the project itself and says so; and BLOCKING FACTS (the endpoint URL, auth, a business rule) - never invented: they go to the mentor and the run
  stops without a prompt until the answer comes back
- the final-brief checks
"""
import re
from pathlib import Path

from agent import tools

CATEGORIES = {"placement", "similar_implementation", "reusable_components", "ui_system", "data_layer", "state", "routing", "libraries",
              "testing", "api_dependency", "backend_pattern", "data_model", "auth", "config", "future_reuse", "other"}
BLOCKER_CATEGORIES = {"api_dependency", "auth"}   # facts only a person can give: the agent never invents them
NO_RELEVANCE_CHECK = {"placement", "routing", "config"}      # the answer is a location: existence is enough
SENSITIVE_RE = re.compile(r"\b(auth\w*|login|password|token|permission\w*|payment\w*|security|secret|encrypt\w*)\b|הרשאה|הרשאות|אימות|תשלום|אבטחה", re.I)
MAX_TOPICS, MAX_DECISIONS, MAX_OPTIONS = 6, 3, 3
GENERIC = {"react", "with", "using", "that", "this", "from", "the", "use", "uses", "used", "and", "for", "our", "src", "app", "file", "files",
           "components", "component", "screen", "screens", "page", "pages", "yes", "none", "idk"}


def tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"\w+", s.lower()) if len(t) >= 3 and t not in GENERIC]


# ------------------------------------------------------------------ checklist
def clean_requirements(raw, limit: int = 12) -> list[str]:
    out = [str(r).strip()[:200] for r in raw if str(r).strip()] if isinstance(raw, list) else []
    return list(dict.fromkeys(out))[:limit]


def clean_topics(raw) -> list[dict]:
    """The LLM proposes a task-specific checklist; only well-formed, de-duplicated topics survive (max 6)."""
    out, seen = [], set()
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        title, question = str(r.get("title", "")).strip(), str(r.get("question", "")).strip()
        if not title or not question or tools.norm_text(title) in seen:
            continue
        seen.add(tools.norm_text(title))
        cat = r.get("category") if r.get("category") in CATEGORIES else "other"
        terms = [str(t).strip().lower() for t in (r.get("search_terms") if isinstance(r.get("search_terms"), list) else []) if str(t).strip()][:6]
        out.append({"title": title[:120], "question": question[:300], "why": str(r.get("why", "")).strip()[:300], "category": cat,
                    "search_terms": terms, "blocker": cat in BLOCKER_CATEGORIES or r.get("blocker") is True,
                    "mockable": cat == "api_dependency" and r.get("mockable") is True and not SENSITIVE_RE.search(title + " " + question),
                    "status": "open", "answer": "", "paths": [], "deps": [], "notes": [], "candidates": [], "mentor": None, "mentor_question": ""})
        if len(out) == MAX_TOPICS:
            break
    for i, t in enumerate(out, 1):
        t["id"] = f"t{i}"
    return out


# Statuses: verified | reported | absent | suspected | unknown | mock_ok | mentor_answered | mentor_needed | open
RESOLVED_FACT = {"verified", "reported", "mock_ok", "mentor_answered"}


def blocking(topics: list[dict]) -> list[dict]:
    """Only a BLOCKING FACT that nobody could supply stops the run. Architecture topics never do: the agent decides those from the project."""
    return [t for t in topics if t["blocker"] and t["status"] not in RESOLVED_FACT]


_ENDPOINT = re.compile(r"https?://\S+|\b(?:GET|POST|PUT|PATCH|DELETE)\s+/\S+|(?<![\w/.:-])/[\w{}:\-]+(?:/[\w{}:.\-]+)+|(?<![\w/.:-])api/[\w{}:\-]+(?:/[\w{}:.\-]+)*", re.I)


_EXPLICIT_ENDPOINT = re.compile(r"https?://[^\s)\]>\"'`,;]+|\b(?:GET|POST|PUT|PATCH|DELETE)\s+/[^\s)\]>\"'`,;]+", re.I)


def find_endpoints(text: str, limit: int = 8) -> list[str]:
    """Every endpoint the developer wrote (a URL, 'GET /path', '/api/x/y') in the task, an attachment or an answer - so none of them can be lost on the way to the brief."""
    out = []
    for m in _ENDPOINT.finditer(text or ""):
        e = m.group(0).rstrip(".,;:)]>'\"`")
        while e.endswith("}") and e.count("}") > e.count("{"):
            e = e[:-1]
        if e and e not in out:
            out.append(e)
    return out[:limit]


def has_endpoint(text: str) -> bool:
    """Does the text contain a concrete URL / path ('GET /api/parking', 'https://...', '/api/v1/facilities')?"""
    return bool(_ENDPOINT.search(text))


def mentor_question(t: dict, why_open: str = "") -> str:
    """The precise question the developer takes to the mentor (never a vague 'ask about it')."""
    if t["category"] == "api_dependency":
        base = (f"{t['title']}: מהו ה-endpoint המדויק (שיטה + כתובת/נתיב), אילו פרמטרים הוא מקבל, מהו מבנה התשובה, והאם יש Swagger/OpenAPI או שירות קיים שכבר קורא אליו? "
                "אם ה-Backend עדיין לא מוכן: האם מותר להתקדם מול Mock, ומי מאשר את החוזה?")
    elif t["category"] == "auth":
        base = f"{t['title']}: איזה מנגנון הרשאה/אימות חל כאן, אילו תפקידים מורשים, ואיפה זה ממומש בפרויקט?"
    else:
        base = t["question"]
    return f"{base} (למה זה חוסם: {t['why'] or t['title']})" + (f" - {why_open}" if why_open else "")


# ---------------------------------------------------------- verifying answers
_SEG = r"[A-Za-z0-9_@.\-]"          # ASCII only: Hebrew letters glued to a path ("ב-src/screens") must not become part of it
_TOKEN = re.compile(rf"{_SEG}+(?:/{_SEG}+)+/?|{_SEG}+\.(?:tsx?|jsx?|py|json|md|ya?ml|graphql|gql|proto|java|kt|swift|cs|go|toml|sql|css|scss)(?![A-Za-z0-9_])")
_EXT = re.compile(r"\.[a-z0-9]{1,5}$", re.I)


def resolve_path(p: str, files: set[str]) -> str | None:
    """Existing project path (file, or directory that contains files) that the developer's text refers to, else None."""
    p = p.strip("`'\"()[],;: ").lstrip("-").rstrip(".").removeprefix("./").strip("/")
    if not p:
        return None
    if p in files:
        return p
    if any(f.startswith(p + "/") for f in files):
        return p
    hits = sorted(f for f in files if f.endswith("/" + p))
    if hits:
        return hits[0]
    if "/" not in p and _EXT.search(p):
        hits = sorted(f for f in files if Path(f).name == p)
        return hits[0] if hits else None
    return None


def extract_paths(text: str, files: set[str]) -> tuple[list[str], list[str]]:
    """-> (existing paths, claimed paths that do not exist). A token without a file extension counts as 'claimed' only when it starts inside an
    existing top-level directory (so API routes like api/parking/list are not mistaken for project files)."""
    tops = {f.split("/")[0] for f in files if "/" in f}
    found, missing = [], []
    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        if tok.lower().startswith(("http", "www.")):
            continue
        r = resolve_path(tok, files)
        if r:
            found.append(r)
        elif _EXT.search(tok.strip("/")) or tok.split("/")[0] in tops:
            missing.append(tok.strip("/"))
    return list(dict.fromkeys(found)), list(dict.fromkeys(missing))


def dep_names(tech: list[str]) -> list[str]:
    return [t.split(":", 1)[1] for t in tech if t.startswith(("npm:", "pip:"))]


def extract_deps(text: str, deps: list[str]) -> list[str]:
    """Dependencies from the manifests that the text mentions (a word of 4+ letters equal to / contained in the package name)."""
    words = {re.sub(r"^[\u0590-\u05ff]+-", "", w) for w in re.findall(r"[\w@/.\-]+", text.lower())}      # "ב-react-query": drop the glued Hebrew prefix
    words = {w for w in words if len(w) >= 4 and w not in GENERIC}
    out = []
    for d in deps:
        dl = d.lower()
        tail = dl.split("/")[-1]
        if any(w == dl or w == tail or (len(w) >= 5 and w in dl) for w in words):
            out.append(d)
    return out


def is_related(topic: dict, path: str, root: str, files: set[str]) -> bool:
    terms = set(topic["search_terms"]) | set(tokens(topic["title"]))
    terms = {t for t in terms if len(t) >= 3 and t not in GENERIC}    # words like "screen" or "component" occur everywhere and prove nothing
    targets = [f for f in files if f.startswith(path + "/")] if path not in files else [path]
    for f in targets[:40]:
        hay = (f + " " + tools.read_project_file(root, f, 20_000)).lower()
        if any(t in hay for t in terms):
            return True
    return False


def verify_answer(topic: dict, text: str, root: str, files: set[str], deps: list[str]) -> dict:
    """-> {status: verified | reported | conflict | unrelated, paths, missing, deps, note}.
    verified = at least one path/dependency the developer named exists in the project and relates to the topic.
    A claim of a path that does not exist is a CONFLICT with the repository and is never accepted."""
    if not files:           # no project was scanned: nothing can be checked, so nothing is "missing" or "verified" - the answer is only the developer's word
        return {"status": "reported", "paths": [], "missing": [], "deps": [], "note": ""}
    found, missing = extract_paths(text, files)
    used = extract_deps(text, deps)
    if topic["category"] not in NO_RELEVANCE_CHECK:
        related = [p for p in found if is_related(topic, p, root, files)]
    else:
        related = found
    unrelated = [p for p in found if p not in related]
    base = {"paths": related, "missing": missing, "deps": used, "note": ""}
    if missing and not (related or used):
        return {**base, "status": "conflict", "note": f"הנתיב {', '.join(missing)} לא קיים בפרויקט."}
    if related or used:
        note = f"שימו לב: {', '.join(missing)} לא קיים בפרויקט (לא נכלל)." if missing else ""
        return {**base, "status": "verified", "note": note}
    if unrelated:
        return {**base, "status": "unrelated", "note": f"הקובץ {', '.join(unrelated)} קיים, אבל לא נמצא קשר בינו לבין '{topic['title']}'. מה בו מתאים?"}
    return {**base, "status": "reported", "note": ""}


_URL = re.compile(r"https?://\S+", re.I)
URL_IS_WRONG = {"placement", "ui_system", "reusable_components", "similar_implementation", "state", "routing", "testing", "future_reuse"}


def off_topic(topic: dict, text: str, earlier: list[str]) -> str:
    """'' or a note for the developer: the answer does not fit the question (a bare API URL for a non-API topic, or the very same text as an earlier answer).
    Asked once - the second answer is accepted as given, flagged as unchecked."""
    s = text.strip()
    if topic["category"] in BLOCKER_CATEGORIES:
        return ""
    if topic["category"] in URL_IS_WRONG and _URL.search(s) and len(re.findall(r"\w+", _URL.sub(" ", s))) <= 1:       # elsewhere (data fetching, backend, libraries...) a URL is a legitimate answer
        return f"זו כתובת API, והשאלה היא על '{topic['title']}'. כתבו תשובה לשאלה עצמה (נתיב, שם רכיב או ספרייה), או 'אין' / 'יש חשד' / 'לא יודע/ת'."
    key = tools.norm_text(s)
    if len(key) >= 6 and key in {tools.norm_text(e) for e in earlier}:
        return f"זו אותה תשובה כמו בשאלה קודמת. האם התכוונתם לכך על '{topic['title']}'? אם לא - כתבו תשובה לשאלה הזו."
    return ""


def candidates(topic: dict, root: str, k: int = 4) -> list[str]:
    """Real project files that probably relate to the topic (BM25 over the project). They are search suggestions, never facts."""
    q = " ".join(topic["search_terms"] + [topic["title"]])
    return list(dict.fromkeys(h["path"] for h in tools.get_index(root).search(q, k=8)))[:k]


def related_candidates(topic: dict, root: str, files: set[str], k: int = 4) -> list[str]:
    """Candidates that really relate to the topic (shared search terms), so 'is there such a component?' can be answered with a hint."""
    return [p for p in candidates(topic, root, 8) if is_related(topic, p, root, files)][:k]


def guidance(topic: dict, root: str, scan: dict) -> dict:
    cands = candidates(topic, root)
    libs = dep_names(scan.get("tech", []))[:15] if topic["category"] in {"libraries", "ui_system", "state", "data_layer", "reusable_components"} else []
    return {"why": topic["why"], "files": cands, "terms": topic["search_terms"][:5], "dirs": scan.get("top_dirs", [])[:8], "dependencies": libs}


# ----------------------------------------------------------- free-text intents
QUIT_RE = re.compile(r"^\s*(q|quit|exit|יציאה|ביטול|צא|סיום)\s*$", re.I)
IDK_RE = re.compile(r"לא יודע|לא יודעת|אין לי מושג|לא מצאתי|לא מוצא|לא מוצאת|לא בטוח|לא בטוחה|עזרה|\bidk\b|don'?t know|do not know|not sure|couldn'?t find|can'?t find|not found|^\s*\?+\s*$|^\s*0\s*$", re.I)
NO_API_RE = re.compile(r"לא קיים|אין (עדיין )?(api|ממשק|endpoint|חוזה|שרת)|עדיין לא|לא מוכן|בפיתוח|\bnot (ready|exist\w*|available|built|yet)\b|doesn'?t exist|does not exist|no (api|endpoint|contract)|in development", re.I)
NO_ANSWER_RE = re.compile(r"^\s*(אין|עדיין אין|עדיין לא|אין עדיין|אין תשובה|לא קיבלתי|none|no answer|not yet)\b", re.I)   # "the mentor has not answered yet"
ABSENT_RE = re.compile(r"^\s*(?:[\w'\"]+[,:]?\s+){0,2}?(אין|אין לנו|אין כזה|אין כזו|לא קיים\w*|ליצור חדש\w*|לא קיימת|none|there is no\b|no such|does ?n[o']t exist)", re.I)   # "it does not exist"
SUSPECT_RE = re.compile(r"חשד|נראה לי|כנראה|אולי|ייתכן|יש משהו|בטוח שיש|\bmaybe\b|\bprobably\b|\bi think\b|suspect|might exist", re.I)             # "I think it exists"
YES_RE = re.compile(r"^\s*(y|yes|כן|בטח|אפשר|ok|אוקיי|בסדר)\b", re.I)
NO_RE = re.compile(r"^\s*(n|no|לא|אי אפשר)\b", re.I)
RECOMMEND_RE = re.compile(r"המלצה|ברירת מחדל|recommend\w*|default", re.I)


def classify_text(raw: str, verified: dict | None = None, category: str = "") -> str:
    """quit | idk | suspect | no_api | absent | answer | empty. A text that names real paths/dependencies is an answer even if it also says 'not sure'."""
    s = raw.strip()
    if not s:
        return "empty"
    if QUIT_RE.match(s):
        return "quit"
    if verified and (verified["paths"] or verified["deps"]):
        return "answer"
    if len(s.split()) <= 12 and SUSPECT_RE.search(s):
        return "suspect"
    if len(s.split()) <= 8 and IDK_RE.search(s):
        return "idk"
    if category == "api_dependency" and (NO_API_RE.search(s) or ABSENT_RE.match(s)):
        return "no_api"
    if len(s.split()) <= 10 and ABSENT_RE.match(s):
        return "absent"
    return "answer"


def parse_yes_no(raw) -> tuple[bool | None, str | None]:
    s = str(raw).strip()
    if YES_RE.match(s):
        return True, None
    if NO_RE.match(s):
        return False, None
    return None, f"לא הבנתי: {s!r}. ענו כן או לא."


def parse_choice(raw, n: int) -> tuple[tuple[str, object] | None, str | None]:
    """-> ((kind, value), error). kind: option (1-based index) | recommended | custom (free text) | quit. 'I don't know' is never an implicit choice."""
    s = str(raw).strip()
    if not s:
        return None, f"תשובה ריקה. בחרו מספר 1-{n}, כתבו אפשרות משלכם, או 'המלצה'."
    if QUIT_RE.match(s):
        return ("quit", None), None
    if re.fullmatch(r"\d+", s):
        i = int(s)
        return (("option", i), None) if 1 <= i <= n else (None, f"המספר {i} מחוץ לטווח 1-{n}.")
    if RECOMMEND_RE.search(s) and len(s.split()) <= 3:
        return ("recommended", None), None
    if len(s.split()) <= 4 and IDK_RE.search(s):
        return None, f"בחירה היא החלטה שלכם. בחרו מספר 1-{n}, כתבו אפשרות משלכם, או 'המלצה' כדי לקבל את ברירת המחדל המוצעת."
    return ("custom", s[:300]), None


# ------------------------------------------------------------ solution options
def clean_decisions(raw, root: str, files: set[str], deps: list[str], topic_ids: set[str] = frozenset()) -> list[dict]:
    """Options must stand on the existing project (an existing file or a dependency already in the manifests). An option that proposes a NEW
    dependency is allowed only when it is explicitly flagged. Decisions left with no grounded option are dropped; invented files never survive."""
    out = []
    lower = {d.lower(): d for d in deps}
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or not str(r.get("question", "")).strip():
            continue
        opts = []
        for o in r.get("options") if isinstance(r.get("options"), list) else []:
            if not isinstance(o, dict) or not str(o.get("label", "")).strip():
                continue
            ev = [resolve_path(str(p), files) for p in (o.get("evidence") if isinstance(o.get("evidence"), list) else [])]
            ev = list(dict.fromkeys(p for p in ev if p))
            dep = lower.get(str(o.get("uses_dependency") or "").strip().lower())
            new = o.get("new_dependency") is True
            if not (ev or dep or new):
                continue
            opts.append({"label": str(o["label"]).strip()[:120], "description": str(o.get("description", "")).strip()[:300],
                         "pros": str(o.get("pros", "")).strip()[:200], "cons": str(o.get("cons", "")).strip()[:200],
                         "evidence": ev, "dependency": dep, "new_dependency": new and not dep})
        opts = opts[:MAX_OPTIONS]
        if not opts:
            continue
        rec = r.get("recommended")
        rec = rec if isinstance(rec, int) and not isinstance(rec, bool) and 0 <= rec < len(opts) else 0
        for k, o in enumerate(opts):
            o["id"], o["recommended"] = k + 1, k == rec
        topic = str(r.get("topic") or "").strip()
        out.append({"question": str(r["question"]).strip()[:300], "title": str(r.get("title") or r["question"]).strip()[:120], "options": opts,
                    "topic": topic if topic in topic_ids else "", "status": "open", "chosen": None})
        if len(out) == MAX_DECISIONS:
            break
    for i, d in enumerate(out, 1):
        d["id"] = f"d{i}"
    return out


# ----------------------------------------------------------------- final brief
ISSUE_TYPES = {"unsupported_claim", "contradiction", "invented_file_path", "unverified_project_convention", "scope_expansion",
               "unjustified_architecture_choice", "unlabeled_assumption", "missing_source_reference", "invented_api_contract"}
SEVERITIES = {"critical", "major", "minor"}
_PATH = re.compile(r"(?<![\w/.:-])((?:[\w.-]+/)*[\w.-]+\.(?:tsx?|jsx?|py|md|json|ya?ml|graphql|gql|proto|java|kt|swift|cs|go|toml|txt|sql))(?![\w/-])")
_NOT_FILES = {"node.js", "react.js", "next.js", "vue.js", "express.js", "d3.js", "chart.js"}
_NEW_MARK = re.compile(r"\(new\)|new file|חדש", re.I)


def path_exists(path: str, files: set[str]) -> bool:
    return path in files or any(f.endswith("/" + path) for f in files) or ("/" not in path and path in {Path(f).name for f in files})


def issue(type_, severity, section, explanation, action, source="deterministic") -> dict:
    return {"type": type_, "severity": severity, "section": section, "explanation": explanation, "action": action, "source": source}


def check_brief(brief: str, files: set[str], topics: list[dict], decisions: list[dict], known_text: str = "", known_endpoints: tuple = ()) -> list[dict]:
    """known_text: with NO project, the only legitimate file names are the ones the developer wrote (task / answers); they are reported, not verified."""
    out = []
    said = {m.group(1) for m in _PATH.finditer(known_text)} if known_text else set()
    for ln in brief.splitlines():
        for m in _PATH.finditer(ln):
            p = m.group(1)
            if p.lower() in _NOT_FILES or path_exists(p, files) or _NEW_MARK.search(ln) or p in said:
                continue
            out.append(issue("invented_file_path", "critical", ln.strip()[:80], f"{p} does not exist in the project and is not marked as a new file",
                             "Remove it, use an existing file, or mark it explicitly as a proposed (new) file with justification."))
    given = set(known_endpoints)
    for m in _EXPLICIT_ENDPOINT.finditer(brief):
        e = m.group(0).rstrip(".,;:)]}>'\"`")
        if not any(e == g or e in g or g in e for g in given):
            out.append(issue("invented_api_contract", "critical", "G", f"{e} was never given by the developer", "Remove it: only endpoints the developer wrote may appear, labeled unverified."))
    for b in blocking(topics):
        out.append(issue("contradiction", "critical", "B", f"blocking fact {b['id']} ({b['title']}) is unresolved but a brief was produced", "Do not produce a brief."))
    for d in decisions:
        if d.get("chosen") and d["chosen"]["label"] not in brief:
            out.append(issue("contradiction", "critical", "C", f"the developer's choice for {d['id']} ({d['chosen']['label']}) is missing from the brief",
                             "State the chosen option exactly as chosen."))
    if any(t["status"] == "mock_ok" for t in topics) and "ASSUMPTION" not in brief:
        out.append(issue("unlabeled_assumption", "major", "E", "a mock is used but nothing is labeled ASSUMPTION", "Label the provisional interface."))
    return out


def clean_llm_issues(raw) -> list[dict]:
    out = []
    for r in raw if isinstance(raw, list) else []:
        if isinstance(r, dict) and r.get("type") in ISSUE_TYPES:
            out.append(issue(r["type"], r.get("severity") if r.get("severity") in SEVERITIES else "major",
                             str(r.get("section", ""))[:80], str(r.get("explanation", ""))[:300], str(r.get("action", ""))[:300], source="llm"))
    return out


def unknown_paths(text: str, files: set[str]) -> list[str]:
    return [m.group(1) for m in _PATH.finditer(text) if m.group(1).lower() not in _NOT_FILES and not path_exists(m.group(1), files)]
