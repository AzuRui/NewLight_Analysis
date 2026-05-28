@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "PAUSE_ON_EXIT=1"
if /I "%~1"=="/nopause" set "PAUSE_ON_EXIT=0"
if /I "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"

echo ========================================
echo Building NewLight_Analysis portable EXE
echo ========================================
echo.

if not exist "DeepCADRT_Model\E_02_Iter_6416.pth" (
  echo Missing DeepCAD-RT model:
  echo   %CD%\DeepCADRT_Model\E_02_Iter_6416.pth
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

echo Patching frozen OpenCV loader paths...
python tools\patch_frozen_cv2.py dist\NewLight_Analysis
if errorlevel 1 (
  echo OpenCV loader patch failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Preparing release folder...
mkdir build_release
xcopy /e /i /y dist\NewLight_Analysis build_release\NewLight_Analysis >nul
copy /y check_backends.bat build_release\NewLight_Analysis\check_backends.bat >nul
copy /y setup_caiman_latest.bat build_release\NewLight_Analysis\setup_caiman_latest.bat >nul

echo Writing release launcher...
> build_release\Run_NewLight_Analysis.bat echo @echo off
>> build_release\Run_NewLight_Analysis.bat echo cd /d "%%~dp0NewLight_Analysis"
>> build_release\Run_NewLight_Analysis.bat echo start "" "NewLight_Analysis.exe"

echo.
echo Build complete:
echo   %CD%\build_release\NewLight_Analysis\NewLight_Analysis.exe
echo.
echo Notes:
echo - NewLight_Worker.exe is bundled under _internal for backend worker tasks.
echo - NeuroSeg3 source/weights, NeuroAlign source, DeepCAD-RT source, and DeepCAD-RT model are bundled.
echo - Run check_backends.bat inside the release folder on target machines.
echo.
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
