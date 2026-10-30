"""Web bridge tests over real HTTP (scripted LLM). They prove the protocol and the security checks, not model quality."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from agent import llm, server
from conftest import PARKING, Script, checklist, decision, option, topic

TASK = "Add a parking facilities list screen with search"
LIST = "src/screens/VehicleListScreen.tsx"
CHECK = checklist(topic("Existing list screen with search", terms=["list", "search"]),
                  topic("Parking facilities API", category="api_dependency", mockable=True, terms=["parking"]))
OPTIONS = {"decisions": [decision("Data fetching", option("React Query hook", evidence=[LIST], dep="@tanstack/react-query"), option("Plain axios", dep="axios"))]}


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-key-123456")
    monkeypatch.setattr(server, "CONFIG_DIR", tmp_path / "home")
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>ui</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("top secret", encoding="utf-8")
    srv = server.make_server(0, PARKING, dist)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()
    srv.server_close()


def install(script, monkeypatch):
    """Install the scripted LLM and record usage like the real client does (the script replaces llm.invoke*)."""
    script.install(monkeypatch)
    for name in ("invoke_json", "invoke"):
        real = getattr(llm, name)
        def wrapped(node, *a, _real=real, **k):
            llm.TRACKER.add(node, "meta-llama/llama-3.3-70b-instruct:free", 1200, 300, 0.1)
            return _real(node, *a, **k)
        monkeypatch.setattr(llm, name, wrapped)


def post(base, path, body, headers=None, raw=None):
    h = {"Content-Type": "application/json", "X-Readiness-UI": "1", **(headers or {})}
    req = urllib.request.Request(base + path, data=raw if raw is not None else json.dumps(body).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return [json.loads(line) for line in r.read().decode("utf-8").splitlines() if line.strip()]


def get(base, path, headers=None):
    req = urllib.request.Request(base + path, headers=headers or {})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, r.read(), r.headers


ANSWERS = {"text": {"t1": LIST, "t2": "אין עדיין API"}, "choice": "המלצה", "save": "n"}


def drive_to_end(base, events, answers=None):
    """Answer every prompt like a careful developer until the run ends. Returns all events."""
    allev, ans = list(events), {**ANSWERS, **(answers or {})}
    for _ in range(40):
        last = allev[-1]
        if last["type"] != "prompt":
            return allev
        p = last["payload"]
        value = ans["text"][p["id"]] if p["type"] == "text" else ans[p["type"]]
        allev += post(base, "/api/resume", {"run_id": last["run_id"], "value": value})
    raise AssertionError("run did not finish")


def test_full_run_streams_nodes_prompts_and_a_final_state(api, monkeypatch):
    install(Script(build_checklist=CHECK, propose_options=OPTIONS), monkeypatch)
    ev = drive_to_end(api, post(api, "/api/run", {"task": TASK}))
    kinds = [e["type"] for e in ev]
    assert kinds[0] == "node" and ev[0]["name"] == "guardrails" and kinds[-1] == "done" and kinds.count("prompt") == 4
    done = ev[-1]
    assert done["state"]["outcome"] == "prompt" and "## B. Architecture findings" in done["state"]["final_prompt"]
    assert done["usage"]["total"]["calls"] >= 1 and done["usage"]["by_node"] and "OPENROUTER" not in json.dumps(done)
    assert {"text", "choice", "save"} == {e["payload"]["type"] for e in ev if e["type"] == "prompt"}


def test_an_empty_answer_reasks_the_same_question_with_an_error(api, monkeypatch):
    install(Script(build_checklist=CHECK), monkeypatch)
    first = [e for e in post(api, "/api/run", {"task": TASK}) if e["type"] == "prompt"][-1]
    again = [e for e in post(api, "/api/resume", {"run_id": first["run_id"], "value": "  "}) if e["type"] == "prompt"][-1]
    assert again["payload"]["id"] == first["payload"]["id"] and again["payload"]["error"] and not first["payload"]["error"]


def test_i_dont_know_returns_guidance_and_the_run_still_ends_with_a_prompt(api, monkeypatch):
    install(Script(build_checklist=checklist(topic("Existing list screen with search", terms=["list", "search"]))), monkeypatch)
    ev = drive_to_end(api, post(api, "/api/run", {"task": TASK}), {"text": {"t1": "לא יודע"}})
    shown = [e["payload"] for e in ev if e["type"] == "prompt" and e["payload"]["type"] == "text"]
    assert shown[1]["kind"] == "guidance" and shown[1]["guidance"]["files"] and shown[1]["note"]
    st = ev[-1]["state"]
    assert st["outcome"] == "prompt" and st["final_prompt"] and st["topics"][0]["status"] == "unknown"


def test_a_missing_endpoint_ends_with_the_mentor_questions_and_a_saved_session_resumes_with_only_that_question(api, monkeypatch):
    API = topic("Parking facilities endpoint", "Which REST endpoint returns the facilities?", category="api_dependency", mockable=True, terms=["parking"])
    install(Script(build_checklist=checklist(API)), monkeypatch)
    first = drive_to_end(api, post(api, "/api/run", {"task": TASK}), {"text": {"t1": "לא יודע"}, "save": "n"})[-1]["state"]
    assert first["outcome"] == "needs_mentor" and "final_prompt" not in first and first["blocked"][0]["id"] == "t1" and "endpoint" in first["blocked"][0]["question"]
    session = first["session_out"]
    install(Script(), monkeypatch)
    ev = post(api, "/api/run", {"task": TASK, "session": session})
    assert [e for e in ev if e["type"] == "prompt"][-1]["payload"]["kind"] == "mentor"
    done = drive_to_end(api, ev, {"text": {"t1": "GET /api/v1/facilities"}})[-1]["state"]
    assert done["outcome"] == "prompt" and done["topics"][0]["status"] == "mentor_answered"
    assert "Invalid session file" in post(api, "/api/run", {"task": TASK, "session": {"x": 1}})[0]["message"]


def test_out_of_scope_ends_immediately(api, monkeypatch):
    install(Script(guardrails={"in_scope": False}), monkeypatch)
    ev = post(api, "/api/run", {"task": "what is the capital of France"})
    assert ev[-1]["type"] == "done" and ev[-1]["state"]["in_scope"] is False and ev[-1]["state"]["final_message"]


@pytest.mark.parametrize("body,fragment", [({"task": ""}, "Describe the task"), ({"task": "x" * 5000}, "Describe the task"),
                                           ({"task": TASK, "project": "/definitely/not/here"}, "Project folder not found")])
def test_invalid_start_requests_are_reported_as_error_events(api, body, fragment):
    ev = post(api, "/api/run", body)
    assert ev == [{"type": "error", "message": ev[0]["message"]}] and fragment in ev[0]["message"]


def test_unknown_run_and_bad_body(api):
    assert "Unknown or finished run" in post(api, "/api/resume", {"run_id": "nope", "value": "A"})[0]["message"]
    with pytest.raises(urllib.error.HTTPError) as e:
        post(api, "/api/run", None, raw=b"not json")
    assert e.value.code == 400


def test_a_failing_model_becomes_an_error_event_with_a_hint(api, monkeypatch):
    def down(user, n):
        raise ConnectionError("Connection error.")
    install(Script(guardrails=down), monkeypatch)
    ev = post(api, "/api/run", {"task": TASK})
    assert ev[-1]["type"] == "error" and "Network problem" in ev[-1]["message"]


# ------------------------------------------------------------------ security
@pytest.mark.parametrize("headers", [{"X-Readiness-UI": "0"}, {"Host": "evil.example:80"}, {"Origin": "http://evil.example"},
                                     {"Host": "attacker.test"}], ids=["no-ui-header", "foreign-host", "foreign-origin", "rebinding-host"])
def test_untrusted_posts_are_forbidden(api, headers):
    with pytest.raises(urllib.error.HTTPError) as e:
        post(api, "/api/run", {"task": TASK}, headers=headers)
    assert e.value.code == 403


def test_post_without_the_custom_header_is_forbidden(api):
    req = urllib.request.Request(api + "/api/run", data=json.dumps({"task": TASK}).encode(), headers={"Content-Type": "text/plain"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=10)
    assert e.value.code == 403


def test_config_never_exposes_keys(api, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret-value")
    monkeypatch.setenv("LANGSMITH_API_KEY", "ls-secret-value")
    _, body, _ = get(api, "/api/config")
    text = body.decode()
    cfg = json.loads(text)
    assert "secret" not in text and cfg["model"]
    names = {x["name"] for x in cfg["samples"]}
    assert {"parking_app", "sample_project"} <= names and all(__import__("pathlib").Path(x["path"]).is_dir() for x in cfg["samples"])


# ------------------------------------------------------------------ static files
def test_static_files_and_spa_fallback(api):
    assert get(api, "/")[1].startswith(b"<!doctype html>")
    assert get(api, "/assets/app.js")[1] == b"console.log(1)" and get(api, "/assets/app.js")[2]["Content-Type"].startswith("text/javascript")
    assert get(api, "/some/app/route")[1].startswith(b"<!doctype html>")


@pytest.mark.parametrize("path", ["/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"])
def test_path_traversal_is_not_served(api, path):
    try:
        status, body, _ = get(api, path)
        assert b"top secret" not in body
    except urllib.error.HTTPError as e:
        assert e.code in {400, 403, 404}


def test_missing_asset_is_404_not_the_app_shell(api):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(api, "/assets/missing.js")
    assert e.value.code == 404


# ---------------------------------------- the fields the React UI reads must really be sent by the server (UI <-> bridge contract)
UI_FIELDS = {
    "text": {"type", "kind", "id", "n", "total", "title", "question", "why", "category", "note", "guidance", "error"},
    "choice": {"type", "id", "n", "total", "title", "question", "options", "error"},
    "save": {"type", "kind", "path", "error"},
}
OPTION_FIELDS = {"id", "label", "description", "pros", "cons", "evidence", "dependency", "new_dependency", "recommended"}
GUIDANCE_FIELDS = {"why", "files", "terms", "dirs", "dependencies"}
DONE_FIELDS = {"outcome", "topics", "blocked", "decisions", "requirements", "final_prompt", "final_message", "eval_issues", "warnings"}
TOPIC_FIELDS = {"id", "title", "question", "why", "category", "status", "answer", "paths", "deps", "notes", "candidates", "blocker", "mentor", "mentor_question"}


def test_server_payloads_contain_every_field_the_ui_reads(api, monkeypatch):
    install(Script(build_checklist=CHECK, propose_options=OPTIONS), monkeypatch)
    ev = post(api, "/api/run", {"task": TASK})
    seen, sent_idk = {}, False
    for _ in range(40):
        last = ev[-1]
        if last["type"] != "prompt":
            break
        p = last["payload"]
        seen.setdefault(p["type"], p)
        if p.get("guidance"):
            seen["guidance"] = p["guidance"]
        if p["type"] == "text":
            value = "לא יודע" if (p["id"] == "t1" and not sent_idk) else ANSWERS["text"][p["id"]]
            sent_idk = sent_idk or p["id"] == "t1"
        else:
            value = ANSWERS[p["type"]]
        ev += post(api, "/api/resume", {"run_id": last["run_id"], "value": value})
    assert ev[-1]["type"] == "done"
    for kind, fields in UI_FIELDS.items():
        assert kind in seen, f"the run never produced a {kind} prompt"
        assert fields <= set(seen[kind]), f"{kind}: server is missing {fields - set(seen[kind])}"
    assert OPTION_FIELDS <= set(seen["choice"]["options"][0]) and GUIDANCE_FIELDS <= set(seen["guidance"])
    st = ev[-1]["state"]
    assert DONE_FIELDS <= set(st), DONE_FIELDS - set(st)
    assert TOPIC_FIELDS <= set(st["topics"][0]) and {"id", "label", "custom"} <= set(st["decisions"][0]["chosen"])
    assert {"model", "by_node", "total"} <= set(ev[-1]["usage"]) and {"calls", "input_tokens", "output_tokens", "actual_usd", "theoretical_usd"} <= set(ev[-1]["usage"]["total"])


def test_js_mime_ignores_os_registry(api, monkeypatch):
    """Windows registry may map .js to text/plain; the browser then blocks the module script and the page stays blank."""
    import mimetypes
    monkeypatch.setattr(mimetypes, "guess_type", lambda name, strict=True: ("text/plain", None))
    assert get(api, "/assets/app.js")[2]["Content-Type"].startswith("text/javascript")


# ------------------------------------------------- desktop sidecar: key entry
def test_without_a_key_a_run_says_so_and_config_reports_has_key_false(api, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert json.loads(get(api, "/api/config")[1])["has_key"] is False
    ev = post(api, "/api/run", {"task": TASK})
    assert ev[-1]["type"] == "error" and "OPENROUTER_API_KEY" in ev[-1]["message"]


def test_saving_the_key_enables_runs_stores_it_privately_and_never_echoes_it(api, monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    r = post_json(api, "/api/key", {"key": "sk-or-v1-fake-key-0001"})
    assert r == {"ok": True}
    assert json.loads(get(api, "/api/config")[1])["has_key"] is True and "fake-key-0001" not in get(api, "/api/config")[1].decode()
    env = (tmp_path / "home" / ".env").read_text(encoding="utf-8")
    assert env.strip() == "OPENROUTER_API_KEY=sk-or-v1-fake-key-0001"
    assert "fake-key-0001" not in (tmp_path / "dist" / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("key", ["", "short", "has space inside-key-123", 123, None, "x" * 400])
def test_an_implausible_key_is_rejected_and_not_saved(api, monkeypatch, tmp_path, key):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(urllib.error.HTTPError) as e:
        post_json(api, "/api/key", {"key": key})
    assert e.value.code == 400 and not (tmp_path / "home" / ".env").exists()


def test_the_key_endpoint_is_protected_like_the_others(api, tmp_path):
    for headers in ({"X-Readiness-UI": ""}, {"Origin": "http://evil.example"}, {"Host": "evil.example"}):
        with pytest.raises(urllib.error.HTTPError) as e:
            post_json(api, "/api/key", {"key": "sk-or-v1-fake-key-0001"}, headers)
        assert e.value.code == 403
    assert not (tmp_path / "home" / ".env").exists()


def post_json(base, path, body, headers=None):
    h = {"Content-Type": "application/json", "X-Readiness-UI": "1", **(headers or {})}
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())
