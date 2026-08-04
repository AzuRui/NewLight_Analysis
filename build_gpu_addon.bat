@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "PAUSE_ON_EXIT=1"
if /I "%~1"=="/nopause" set "PAUSE_ON_EXIT=0"
if /I "%~1"=="--no-pause" set "PAUSE_ON_EXIT=0"

set "PY=call conda run -n caiman_latest python"
where conda >nul 2>nul
if errorlevel 1 goto :NO_CONDA
call conda run -n caiman_latest python -c "import torch; assert torch.cuda.is_available(); import PyInstaller" >nul 2>nul
if errorlevel 1 (
  echo caiman_latest must contain CUDA-enabled Torch and PyInstaller.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)
if not exist "..\DeepCAD-RT\DeepCAD_RT_pytorch\deepcad" (
  echo Missing DeepCAD-RT source.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)
if not exist "DeepCADRT_Model\E_02_Iter_6416.pth" (
  echo Missing DeepCADRT_Model\E_02_Iter_6416.pth
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Building CUDA worker...
if exist build_gpu_worker rmdir /s /q build_gpu_worker
if exist dist_gpu_worker rmdir /s /q dist_gpu_worker
%PY% -m PyInstaller --noconfirm --distpath dist_gpu_worker --workpath build_gpu_worker NewLight_GPU_Worker.spec
if errorlevel 1 (
  echo GPU worker build failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)

echo Staging GPU extension...
if exist build_gpu_addon rmdir /s /q build_gpu_addon
if exist GPU_Addon_CUDA.zip del /q GPU_Addon_CUDA.zip
mkdir build_gpu_addon\GPU_Addon
xcopy /e /i /y dist_gpu_worker\NewLight_GPU_Worker build_gpu_addon\GPU_Addon >nul
mkdir build_gpu_addon\GPU_Addon\DeepCAD-RT\DeepCAD_RT_pytorch
mkdir build_gpu_addon\GPU_Addon\DeepCADRT_Model
xcopy /e /i /y "..\DeepCAD-RT\DeepCAD_RT_pytorch\deepcad" build_gpu_addon\GPU_Addon\DeepCAD-RT\DeepCAD_RT_pytorch\deepcad >nul
xcopy /e /i /y DeepCADRT_Model build_gpu_addon\GPU_Addon\DeepCADRT_Model >nul
for /d /r "build_gpu_addon" %%D in (__pycache__) do @if exist "%%D" rmdir /s /q "%%D"
del /s /q "build_gpu_addon\*.pyc" >nul 2>nul

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'build_gpu_addon\GPU_Addon' -DestinationPath 'GPU_Addon_CUDA.zip' -CompressionLevel Optimal"
if errorlevel 1 (
  echo GPU addon archive creation failed.
  if "%PAUSE_ON_EXIT%"=="1" pause
  exit /b 1
)
echo GPU addon archive:
echo   %CD%\GPU_Addon_CUDA.zip
certutil -hashfile GPU_Addon_CUDA.zip SHA256
echo Splitting GPU addon into GitHub-compatible parts...
del /q GPU_Addon_CUDA.zip.part* >nul 2>nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$source=[IO.File]::OpenRead('GPU_Addon_CUDA.zip'); $size=1500000000; $i=1; try { while($source.Position -lt $source.Length) { $name=('GPU_Addon_CUDA.zip.part{0:D2}' -f $i); $target=[IO.File]::Create($name); try { $remaining=$size; $buffer=New-Object byte[] (4MB); while($remaining -gt 0 -and $source.Position -lt $source.Length) { $read=$source.Read($buffer,0,[Math]::Min($buffer.Length,$remaining)); if($read -le 0){break}; $target.Write($buffer,0,$read); $remaining-=$read } } finally { $target.Dispose() }; certutil -hashfile $name SHA256; $i++ } } finally { $source.Dispose() }"
echo Update gpu_addon_manifest.json with the new URL and SHA-256 before publishing.
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
exit /b 0

:NO_CONDA
echo Conda was not found on PATH.
if "%PAUSE_ON_EXIT%"=="1" pause
endlocal
exit /b 1
