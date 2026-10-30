import builtins
import json
import sys

from agent import cli
from conftest import PARKING, Script, checklist, decision, option, topic

sys.path.insert(0, "evals")

TASK = "Add a parking facilities list screen with search"
LIST = "src/screens/VehicleListScreen.tsx"
CHECK = checklist(topic("Existing list screen with search", terms=["list", "search"]))


def test_ask_human_shows_note_guidance_and_returns_raw_input(monkeypatch, capsys):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "src/screens")
    payload = {"type": "text", "kind": "guidance", "id": "t1", "n": 1, "total": 2, "title": "t", "question": "q", "why": "w", "critical": True,
               "category": "placement", "error": "התשובה ריקה.", "note": "הנתיב לא קיים בפרויקט.",
               "guidance": {"why": "כדי לדעת איפה לשים את הקוד", "files": [LIST], "terms": ["list"], "dirs": ["src"], "dependencies": ["axios"]}}
    assert cli.ask_human(payload) == "src/screens"
    out = capsys.readouterr().out
    assert "! התשובה ריקה." in out and "הנתיב לא קיים" in out and LIST in out and "מילות חיפוש: list" in out and "axios" in out


def test_ask_human_choice_marks_recommendation_and_new_dependency(monkeypatch, capsys):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "1")
    opts = [{"id": 1, "label": "A", "description": "", "pros": "p", "cons": "c", "evidence": [LIST], "dependency": None, "new_dependency": False, "recommended": True},
            {"id": 2, "label": "B", "description": "", "pros": "p", "cons": "c", "evidence": [], "dependency": None, "new_dependency": True, "recommended": False}]
    cli.ask_human({"type": "choice", "id": "d1", "n": 1, "total": 1, "title": "t", "question": "q", "options": opts, "error": None})
    out = capsys.readouterr().out
    assert "(מומלץ)" in out and "[NEW DEPENDENCY]" in out and LIST in out


def test_run_task_end_to_end_and_keyboard_interrupt(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    Script(build_checklist=CHECK).install(monkeypatch)
    monkeypatch.setattr(cli, "ask_human", lambda p: LIST if p["type"] == "text" else "n")
    log = []
    cli.run_task(cli.build_graph(), TASK, PARKING, [], log)
    out = capsys.readouterr().out
    assert "[INFO] Entering Node: guardrails" in out and "IMPLEMENTATION PROMPT" in out and "Usage and cost" in out
    assert log[0]["outcome"] == "prompt"

    def boom(p):
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, "ask_human", boom)
    cli.run_task(cli.build_graph(), TASK, PARKING, [], log)
    assert "Cancelled. Nothing was saved." in capsys.readouterr().out and len(log) == 1   # no half-finished entry


def test_cli_blocked_fact_stops_then_resume_continues_with_only_the_mentor_question(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    api = topic("Parking facilities endpoint", "Which REST endpoint returns the facilities?", category="api_dependency", mockable=True, terms=["parking"])
    Script(build_checklist=checklist(api)).install(monkeypatch)
    answers = iter(["לא יודע", "לא יודע", "y"])
    monkeypatch.setattr(cli, "ask_human", lambda p: next(answers))
    cli.run_task(cli.build_graph(), TASK, PARKING, [], [])
    out = capsys.readouterr().out
    assert "לא הופק פרומפט" in out and "--resume" in out and "endpoint" in out
    session_file = next((tmp_path / "briefs").glob("session-*.json"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    seen = []
    monkeypatch.setattr(cli, "ask_human", lambda p: (seen.append(p["kind"]) or "GET /api/v1/facilities") if p["type"] == "text" else "n")
    assert cli.main(["--project", PARKING, "--resume", str(session_file)]) == 0
    out = capsys.readouterr().out
    assert seen == ["mentor"] and "Continuing:" in out and "IMPLEMENTATION PROMPT" in out and "MENTOR-CONFIRMED" in out
    assert json.loads(session_file.read_text(encoding="utf-8"))["topics"][0]["status"] == "mentor_needed"     # the saved session itself is not modified


def test_cli_text_prompts_show_the_note_and_the_guidance(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": "x")
    cli.ask_human({"type": "text", "kind": "guidance", "id": "t1", "n": 1, "total": 1, "title": "T", "question": "Q?", "why": "w", "category": "other",
                   "note": "בטוחים שאין?", "guidance": {"why": "w", "files": ["src/a.ts"], "terms": ["search"], "dirs": ["src"], "dependencies": []}})
    out = capsys.readouterr().out
    assert "בטוחים שאין?" in out and "src/a.ts" in out and "search" in out and "מנטור" not in out.split("בטוחים שאין?")[1]


def test_friendly_error_finds_ssl_cause_behind_generic_connection_error():
    import ssl
    try:
        raise ConnectionError("Connection error.") from ssl.SSLCertVerificationError("self-signed certificate in certificate chain")
    except Exception as e:
        assert "SSL certificate problem" in cli.friendly_error(e)


def test_eval_driver_runs_the_graph_and_reports_deterministic_metrics(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    Script(build_checklist=checklist(topic("Existing list screen with search", terms=["list", "search"])),
           propose_options={"decisions": [decision("Fetching", option("React Query", dep="@tanstack/react-query"), option("axios", dep="axios"))]}).install(monkeypatch)
    import _driver
    state, seconds, cost = _driver.run_auto(TASK, "test/model", PARKING)
    m = _driver.deterministic_metrics(state)
    assert m["outcome"] == "prompt" and m["brief_accepted"] is True and m["invented_paths"] == 0 and m["verified"] == 1 and m["decisions"] == 1


def test_scope_eval_decides_from_the_guardrails_node_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    Script(guardrails=lambda user, n: {"in_scope": "capital" not in user}, build_checklist=CHECK).install(monkeypatch)
    import scope_eval
    graph = scope_eval.build_graph()
    assert scope_eval.refused(graph, "What is the capital of Australia?") is True
    assert scope_eval.refused(graph, "Add an alerts tab to the sensor details screen using apiClient") is False
