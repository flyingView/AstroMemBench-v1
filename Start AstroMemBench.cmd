@echo off
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Create the environment and install AstroMemBench first:
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -e .
  echo Then open this file again. See docs\installation.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "scripts\start_webui.py" %*
if errorlevel 1 pause
