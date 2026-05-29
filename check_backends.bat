@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set "RESOURCE_DIR=%CD%"
if exist "%CD%\_internal\workers" set "RESOURCE_DIR=%CD%\_internal"
set "WORKER_PY=python"
if exist "%RESOURCE_DIR%\NewLight_Worker.exe" set "WORKER_PY=%RESOURCE_DIR%\NewLight_Worker.exe"
if exist "%CD%\NewLight_Worker.exe" set "WORKER_PY=%CD%\NewLight_Worker.exe"

echo Bundled Python:
"%WORKER_PY%" -c "import sys, numpy, scipy, cv2, tifffile, pandas, matplotlib, torch; print(sys.executable); print('bundled imports OK'); print('torch CUDA:', torch.version.cuda); print('cuDNN:', torch.backends.cudnn.version())"
if errorlevel 1 echo Bundled Python check failed.
echo.
echo NeuroSeg3 backend:
"%WORKER_PY%" "%RESOURCE_DIR%\workers\run_neuroseg3.py" --help >nul
if errorlevel 1 (
  echo NeuroSeg3 backend check failed.
) else (
  set "NS3_WEIGHTS=%RESOURCE_DIR%\NeuroSeg3\weights\segmentation\yolov8s-seg.pt"
  if not exist "!NS3_WEIGHTS!" if exist "%CD%\..\NeuroSeg3\weights\segmentation\yolov8s-seg.pt" set "NS3_WEIGHTS=%CD%\..\NeuroSeg3\weights\segmentation\yolov8s-seg.pt"
  if not exist "!NS3_WEIGHTS!" (
    echo NeuroSeg3 weights missing: !NS3_WEIGHTS!
    echo NeuroSeg3 backend check failed.
  ) else (
    set "NS3_SMOKE_DIR=%TEMP%\newlight_neuroseg3_smoke_%RANDOM%"
    mkdir "!NS3_SMOKE_DIR!" >nul 2>nul
    "%WORKER_PY%" -c "from pathlib import Path; import cv2, numpy as np; p=Path(r'!NS3_SMOKE_DIR!\input.png'); img=np.zeros((128,128),np.uint8); cv2.circle(img,(64,64),24,220,-1); cv2.imwrite(str(p),img); print(p)" >nul
    if errorlevel 1 (
      echo NeuroSeg3 smoke input creation failed.
      echo NeuroSeg3 backend check failed.
    ) else (
      "%WORKER_PY%" "%RESOURCE_DIR%\workers\run_neuroseg3.py" --input "!NS3_SMOKE_DIR!\input.png" --output "!NS3_SMOKE_DIR!\masks.npz" --weights "!NS3_WEIGHTS!" --conf 0.002 --imgsz 128
      if errorlevel 1 (
        echo NeuroSeg3 backend check failed.
      ) else if not exist "!NS3_SMOKE_DIR!\masks.npz" (
        echo NeuroSeg3 smoke output missing.
        echo NeuroSeg3 backend check failed.
      ) else (
        echo NeuroSeg3 backend OK.
      )
    )
    rmdir /s /q "!NS3_SMOKE_DIR!" >nul 2>nul
  )
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
