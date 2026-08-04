@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PAUSE_ON_EXIT=1"
if /I "%~1"=="/nopause" set "PAUSE_ON_EXIT=0"
if /I "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"

echo ========================================
echo NewLight_Analysis build environment setup
echo ========================================
echo.

where conda >nul 2>nul
if errorlevel 1 (
  echo Conda was not found on PATH.
  echo Install Miniconda or Anaconda, then open a new terminal.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

set "ENV_NAME=caiman_latest"
set "ENV_FILE=environment-build.yml"
call conda env list | findstr /R /C:"^[ ]*%ENV_NAME%[ ]" >nul 2>nul
if errorlevel 1 (
  echo Environment %ENV_NAME% was not found. Creating it from %ENV_FILE%...
  call conda env create -f "%ENV_FILE%"
  if errorlevel 1 (
    echo Failed to create %ENV_NAME%.
    if "%PAUSE_ON_EXIT%"=="1" pause
    exit /b 1
  )
) else (
  echo Using existing %ENV_NAME% environment; CUDA packages will not be replaced.
)

echo Installing build-only compatibility packages...
call conda run -n %ENV_NAME% python -m pip install "setuptools<81" "pyinstaller>=6,<7"
if errorlevel 1 (
  echo Failed to install PyInstaller compatibility packages.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Checking build inputs...
set "FAILED=0"
if not exist "..\NeuSuite2p\segment_model.pt" (
  echo Missing NeuSuite fast ROI model: %CD%\..\NeuSuite2p\segment_model.pt
  set "FAILED=1"
)
if not exist "NeuSuite_RuntimeDeps" (
  echo Missing NeuSuite runtime dependencies: %CD%\NeuSuite_RuntimeDeps
  echo Run setup_neusuite_runtime.bat before building if needed.
  set "FAILED=1"
)
if not exist "CaImAn_Resources\model\cnn_model.pkl" (
  echo Missing CaImAn CNN resources. Run setup_newlight_caiman.bat first.
  set "FAILED=1"
)
if "%FAILED%"=="1" (
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Verifying scientific imports used by PyInstaller...
call conda run -n %ENV_NAME% python -c "import sys, numpy, cv2, scipy, skimage, pandas, tifffile, matplotlib, torch, torchvision, timm, caiman, igraph, leidenalg, hdmf, pynwb; print(sys.executable); print('Build imports OK')"
if errorlevel 1 (
  echo Build imports are incomplete.
  echo Repair the %ENV_NAME% environment, then run this script again.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo.
echo Build environment is ready.
echo Use build_portable_exe.bat to build the portable EXE.
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
