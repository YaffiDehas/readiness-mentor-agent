"""Local FastAPI sidecar of the desktop app (also what start_ui.bat runs). Serves ui/dist and streams the LangGraph run to the UI as NDJSON.

POST /api/run     {task, project?, attachments?, session?}  -> NDJSON events: node | prompt | done | error
POST /api/resume  {run_id, value}                 -> same events (value = the raw answer string, validated by the graph)
POST /api/key     {key}                           -> saves the OpenRouter key for this user (desktop first run); never echoed back
GET  /api/config  -> model / tracing / limits / has_key (never any key)

Security: bound to 127.0.0.1; POST requires the X-Readiness-UI header (cross-origin pages cannot send it without a CORS preflight, which is never
answered); Host and Origin must be this server. This blocks drive-by requests and DNS rebinding against a local tool that reads local folders.
"""
import argparse
import json
import mimetypes
import os
import socket
import sys
import threading
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

import uvicorn
from dotenv import find_dotenv, load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from langgraph.types import Command

from agent import llm, nodes
from agent.cli import friendly_error
from agent.graph import build_graph

# Fixed types: on Windows mimetypes reads the registry, where .js is often "text/plain" and browsers then refuse the module script (blank page).
MIME = {".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml",
        ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".map": "application/json"}
DIST = Path(__file__).resolve().parent.parent / "ui" / "dist"
ROOT = Path(__file__).resolve().parent.parent
MAX_BODY = 2_000_000
CONFIG_DIR = Path(os.getenv("READINESS_HOME") or Path.home() / ".readiness-mentor")     # per-user settings of the desktop app (the exe has no project folder)
PUBLIC_KEYS = ("in_scope", "cancelled", "outcome", "requirements", "topics", "blocked", "decisions", "final_prompt", "final_message", "saved_path",
               "session_out", "warnings", "eval_issues", "brief_accepted", "retrieval_log")
RUN_LOCK = threading.Lock()  # llm.TRACKER is process-wide: one streaming request at a time


def samples() -> list[dict]:
    """Bundled example projects the developer can pick in the UI to try the agent without a project of their own."""
    out = [{"name": d.name, "path": str(d)} for d in sorted((ROOT / "evals" / "fixtures").glob("*")) if d.is_dir()]
    sp = ROOT / "evals" / "sample_project"
    return out + ([{"name": sp.name, "path": str(sp)}] if sp.is_dir() else [])


def usage() -> dict:
    return {"model": llm.current_model(), "by_node": llm.TRACKER.by_node(), "total": llm.TRACKER.total()}


def public_state(values: dict) -> dict:
    return {k: values[k] for k in PUBLIC_KEYS if k in values}


class Runs:
    """run_id -> LangGraph thread config. One compiled graph (in-memory checkpointer) per server."""

    def __init__(self):
        self.graph = build_graph()
        self.cfgs: dict[str, dict] = {}

    def drive(self, run_id: str, graph_input):
        cfg = self.cfgs[run_id]
        try:
            last = None
            for _mode, chunk in self.graph.stream(graph_input, cfg, stream_mode=["debug"]):
                if chunk["type"] == "task" and chunk["payload"]["name"] != last:
                    last = chunk["payload"]["name"]
                    yield {"type": "node", "name": last}
            snap = self.graph.get_state(cfg)
            if snap.next:
                yield {"type": "prompt", "run_id": run_id, "payload": snap.tasks[0].interrupts[0].value, "usage": usage()}
            else:
                self.cfgs.pop(run_id, None)
                yield {"type": "done", "state": public_state(snap.values), "usage": usage()}
        except Exception as e:  # surfaced to the UI with the same hints as the CLI
            yield {"type": "error", "message": friendly_error(e)}

    def start(self, body: dict, default_project: str):
        task = body.get("task")
        if not isinstance(task, str) or not task.strip() or len(task) > 4000:
            return None, "Describe the task (1-4000 characters)."
        raw_project = str(body.get("project") or default_project or "").strip()
        project = Path(raw_project).expanduser() if raw_project else None
        if project is not None and not project.is_dir():
            return None, f"Project folder not found: {project}"
        atts = []
        for a in (body.get("attachments") or [])[:5]:
            if isinstance(a, dict) and isinstance(a.get("name"), str) and isinstance(a.get("text"), str):
                atts.append({"name": a["name"][:120], "text": a["text"][:20_000]})
        session = body.get("session")
        if session is not None and not (isinstance(session, dict) and isinstance(session.get("topics"), list)):
            return None, "Invalid session file."
        run_id = uuid.uuid4().hex
        self.cfgs[run_id] = {"configurable": {"thread_id": run_id}}
        llm.TRACKER.reset()
        start = {"task": task, "project_root": str(project.resolve()) if project else "", "attachments": atts, "run_id": datetime.now().strftime("%Y%m%d-%H%M%S")}
        if session:
            start["session"] = session
        return (run_id, start), None

    def resume(self, body: dict):
        run_id, value = body.get("run_id"), body.get("value")
        if run_id not in self.cfgs or not isinstance(value, str):
            return None, "Unknown or finished run - start a new task."
        return (run_id, Command(resume=value)), None


def user_env_path() -> Path:
    return CONFIG_DIR / ".env"


def load_env() -> None:
    """Settings: a .env next to where the app is started, then the per-user one (where the desktop app saves the key)."""
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(user_env_path())


def save_key(key: str) -> None:
    """Persist the OpenRouter key for this user only (never inside a project folder, never returned by any endpoint)."""
    path = user_env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [ln for ln in (path.read_text(encoding="utf-8").splitlines() if path.exists() else []) if not ln.startswith("OPENROUTER_API_KEY=")]
    path.write_text("\n".join(lines + [f"OPENROUTER_API_KEY={key}"]) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    os.environ["OPENROUTER_API_KEY"] = key


def create_app(project: str = "", dist: Path = DIST, port: list | None = None) -> FastAPI:
    """port: one-element list holding the real port (known only after binding); the Host/Origin check needs it."""
    runs, ports = Runs(), port if port is not None else [0]
    app = FastAPI(title="Readiness Mentor Agent", docs_url=None, redoc_url=None, openapi_url=None)

    def err(code: int, message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=code, headers={"Cache-Control": "no-store"})

    def trusted(request: Request) -> bool:
        ok_hosts = {f"127.0.0.1:{ports[0]}", f"localhost:{ports[0]}"}
        origin = request.headers.get("origin")
        return request.headers.get("host") in ok_hosts and (origin is None or origin in {f"http://{h}" for h in ok_hosts})

    def stream(started, error):
        def events():
            if error:
                yield {"type": "error", "message": error}
            elif not RUN_LOCK.acquire(blocking=False):
                yield {"type": "error", "message": "Another run is still streaming - wait for it to finish."}
            else:
                try:
                    yield from runs.drive(*started)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # the window was closed mid-run; the graph stays at its last checkpoint
                finally:
                    RUN_LOCK.release()
        gen = events()
        return StreamingResponse((json.dumps(ev, ensure_ascii=False, default=str) + "\n" for ev in gen), media_type="application/x-ndjson; charset=utf-8",
                                 headers={"Cache-Control": "no-store"})

    async def body_of(request: Request):
        raw = await request.body()
        try:
            if not 0 < len(raw) <= MAX_BODY:
                raise ValueError("bad length")
            body = json.loads(raw.decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
            return body, None
        except (ValueError, UnicodeDecodeError):
            return None, err(400, "invalid JSON body")

    def guard(request: Request):
        if not trusted(request) or request.headers.get("x-readiness-ui") != "1":
            return err(403, "forbidden: request not from the local UI")
        return None

    @app.get("/api/config")
    def config(request: Request):
        if not trusted(request):
            return err(403, "forbidden")
        return JSONResponse({"model": llm.current_model(), "mentor": nodes.MENTOR, "has_key": bool(os.getenv("OPENROUTER_API_KEY")),
                             "langsmith": os.getenv("LANGSMITH_TRACING", "").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY")),
                             "samples": samples(), "project": str(Path(project).resolve()) if project else ""}, headers={"Cache-Control": "no-store"})

    @app.post("/api/run")
    async def run(request: Request):
        if (denied := guard(request)) is not None:
            return denied
        body, bad = await body_of(request)
        if bad is not None:
            return bad
        if not os.getenv("OPENROUTER_API_KEY"):
            return stream(None, "OPENROUTER_API_KEY is not set - enter your OpenRouter key in the app first.")
        started, error = runs.start(body, project)
        return stream(started, error)

    @app.post("/api/resume")
    async def resume(request: Request):
        if (denied := guard(request)) is not None:
            return denied
        body, bad = await body_of(request)
        if bad is not None:
            return bad
        started, error = runs.resume(body)
        return stream(started, error)

    @app.post("/api/key")
    async def key(request: Request):
        if (denied := guard(request)) is not None:
            return denied
        body, bad = await body_of(request)
        if bad is not None:
            return bad
        k = body.get("key")
        if not isinstance(k, str) or not 8 <= len(k.strip()) <= 300 or any(c.isspace() for c in k.strip()):
            return err(400, "That does not look like an OpenRouter key.")
        save_key(k.strip())
        return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})

    @app.api_route("/{path:path}", methods=["GET", "HEAD"])
    def static(path: str):
        if path.startswith("api/"):
            return err(404, "not found")
        if not dist.is_dir():
            return err(404, "UI not built. Run: cd ui && npm install && npm run build")
        target = (dist / path).resolve()
        if dist.resolve() not in target.parents and target != dist.resolve():
            return err(403, "forbidden")
        if not target.is_file():
            if "." in Path(path).name:  # a missing asset is a 404, only app routes fall back to the SPA shell
                return err(404, "not found")
            target = dist / "index.html"
        ctype = MIME.get(target.suffix.lower()) or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return Response(target.read_bytes(), media_type=ctype + ("; charset=utf-8" if target.suffix in {".html", ".js", ".css"} else ""), headers={"Cache-Control": "no-cache"})

    return app


class LocalServer:
    """uvicorn on 127.0.0.1 with the same small surface the tests and main() use (serve_forever / shutdown / server_close / server_address)."""

    def __init__(self, port: int, project: str, dist: Path):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(64)
        self.server_address = self.sock.getsockname()
        self._started, self._stopped = False, threading.Event()
        self.uv = uvicorn.Server(uvicorn.Config(create_app(project, dist, [self.server_address[1]]), log_level="warning", access_log=False, lifespan="off"))

    def serve_forever(self):
        self._started = True
        try:
            self.uv.run(sockets=[self.sock])
        finally:
            self._stopped.set()

    def shutdown(self):
        self.uv.should_exit = True
        if self._started:                                   # the socket may be closed only after uvicorn has finished with it
            self._stopped.wait(10)

    def server_close(self):
        self.sock.close()


def make_server(port: int = 8787, project: str = "", dist: Path = DIST) -> LocalServer:
    return LocalServer(port, project, dist)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Readiness Mentor Agent - local web UI / desktop sidecar")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--project", default="", help="default project folder shown in the UI (empty = no project)")
    ap.add_argument("--model", help="OpenRouter model id (overrides OPENROUTER_MODEL)")
    ap.add_argument("--open", action="store_true", help="open the browser")
    ap.add_argument("--workdir", help="folder where briefs/ and session files are written (default: the current folder; the packaged desktop app uses ~/.readiness-mentor/work)")
    args = ap.parse_args(argv)
    workdir = args.workdir or (str(CONFIG_DIR / "work") if getattr(sys, "frozen", False) else None)     # an installed app may not write next to itself
    if workdir:
        Path(workdir).mkdir(parents=True, exist_ok=True)
        os.chdir(workdir)
    load_env()
    if args.model:
        llm.CONFIG["model"] = args.model
    try:
        srv = make_server(args.port, args.project)
    except OSError as e:
        print(f"[ERROR] cannot listen on 127.0.0.1:{args.port}: {e}")
        return 2
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"Readiness Mentor Agent UI: {url}   (model: {llm.current_model()})" + ("" if DIST.is_dir() else "\n[WARN] ui/dist not found - run: cd ui && npm install && npm run build"), flush=True)
    if not os.getenv("OPENROUTER_API_KEY"):
        print("[WARN] OPENROUTER_API_KEY is not set - the UI will ask for it.", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    return 0


if __name__ == "__main__":
    sys.exit(main())
