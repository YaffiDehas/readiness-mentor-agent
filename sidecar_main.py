"""Entry point of the packaged desktop sidecar (PyInstaller): the FastAPI server that the Tauri window talks to."""
import sys

from agent.server import main

if __name__ == "__main__":
    sys.exit(main())
