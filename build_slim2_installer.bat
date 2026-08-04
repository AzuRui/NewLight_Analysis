@echo off
setlocal
cd /d "%~dp0"

set "PAUSE_ON_EXIT=1"
if /I "%~1"=="/nopause" set "PAUSE_ON_EXIT=0"
if /I "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"

echo ========================================
echo Build NewLight_Analysis slim2 installer
echo ========================================
echo.

set "SOURCE=dist_slim2_20260804\NewLight_Analysis"
if not exist "%SOURCE%\NewLight_Analysis.exe" (
  echo Slim2 package was not found:
  echo   %CD%\%SOURCE%
  echo Build it with the slim PyInstaller spec first.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)
if not exist "%SOURCE%\_internal\NewLight_Worker.exe" (
  echo Slim2 worker was not found under _internal.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo Inno Setup 6 ISCC.exe was not found.
  echo Install Inno Setup 6, then run this script again.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

if not exist Output mkdir Output
echo Compiling optimized installer...
"%ISCC%" NewLight_Analysis_slim2_setup.iss
if errorlevel 1 (
  echo Inno Setup compilation failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo.
echo Installer created:
echo   %CD%\Output\NewLight_Analysis_slim2_setup.exe
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
