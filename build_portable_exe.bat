@echo off
setlocal
cd /d "%~dp0"

set "PAUSE_ON_EXIT=1"
if /I "%~1"=="/nopause" set "PAUSE_ON_EXIT=0"
if /I "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"

echo ========================================
echo Prepare environment and build portable EXE
echo ========================================
echo.

call setup_build_environment.bat /nopause
if errorlevel 1 (
  echo Environment setup failed. Build cancelled.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

call build_exe.bat /nopause
if errorlevel 1 (
  echo Portable EXE build failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo.
echo Portable build complete:
echo   %CD%\dist\NewLight_Analysis\NewLight_Analysis.exe
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
