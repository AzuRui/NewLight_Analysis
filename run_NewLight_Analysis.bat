@echo off
setlocal enabledelayedexpansion

set "APP_DIR=%~dp0NewLight_Analysis"
if not exist "%APP_DIR%\NewLight_Analysis.exe" set "APP_DIR=%~dp0build_release\NewLight_Analysis"
if not exist "%APP_DIR%\NewLight_Analysis.exe" set "APP_DIR=%~dp0"

if exist "%APP_DIR%\NewLight_Analysis.exe" (
  pushd "%APP_DIR%" || (
    echo Failed to enter app folder:
    echo   %APP_DIR%
    pause
    exit /b 1
  )
  start "" "%APP_DIR%\NewLight_Analysis.exe"
  popd
  exit /b 0
)

if exist "%~dp0launch.py" (
  set "RUN_PY=python"
  where conda >nul 2>nul
  if not errorlevel 1 (
    call conda run -n caiman_latest python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "RUN_PY=call conda run -n caiman_latest python"
  )
  cd /d "%~dp0"
  !RUN_PY! launch.py
  if errorlevel 1 (
    pause
    exit /b 1
  )
  exit /b 0
)

echo NewLight_Analysis.exe or source launch.py was not found.
echo Looked in:
echo   %~dp0NewLight_Analysis
echo   %~dp0build_release\NewLight_Analysis
echo   %~dp0
echo   %~dp0launch.py
pause
exit /b 1
