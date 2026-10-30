"""Builds the FastAPI sidecar with PyInstaller and places it where Tauri expects it:  src-tauri/binaries/agent-server-<target-triple>[.exe]
Usage:  python build_sidecar.py        (needs: pip install -r requirements.txt pyinstaller; the UI is built first if ui/dist is missing)"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def host_triple() -> str:
    return re.search(r"host: (\S+)", subprocess.check_output(["rustc", "-vV"], text=True)).group(1)


def main() -> int:
    if not (ROOT / "ui" / "dist" / "index.html").is_file():
        npm = shutil.which("npm")
        if not npm:
            print("[ERROR] ui/dist is missing and npm was not found: run  cd ui && npm install && npm run build")
            return 2
        subprocess.check_call([npm, "install"], cwd=ROOT / "ui")
        subprocess.check_call([npm, "run", "build"], cwd=ROOT / "ui")
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--name", "agent-server", "--console",
           "--add-data", f"ui/dist{sep}ui/dist", "--collect-submodules", "agent", "--collect-submodules", "uvicorn",
           "--collect-all", "langgraph", "--collect-all", "langchain_openai", "--collect-all", "langchain_core", "--collect-all", "langsmith",
           "--collect-all", "tiktoken", "--collect-all", "tiktoken_ext", "sidecar_main.py"]
    subprocess.check_call(cmd, cwd=ROOT)
    exe = ROOT / "dist" / ("agent-server.exe" if os.name == "nt" else "agent-server")
    dest = ROOT / "src-tauri" / "binaries" / f"agent-server-{host_triple()}{'.exe' if os.name == 'nt' else ''}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, dest)
    print(f"[OK] sidecar -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
