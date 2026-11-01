@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import bs4" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
if not exist config.json (
  .venv\Scripts\python.exe monitor.py --setup
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe monitor.py
:failed
pause
