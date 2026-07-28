@echo off
setlocal
cd /d "%~dp0"

where conda >nul 2>nul
if errorlevel 1 (
  echo Conda was not found on PATH.
  exit /b 1
)
for /f "delims=" %%I in ('conda info --base') do set "CONDA_BASE=%%I"

if not exist "NeuSuite_RuntimeDeps" mkdir "NeuSuite_RuntimeDeps"
call conda run -n neuroseg3 --no-capture-output python -m pip install --upgrade --target "%CD%\NeuSuite_RuntimeDeps" -r requirements-neusuite-runtime.txt
if errorlevel 1 (
  echo Online install failed; using the pure-Python packages bundled with NeuSuite2p.
  powershell -NoProfile -ExecutionPolicy Bypass -File tools\copy_neusuite_runtime_deps.ps1 -SourceRoot "%CD%\..\NeuSuite2p\_internal" -DestinationRoot "%CD%\NeuSuite_RuntimeDeps" -FallbackSourceRoot "%CONDA_BASE%\Lib\site-packages"
  if errorlevel 1 exit /b 1
)

call conda run -n neuroseg3 --no-capture-output python -c "import sys; sys.path.insert(0,r'%CD%\NeuSuite_RuntimeDeps'); import einops, efficientnet_pytorch, dill; import cpuinfo; print('NeuSuite runtime dependencies OK')"
if errorlevel 1 exit /b 1

echo NeuSuite runtime dependencies are ready.
endlocal
