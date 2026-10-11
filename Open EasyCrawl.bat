@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
    echo EasyCrawl's Python environment is missing. Set up .venv first.
    pause
    exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m crawl.ui %*
