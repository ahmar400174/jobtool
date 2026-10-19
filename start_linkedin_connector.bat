@echo off
title Job Finder - LinkedIn connector
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first, then try again.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing the web connector dependency...
    ".venv\Scripts\python.exe" -m pip install "Flask>=3.1.0,<4"
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" scripts\linkedin_connector.py
pause
