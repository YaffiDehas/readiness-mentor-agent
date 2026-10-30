"""v9: NO PROJECT mode (nothing scanned, nothing claimed about code), wrong-answer detection, honest status labels, and the brief sections the
agent spec asks for (readiness decision, what changes on real integration, risks/approvals/tests, Conflicting)."""
from conftest import PARKING, ROOT, Human, Script, checklist, decision, option, topic
from agent import arch, tools
from agent.server import Runs

TASK = "הצגת היסטוריית חיובים של לקוח במסך הפרופיל"
API = topic("Charges API", "Is there an API for the charges? Which endpoint?", category="api_dependency", terms=["charges", "billing"], mockable=True)
PLACE = topic("Profile screen location", "Where is the profile screen?", category="placement", terms=["profile", "screen"])
TABLE = topic("Existing table component", "Is there an existing table component?", category="reusable_components", terms=["table"])
STATE = topic("State management", "How does the project keep state?", category="state", terms=["state", "store"])


def section(brief, letter):
    return brief.split(f"## {letter}.")[1].split("\n## ")[0]


def asked(res, **kw):
    return [p for p in res.prompts if all(p.get(k) == v for k, v in kw.items())]


def no_project_run(run, script=None, human=None, project=""):
    script = script or Script(build_checklist=checklist(PLACE, TABLE, STATE, API))
    human = human or Human(text={"t1": ["src/screens"], "t2": ["יש ספריה components"], "t3": ["אין"], "t4": ["אין"]})
    return run(project, TASK, script, human)


# ------------------------------------------------------------------ no project
def test_without_a_project_nothing_is_scanned_and_no_file_of_the_agent_appears_in_the_brief(run):
    """The reported bug: the agent scanned ITS OWN repo and told the junior to reuse ui/src/lib/reducer.js."""
    opt = decision("State", option("Reducer", evidence=["ui/src/lib/reducer.js"]), topic="t3")
    s = Script(build_checklist=checklist(PLACE, TABLE, STATE, API), propose_options={"decisions": [opt]})
    r = no_project_run(run, s)
    v, brief = r.values, r.values["final_prompt"]
    assert v["no_project"] is True and v["project_files"] == [] and v["evidence_files"] == [] and v["dependencies"] == []
    assert s.count("propose_options") == 0 and v["decisions"] == []
    for leak in ("reducer.js", "test_flow", "test_arch_units", "demo.js", "README.md", "possible matches"):
        assert leak not in brief
    assert "NO PROJECT WAS SCANNED" in section(brief, "B") or "NO PROJECT WAS SCANNED" in brief
    assert all(t["candidates"] == [] and t["paths"] == [] for t in v["topics"])


def test_without_a_project_section_h_does_not_claim_conventions_were_checked(run):
    h = section(no_project_run(run).values["final_prompt"], "H")
    assert "NOT checked" in h and "were found in the project" not in h and "No lint / formatting" not in h
    assert "Search your project before creating anything new" in h


def test_without_a_project_the_developers_own_statements_are_reported_never_verified(run):
    r = no_project_run(run, human=Human(text={"t1": ["src/screens/ProfileScreen.tsx"], "t2": ["components/Table"], "t3": ["אין"], "t4": ["אין"]}))
    assert [t["status"] for t in r.values["topics"]][:2] == ["reported", "reported"] and not any(t["status"] == "verified" for t in r.values["topics"])
    assert r.values["topics"][0]["notes"] == [] and "לא קיים בפרויקט" not in r.values["final_prompt"]


def test_the_agents_own_folder_is_treated_as_no_project(run):
    r = no_project_run(run, project=str(ROOT))
    assert r.values["no_project"] is True and r.values["project_root"] == "" and r.values["project_files"] == []
    assert any("תיקיית הסוכן" in w for w in r.values["warnings"])


def test_resolve_root_rules(tmp_path):
    assert tools.resolve_root("") == ("", False) and tools.resolve_root(None) == ("", False) and tools.resolve_root("  ") == ("", False)
    assert tools.resolve_root(str(ROOT)) == ("", True)
    assert tools.resolve_root(PARKING)[0] and not tools.resolve_root(PARKING)[1]
    try:
        tools.resolve_root(str(tmp_path / "nope"))
        raise AssertionError("must raise")
    except FileNotFoundError:
        pass


def test_a_file_name_the_developer_wrote_is_allowed_without_a_project_but_an_invented_one_is_corrected(run):
    bad = "=== A ===\nok\n=== D ===\nCreate src/invented/BillingTable.tsx and edit ReportsScreen.tsx\n=== F ===\nUNKNOWN\n=== G ===\ngo"
    good = "=== A ===\nok\n=== D ===\nEdit ReportsScreen.tsx\n=== F ===\nUNKNOWN\n=== G ===\ngo"
    s = Script(build_checklist=checklist(PLACE), compose_prompt=[bad, good])
    r = run("", TASK + " (ReportsScreen.tsx)", s, Human(text={"t1": ["src/screens/ReportsScreen.tsx"]}))
    assert s.count("compose_prompt") == 2 and r.values["brief_accepted"] and "BillingTable" not in r.values["final_prompt"]


def test_without_a_project_an_unknown_topic_is_not_decided_by_the_agent(run):
    r = no_project_run(run, human=Human(text={"t1": ["src/screens"], "t2": ["לא יודע", "לא יודע"], "t3": ["אין"], "t4": ["אין"]}))
    e = section(r.values["final_prompt"], "E")
    assert "no project was scanned, so the agent cannot suggest an answer" in e and "DECIDED BY THE AGENT" not in r.values["final_prompt"]


# ------------------------------------------------------------ wrong answers
def test_a_url_given_for_a_design_question_is_asked_again_once(run):
    ui = topic("Screen design", "What design system does the app use?", category="ui_system", terms=["design"])
    r = run(PARKING, TASK, Script(build_checklist=checklist(ui)), Human(text={"t1": ["http://localhost:3001/getCars", "tailwind"]}))
    ps = asked(r, id="t1", type="text")
    assert [p["kind"] for p in ps] == ["topic", "guidance"] and "כתובת API" in ps[1]["note"]
    assert r.values["topics"][0]["answer"] == "tailwind"


def test_the_same_answer_twice_in_a_row_is_questioned_and_a_second_identical_answer_is_accepted_but_flagged(run):
    a = topic("Screen design", category="ui_system", terms=["design"])
    b = topic("Date format", "How are dates formatted?", category="other", terms=["date"])
    r = run(PARKING, TASK, Script(build_checklist=checklist(a, b)), Human(text={"t1": ["src/theme.ts"], "t2": ["src/theme.ts", "src/theme.ts"]}))
    ps = asked(r, id="t2", type="text")
    assert [p["kind"] for p in ps] == ["topic", "guidance"] and "אותה תשובה" in ps[1]["note"]
    assert any("לא קשורה" in n for n in r.values["topics"][1]["notes"])


def test_a_url_is_the_expected_answer_for_an_api_topic_not_questioned(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(API)), Human(text={"t1": ["GET http://localhost:3001/getCars"]}))
    assert len(asked(r, id="t1", type="text")) == 1 and r.values["topics"][0]["status"] == "reported"


# ------------------------------------------------------- honest brief content
def test_g_never_says_verified_architecture_when_nothing_was_verified_and_ends_with_statuses(run):
    s = Script(build_checklist=checklist(PLACE),
               compose_prompt="=== A ===\nok\n=== D ===\nplan\n=== F ===\nUNKNOWN\n=== G ===\nVerified architecture and files to reuse:\n- src/screens")
    g = section(run(PARKING, TASK, s, Human(text={"t1": ["בתיקיית המסכים"]})).values["final_prompt"], "G")
    assert "Verified architecture" not in g and "Architecture findings" in g
    assert "Status of every fact above" in g and "Profile screen location: " in g and "Rules: never invent an endpoint" in g


def test_mock_fields_are_not_attributed_to_the_task_and_the_mentor_is_asked_for_the_contract(run):
    e = section(no_project_run(run).values["final_prompt"], "E")
    assert "the task's requirements" not in e and "is NOT known" in e and "Use only the fields the task itself names" in e
    assert "real contract of 'Charges API'" in e and "who approves it" in e


def test_a_reported_endpoint_says_to_call_it_and_inspect_the_real_response(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(API)), Human(text={"t1": ["GET http://localhost:3001/getCars"]}))
    e = section(r.values["final_prompt"], "E")
    assert "call the endpoint and inspect the real response" in e and "never guess field names" in e and "documented anywhere" in e


# ------------------------------------------------------------ spec sections
def test_readiness_decision_proceed_with_limits_lists_each_limit(run):
    r = no_project_run(run)
    rd = section(r.values["final_prompt"], "R")
    assert "Decision: PROCEED WITH LIMITS" in rd and "No project was scanned" in rd and "labeled MOCK" in rd
    assert r.values["final_prompt"].index("## R.") < r.values["final_prompt"].index("## A.")


def test_readiness_decision_is_plain_proceed_when_everything_was_found(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(topic("Existing list screen", terms=["list"]))), Human(text={"t1": ["src/screens/VehicleListScreen.tsx"]}))
    rd = section(r.values["final_prompt"], "R")
    assert r.values["topics"][0]["status"] == "verified" and "Decision: PROCEED**" in rd and "LIMITS" not in rd


def test_section_i_describes_what_changes_when_the_real_api_connects(run):
    i = section(no_project_run(run).values["final_prompt"], "I")
    assert "ONE interface" in i and "ASSUMPTION" in i and "Re-run the tests" in i and "/" not in i.replace("/ ", " ").split("ONE interface")[0][-1:]


def test_section_i_is_absent_when_no_api_dependency_exists(run):
    assert "## I." not in run(PARKING, TASK, Script(build_checklist=checklist(PLACE)), Human(text={"t1": ["src/screens"]})).values["final_prompt"]


def test_section_j_has_risks_approvals_and_tests(run):
    j = section(no_project_run(run).values["final_prompt"], "J")
    assert "Risks" in j and "A mock can hide the real contract" in j and "Needs approval from" in j and "The contract of" not in j.split("Tests")[1]
    assert "ask" in j.split("**Tests**")[1] and "loading, empty and error" in j


def test_a_conflict_between_the_developer_and_the_project_search_is_labeled_conflicting(run):
    s = Script(build_checklist=checklist(topic("Existing search component", category="reusable_components", terms=["search", "input"])))
    r = run(PARKING, TASK, s, Human(text={"t1": ["אין", "אין"]}))
    t = r.values["topics"][0]
    assert t["status"] == "absent" and t["candidates"]
    brief = r.values["final_prompt"]
    assert "CONFLICTING with the project search" in section(brief, "B") and "CONFLICTING" in section(brief, "R") and "Decision: PROCEED WITH LIMITS" in brief


# ------------------------------------------------------------- entry points
def test_server_without_a_project_starts_a_run_with_no_project_root():
    (rid, start), err = Runs().start({"task": TASK}, "")
    assert err is None and start["project_root"] == ""


def test_server_still_rejects_a_project_folder_that_does_not_exist():
    _, err = Runs().start({"task": TASK, "project": "/definitely/not/here"}, "")
    assert "Project folder not found" in err


def test_off_topic_unit():
    ui = {"category": "ui_system", "title": "design"}
    assert arch.off_topic(ui, "http://x.y/z", []) and arch.off_topic(ui, "ראיתי את זה ב http://x.y/z", []) == ""  # a sentence that mentions a URL is not "a bare URL"
    assert arch.off_topic({"category": "api_dependency", "title": "api"}, "http://x.y/z", []) == ""


# ------------------------------------------- the developer's endpoint must reach the brief
URL = "https://api.example.com/customers/{id}/charges"
FETCH = topic("שליפת נתונים", "איך הפרויקט שולף נתונים?", category="data_layer", terms=["fetch"])


def test_a_url_given_for_a_data_fetching_question_is_kept_not_asked_again(run):
    """The reported bug: the URL was answered to 'how is data fetched', set aside as 'a URL is not an answer', and lost when the developer then wrote 'axios'."""
    r = run("", TASK, Script(build_checklist=checklist(FETCH)), Human(text={"t1": [f"axios, {URL}"]}))
    assert len(asked(r, id="t1", type="text")) == 1
    assert URL in section(r.values["final_prompt"], "E") and URL in section(r.values["final_prompt"], "G")


def test_even_an_answer_asked_again_as_off_topic_is_kept_and_its_endpoint_reaches_the_brief(run):
    design = topic("Screen design", "What design system?", category="ui_system", terms=["design"])
    r = run("", TASK, Script(build_checklist=checklist(design)), Human(text={"t1": [URL, "material"]}))
    t = r.values["topics"][0]
    assert t["answer"] == "material" and any(URL in n for n in t["notes"])
    assert URL in section(r.values["final_prompt"], "E") and URL in section(r.values["final_prompt"], "R")


def test_an_endpoint_written_in_the_task_text_is_carried_into_the_brief_even_if_the_model_drops_it(run):
    r = run("", TASK + f". ה-API: GET {URL}", Script(build_checklist=checklist(PLACE)), Human(text={"t1": ["src/screens"]}))
    g = section(r.values["final_prompt"], "G")
    assert URL in section(r.values["final_prompt"], "E") and f"{URL}" in g and "the only ones you may use" in g


def test_the_brief_never_claims_an_endpoint_was_given_when_none_was(run):
    blocker_fetch = topic("שליפת נתונים", "איך הפרויקט שולף נתונים?", category="data_layer", terms=["fetch"], blocker=True)
    r = run("", TASK, Script(build_checklist=checklist(blocker_fetch)), Human(text={"t1": ["axios"]}))
    e = section(r.values["final_prompt"], "E")
    assert "gave only the address" not in e and "NO endpoint (method + path) was given" in e and "What is the exact endpoint" in e


def test_an_endpoint_the_model_invents_is_a_critical_issue_and_corrected(run):
    bad = "=== A ===\nok\n=== D ===\nFetch from https://invented.example.org/charges\n=== F ===\nUNKNOWN\n=== G ===\ngo"
    good = "=== A ===\nok\n=== D ===\nFetch from the endpoint the developer gave\n=== F ===\nUNKNOWN\n=== G ===\ngo"
    s = Script(build_checklist=checklist(PLACE), compose_prompt=[bad, good])
    r = run("", TASK + f" {URL}", s, Human(text={"t1": ["src/screens"]}))
    assert s.count("compose_prompt") == 2 and "invented.example.org" not in r.values["final_prompt"] and URL in r.values["final_prompt"]


def test_find_endpoints_unit():
    assert arch.find_endpoints("see https://a.b/c/d. and GET /api/x/y, also /v1/items/{id}") == ["https://a.b/c/d", "GET /api/x/y", "/v1/items/{id}"]
    assert arch.find_endpoints("src/screens/A.tsx and 10/30/2026 and and/or") == []
