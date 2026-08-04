# NewLight_Analysis Packaging

Use `build_exe.bat` to create a portable Windows folder build, or `build_full_release.bat` to create the portable build and then compile the Inno Setup installer when `ISCC.exe` is available.

For a new build machine, use the combined entry point:

```powershell
E:\WorkSpace\NewLight_Analysis\build_portable_exe.bat
```

It first runs `setup_build_environment.bat`, then invokes the existing
portable build. The setup script uses an existing `caiman_latest` environment
without replacing its CUDA packages. If that environment does not exist, it
creates a conservative Python 3.8 base from `environment-build.yml`; install
the matching CUDA-enabled PyTorch build separately when DeepCAD-RT or GPU ROI
inference is required.

To prepare only the environment:

```powershell
E:\WorkSpace\NewLight_Analysis\setup_build_environment.bat
```

Both scripts accept `/nopause` for unattended execution. The scripts require
Conda and the external source/model folders referenced by `NewLight_Analysis.spec`.

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
- The optional unified GPU addon manifest; CUDA Torch, NeuSuite Fast ROI,
  DeepCAD-RT source, and both model payloads are downloaded as one package.
- A small `csbdeep.utils.normalize` compatibility module used by DeepCAD-RT display helpers.

Backend tasks launched from the installed app use `_internal\NewLight_Worker.exe`,
so target machines should not need the original workspace folders or separate
conda environments for normal bundled workflows.

GPU-only backends are intentionally separated from the core package. The one
addon archive contains CUDA Torch, NeuSuite Fast ROI and `segment_model.pt`,
`DeepCAD-RT\DeepCAD_RT_pytorch\deepcad`, and `DeepCADRT_Model\*.pth`; none of
these payloads are included in the core PyInstaller `datas` list.
The first frozen launch detects an NVIDIA/CUDA-capable runtime and downloads
the archive from `gpu_addon_manifest.json` into
`_internal\GPU_Addon`. The archive is verified with SHA-256 before
installation and extracted with a path-traversal check. On AMD/Intel or CPU
machines, DeepCAD-RT is skipped and the remaining CPU-compatible features stay
available.

Build the addon separately with:

```bat
build_gpu_addon.bat
```

Upload `GPU_Addon_CUDA.zip.part01` and `.part02` to the Release referenced by
the manifest. The manifest pins each part and the reconstructed archive by
SHA-256. The core contains no Torch/CUDA; the GPU addon contains CUDA Torch,
NeuSuite, DeepCAD source/model, and `NewLight_GPU_Worker.exe`.

The manifest URL is pinned to a GitHub Release asset rather than a mutable
branch archive. Do not replace the ZIP without updating its SHA-256. When the
addon contents change, publish a new release tag and update the URL and hash
together.

GitHub private-repository assets require authentication and therefore cannot be
downloaded by an installed application without embedding user credentials. The
current repository's Release is prepared for project collaborators; external
distribution requires a public asset host or an application-level authenticated
download flow.

## CPU core and GPU addon

The core package is built without Torch:

```bat
build_exe.bat
```

The optional GPU package is built separately with the CUDA-enabled
`caiman_latest` environment:

```bat
build_gpu_addon.bat
```

It produces `GPU_Addon_CUDA.zip.part01` and `.part02`. The first-run setup
downloads both parts, verifies each part and the reconstructed archive, then
extracts the CUDA worker, CUDA runtime, DeepCAD source, and model into
`_internal\GPU_Addon`. This is the only package that contains CUDA Torch and
CUDA DLLs; the core package retains CaImAn/OpenCV CPU functionality.

The build also patches frozen OpenCV loader config files after PyInstaller
collection. This removes conda build-machine paths from `_internal\cv2` and
keeps `cv2` import self-contained on other computers.

The PyInstaller spec excludes unused notebook/desktop stacks such as Jupyter,
Panel, Bokeh, PySide6, OpenVINO, PyAV, imagecodecs, and optional NWB schemas.
After Torch, CUDA, and NeuSuite moved to the GPU addon, the verified core
portable directory is `1,102,414,238` bytes (about `1.027 GiB`). The frozen CPU
backend checks passed. The final compressed installer size still needs to be
measured on a machine with Inno Setup installed.

To package the isolated slim2 build directly, install Inno Setup 6 and run:

```bat
build_slim2_installer.bat
```

This uses `NewLight_Analysis_slim2_setup.iss` and writes
`Output\NewLight_Analysis_slim2_setup.exe` with explicit solid LZMA2 ultra64
compression settings.

PyTorch/DeepCAD-RT CUDA builds also need the full conda CUDA/cuDNN runtime from
`Library\bin`. The spec explicitly collects cuDNN split DLLs, NVRTC, cuFFT
wrappers, and related CUDA runtime DLLs. `check_backends.bat` verifies this by
printing CUDA and cuDNN versions from the bundled worker.

On target machines, run this from inside the release folder:

```powershell
build_release\NewLight_Analysis\check_backends.bat
```

Expected result: bundled Python imports succeed, and NeuroSeg3 and CaImAn
backend checks report OK. DeepCAD-RT reports `optional GPU addon is not
installed` until the first CUDA-capable launch downloads the addon. The bundled
Python section should also print a non-empty `cuDNN` version.

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
