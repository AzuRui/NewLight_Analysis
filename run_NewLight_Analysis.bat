@echo off
setlocal
cd /d "%~dp0"
python launch.py
if errorlevel 1 pause
endlocal
