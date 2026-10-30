"""Deterministic units: cleaning of untrusted LLM drafts, verification of the developer's answers against the real project, intents, brief checks."""
import pytest

from agent import arch, tools
from conftest import PARKING, decision, option, topic

FILES = set(tools.scan_project(PARKING)["files"])
DEPS = arch.dep_names(tools.scan_project(PARKING)["tech"])


def T(**kw):
    return arch.clean_topics([topic("Existing list screens", terms=["list", "search", "screen"], **kw)])[0]


# ---------------------------------------------------------------- checklist
def test_checklist_is_capped_and_deduplicated():
    raw = [topic(f"topic {i}", category="placement" if i == 0 else "other") for i in range(9)] + [topic("topic 1")]
    out = arch.clean_topics(raw)
    assert len(out) == arch.MAX_TOPICS and [t["id"] for t in out] == [f"t{i}" for i in range(1, 7)]
    assert all(t["status"] == "open" and t["candidates"] == [] for t in out) and "critical" not in out[0]


def test_malformed_topics_are_dropped_and_unknown_categories_become_other():
    out = arch.clean_topics(["x", {"title": "", "question": "q"}, {"title": "a"}, topic("ok", category="made-up")])
    assert len(out) == 1 and out[0]["category"] == "other"


def test_mock_is_never_offered_for_auth_or_security_topics():
    ok = arch.clean_topics([topic("Parking facilities API", category="api_dependency", mockable=True)])[0]
    bad = arch.clean_topics([topic("Login API", "Where is the login endpoint?", category="api_dependency", mockable=True)])[0]
    assert ok["mockable"] and not bad["mockable"]


# NOTE: there is no stop rule any more (no "critical"/"blocking"): whatever is unknown ends up in the prompt as an open item.


# ------------------------------------------------------------ verification
def verify(text, t=None):
    return arch.verify_answer(t or T(), text, PARKING, FILES, DEPS)


def test_an_existing_related_file_is_verified():
    r = verify("src/screens/VehicleListScreen.tsx")
    assert r["status"] == "verified" and r["paths"] == ["src/screens/VehicleListScreen.tsx"]


def test_a_bare_file_name_and_a_directory_resolve_to_real_paths():
    assert verify("VehicleListScreen.tsx")["paths"] == ["src/screens/VehicleListScreen.tsx"]
    assert arch.resolve_path("src/screens/", FILES) == "src/screens"


def test_a_path_that_does_not_exist_is_a_conflict_never_accepted():
    r = verify("src/screens/ParkingFacilitiesScreen.tsx")
    assert r["status"] == "conflict" and "לא קיים" in r["note"]


def test_an_existing_but_unrelated_file_is_not_verified():
    r = verify("src/screens/ReportsScreen.tsx")
    assert r["status"] == "unrelated" and r["paths"] == []


def test_hebrew_text_around_a_path_does_not_break_it():
    for text in ("המסכים נמצאים ב-src/screens.", "הקובץ הוא src/screens/VehicleListScreen.tsx, ושם החיפוש", "(src/screens/VehicleListScreen.tsx)", "בתיקייה src/screens/"):
        r = verify(text)
        assert r["status"] == "verified" and not r["missing"], text


def test_api_routes_are_not_mistaken_for_missing_project_files():
    assert verify("the endpoint is api/parking/list")["status"] == "reported"


def test_a_dependency_from_the_manifest_is_verified_and_an_unknown_one_is_not():
    t = arch.clean_topics([topic("UI library", category="ui_system", terms=["ui"])])[0]
    r = verify("we use MUI (@mui/material)", t)
    assert r["status"] == "verified" and r["deps"] == ["@mui/material"]
    assert verify("we use bootstrap", t)["status"] == "reported"


def test_text_without_anything_checkable_is_only_reported():
    assert verify("we have a convention for this")["status"] == "reported"


def test_one_real_path_among_wrong_ones_is_verified_with_a_note():
    r = verify("src/screens/VehicleListScreen.tsx and src/screens/Nope.tsx")
    assert r["status"] == "verified" and "Nope.tsx" in r["note"]


# ------------------------------------------------------------------ intents
@pytest.mark.parametrize("text,kind", [("q", "quit"), ("יציאה", "quit"), ("לא יודע", "idk"), ("לא מצאתי", "idk"), ("I don't know", "idk"),
                                       ("אני לא יודעת איפה הנתיב", "idk"), ("", "empty"), ("src/screens", "answer"),
                                       ("הבק-אנד עדיין לא מוכן", "no_api")])
def test_free_text_classification(text, kind):
    assert arch.classify_text(text, None, "api_dependency" if kind == "no_api" else "") == kind


@pytest.mark.parametrize("text,kind", [("אין", "absent"), ("בדקתי, אין", "absent"), ("אין לנו רכיב חיפוש", "absent"), ("לא קיים", "absent"),
                                       ("נראה לי שיש אבל לא מצאתי", "suspect"), ("יש חשד שקיים", "suspect"), ("אולי יש משהו כזה", "suspect"),
                                       ("יש לנו קונבנציה ברורה, אין בעיה לקרוא לה", "answer"), ("אנחנו משתמשים ב-MUI", "answer")])
def test_none_exists_and_suspicion_are_told_apart_from_answers(text, kind):
    assert arch.classify_text(text) == kind


def test_none_exists_for_an_api_topic_means_the_api_is_missing():
    assert arch.classify_text("אין", None, "api_dependency") == "no_api" and arch.classify_text("אין", None, "other") == "absent"


def test_naming_real_files_is_an_answer_even_with_doubt_in_the_text():
    r = verify("לא בטוח אבל אולי src/screens/VehicleListScreen.tsx")
    assert arch.classify_text("לא בטוח אבל אולי src/screens/VehicleListScreen.tsx", r) == "answer"


def test_yes_no_hebrew_and_english_and_garbage():
    assert arch.parse_yes_no("כן")[0] is True and arch.parse_yes_no("no")[0] is False and arch.parse_yes_no("אולי")[0] is None


def test_choice_parsing_never_turns_idk_into_a_choice():
    assert arch.parse_choice("2", 3)[0] == ("option", 2)
    assert arch.parse_choice("9", 3)[0] is None
    assert arch.parse_choice("המלצה", 3)[0] == ("recommended", None)
    assert arch.parse_choice("לא יודע", 3)[0] is None
    assert arch.parse_choice("useReducer מקומי", 3)[0] == ("custom", "useReducer מקומי")
    assert arch.parse_choice("", 3)[0] is None and arch.parse_choice("q", 3)[0] == ("quit", None)


# ------------------------------------------------------------------ options
def test_options_must_rest_on_the_existing_project():
    raw = [decision("Data fetching",
                    option("React Query hook", evidence=["src/screens/VehicleListScreen.tsx"], dep="@tanstack/react-query"),
                    option("Invented store", evidence=["src/store/fancy.ts"]),                 # file does not exist -> dropped
                    option("Zustand", dep="zustand"),                                          # not in the manifests -> dropped
                    option("SWR", new=True))]
    out = arch.clean_decisions(raw, PARKING, FILES, DEPS)
    labels = [o["label"] for o in out[0]["options"]]
    assert labels == ["React Query hook", "SWR"]
    assert out[0]["options"][1]["new_dependency"] is True and out[0]["options"][0]["dependency"] == "@tanstack/react-query"


def test_a_decision_without_any_grounded_option_is_dropped():
    assert arch.clean_decisions([decision("X", option("a", evidence=["nope.ts"]), option("b"))], PARKING, FILES, DEPS) == []


def test_recommended_index_is_validated_and_decisions_are_capped():
    raw = [decision(f"D{i}", option("a", dep="axios"), option("b", dep="axios"), recommended=7) for i in range(5)]
    out = arch.clean_decisions(raw, PARKING, FILES, DEPS)
    assert len(out) == arch.MAX_DECISIONS and out[0]["options"][0]["recommended"] and [d["id"] for d in out] == ["d1", "d2", "d3"]


# ------------------------------------------------------------------- brief
def test_brief_check_rejects_invented_paths_but_allows_marked_new_files():
    bad = arch.check_brief("Edit src/screens/Invented.tsx to add it", FILES, [], [])
    assert [i["type"] for i in bad] == ["invented_file_path"]
    assert arch.check_brief("Create src/screens/FacilityListScreen.tsx (new) for the list", FILES, [], []) == []
    assert arch.check_brief("Edit src/screens/VehicleListScreen.tsx", FILES, [], []) == []


def test_brief_check_rejects_a_brief_that_misses_the_developers_choice():
    d = {"id": "d1", "chosen": {"label": "React Query hook"}}
    assert [i["type"] for i in arch.check_brief("nothing", FILES, [T()], [d])] == ["contradiction"]
    assert arch.check_brief("we chose React Query hook", FILES, [T()], [d]) == []


def test_an_unknown_topic_does_not_invalidate_the_brief():
    t = T()
    t["status"] = "unknown"
    assert arch.check_brief("brief", FILES, [t], []) == []


def test_unlabeled_mock_is_flagged():
    t = T()
    t["status"] = "mock_ok"
    assert arch.check_brief("a mock is used", FILES, [t], [])[0]["type"] == "unlabeled_assumption"
    assert arch.check_brief("a mock is used (ASSUMPTION)", FILES, [t], []) == []


def test_a_library_name_glued_to_a_hebrew_prefix_is_still_recognized():
    assert arch.extract_deps("אנחנו משתמשים ב-react-query ו-axios", DEPS) == [d for d in DEPS if d in {"@tanstack/react-query", "axios"}]
