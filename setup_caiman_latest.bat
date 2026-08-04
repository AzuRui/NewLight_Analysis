@echo off
setlocal
cd /d "%~dp0"
echo setup_caiman_latest.bat is retained for compatibility.
echo NewLight now uses the isolated newlight_caiman environment.
call setup_newlight_caiman.bat
exit /b %errorlevel%
