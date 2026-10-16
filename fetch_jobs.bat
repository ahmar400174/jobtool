@echo off
title QA Job Finder
cd /d "%~dp0scripts"
call ..\.venv\Scripts\activate.bat
python fetch_jobs.py --open
pause
