"""End-to-end flow tests (scripted LLM, scripted developer).
Two kinds of gaps: ARCHITECTURE questions the developer cannot answer never stop the run (the agent decides from the project and says so);
a BLOCKING FACT (the endpoint, auth) is never invented - the run stops without a prompt and the developer takes precise questions to the mentor."""
import json
from pathlib import Path

from conftest import PARKING, SENSORS, Human, Script, checklist, decision, option, topic

TASK = "מסך רשימת חניונים: שם, שעת כניסה ויציאה, חיפוש אחרי 3 תווים, בעיצוב הקיים"
LIST = "src/screens/VehicleListScreen.tsx"
SEARCH = "src/components/ui/SearchInput.tsx"


def search_topic(**kw):
    return topic("Existing search component", "Is there an existing search component or a component library that has one?",
                 category="reusable_components", terms=["search", "input"], **kw)


def parking_checklist():
    return checklist(
        topic("Where list screens live", "Where are the existing list screens?", category="placement", terms=["list", "screen"]),
        topic("Existing list screen with search", "Which existing screen has a list with search?", terms=["list", "search"]),
        search_topic(),
        topic("Parking facilities API", "Does an API for parking facilities exist? Where?", category="api_dependency", terms=["parking", "facilities"], mockable=True),
        requirements=["facility name", "entry/exit time", "search after 3 chars", "match the existing design"])


def asked(res, **kw):
    return [p for p in res.prompts if all(p.get(k) == v for k, v in kw.items())]


def status(res, i=0):
    return res.values["topics"][i]["status"]


def section(brief, letter):
    return brief.split(f"## {letter}.")[1].split("\n## ")[0]


# ------------------------------------------------------------ happy path
def test_parking_lot_scenario_full_flow(run):
    """The API does not exist and the backend is not ready: continue with a labeled mock, never invent the contract; developer picks options; prompt produced."""
    decisions = {"decisions": [decision("Data fetching", option("React Query hook like the vehicles screen", evidence=[LIST], dep="@tanstack/react-query"),
                                        option("Plain useEffect + http", evidence=["src/services/http.ts"])),
                               decision("Search box", option("Reuse SearchInput", evidence=[SEARCH]), option("New input", new=True))]}
    s = Script(build_checklist=parking_checklist(), propose_options=decisions)
    h = Human(text={"t1": ["src/screens"], "t2": [LIST], "t3": ["SearchInput and ListRow in src/components/ui"], "t4": ["אני לא יודע את הנתיב של ה-API", "הבק-אנד עדיין בפיתוח, אין עדיין API"]},
              choice=["1", "המלצה"])
    r = run(PARKING, TASK, s, h)
    v = r.values
    assert v["outcome"] == "prompt" and v["brief_accepted"]
    assert [t["status"] for t in v["topics"]] == ["verified", "verified", "verified", "mock_ok"]
    assert [p["kind"] for p in asked(r, id="t4", type="text")] == ["topic", "guidance"]       # "I don't know" -> guidance, not a repeated question
    assert not asked(r, type="confirm")                                                       # no extra yes/no gate before a mock
    brief = v["final_prompt"]
    assert "MOCK (provisional - ASSUMPTION)" in brief and "VERIFIED (found in the project)" in brief
    assert "React Query hook like the vehicles screen" in brief and "Reuse SearchInput" in brief
    assert s.count("compose_prompt") == 1 and v["requirements"][2] == "search after 3 chars"


def test_the_agent_reads_the_project_before_asking_anything(run):
    seen = {}

    def spy(user, n):
        seen["user"] = user
        return checklist()
    r = run(PARKING, TASK, Script(build_checklist=spy))
    assert "@tanstack/react-query" in seen["user"] and "VehicleListScreen" in seen["user"] and r.nodes.index("context_retrieval") < r.nodes.index("build_checklist")


def test_checklist_is_task_specific_not_a_fixed_questionnaire(run):
    db = checklist(topic("Existing migrations", category="data_model", terms=["migration", "table"]))
    r = run(SENSORS, "Create tables for customers and orders", Script(build_checklist=db), Human(text={"t1": ["docs/architecture.md"]}))
    assert len(asked(r, type="text")) == 1 and r.values["topics"][0]["category"] == "data_model"


# ------------------------------- "is there such a component?" (reuse or create)
def test_the_developer_names_the_existing_component(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(search_topic())), Human(text={"t1": [SEARCH]}))
    assert status(r) == "verified" and r.values["topics"][0]["paths"] == [SEARCH] and len(asked(r, type="text")) == 1


def test_idk_shows_where_to_look_and_asks_if_the_developer_is_sure_it_does_not_exist(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(search_topic())), Human(text={"t1": ["לא יודע", "אין"]}))
    second = asked(r, id="t1")[1]
    assert second["kind"] == "guidance" and SEARCH in second["guidance"]["files"] and set(second["guidance"]["files"]) <= set(r.values["project_files"])
    assert "בטוחים שאין" in second["note"] or "'אין'" in second["note"]
    assert second["guidance"]["terms"] == ["search", "input"]
    t = r.values["topics"][0]
    assert t["status"] == "absent" and SEARCH in t["candidates"]                                # a new one is allowed, but the possible match is recorded
    e = section(r.values["final_prompt"], "E")
    assert "does not exist, so a new one may be created" in e and SEARCH in e and r.values["outcome"] == "prompt"


def test_a_suspicion_that_it_exists_is_written_into_the_prompt(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(search_topic())), Human(text={"t1": ["לא יודע", "יש חשד שקיים אבל לא מצאתי"]}))
    t = r.values["topics"][0]
    assert t["status"] == "suspected" and SEARCH in t["candidates"]
    e = section(r.values["final_prompt"], "E")
    assert "SUSPECTED EXISTING" in e and "Search the project before creating anything new" in e and SEARCH in e
    assert "Is there an existing search component" in e                                     # and the question for the mentor is listed, without blocking
    assert r.values["outcome"] == "prompt" and "SUSPECTED EXISTING" in r.values["final_prompt"].split("## B.")[1].split("## C.")[0]


def test_saying_none_exists_while_the_project_has_candidates_is_double_checked_once(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(search_topic())), Human(text={"t1": ["אין לנו רכיב חיפוש", "בדקתי, אין"]}))
    assert [p["kind"] for p in asked(r, id="t1")] == ["topic", "guidance"] and status(r) == "absent"
    assert "מצאתי קבצים שאולי קשורים" in asked(r, id="t1")[1]["note"]


def test_saying_none_exists_when_nothing_in_the_project_relates_is_accepted_at_once(run):
    s = Script(build_checklist=checklist(topic("Payment gateway", "Is there an existing payment gateway?", terms=["payment", "gateway"])))
    r = run(PARKING, TASK, s, Human(text={"t1": ["אין"]}))
    assert len(asked(r, type="text")) == 1 and status(r) == "absent" and r.values["topics"][0]["candidates"] == []


def test_not_knowing_hands_the_decision_to_the_developer_with_options(run):
    """Data fetching: the developer does not know how the project does it -> the agent proposes solutions based on the project and the developer decides."""
    seen = {}

    def options(user, n):
        seen["user"] = user
        return {"decisions": [decision("Data fetching", option("React Query hook", evidence=[LIST], dep="@tanstack/react-query"), option("Plain axios call", dep="axios"))]}
    s = Script(build_checklist=checklist(topic("Data fetching", "How does the project fetch data?", category="data_layer", terms=["http", "query"])), propose_options=options)
    r = run(PARKING, TASK, s, Human(text={"t1": ["לא יודע", "לא יודע"]}, choice=["2"]))
    assert status(r) == "unknown" and '"status": "unknown"' in seen["user"]               # the options step is told this is unresolved
    brief = r.values["final_prompt"]
    assert "Plain axios call" in brief and "chosen by the developer" in brief and "UNKNOWN" in section(brief, "E") and r.values["outcome"] == "prompt"


# ---------------------------------------- light check, never a gate
def test_a_path_that_does_not_exist_is_recorded_not_rejected_and_not_asked_again(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(topic("Where list screens live", category="placement"))),
            Human(text={"t1": ["src/pages/Facilities.tsx"]}))
    t = r.values["topics"][0]
    assert len(asked(r, id="t1")) == 1 and t["status"] == "reported" and t["paths"] == [] and any("לא קיים" in n for n in t["notes"])
    assert "DEVELOPER-REPORTED (not verified)" in r.values["final_prompt"] and r.values["outcome"] == "prompt"


def test_a_statement_without_a_checkable_path_is_kept_as_developer_reported(run):
    s = Script(build_checklist=checklist(topic("Existing list screen with search", terms=["search"])))
    r = run(PARKING, TASK, s, Human(text={"t1": ["יש לנו קונבנציה לזה, כמו תמיד"]}))
    assert status(r) == "reported" and "DEVELOPER-REPORTED (not verified)" in r.values["final_prompt"] and r.values["outcome"] == "prompt"


def test_architecture_unknowns_never_stop_the_run_the_agent_decides_from_the_project(run):
    """The developer knows nothing about placement / components / data: no stop - the agent picks from what the project has and labels it AGENT-DECIDED."""
    d = decision("Where the list lives", option("Next to VehicleListScreen", evidence=[LIST]), option("A new folder", new=True), topic="t1")
    s = Script(build_checklist=checklist(topic("Where list screens live", category="placement", terms=["list", "screen"]),
                                         topic("Existing search component", category="reusable_components", terms=["search"])),
               propose_options={"decisions": [d]})
    r = run(PARKING, TASK, s, Human(text={"t1": ["לא יודע", "לא יודע"], "t2": ["לא יודע", "לא יודע"]}))
    v = r.values
    assert v["outcome"] == "prompt" and not asked(r, type="choice") and s.count("compose_prompt") == 1
    assert [t["status"] for t in v["topics"]] == ["unknown", "unknown"]
    c, e = section(v["final_prompt"], "C"), section(v["final_prompt"], "E")
    assert "DECIDED BY THE AGENT" in c and "Next to VehicleListScreen" in c and LIST in c
    assert "[t1]" in e and "DECIDED BY THE AGENT" in e.split("[t1]")[1].split("[t2]")[0]
    assert "no grounded option was found" in e.split("[t2]")[1]                              # no grounded option -> follow the closest existing pattern, do not invent
    assert "Questions to clarify with" in e and "Existing search component" not in e.split("Questions to clarify with")[0].split("[t1]")[0]


def test_a_real_design_choice_is_still_the_developers(run):
    d = decision("Data fetching", option("React Query hook", evidence=[LIST], dep="@tanstack/react-query"), option("Plain axios call", dep="axios"))
    r = run(PARKING, TASK, with_options(d), Human(text={"t1": [LIST]}, choice=["2"]))
    assert len(asked(r, type="choice")) == 1 and "chosen by the developer" in section(r.values["final_prompt"], "C")


# -------------------------------------------------------------- missing API
def test_missing_backend_api_continues_with_a_labeled_mock(run):
    s = Script(build_checklist=checklist(topic("Parking facilities API", category="api_dependency", mockable=True, terms=["parking"])))
    r = run(PARKING, TASK, s, Human(text={"t1": ["אין עדיין API"]}))
    e = section(r.values["final_prompt"], "E")
    assert status(r) == "mock_ok" and "MOCK" in e and "ASSUMPTION" in e and r.values["outcome"] == "prompt"


def test_missing_auth_api_is_never_mocked_and_goes_to_the_mentor(run):
    s = Script(build_checklist=checklist(topic("Login API", "Where is the login endpoint?", category="api_dependency", mockable=True)))
    r = run(PARKING, TASK, s, Human(text={"t1": ["אין עדיין API"]}))
    assert status(r) == "mentor_needed" and r.values["outcome"] == "needs_mentor" and "final_prompt" not in r.values


def test_an_existing_contract_is_verified_not_mocked(run):
    s = Script(build_checklist=checklist(topic("Vehicles API client", category="api_dependency", mockable=True, terms=["vehicles"])))
    r = run(PARKING, TASK, s, Human(text={"t1": ["src/services/vehicles.ts"]}))
    assert status(r) == "verified"


# ------------------------------------------------------- choosing options
def with_options(*decisions):
    return Script(build_checklist=checklist(topic("Existing list screen", terms=["list"])), propose_options={"decisions": list(decisions)})


D1 = decision("Data fetching", option("React Query hook", evidence=[LIST], dep="@tanstack/react-query"), option("Plain axios call", dep="axios"))


def test_invalid_choices_are_rejected_and_idk_is_not_a_choice(run):
    r = run(PARKING, TASK, with_options(D1), Human(text={"t1": [LIST]}, choice=["9", "לא יודע", "", "2"]))
    errors = [p["error"] for p in asked(r, type="choice")]
    assert errors[0] is None and all(errors[1:]) and len(errors) == 4
    assert r.values["decisions"][0]["chosen"]["label"] == "Plain axios call"


def test_a_custom_choice_is_kept_but_flagged_as_not_grounded(run):
    r = run(PARKING, TASK, with_options(D1), Human(text={"t1": [LIST]}, choice=["useReducer מקומי"]))
    assert "developer's own option - not grounded in the project" in r.values["final_prompt"] and "useReducer מקומי" in r.values["final_prompt"]


def test_invented_options_never_reach_the_developer(run):
    bad = decision("Store", option("Redux slice", evidence=["src/store/slice.ts"]), option("Zustand", dep="zustand"))
    r = run(PARKING, TASK, with_options(bad), Human(text={"t1": [LIST]}))
    assert not asked(r, type="choice") and r.values["decisions"] == []


def test_a_new_dependency_is_flagged_in_the_prompt(run):
    d = decision("Fetching", option("SWR", new=True), option("React Query", dep="@tanstack/react-query"))
    r = run(PARKING, TASK, with_options(d), Human(text={"t1": [LIST]}, choice=["1"]))
    assert "NEW DEPENDENCY" in r.values["final_prompt"]


# --------------------------------------------------- control and brief checks
def test_quit_at_any_prompt_cancels_without_a_prompt(run):
    r = run(PARKING, TASK, Script(build_checklist=parking_checklist()), Human(text={"t1": ["src/screens"], "t2": ["q"]}))
    assert r.values["cancelled"] and "final_prompt" not in r.values and r.script.count("compose_prompt") == 0


def test_empty_answers_are_rejected_and_five_in_a_row_cancel(run):
    s = Script(build_checklist=checklist(topic("Where list screens live", category="placement")))
    ok = run(PARKING, TASK, s, Human(text={"t1": ["", "src/screens"]}))
    assert asked(ok, id="t1")[1]["error"] and ok.values["topics"][0]["status"] == "verified"
    bad = run(PARKING, TASK, Script(build_checklist=checklist(topic("Where list screens live", category="placement"))), Human(text={"t1": [""] * 5}))
    assert bad.values["cancelled"]


def test_out_of_scope_request_ends_immediately(run):
    r = run(PARKING, "מה מזג האוויר?", Script(guardrails={"in_scope": False}))
    assert not r.prompts and r.values["in_scope"] is False


def test_no_relevant_topics_goes_straight_to_the_prompt(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist()))
    assert not r.prompts[:-1] and r.values["outcome"] == "prompt" and "none (the task needed no architecture checks)" in r.values["final_prompt"]


def test_an_invented_path_in_the_prompt_triggers_a_correction_then_is_accepted(run):
    bad = GOOD_WITH("Edit src/screens/Invented.tsx")
    s = Script(build_checklist=checklist(), compose_prompt=[bad, GOOD_WITH("Edit src/screens/VehicleListScreen.tsx")])
    r = run(PARKING, TASK, s)
    assert s.count("compose_prompt") == 2 and r.values["brief_accepted"] and "Invented" not in r.values["final_prompt"]


def test_a_prompt_that_keeps_inventing_paths_is_delivered_as_unaccepted(run, tmp_path):
    s = Script(build_checklist=checklist(), compose_prompt=GOOD_WITH("Edit src/screens/Invented.tsx"))
    r = run(PARKING, TASK, s, Human(save="y"))
    assert not r.values["brief_accepted"] and r.values["saved_path"].endswith("-unaccepted.md") and "לא עבר את הבדיקה" in r.values["final_message"]


def GOOD_WITH(line):
    return f"=== A ===\nTask.\n=== D ===\n{line}\n=== F ===\nUNKNOWN.\n=== G ===\nImplement."


# ------------------------------------------ blocking facts: never invented, precise questions for the mentor
API_TOPIC = topic("Parking facilities endpoint", "Which REST endpoint returns the parking facilities?", category="api_dependency", mockable=True, terms=["parking", "facilities"])


def test_a_concrete_endpoint_is_accepted_and_marked_for_confirmation_with_the_backend(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(API_TOPIC)), Human(text={"t1": ["GET /api/parking/facilities, מחזיר מערך"]}))
    assert status(r) == "reported" and r.values["outcome"] == "prompt"
    assert "given by the developer (see above) - confirm with the backend" in section(r.values["final_prompt"], "E")


def test_an_unknown_endpoint_is_not_invented_the_run_stops_with_a_precise_question_for_the_mentor(run, tmp_path):
    """The user's motto: a missing URL stops the task. The dialogue still goes on with the other topics, then NO prompt, only the exact question."""
    s = Script(build_checklist=checklist(topic("Where list screens live", category="placement", terms=["list", "screen"]), API_TOPIC))
    r = run(PARKING, TASK, s, Human(text={"t1": ["src/screens"], "t2": ["לא יודע", "לא יודע"]}, save="y"))
    v = r.values
    assert v["outcome"] == "needs_mentor" and "final_prompt" not in v and s.count("compose_prompt") == 0 and s.count("propose_options") == 0
    assert [b["id"] for b in v["blocked"]] == ["t2"]
    q = v["blocked"][0]["question"]
    assert "endpoint" in q and "Swagger" in q and "Mock" in q and "Parking facilities endpoint" in q
    assert "--resume" in v["final_message"] and "src/screens" not in v["final_message"].split("לברר מול")[1].split("מה שכבר נקבע")[0]
    saved = json.loads(Path(v["saved_path"]).read_text(encoding="utf-8"))
    assert saved["topics"][0]["status"] == "verified" and saved["topics"][1]["status"] == "mentor_needed"
    assert [p["kind"] for p in asked(r, id="t2", type="text")] == ["topic", "guidance"] and "ואני לא ממציא" in asked(r, id="t2", kind="guidance")[0]["note"]


def test_an_answer_about_the_api_without_any_url_or_file_is_not_enough(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(API_TOPIC)), Human(text={"t1": ["יש לנו API לזה", "כן כן יש"]}))
    assert status(r) == "mentor_needed" and r.values["outcome"] == "needs_mentor"


def test_auth_is_a_blocking_fact_too_it_is_never_assumed(run):
    auth = topic("Delete permission", "Which roles may delete a facility?", category="auth")
    unknown = run(PARKING, TASK, Script(build_checklist=checklist(auth)), Human(text={"t1": ["לא יודע", "לא יודע"]}))
    assert status(unknown) == "mentor_needed" and unknown.values["outcome"] == "needs_mentor" and "הרשאה" in unknown.values["blocked"][0]["question"]
    known = run(PARKING, TASK, Script(build_checklist=checklist(auth)), Human(text={"t1": ["רק תפקיד admin"]}))
    assert status(known) == "reported" and known.values["outcome"] == "prompt"


def test_an_existing_service_file_counts_as_the_answer(run):
    r = run(PARKING, TASK, Script(build_checklist=checklist(API_TOPIC)), Human(text={"t1": ["src/services/vehicles.ts"]}))
    assert status(r) == "verified" and r.values["outcome"] == "prompt"


def test_resume_asks_only_the_blocked_question_and_records_the_mentors_answer_as_a_statement(run):
    s1 = Script(build_checklist=checklist(topic("Where list screens live", category="placement", terms=["list"]), API_TOPIC))
    first = run(PARKING, TASK, s1, Human(text={"t1": [LIST], "t2": ["לא יודע", "לא יודע"]}))
    assert first.values["outcome"] == "needs_mentor"
    s2 = Script()
    s2.r.pop("build_checklist")                                                    # the checklist must NOT be generated again
    second = run(PARKING, TASK, s2, Human(mentor={"t2": "GET /api/v2/facilities (המנטור אישר), ראו גם src/services/facilities.ts"}), session=first.values["session_out"])
    assert [p["id"] for p in second.prompts if p["type"] == "text"] == ["t2"] and asked(second, id="t2")[0]["kind"] == "mentor"
    t = second.values["topics"][1]
    assert t["status"] == "mentor_answered" and t["mentor"]["not_in_project"] == ["src/services/facilities.ts"]
    brief = second.values["final_prompt"]
    assert second.values["outcome"] == "prompt" and "MENTOR-CONFIRMED (not verified in the project)" in brief and "does not exist in the project" in brief
    assert "VERIFIED" in brief.split("[t1]")[1].split("[t2]")[0]                  # the settled topic is still there, untouched


def test_resume_with_no_answer_yet_stays_blocked(run):
    first = run(PARKING, TASK, Script(build_checklist=checklist(API_TOPIC)), Human(text={"t1": ["לא יודע", "לא יודע"]}))
    second = run(PARKING, TASK, Script(), Human(mentor={"t1": "עדיין אין"}), session=first.values["session_out"])
    assert second.values["outcome"] == "needs_mentor" and second.values["topics"][0]["notes"][-1] == "עדיין אין תשובה מהמנטור"


# -------------------------------------------- section H: what the junior must pay attention to
def project_with(tmp_path, files):
    for rel, text in files.items():
        f = tmp_path / "proj" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return str(tmp_path / "proj")


def test_section_h_names_the_conventions_found_in_the_project(run, tmp_path):
    proj = project_with(tmp_path, {"package.json": '{"dependencies": {"react": "18"}}', ".eslintrc.json": "{}", ".prettierrc": "{}", "tsconfig.json": "{}",
                                   "src/screens/A.tsx": "export const A = () => null;"})
    h = section(run(proj, TASK, Script(build_checklist=checklist())).values["final_prompt"], "H")
    assert "lint rules: .eslintrc.json" in h and "formatting: .prettierrc" in h and "TypeScript config: tsconfig.json" in h and "do not add rules of your own" in h
    assert "Do not write code just because it looks right" in h and "Never invent an endpoint" in h and "loading, empty and error states" in h


def test_section_h_says_so_when_no_convention_files_exist_and_does_not_invent_any(run):
    h = section(run(PARKING, TASK, Script(build_checklist=checklist())).values["final_prompt"], "H")
    assert "No lint / formatting / style-guide / test-config files were found" in h and "eslint" not in h.lower()


def test_section_h_lists_existing_code_to_reuse_and_places_to_search_first(run):
    s = Script(build_checklist=checklist(topic("Existing list screen", terms=["list"]), search_topic()))
    h = section(run(PARKING, TASK, s, Human(text={"t1": [LIST], "t2": ["לא יודע", "יש חשד שקיים"]})).values["final_prompt"], "H")
    assert LIST in h.split("Existing code to read first")[1] and SEARCH in h.split("Search these before creating anything new")[1]


def test_section_h_follows_the_answer_about_future_reuse(run):
    reuse = topic("Future reuse", "Will another screen need this component later?", category="future_reuse")
    shared = topic("Reusable components", category="reusable_components", terms=["search"])
    base = lambda *answer: section(run(PARKING, TASK, Script(build_checklist=checklist(shared, reuse)),
                                       Human(text={"t1": [SEARCH], "t2": list(answer)})).values["final_prompt"], "H")
    assert "build it as a generic, props-driven component in the shared components folder (src/components/ui)" in base("כן, גם מסך הדוחות יצטרך אותו")
    assert "local to this feature" in base("לא, רק כאן")
    assert "Reuse is not known" in base("לא יודע", "לא יודע")
