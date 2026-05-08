@echo off
setlocal
echo Creating/updating the optional CaImAn backend environment.
echo This can take a long time the first time.
conda create -n caiman_latest -c conda-forge caiman=1.13.1 python=3.11 -y
if errorlevel 1 (
  echo Failed to create caiman_latest.
  exit /b 1
)
echo.
echo Verifying CaImAn...
conda run -n caiman_latest python -c "import caiman as cm; from caiman.motion_correction import MotionCorrect; print('caiman', getattr(cm, '__version__', 'unknown')); print('motion correction import OK')"
endlocal

