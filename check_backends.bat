@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "OPTION_EXIT=0"
if /I "%~1"=="/install-gpu-driver" goto :INSTALL_GPU_DRIVER
if /I "%~1"=="/verify-only" goto :VERIFY_BACKENDS
if /I "%~1"=="/update-gpu" goto :UPDATE_GPU
if /I "%~1"=="/help" goto :USAGE
if "%~1"=="" goto :SETUP_MACHINE
echo Unknown option: %~1
echo A mistyped option is reported here and exits with code 64; it never means a check passed.
set "OPTION_EXIT=64"
goto :USAGE

:USAGE
echo Usage: check_backends.bat [/verify-only ^| /update-gpu ^| /install-gpu-driver ^| /help]
echo   (no argument)       run the first-run setup and print every progress message
echo   /verify-only        check the installed backends and print the paths being checked
echo   /update-gpu         install or update the optional unified GPU addon with progress
echo   /install-gpu-driver run the bundled NVIDIA driver installer
endlocal & exit /b %OPTION_EXIT%

:RESOLVE_PY
rem Resolve RESOURCE_DIR and WORKER_PY for the directory this script lives in.
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
exit /b 0

:SETUP_MACHINE
call :RESOLVE_PY
echo Starting first-run setup for: %CD%
echo Worker used: %WORKER_PY%
echo Every stage is printed below as it runs; the GPU addon download is the slow part.
echo The application logs its own setup stages to:
echo   %PROGRAMDATA%\NewLight_Analysis\setup_progress.log
"%WORKER_PY%" -c "import sys; from pathlib import Path; from machine_setup import ensure_first_run_setup; getattr(sys.stdout, 'reconfigure', lambda **kwargs: None)(errors='replace'); ok = ensure_first_run_setup(Path(r'%CD%'), progress=lambda message: print('[NewLight] ' + str(message), flush=True)); print('[NewLight] setup result: ' + str(ok), flush=True); raise SystemExit(0 if ok else 1)"
set "SETUP_RESULT=%ERRORLEVEL%"
echo First-run setup exit code: %SETUP_RESULT%
endlocal & exit /b %SETUP_RESULT%

:UPDATE_GPU
call :RESOLVE_PY
echo Installing or updating the optional unified GPU addon.
echo   application directory : %CD%
echo   addon target directory: %RESOURCE_DIR%\GPU_Addon
echo   download cache        : %PROGRAMDATA%\NewLight_Analysis
echo A full download is about 2.5 GB and is skipped when a verified cache already exists.
"%WORKER_PY%" -c "import sys; from pathlib import Path; from machine_setup import ensure_gpu_addon; getattr(sys.stdout, 'reconfigure', lambda **kwargs: None)(errors='replace'); ok, message = ensure_gpu_addon(Path(r'%CD%'), progress=lambda line: print('[GPU] ' + str(line), flush=True)); print('[GPU] installed: ' + str(ok), flush=True); print('[GPU] message: ' + str(message), flush=True); raise SystemExit(0 if ok else 1)"
set "GPU_UPDATE_RESULT=%ERRORLEVEL%"
echo GPU addon update exit code: %GPU_UPDATE_RESULT% (0 = addon present, 1 = see the message above)
if "%GPU_UPDATE_RESULT%"=="0" echo Reopen this script with /verify-only to check the GPU backends.
endlocal & exit /b %GPU_UPDATE_RESULT%

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
call :RESOLVE_PY
set "GPU_WORKER=%RESOURCE_DIR%\GPU_Addon\NewLight_GPU_Worker.exe"
set "GPU_ROI_SCRIPT=%RESOURCE_DIR%\GPU_Addon\workers\run_neusuite_roi.py"
echo Paths checked by this script:
echo   application directory: %CD%
echo   resource directory   : %RESOURCE_DIR%
echo   bundled worker       : %WORKER_PY%
echo   GPU addon worker     : %GPU_WORKER%
echo   GPU ROI script       : %GPU_ROI_SCRIPT%
echo.
echo Bundled Python:
echo   start !TIME!
"%WORKER_PY%" -c "import sys, numpy, scipy, cv2, tifffile, pandas, openpyxl, matplotlib; print(sys.executable); print('CPU core imports OK')"
set "CORE_CHECK_RESULT=!ERRORLEVEL!"
echo   done !TIME! exit code !CORE_CHECK_RESULT!
if not "!CORE_CHECK_RESULT!"=="0" (
  echo Bundled Python check failed with exit code !CORE_CHECK_RESULT!.
  set "FAILED=1"
)
echo.
echo ROI statistics Excel export:
set "EXCEL_VERIFY_DIR=%TEMP%\newlight_excel_verify_%RANDOM%_%RANDOM%"
mkdir "%EXCEL_VERIFY_DIR%" >nul 2>nul
pushd "%EXCEL_VERIFY_DIR%"
echo   start !TIME!
"%WORKER_PY%" -c "import numpy, pathlib, pandas; from analysis_core import roi_statistics, save_roi_statistics_table; traces = numpy.zeros((12, 2), dtype=numpy.float32); traces[3, 0] = 1.0; traces[8, 1] = 1.0; stats = roi_statistics(traces, ['roi_a', 'roi_b'], 10.0, [], min_peak_percentile=90.0); path = pathlib.Path(r'%EXCEL_VERIFY_DIR%') / 'roi_statistics.xlsx'; save_roi_statistics_table(str(path), stats, movie=numpy.zeros((12, 4, 4), dtype=numpy.uint16), fs=10.0, roi_count=2, trigger_count=0); sheets = pandas.read_excel(path, sheet_name=None); assert sorted(sheets) == ['Experiment Info', 'ROI Statistics'], sorted(sheets); print('ROI statistics Excel export OK:', sorted(sheets))"
set "EXCEL_CHECK_RESULT=!ERRORLEVEL!"
popd
rmdir /s /q "%EXCEL_VERIFY_DIR%" >nul 2>nul
echo   done !TIME! exit code !EXCEL_CHECK_RESULT!
if not "!EXCEL_CHECK_RESULT!"=="0" (
  echo ROI statistics Excel export check failed with exit code !EXCEL_CHECK_RESULT!.
  echo Exporting ROI statistics needs openpyxl inside the application bundle.
  set "FAILED=1"
)
echo.
echo NeuSuite fast ROI CPU backend (model bundled in the core package):
set "CORE_ROI_MODEL=%RESOURCE_DIR%\NeuSuite2p\segment_model.pt"
set "CORE_ROI_RUNTIME=%RESOURCE_DIR%\NeuSuite2p\method\ultralytics"
if not exist "%CORE_ROI_MODEL%" (
  echo No bundled CPU model in this package:
  echo   %CORE_ROI_MODEL%
  if exist "%GPU_WORKER%" (
    echo The GPU addon is installed, so fast ROI still runs on CUDA. A core package
    echo rebuilt with the bundled model is needed for machines without a GPU addon.
  ) else (
    echo Without the bundled model and without the GPU addon, fast ROI cannot run.
    echo Install the GPU addon with: check_backends.bat /update-gpu
    set "FAILED=1"
  )
) else if not exist "%CORE_ROI_RUNTIME%" (
  echo Bundled NeuSuite runtime is incomplete:
  echo   %CORE_ROI_RUNTIME%
  set "FAILED=1"
) else (
  rem Every variable below is both set and used inside this parenthesised block,
  rem so it needs delayed expansion; an early percent expansion would be empty.
  set "ROI_CPU_DIR=!TEMP!\newlight_roi_cpu_verify_!RANDOM!_!RANDOM!"
  mkdir "!ROI_CPU_DIR!" >nul 2>nul
  pushd "!ROI_CPU_DIR!"
  echo   start !TIME!
  "%WORKER_PY%" -c "import numpy, pathlib; import analysis_core as core; image = (numpy.random.default_rng(0).random((96, 112)) * 200).astype('float32'); result = core.run_fast_roi_segmentation(image, str(pathlib.Path(r'!ROI_CPU_DIR!')), device='cpu', image_size=320); print('CPU fast ROI backend:', result.log.splitlines()[0]); print('CPU fast ROI OK:', int(result.masks.shape[0]), 'masks from', int(result.masks.shape[1]), 'x', int(result.masks.shape[2]))"
  set "ROI_CPU_RESULT=!ERRORLEVEL!"
  popd
  rmdir /s /q "!ROI_CPU_DIR!" >nul 2>nul
  echo   done !TIME! exit code !ROI_CPU_RESULT!
  if not "!ROI_CPU_RESULT!"=="0" (
    echo Fast ROI CPU check failed with exit code !ROI_CPU_RESULT!.
    echo The bundled torch/timm/torchvision stack or the shipped NeuSuite model is broken.
    set "FAILED=1"
  )
)
echo.
echo Authorized NeuSuite fast ROI GPU backend:
if not exist "%GPU_WORKER%" (
  echo Optional GPU ROI addon is not installed; fast ROI stays on the CPU path above.
  echo To add CUDA acceleration, run: check_backends.bat /update-gpu
) else if not exist "%GPU_ROI_SCRIPT%" (
  echo GPU addon is out of date: the fast ROI worker script is missing.
  echo   %GPU_ROI_SCRIPT%
  echo Reinstall the unified GPU addon to update its worker scripts.
  set "FAILED=1"
) else (
  echo   start !TIME!
  "%GPU_WORKER%" "%GPU_ROI_SCRIPT%" --help >nul
  set "ROI_CHECK_RESULT=!ERRORLEVEL!"
  echo   done !TIME! exit code !ROI_CHECK_RESULT!
  if not "!ROI_CHECK_RESULT!"=="0" (
    echo Fast ROI GPU worker check failed with exit code !ROI_CHECK_RESULT!.
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
echo   start !TIME!
"%WORKER_PY%" -c "from caiman_headless import install_caiman_headless_compat; install_caiman_headless_compat(); import caiman; from caiman.source_extraction.cnmf.params import CNMFParams; CNMFParams(params_dict={}); print('CaImAn frozen CNMFParams OK', caiman.__version__)"
set "CAIMAN_CHECK_RESULT=!ERRORLEVEL!"
popd
rmdir "%CAIMAN_VERIFY_DIR%" >nul 2>nul
echo   done !TIME! exit code !CAIMAN_CHECK_RESULT!
if not "!CAIMAN_CHECK_RESULT!"=="0" (
  echo CaImAn backend check failed.
  set "FAILED=1"
) else (
  "%WORKER_PY%" "%RESOURCE_DIR%\workers\run_caiman_roi.py" --help >nul
  set "CAIMAN_ROI_RESULT=!ERRORLEVEL!"
  if not "!CAIMAN_ROI_RESULT!"=="0" (
    echo CaImAn ROI backend check failed with exit code !CAIMAN_ROI_RESULT!.
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
if not exist "%GPU_WORKER%" (
  echo DeepCAD-RT optional GPU addon is not installed; skipping DeepCAD-RT check.
) else (
  echo   start !TIME!
  "%GPU_WORKER%" -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
  set "DEEPCAD_CHECK_RESULT=!ERRORLEVEL!"
  echo   done !TIME! exit code !DEEPCAD_CHECK_RESULT!
  if not "!DEEPCAD_CHECK_RESULT!"=="0" (
    echo DeepCAD-RT CUDA worker check failed with exit code !DEEPCAD_CHECK_RESULT!.
    set "FAILED=1"
  ) else (
    echo DeepCAD-RT CUDA worker OK.
  )
)
echo.
echo Verification exit code: %FAILED% (0 = every enabled backend passed)
endlocal & exit /b %FAILED%
