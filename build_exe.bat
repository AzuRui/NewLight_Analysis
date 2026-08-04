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
    set "BUILD_PY_LABEL=conda env caiman_latest"
  )
)

echo Build Python: %BUILD_PY_LABEL%
%BUILD_PY% -c "import sys; print(sys.executable); print(sys.version)"
if errorlevel 1 (
  echo Failed to start the selected build Python.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

if not exist "DeepCADRT_Model\E_02_Iter_6416.pth" (
  echo Missing DeepCAD-RT model:
  echo   %CD%\DeepCADRT_Model\E_02_Iter_6416.pth
  echo Put the trained .pth file there before building.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

if not exist "..\NeuSuite2p\segment_model.pt" (
  echo Missing NeuSuite fast ROI model:
  echo   %CD%\..\NeuSuite2p\segment_model.pt
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

if not exist "NeuSuite_RuntimeDeps" (
  echo Missing bundled NeuSuite runtime dependencies:
  echo   %CD%\NeuSuite_RuntimeDeps
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

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

%BUILD_PY% -c "import numpy, cv2, scipy, skimage, pandas, tifffile, matplotlib, torch, torchvision, timm, caiman, igraph, leidenalg, hdmf, pynwb" >nul 2>nul
if errorlevel 1 (
  echo The selected Python is missing NewLight_Analysis build dependencies.
  echo Please build from the caiman_latest environment or repair that environment.
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
echo - NeuSuite fast ROI model/runtime, CaImAn resources, NeuroAlign source, DeepCAD-RT source, and its model are bundled.
echo - Run check_backends.bat inside dist\NewLight_Analysis on target machines.
echo.
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
