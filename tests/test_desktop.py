"""Track B packaging: the pieces must agree with each other (names, entry points, workflow). The real build/run of the Tauri shell is done by hand / in CI."""
import json
import os
import sys
from pathlib import Path

from conftest import ROOT
from agent import server


def test_tauri_config_points_at_the_sidecar_that_build_sidecar_produces():
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert conf["bundle"]["externalBin"] == ["binaries/agent-server"] and conf["app"]["windows"] == []          # the window is created by main.rs once the sidecar answers
    assert '"--name", "agent-server"' in (ROOT / "build_sidecar.py").read_text(encoding="utf-8")
    assert 'sidecar("agent-server")' in (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
    for icon in conf["bundle"]["icon"]:
        assert (ROOT / "src-tauri" / icon).is_file(), icon


def test_the_sidecar_entry_point_runs_the_fastapi_server_and_the_shell_passes_a_free_port():
    assert "from agent.server import main" in (ROOT / "sidecar_main.py").read_text(encoding="utf-8")
    rs = (ROOT / "src-tauri" / "src" / "main.rs").read_text(encoding="utf-8")
    assert '"--port"' in rs and "free_port()" in rs and "child.kill()" in rs                                       # a free port, and the sidecar stops with the app


def test_the_release_workflow_builds_both_the_cli_exe_and_the_desktop_installer():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "dist\\agent.exe" in wf and "python build_sidecar.py" in wf and "cargo tauri build" in wf and "bundle/nsis" in wf


def test_requirements_include_the_sidecar_stack():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "fastapi" in req and "uvicorn" in req


def test_a_frozen_sidecar_works_in_a_writable_folder_not_next_to_itself(monkeypatch, tmp_path):
    """An installed app may live in a read-only folder: briefs/ and sessions go to ~/.readiness-mentor/work."""
    monkeypatch.setattr(server, "CONFIG_DIR", tmp_path / "home")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.chdir(tmp_path)
    started = {}

    class Stub:
        server_address = ("127.0.0.1", 1)

        def serve_forever(self):
            started["cwd"] = os.getcwd()
            raise KeyboardInterrupt

    monkeypatch.setattr(server, "make_server", lambda port, project: Stub())
    assert server.main(["--port", "0"]) == 0
    assert Path(started["cwd"]) == (tmp_path / "home" / "work").resolve()
