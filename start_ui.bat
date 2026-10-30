@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Readiness Mentor

REM ---- 1. Python (once): a private virtual environment inside this folder. You never activate it yourself.
if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating the virtual environment ^(first run only^)...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Python 3.10+ was not found. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^) and run this file again.
    pause & exit /b 1
  )
)

REM ---- 2. Dependencies: installed on the first run, and again only when requirements.txt changes.
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo [setup] Installing dependencies ^(first run, or requirements.txt changed^)...
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
  if errorlevel 1 ( echo [ERROR] pip install failed - check your internet connection. & pause & exit /b 1 )
  copy /y requirements.txt .venv\requirements.installed >nul
)

REM ---- 3. API key (once): saved to .env next to this file.
if not exist ".env" (
  echo.
  echo [setup] Get a free key at https://openrouter.ai/keys
  set /p KEY="Paste your OPENROUTER_API_KEY and press Enter: "
  > .env echo OPENROUTER_API_KEY=%KEY%
  findstr /v /b "OPENROUTER_API_KEY" .env.example >> .env
)

REM ---- 4. The UI is pre-built in ui\dist. Rebuild it only if it is missing and Node.js is installed.
if not exist "ui\dist\index.html" (
  where npm >nul 2>&1 && ( echo [setup] Building the UI... & pushd ui & call npm install --no-audit --no-fund --loglevel=error & call npm run build & popd ) || echo [WARN] ui\dist is missing and Node.js was not found - the page will not load.
)

echo.
echo Starting Readiness Mentor at http://127.0.0.1:8787  ^(close this window to stop^)
".venv\Scripts\python.exe" -m agent.server --open
pause
