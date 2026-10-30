#!/usr/bin/env bash
# One command to try the agent in the browser (macOS / Linux). Creates .venv once; you never activate it yourself.
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "[setup] Creating the virtual environment (first run only)..."; python3 -m venv .venv; }
if ! cmp -s requirements.txt .venv/requirements.installed; then
  echo "[setup] Installing dependencies..."
  .venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
if [ ! -f .env ]; then
  echo "[setup] Get a free key at https://openrouter.ai/keys"
  read -r -p "Paste your OPENROUTER_API_KEY and press Enter: " KEY
  { echo "OPENROUTER_API_KEY=$KEY"; grep -v '^OPENROUTER_API_KEY' .env.example; } > .env
fi
if [ ! -f ui/dist/index.html ] && command -v npm >/dev/null; then (cd ui && npm install --no-audit --no-fund --loglevel=error && npm run build); fi
echo "Starting Readiness Mentor at http://127.0.0.1:8787 (Ctrl+C to stop)"
exec .venv/bin/python -m agent.server --open
