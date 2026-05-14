@echo off
setlocal
cd /d "%~dp0"
set "RESOURCE_DIR=%CD%"
if exist "%CD%\_internal\workers" set "RESOURCE_DIR=%CD%\_internal"
set "WORKER_PY=python"
if exist "%CD%\NewLight_Worker.exe" set "WORKER_PY=%CD%\NewLight_Worker.exe"

echo Bundled Python:
"%WORKER_PY%" -c "import sys, numpy, scipy, cv2, tifffile, pandas, matplotlib; print(sys.executable); print('bundled imports OK')"
if errorlevel 1 echo Bundled Python check failed.
echo.
echo NeuroSeg3 backend:
"%WORKER_PY%" "%RESOURCE_DIR%\workers\run_neuroseg3.py" --help
if errorlevel 1 (
  echo NeuroSeg3 backend check failed.
) else (
  echo NeuroSeg3 backend OK.
)
echo.
echo CaImAn backend:
"%WORKER_PY%" "%RESOURCE_DIR%\workers\run_caiman.py" --help
if errorlevel 1 (
  echo CaImAn backend check failed.
) else (
  echo CaImAn backend OK.
)
echo.
echo DeepCAD-RT backend:
if not exist "%RESOURCE_DIR%\DeepCADRT_Model\E_02_Iter_6416.pth" (
  echo DeepCAD-RT model missing: %RESOURCE_DIR%\DeepCADRT_Model\E_02_Iter_6416.pth
) else (
  "%WORKER_PY%" "%RESOURCE_DIR%\workers\run_deepcadrt.py" --help
  if errorlevel 1 (
    echo DeepCAD-RT backend check failed.
  ) else (
    echo DeepCAD-RT backend OK.
  )
)
endlocal
