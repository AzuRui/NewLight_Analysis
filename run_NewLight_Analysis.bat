@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist "launch.py" (
  echo Source launcher was not found:
  echo   %CD%\launch.py
  pause
  exit /b 1
)

set "RUN_PY=python"
set "RUN_LABEL=active PATH python"
where conda >nul 2>nul
if not errorlevel 1 (
  call conda run -n caiman_latest python -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    set "RUN_PY=call conda run -n caiman_latest python"
    set "RUN_LABEL=conda env caiman_latest"
  )
)

echo Running NewLight_Analysis from source with %RUN_LABEL%...
!RUN_PY! launch.py
if errorlevel 1 (
  pause
  exit /b 1
)

endlocal
