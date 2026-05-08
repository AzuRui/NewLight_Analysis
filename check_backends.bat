@echo off
setlocal
cd /d "%~dp0"
echo Main Python:
python -c "import sys, numpy, scipy, cv2, tifffile, pandas, matplotlib; print(sys.executable); print('main imports OK')"
if errorlevel 1 echo Main Python check failed.
echo.
echo NeuroSeg3 backend:
call conda run -n neuroseg3 python workers\run_neuroseg3.py --help
if errorlevel 1 (
  echo NeuroSeg3 backend check failed.
) else (
  echo NeuroSeg3 backend OK.
)
echo.
echo CaImAn backend:
call conda run -n caiman_latest python workers\run_caiman.py --help
if errorlevel 1 (
  echo CaImAn backend check failed.
) else (
  echo CaImAn backend OK.
)
endlocal
