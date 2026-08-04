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

set "BUILD_PY=python"
set "BUILD_PY_LABEL=active PATH python"
where conda >nul 2>nul
if not errorlevel 1 (
  call conda run -n caiman_latest python -c "import sys" >nul 2>nul
  if not errorlevel 1 (
    set "BUILD_PY=call conda run -n caiman_latest python"
    set "BUILD_PY_LABEL=conda env caiman_latest (CPU core, no Torch/CUDA)"
  )
)

echo Build Python: %BUILD_PY_LABEL%
%BUILD_PY% -c "import sys; print(sys.executable); print(sys.version)"
if errorlevel 1 (
  echo caiman_latest was not found. Run setup_build_environment.bat first.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

set "NEWLIGHT_BUILD_MODE=cpu"

if not exist "CaImAn_Resources" (
  echo Missing bundled CaImAn resources:
  echo   %CD%\CaImAn_Resources
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

%BUILD_PY% -c "import pkg_resources" >nul 2>nul
if errorlevel 1 (
  echo Installing setuptools<81 for PyInstaller pkg_resources compatibility...
  %BUILD_PY% -m pip install "setuptools<81"
  if errorlevel 1 (
    echo Failed to install compatible setuptools.
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
  )
)

%BUILD_PY% -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo PyInstaller is not installed in this Python.
  echo Installing PyInstaller...
  %BUILD_PY% -m pip install pyinstaller
  if errorlevel 1 (
    echo Failed to install PyInstaller.
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
  )
)

%BUILD_PY% -c "import numpy, cv2, scipy, skimage, pandas, tifffile, matplotlib, caiman, igraph, leidenalg" >nul 2>nul
if errorlevel 1 (
  echo The selected Python is missing NewLight_Analysis build dependencies.
  echo Please build from the caiman_latest environment or run setup_build_environment.bat.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Cleaning previous build folders...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Running PyInstaller...
%BUILD_PY% -m PyInstaller --noconfirm NewLight_Analysis.spec
if errorlevel 1 (
  echo PyInstaller build failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Patching frozen OpenCV loader paths...
%BUILD_PY% tools\patch_frozen_cv2.py dist\NewLight_Analysis
if errorlevel 1 (
  echo OpenCV loader patch failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Preparing dist release files...
copy /y check_backends.bat dist\NewLight_Analysis\check_backends.bat >nul
if exist "docs\NewLight_Analysis_User_Manual.md" (
  copy /y "docs\NewLight_Analysis_User_Manual.md" "dist\NewLight_Analysis\NewLight_Analysis_User_Manual.md" >nul
)
if exist "docs\NewLight_Analysis_User_Manual.docx" (
  copy /y "docs\NewLight_Analysis_User_Manual.docx" "dist\NewLight_Analysis\NewLight_Analysis_User_Manual.docx" >nul
)
if exist "docs\NewLight_Analysis_User_Manual.pdf" (
  copy /y "docs\NewLight_Analysis_User_Manual.pdf" "dist\NewLight_Analysis\NewLight_Analysis_User_Manual.pdf" >nul
)

echo Verifying frozen backend imports...
call "dist\NewLight_Analysis\check_backends.bat" /verify-only
if errorlevel 1 (
  echo Frozen backend verification failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo.
echo Build complete:
echo   %CD%\dist\NewLight_Analysis\NewLight_Analysis.exe
echo.
echo Notes:
echo - Start the packaged application with NewLight_Analysis.exe.
echo - No legacy setup or batch launcher is published in the release folder.
echo - NewLight_Worker.exe is bundled under _internal for backend worker tasks.
echo - DeepCAD-RT is an optional CUDA addon downloaded after first-run CUDA detection.
echo - Run check_backends.bat inside dist\NewLight_Analysis on target machines.
echo.
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
