@echo off
setlocal
cd /d "%~dp0"

where conda >nul 2>nul
if errorlevel 1 (
  echo Conda was not found on PATH.
  exit /b 1
)

echo Creating or updating the isolated newlight_caiman environment...
set "CONDA_PKGS_DIRS=%CD%\.conda_pkgs"
set "NEWLIGHT_CAIMAN_PREFIX=%CD%\.conda_envs\newlight_caiman"
if not exist "%CONDA_PKGS_DIRS%" mkdir "%CONDA_PKGS_DIRS%"
if not exist "%CD%\.conda_envs" mkdir "%CD%\.conda_envs"
call conda env update -p "%NEWLIGHT_CAIMAN_PREFIX%" -f environment-newlight-caiman.yml --prune
if errorlevel 1 (
  echo Failed to create or update newlight_caiman.
  exit /b 1
)

set "MKL_THREADING_LAYER=SEQUENTIAL"
set "KERAS_BACKEND=torch"
set "CAIMAN_DATA=%CD%\CaImAn_Resources"
set "CAIMAN_TEMP=%TEMP%\newlight_caiman_setup"

if not exist "%CAIMAN_DATA%\model" mkdir "%CAIMAN_DATA%\model"
if not exist "%CAIMAN_TEMP%" mkdir "%CAIMAN_TEMP%"

echo Copying the CaImAn CNN classifiers into the controlled resource folder...
call conda run -p "%NEWLIGHT_CAIMAN_PREFIX%" --no-capture-output python -c "from pathlib import Path; import shutil, sys; src=Path(sys.prefix)/'share'/'caiman'/'model'; dst=Path(r'%CAIMAN_DATA%')/'model'; required=('cnn_model.pkl','cnn_model_online.pkl'); missing=[name for name in required if not (src/name).is_file()]; assert not missing, 'Missing CaImAn CNN files: '+str(missing); [shutil.copy2(src/name,dst/name) for name in required]; print('CaImAn CNN resources:', dst)"
if errorlevel 1 exit /b 1

echo Verifying direct scientific imports and CNMF...
call conda run -p "%NEWLIGHT_CAIMAN_PREFIX%" --no-capture-output python -c "import os; assert os.environ['MKL_THREADING_LAYER']=='SEQUENTIAL'; import numpy, torch, keras, caiman; from caiman.source_extraction.cnmf.cnmf import CNMF; from pathlib import Path; model=Path(os.environ['CAIMAN_DATA'])/'model'; assert (model/'cnn_model.pkl').is_file(); assert (model/'cnn_model_online.pkl').is_file(); print('numpy',numpy.__version__); print('torch',torch.__version__); print('keras',keras.__version__); print('caiman',caiman.__version__); print('CNMF and CNN resources OK')"
if errorlevel 1 exit /b 1

call conda run -p "%NEWLIGHT_CAIMAN_PREFIX%" --no-capture-output python workers\run_caiman_roi.py --help >nul
if errorlevel 1 exit /b 1

echo newlight_caiman is ready.
endlocal
