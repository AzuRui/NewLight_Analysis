@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PAUSE_ON_EXIT=1"
if /I "%~1"=="/nopause" set "PAUSE_ON_EXIT=0"
if /I "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"

echo ========================================
echo NewLight_Analysis full release build
echo ========================================
echo.

set "MODEL=DeepCADRT_Model\E_02_Iter_6416.pth"
if not exist "%MODEL%" (
  echo Missing DeepCAD-RT model:
  echo   %CD%\%MODEL%
  echo Put the trained .pth file there before building.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo PyInstaller is not installed in this Python.
  echo Installing PyInstaller...
  python -m pip install pyinstaller
  if errorlevel 1 (
    echo Failed to install PyInstaller.
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
  )
)

echo Cleaning previous build folders...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist build_release rmdir /s /q build_release

echo Running PyInstaller...
python -m PyInstaller --noconfirm NewLight_Analysis.spec
if errorlevel 1 (
  echo PyInstaller build failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Preparing portable release folder...
mkdir build_release
xcopy /e /i /y dist\NewLight_Analysis build_release\NewLight_Analysis >nul
copy /y check_backends.bat build_release\NewLight_Analysis\check_backends.bat >nul
copy /y setup_caiman_latest.bat build_release\NewLight_Analysis\setup_caiman_latest.bat >nul

> build_release\Run_NewLight_Analysis.bat echo @echo off
>> build_release\Run_NewLight_Analysis.bat echo cd /d "%%~dp0NewLight_Analysis"
>> build_release\Run_NewLight_Analysis.bat echo start "" "NewLight_Analysis.exe"

set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 set "ISCC=ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"

if defined ISCC (
  echo Building installer with Inno Setup...
  "%ISCC%" NewLight_Analysis_setup.iss
  if errorlevel 1 (
    echo Inno Setup build failed.
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
  )
) else (
  echo Inno Setup compiler was not found. Portable release is ready; installer was skipped.
)

echo.
echo Full release build finished.
echo Portable EXE:
echo   %CD%\build_release\NewLight_Analysis\NewLight_Analysis.exe
echo.
echo Notes:
echo - DeepCAD-RT model is bundled from %MODEL%.
echo - NeuroSeg3, CaImAn, and DeepCAD-RT code/env remain external conda backends.
echo - Run check_backends.bat in the release folder on target machines.
echo.
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
