@echo off
setlocal
cd /d "%~dp0"
set "RESOURCE_DIR=%CD%"
if exist "%CD%\_internal\workers" set "RESOURCE_DIR=%CD%\_internal"

echo Main Python:
python -c "import sys, numpy, scipy, cv2, tifffile, pandas, matplotlib; print(sys.executable); print('main imports OK')"
if errorlevel 1 echo Main Python check failed.
echo.
echo NeuroSeg3 backend:
call conda run -n neuroseg3 python "%RESOURCE_DIR%\workers\run_neuroseg3.py" --help
if errorlevel 1 (
  echo NeuroSeg3 backend check failed.
) else (
  echo NeuroSeg3 backend OK.
)
echo.
echo CaImAn backend:
call conda run -n caiman_latest python "%RESOURCE_DIR%\workers\run_caiman.py" --help
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
  call conda run -n deepcadrt python "%RESOURCE_DIR%\workers\run_deepcadrt.py" --help
  if errorlevel 1 (
    echo DeepCAD-RT backend check failed.
  ) else (
    echo DeepCAD-RT backend OK.
  )
)
endlocal
