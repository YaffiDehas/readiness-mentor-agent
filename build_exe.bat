@echo off
REM Builds a standalone console agent.exe (Windows). Output: dist\agent.exe
pip install -r requirements.txt pyinstaller
pyinstaller --onefile --name agent --console ^
  --collect-submodules agent ^
  --collect-all langgraph --collect-all langchain_openai --collect-all langchain_core ^
  --collect-all langsmith --collect-all tiktoken --collect-all tiktoken_ext ^
  main.py
echo.
echo Done: dist\agent.exe  (put a .env next to it, or run it from the folder that has one)
