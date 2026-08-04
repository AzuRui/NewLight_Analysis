# NewLight_Analysis Packaging

Use `build_exe.bat` to create a portable Windows folder build, or `build_full_release.bat` to create the portable build and then compile the Inno Setup installer when `ISCC.exe` is available.

Do not start a build unless the user explicitly asks for compilation.

## Build

```powershell
E:\WorkSpace\NewLight_Analysis\build_exe.bat
```

For unattended builds:

```powershell
E:\WorkSpace\NewLight_Analysis\build_exe.bat /nopause
```

The build scripts automatically prefer the `caiman_latest` conda environment
when it is available. They also check for PyInstaller's `pkg_resources`
compatibility dependency and install `setuptools<81` in the selected build
Python if needed.

Full release script:

```powershell
E:\WorkSpace\NewLight_Analysis\build_full_release.bat
```

Output:

```text
E:\WorkSpace\NewLight_Analysis\build_release\NewLight_Analysis\NewLight_Analysis.exe
E:\WorkSpace\NewLight_Analysis\build_release\NewLight_Analysis\_internal\NewLight_Worker.exe
```

## Distribution

Distribute the whole `build_release` folder, or zip it. Do not copy only
`NewLight_Analysis.exe`; PyInstaller onedir resources live beside it under
`NewLight_Analysis\_internal`.

The release folder contains the main GUI, Python dependencies from the build
environment, a console `NewLight_Worker.exe` hidden under `_internal`, and
bundled backend resources:

- NeuroSeg3 local `ultralytics` source and weights.
- NeuroAlign source from `2cafe_analysis\NeuroAlign`.
- DeepCAD-RT local `deepcad` source and the project DeepCAD-RT model.
- A small `csbdeep.utils.normalize` compatibility module used by DeepCAD-RT display helpers.

Backend tasks launched from the installed app use `_internal\NewLight_Worker.exe`,
so target machines should not need the original workspace folders or separate
conda environments for normal bundled workflows.

The default DeepCAD-RT model is bundled from:

```text
E:\WorkSpace\NewLight_Analysis\DeepCADRT_Model\E_02_Iter_6416.pth
```

Both build scripts check this file before running PyInstaller, and `NewLight_Analysis.spec` includes the `DeepCADRT_Model` folder in the onedir bundle.

The build also patches frozen OpenCV loader config files after PyInstaller
collection. This removes conda build-machine paths from `_internal\cv2` and
keeps `cv2` import self-contained on other computers.

PyTorch/DeepCAD-RT CUDA builds also need the full conda CUDA/cuDNN runtime from
`Library\bin`. The spec explicitly collects cuDNN split DLLs, NVRTC, cuFFT
wrappers, and related CUDA runtime DLLs. `check_backends.bat` verifies this by
printing CUDA and cuDNN versions from the bundled worker.

On target machines, run this from inside the release folder:

```powershell
build_release\NewLight_Analysis\check_backends.bat
```

Expected result: bundled Python imports succeed, and NeuroSeg3, CaImAn, and
DeepCAD-RT backend `--help` checks report OK. The bundled Python section should
also print a non-empty `cuDNN` version.

DeepCAD-RT denoising still requires a CUDA-capable NVIDIA GPU and compatible
driver at runtime. The model and Python code are bundled, but the target machine
must provide working GPU hardware/driver support for actual DeepCAD inference.

## Notes

- The app icon is `xhr.ico`.
- The build mode is PyInstaller `onedir`, which creates a folder plus `NewLight_Analysis.exe`.
- PyInstaller runtime resources live under `build_release\NewLight_Analysis\_internal`; `check_backends.bat` detects this folder and runs backend worker checks from there.
- This is preferred over single-file mode because scientific Python libraries start faster and are easier to debug in folder mode.
- `build_full_release.bat` compiles `NewLight_Analysis_setup.iss` after the
  PyInstaller build when Inno Setup's `ISCC.exe` is installed. If `ISCC.exe` is
  absent, the script leaves the complete portable release in `build_release`.
