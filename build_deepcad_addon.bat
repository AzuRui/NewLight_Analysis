@echo off
rem Backward-compatible name. The addon now contains the CUDA worker as well.
call "%~dp0build_gpu_addon.bat" %*
exit /b %ERRORLEVEL%
