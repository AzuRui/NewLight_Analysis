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
"%WORKER_PY%" -c "import sys, numpy, scipy, cv2, tifffile, pandas, matplotlib, torch; print(sys.executable); print('bundled imports OK'); print('torch CUDA:', torch.version.cuda); print('cuDNN:', torch.backends.cudnn.version())"
if errorlevel 1 (
  echo Bundled Python check failed.
  set "FAILED=1"
)
echo.
echo Authorized NeuSuite fast ROI backend:
"%WORKER_PY%" "%RESOURCE_DIR%\workers\run_neusuite_roi.py" --help >nul
if errorlevel 1 (
  echo Fast ROI backend check failed.
  set "FAILED=1"
) else (
  set "FAST_WEIGHTS=%RESOURCE_DIR%\NeuSuite2p\segment_model.pt"
  set "FAST_METHOD=%RESOURCE_DIR%\NeuSuite2p\method"
  if not exist "!FAST_WEIGHTS!" if exist "%CD%\..\NeuSuite2p\segment_model.pt" set "FAST_WEIGHTS=%CD%\..\NeuSuite2p\segment_model.pt"
  if not exist "!FAST_METHOD!\ultralytics" if exist "%CD%\..\NeuSuite2p\method\ultralytics" set "FAST_METHOD=%CD%\..\NeuSuite2p\method"
  if not exist "!FAST_WEIGHTS!" (
    echo NeuSuite weights missing: !FAST_WEIGHTS!
    echo Fast ROI backend check failed.
    set "FAILED=1"
  ) else if not exist "!FAST_METHOD!\ultralytics" (
    echo NeuSuite custom runtime missing: !FAST_METHOD!\ultralytics
    echo Fast ROI backend check failed.
    set "FAILED=1"
  ) else (
    "%WORKER_PY%" -c "from pathlib import Path; from workers.run_neusuite_roi import import_neusuite_yolo; YOLO = import_neusuite_yolo(Path(r'!FAST_METHOD!')); print('NeuSuite runtime import OK:', YOLO.__module__)"
    if errorlevel 1 (
      echo Fast ROI runtime import failed.
      set "FAILED=1"
    ) else (
      echo Fast ROI model and custom runtime OK.
    )
  )
)
echo.
echo CaImAn backend:
"%WORKER_PY%" "%RESOURCE_DIR%\workers\run_caiman.py" --help
if errorlevel 1 (
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
if not exist "%RESOURCE_DIR%\DeepCADRT_Model\E_02_Iter_6416.pth" (
  echo DeepCAD-RT model missing: %RESOURCE_DIR%\DeepCADRT_Model\E_02_Iter_6416.pth
  set "FAILED=1"
) else (
  "%WORKER_PY%" "%RESOURCE_DIR%\workers\run_deepcadrt.py" --help
  if errorlevel 1 (
    echo DeepCAD-RT backend check failed.
    set "FAILED=1"
  ) else (
    echo DeepCAD-RT backend OK.
  )
)
endlocal & exit /b %FAILED%
