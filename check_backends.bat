@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
if /I "%~1"=="/install-gpu-driver" goto :INSTALL_GPU_DRIVER
if /I "%~1"=="/verify-only" goto :VERIFY_BACKENDS
if "%~1"=="" goto :SETUP_MACHINE
echo Unknown option: %~1
echo Usage: check_backends.bat [/verify-only ^| /install-gpu-driver]
endlocal & exit /b 64

:SETUP_MACHINE
set "RESOURCE_DIR=%CD%"
if exist "%CD%\_internal\workers" set "RESOURCE_DIR=%CD%\_internal"
set "WORKER_PY=python"
where conda >nul 2>nul
if not errorlevel 1 (
  set "CAIMAN_PY="
  for /f "usebackq delims=" %%I in (`conda run -n caiman_latest where python 2^>nul`) do (
    if not defined CAIMAN_PY if exist "%%I" set "CAIMAN_PY=%%I"
  )
  if defined CAIMAN_PY set "WORKER_PY=!CAIMAN_PY!"
)
if exist "%RESOURCE_DIR%\NewLight_Worker.exe" set "WORKER_PY=%RESOURCE_DIR%\NewLight_Worker.exe"
if exist "%CD%\NewLight_Worker.exe" set "WORKER_PY=%CD%\NewLight_Worker.exe"
"%WORKER_PY%" -c "from pathlib import Path; from machine_setup import ensure_first_run_setup; raise SystemExit(0 if ensure_first_run_setup(Path(r'%CD%')) else 1)"
set "SETUP_RESULT=%ERRORLEVEL%"
endlocal & exit /b %SETUP_RESULT%

:INSTALL_GPU_DRIVER
set "RESOURCE_DIR=%CD%"
if exist "%CD%\_internal\tools" set "RESOURCE_DIR=%CD%\_internal"
set "DRIVER_SETUP_PS=%RESOURCE_DIR%\tools\install_nvidia_driver.ps1"
if not exist "%DRIVER_SETUP_PS%" (
  echo NVIDIA driver setup script is missing:
  echo   %DRIVER_SETUP_PS%
  endlocal & exit /b 40
)
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%DRIVER_SETUP_PS%"
set "INSTALL_RESULT=%ERRORLEVEL%"
endlocal & exit /b %INSTALL_RESULT%

:VERIFY_BACKENDS
set "FAILED=0"
set "RESOURCE_DIR=%CD%"
if exist "%CD%\_internal\workers" set "RESOURCE_DIR=%CD%\_internal"
set "WORKER_PY=python"
where conda >nul 2>nul
if not errorlevel 1 (
  set "CAIMAN_PY="
  for /f "usebackq delims=" %%I in (`conda run -n caiman_latest where python 2^>nul`) do (
    if not defined CAIMAN_PY if exist "%%I" set "CAIMAN_PY=%%I"
  )
  if defined CAIMAN_PY set "WORKER_PY=!CAIMAN_PY!"
)
if exist "%RESOURCE_DIR%\NewLight_Worker.exe" set "WORKER_PY=%RESOURCE_DIR%\NewLight_Worker.exe"
if exist "%CD%\NewLight_Worker.exe" set "WORKER_PY=%CD%\NewLight_Worker.exe"

echo Bundled Python:
"%WORKER_PY%" -c "import sys, numpy, scipy, cv2, tifffile, pandas, matplotlib; print(sys.executable); print('CPU core imports OK')"
if errorlevel 1 (
  echo Bundled Python check failed.
  set "FAILED=1"
)
echo.
echo Authorized NeuSuite fast ROI backend:
set "GPU_WORKER=%RESOURCE_DIR%\GPU_Addon\NewLight_GPU_Worker.exe"
if not exist "%GPU_WORKER%" (
  echo Optional GPU ROI addon is not installed; skipping NeuSuite fast ROI check.
) else (
  "%GPU_WORKER%" "workers\run_neusuite_roi.py" --help >nul
  if errorlevel 1 (
    echo Fast ROI GPU worker check failed.
    set "FAILED=1"
  ) else echo NeuSuite fast ROI GPU worker OK.
)
echo.
echo CaImAn backend:
set "CAIMAN_DATA=%RESOURCE_DIR%\CaImAn_Resources"
set "PYTHONPATH=%RESOURCE_DIR%;%PYTHONPATH%"
set "CAIMAN_VERIFY_DIR=%TEMP%\newlight_caiman_verify_%RANDOM%_%RANDOM%"
mkdir "%CAIMAN_VERIFY_DIR%" >nul 2>nul
pushd "%CAIMAN_VERIFY_DIR%"
"%WORKER_PY%" -c "from caiman_headless import install_caiman_headless_compat; install_caiman_headless_compat(); import caiman; from caiman.source_extraction.cnmf.params import CNMFParams; CNMFParams(params_dict={}); print('CaImAn frozen CNMFParams OK', caiman.__version__)"
set "CAIMAN_CHECK_RESULT=!ERRORLEVEL!"
popd
rmdir "%CAIMAN_VERIFY_DIR%" >nul 2>nul
if not "!CAIMAN_CHECK_RESULT!"=="0" (
  echo CaImAn backend check failed.
  set "FAILED=1"
) else (
  "%WORKER_PY%" "%RESOURCE_DIR%\workers\run_caiman_roi.py" --help >nul
  if errorlevel 1 (
    echo CaImAn ROI backend check failed.
    set "FAILED=1"
  ) else if not exist "%RESOURCE_DIR%\CaImAn_Resources\model\cnn_model.pkl" (
    echo CaImAn CNN resource missing.
    set "FAILED=1"
  ) else (
    echo CaImAn motion and ROI backends OK.
  )
)
echo.
echo DeepCAD-RT backend:
set "GPU_WORKER=%RESOURCE_DIR%\GPU_Addon\NewLight_GPU_Worker.exe"
if not exist "%GPU_WORKER%" (
  echo DeepCAD-RT optional GPU addon is not installed; skipping DeepCAD-RT check.
) else (
  "%GPU_WORKER%" -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
  if errorlevel 1 (
    echo DeepCAD-RT CUDA worker check failed.
    set "FAILED=1"
  ) else (
    echo DeepCAD-RT CUDA worker OK.
  )
)
endlocal & exit /b %FAILED%
