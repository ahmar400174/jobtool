@echo off
title QA Job Finder — Setup
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
echo.
echo  Setup complete. Double-click start.bat to open Job Finder.
pause
