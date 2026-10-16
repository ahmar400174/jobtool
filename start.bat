@echo off
title Job Finder
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  Virtual environment not found.
    echo  Run setup.bat first, then try again.
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0scripts"
call ..\.venv\Scripts\activate.bat
pythonw gui.py 2>nul
if errorlevel 1 (
    REM Fallback if pythonw is unavailable — keep a console for errors
    python gui.py
    if errorlevel 1 pause
)
