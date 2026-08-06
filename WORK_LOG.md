# Work Log

## 2026-08-04 - Local CPU and full portable builders

- Added local-only `build_cpu_exe.bat` and `build_full_exe.bat`. They are
  explicitly ignored by Git so the cleaned user-facing repository remains free
  of release manufacturing tools.
- `build_cpu_exe.bat` recreates the CPU core under `dist\NewLight_Analysis`.
  `build_full_exe.bat` rebuilds that core, embeds the verified unified
  `GPU_Addon`, and writes `full_diss\NewLight_Analysis`.
- Full frozen verification passed for CPU imports, CaImAn motion/ROI, NeuSuite
  Fast ROI GPU Worker, and DeepCAD CUDA Worker on NVIDIA GeForce RTX 4080.
- The full portable folder contains `8,347` files and `4,955,190,890` bytes.
  Main EXE SHA-256 is
  `293160f3a718f3a7e959881237b120bfdac055bd041bf039c26b693a813a7d81`.
  DeepCAD and NeuSuite model files are present. No NewLight user manual is
  included; the only filename containing `manual` is an internal Torch module.

## 2026-08-04 - Removed packaging toolchain from the user repository

- Removed PyInstaller specs, Inno Setup scripts, portable/installer/GPU addon
  build batches, build-only Conda environment files, packaging documentation,
  frozen OpenCV patch tooling, and the packaging-only contract test from the
  GitHub default branch.
- Kept application source, runtime workers, `gpu_addon_manifest.json`,
  `check_backends.bat`, source-environment setup, retained functional tests,
  and the NVIDIA driver helper. These are needed to run, maintain, or diagnose
  the application rather than to manufacture release artifacts.
- Simplified `README.md` to user operation and direct Release download links.
  The already published core installer and GPU addon Release assets are not
  affected by deleting build files from the source tree.
- Full remaining source regression passed: `301 passed, 15 subtests passed`.

## 2026-08-04 - User-facing core installer release cleanup

- Promoted `codex/unified-gpu-addon` to the GitHub default branch and deleted
  the obsolete remote `codex/dual-roi-engines` branch without force-pushing or
  rewriting either branch history.
- Changed the core installer version to `1.0.1`, removed the installer password,
  and renamed the output to `NewLight_Analysis_Core_Setup_v1.0.1.exe` so users
  can distinguish it from the optional GPU addon.
- Release staging now includes only the executable, `_internal` runtime, and
  required `check_backends.bat`. PDF, DOCX, Markdown, source launchers, and
  build scripts are not copied into `dist` or the user installation. Manuals
  are maintained and distributed separately.
- Added the locally installed `D:\Inno Setup 6\ISCC.exe` lookup to the full
  release builder.
- Rebuilt and verified the user-facing core package. The portable directory is
  `1,088,505,217` bytes with zero GPU artifacts and zero manual files. The
  installer is `335,482,844` bytes with SHA-256
  `b1d727e161e10a9c922ea0401ed6f311548d4c7d0ec80ada41f4973252de5538`.
- Frozen CPU/CaImAn backend verification passed, and the focused packaging,
  setup, GPU-routing, and short-movie suite passed `66` tests.

## 2026-08-04 - GPU setup is optional and rechecked on every launch

- Removed CUDA, NVIDIA driver installation, adapter detection, and pending
  restart as GUI startup gates. A user who declines installation, encounters a
  Windows Update failure, has an unsupported GPU such as GTX 960, or receives
  no WMI adapter result now enters the application in CPU mode.
- Kept the first frozen administrator launch and bundled CPU backend check as
  hard requirements. A broken core backend still blocks startup because the
  ordinary analysis application cannot run reliably in that state.
- Added `inspect_gpu_addon()` and invoke it for every completed frozen startup.
  It verifies the complete addon layout and, when installed, runs the GPU
  worker CUDA check. A missing addon is retried for `complete_cuda` machines;
  all GPU failures remain nonfatal.
- `pending_restart` is now a launchable state. The application reminds the user
  that GPU capability awaits restart, then continues in CPU mode.
- Added regression coverage for installation cancellation/failure, unknown
  adapters, pending restart, and GTX 960-style CPU-mode addon inspection.

## 2026-08-04 - Unified GPU addon naming and completeness contract

- Confirmed that `GPU_Addon_CUDA.zip` is one package containing CUDA Torch,
  DeepCAD-RT source/model, NeuSuite Fast ROI runtime/model, and
  `NewLight_GPU_Worker.exe`; DeepCAD is not a separate downloadable package.
- Renamed the active manifest to `gpu_addon_manifest.json` and the active
  installer entry point to `ensure_gpu_addon()`. Older names remain read-only
  compatibility aliases so an upgraded executable can still recognize an old
  release layout.
- Strengthened addon readiness checks to require both DeepCAD and NeuSuite
  payloads. A partial DeepCAD-only directory can no longer be reported as a
  complete GPU extension.

## 2026-08-03

### Release Folder Legacy BAT Removal

- Removed publication of `setup_caiman_latest.bat` and
  `run_NewLight_Analysis.bat` from both `build_exe.bat` and
  `build_full_release.bat`. Portable and installer staging folders now expose
  `NewLight_Analysis.exe` as the only application launcher.
- Kept the project-root `run_NewLight_Analysis.bat` unchanged as a source-only
  development launcher. Kept root `setup_caiman_latest.bat` only as a legacy
  compatibility redirect for source environment setup; neither file is a
  compiled-runtime dependency.
- Added a packaging contract test that rejects either legacy BAT name in both
  release builders. Updated the user manual and handoff so future builds do
  not reintroduce them.

### First-Run Administrator and Automatic NVIDIA Driver Setup

- Added a frozen-only, versioned first-run gate in `machine_setup.py` and
  connected it in `launch.py` after Worker dispatch but before GUI imports.
  Source launches bypass this gate. A missing machine record requires an
  administrator launch; non-admin first runs show a blocking Chinese message
  and exit without self-elevating.
- Machine state is written atomically to
  `%ProgramData%\NewLight_Analysis\machine_setup_v1.json`. Current states are
  `complete_cuda`, `complete_cpu_only`, and `pending_restart`; the file contains
  capability/setup metadata only and no remote-control, licensing, identity,
  or expiry fields.
- Display adapters are detected by both display name and PNP vendor ID. NVIDIA
  `VEN_10DE` is recognized even when Windows shows a basic display adapter;
  mixed Intel/AMD plus NVIDIA systems follow the NVIDIA path. Explicit
  AMD/Intel-only systems record CPU mode and warn that DeepCAD-RT and other
  CUDA-only paths are unavailable. An empty WMI result blocks initialization
  rather than permanently misclassifying the machine.
- Added `tools\install_nvidia_driver.ps1`. Its Windows Update Agent COM flow
  requires administrator rights, searches only applicable uninstalled driver
  updates, filters NVIDIA display-class updates, accepts their EULA, downloads
  and installs them, and writes diagnostics under ProgramData. It does not
  install the full CUDA Toolkit because the portable package includes its
  CUDA/cuDNN runtime.
- Split `check_backends.bat` into explicit modes: no argument runs the machine
  setup UI, `/verify-only` performs non-mutating backend checks, and
  `/install-gpu-driver` is the only driver-install path. Both portable build
  scripts use `/verify-only`, so building and testing cannot install a driver
  or restart Windows accidentally. Source checks now locate the actual
  `caiman_latest` Python; frozen checks continue preferring the bundled Worker.
- Successful driver installation records the current Windows boot marker as
  `pending_restart`. The user gets a yes/no restart dialog with no countdown;
  a declined restart leaves the system running. Re-launching during the same
  boot only reminds the user to restart and never repeats installation. After
  a real reboot, an elevated launch rechecks CUDA before completing setup.
- Added state-machine, packaging-contract, and retained-example tests. Final
  serial source regression passed `269 passed`. A new read-only smoke uses
  only `example\twophone.avi`; source and frozen reads returned three preview
  frames at shape `(3, 195, 410)` and 40 FPS, with SHA-256 unchanged.
- Rebuilt `dist\NewLight_Analysis\NewLight_Analysis.exe` with Python 3.11.15
  and PyInstaller 6.20.0. The build returned code 0 and passed frozen NeuSuite,
  CaImAn, DeepCAD-RT, CUDA 13.0, and cuDNN 92101 verification. Frozen resources
  include `_internal\machine_setup.py` and
  `_internal\tools\install_nvidia_driver.ps1`. No live driver installation,
  ProgramData setup record, or restart was performed on the development host.

### Frozen NeuSuite Dependency and Worker Multiprocessing Repair

- Reproduced the packaged Fast ROI failure from the user screenshot as
  `ModuleNotFoundError: No module named 'timm.models.layers'`. The source
  `caiman_latest` environment contains the deprecated compatibility modules
  `timm.models.layers`, `timm.models.helpers`, and `timm.models.registry`, but
  PyInstaller had omitted all three from the frozen Worker.
- Added those three compatibility entry points to the explicit hidden imports
  in `NewLight_Analysis.spec`. This preserves the authorized NeuSuite custom
  runtime without changing its model code or checkpoint.
- Strengthened `check_backends.bat`: it now imports the actual NeuSuite YOLO
  runtime, checks the Fast ROI model/runtime, CaImAn motion and ROI workers,
  CaImAn CNN resource, DeepCAD-RT worker/model, and returns a nonzero exit code
  if any check fails. `build_exe.bat` runs this check before reporting build
  completion, so a package with a missing frozen backend can no longer be
  published as successful.
- During a real frozen Fast ROI inference, reproduced
  `Worker script not found: --multiprocessing-fork`; a minimal frozen
  `multiprocessing.Process` exited with code 2. The root cause was the shared
  PyInstaller entry point not calling `multiprocessing.freeze_support()`.
  Added that call at the earliest executable entry in `launch.py`; the same
  frozen process smoke now prints `child-ok` and exits with code 0.
- Added packaging contract coverage for the timm compatibility modules, real
  backend verification, post-build verification, and multiprocessing freeze
  support. Focused packaging/ROI worker verification passed `21` tests.
- Rebuilt the portable release with Python 3.11.15 and PyInstaller 6.20.0.
  The final build returned code 0, copied all release files, and passed its
  automatic NeuSuite, CaImAn, DeepCAD-RT, CUDA 13.0, and cuDNN 92101 checks.
  The final EXE is `dist\NewLight_Analysis\NewLight_Analysis.exe`, built at
  2026-08-03 13:14.
- Ran the frozen NeuSuite model on one read-only frame from
  `eye\data\2\A01\result.avi` using CPU inference. It completed in the
  packaged Worker and produced 15 ROI instances plus NPZ/JSON artifacts in a
  temporary smoke directory. The source sample was not modified or removed.
- PyInstaller still emits optional/deprecation warnings for old timm imports,
  DCNv3 AMP decorators, Intel/MS MPI libraries, and the local Conda OpenCL
  exit hook. They did not affect the verified application backends or real
  Fast ROI inference. The timm warnings can only be removed cleanly by later
  migrating the authorized NeuSuite source to current timm APIs.

## 2026-07-31

### DeepCAD-RT CUDA Manual Requirement

- Confirmed DeepCAD-RT inference is a CUDA-only workflow in the current
  application. It has no CPU fallback even though several other NewLight
  operations can run on CPU.
- Added a prominent warning to the README CUDA section: a CUDA-capable NVIDIA
  GPU and compatible NVIDIA driver are mandatory; bundling the `.pth` model,
  worker, and CUDA runtime files is not sufficient on a CPU-only computer.
- Added a permanent user-manual rule to `PROJECT_HANDOFF.md`. Every future
  manual revision must repeat the warning in system requirements, the
  DeepCAD-RT feature description, troubleshooting, and the backend
  compatibility table.
- Recorded that the warning must live outside generated `dist` output because
  `build_exe.bat` deletes `dist` before rebuilding. No application code or EXE
  was changed for this documentation-only update.

### Detailed Current User Manual

- Replaced reliance on the deleted/outdated generated manual with a durable,
  source-controlled manual at `docs\NewLight_Analysis_User_Manual.md`.
- Documented the current Chinese four-tab UI, parameter sidebar, image/ROI
  toolbars, two-photon TDMS conversion, 8/16-bit import, five-channel
  grayscale/pseudocolor behavior, protocol baseline rules, stimulus mapping,
  DeepCAD blending, all preprocessing controls, manual/adaptive ROI workflows,
  Fast ROI and CaImAn parameters, Atlas Builder, three-stage NeuroAlign,
  dF/F/peak/correlation/event-average/heatmap analysis, all exports, FIFO task
  states, and reusable `.nlworkflow.json` behavior.
- Added formulas and publication-method templates, a 20-row troubleshooting
  table, compatibility guidance, and 15 numbered screenshot placeholders with
  exact suggestions for images the user can add later.
- Added `tools\build_user_manual.py` to generate a consistently styled DOCX.
  The generated manual contains 314 body paragraphs, 72 headings, 52 tables,
  and all 15 placeholders.
- Exported the DOCX through Microsoft Word as a 26-page PDF. Raster review of
  every page and full-size checks of the cover, long tables, method callouts,
  formulas, and final glossary found no clipping, overlap, or blank pages.
- Updated `build_exe.bat` to copy the durable Markdown, DOCX, and PDF manuals
  into `dist\NewLight_Analysis` after every portable build. The current copies
  were also placed in the existing dist release without rebuilding the EXE.

## 2026-07-27

### DeepCAD-RT Short-Movie Temporal Stitching Repair

- Diagnosed a real DeepCAD-RT upstream stitching defect with the 19-frame
  `eye\data\20260723_A04\bin10.tif` validation movie. With the old worker,
  `patch_t` was reduced to 19 and the single temporal patch wrote only frames
  0-12; output frames 13-18 were all zero even though their inputs were not
  empty.
- Updated `workers\run_deepcadrt.py` to retain the configured temporal patch
  length and edge-pad movies no longer than one patch to one patch plus one
  temporal stride. DeepCAD-RT therefore has a leading and trailing temporal
  stitch window, then its result is cropped back to the original length.
- Added a second safety net in `analysis_core.preserve_invalid_denoised_frames`:
  a zero DeepCAD-RT output for a nonempty input frame falls back to that source
  frame rather than contaminating preview or export through raw/denoised
  blending.
- Real GPU validation on the 19-frame sample produced no zero output frames.
  Its high-pass standard deviation decreased from `383.65` to `9.21`
  (`2.4%` of the raw value); all former tail frames now have nonzero output.
- The short-stack repair performs two temporal stitch passes (128 patches for
  this sample instead of 64), increasing the test runtime to about 18 seconds.
  This is intentional and required for valid coverage of every frame.
- Added `tests\test_deepcadrt_short_movie.py`; full regression suite passed:
  `59 passed`.

## 2026-07-19

### TIFF Import Bit Depth Control

- Added an `Import depth` selector in the Data tab with `Auto`, `16-bit`, and `8-bit` options.
- Updated `analysis_core.load_movie` so TIFF imports can preserve native 16-bit values in `Auto` / `16-bit` mode, or be intentionally quantized to 8-bit on request.
- Kept the analysis pipeline in `float32`; only explicit 8-bit import or export paths quantize the data.
- Extended `analysis_core.save_movie_tiff` and `analysis_core.save_movie` with a `bit_depth` option so TIFF output can be written as `uint8`, `uint16`, or float stack when needed.
- Added regression tests for TIFF import preservation, TIFF 8-bit conversion, TIFF 16-bit output, and the Data-tab import-depth selector.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_bit_depth tests.test_gui_static`.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_two_photon_converter tests.test_baseline tests.test_stimulus_input tests.test_interlacing_shift tests.test_background_image`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py tests\test_bit_depth.py tests\test_gui_static.py`.

## 2026-07-20

### Embedded Parameter Panel Layout

- Added a fixed-width `Parameters` panel between the left function tabs and the main image workspace, matching the left control column width.
- Moved the image canvas, Matplotlib toolbar, ROI action row, frame slider, and Run Log into the workspace column to the right of the new parameter panel.
- Kept image fitting based on the remaining workspace canvas size, so the image stays centered and aspect-preserved after resize/maximize.
- Changed simple parameter prompts to render inside the new parameter panel instead of opening small modal popups.
- Updated Preprocess buttons so clicking a tool loads its parameters into the panel and `Run` executes it.
- Expanded exposed Preprocess parameters: Image Shift row parity, Enhance Contrast clip limit, Detect Vessels overlay alpha, and Remove Vessel Artifact threshold.
- Added static GUI tests for the parameter side panel and embedded Preprocess parameter workflow.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_gui_static`.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_bit_depth tests.test_background_image tests.test_interlacing_shift`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py tests\test_gui_static.py`.
- Smoke-tested hidden Tk construction and confirmed `Image Shift` loads `range,row_parity` into the parameter panel while the canvas occupies the workspace column.

## 2026-06-30

### Window Background Image

- Added a full-window background layer using `background.png` at the project root.
- The background now fills the entire application window using centered cover-crop resizing, so the image preserves aspect ratio while filling the available space.
- Added a dedicated `ui_background.py` helper to keep the resize/crop logic isolated from the main GUI file.
- Bundling now includes `background.png` in `NewLight_Analysis.spec` so the packaged EXE keeps the same window background.
- Added regression coverage in `tests\test_background_image.py` for cover-crop behavior and background-path lookup.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_background_image tests.test_gui_static`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py ui_background.py tests\test_background_image.py`.

### Two-Photon Image Shift

- Added automatic interlacing image-shift correction to two-photon folder / `.tdms` conversion.
- The converter estimates the horizontal odd-line correction shift from Ch1 using a default `+/-10 px` search range and applies the same shift to all loaded channels.
- Rebuilds the grayscale analysis movie from corrected channels so ROI, dF/F, heatmaps, and save/export use the corrected data.
- Added a manual `Image Shift` button in the Preprocess tab for rerunning the correction on normal movies or already loaded channel movies.
- Manual multi-channel correction also estimates from Ch1 and applies the same shift to all channels to avoid weak-channel noise causing inconsistent geometry.
- Added `tests\test_interlacing_shift.py` for shift estimation, movie correction, and automatic two-photon conversion correction.
- Added `tests\test_gui_static.py` to guard the Preprocess-tab `Image Shift` button.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_interlacing_shift tests.test_two_photon_converter tests.test_baseline tests.test_stimulus_input tests.test_gui_static`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py tests\test_interlacing_shift.py tests\test_gui_static.py`.
- Fixed the first-pass edge fill behavior: exposed pixels after horizontal odd-line shifting now use the nearest valid row-edge value instead of `0`, preventing the two-photon `+32768` display range from being crushed and making the image look washed out.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_interlacing_shift tests.test_two_photon_converter`.
- Verified `conda run -n caiman_latest python -m py_compile analysis_core.py tests\test_interlacing_shift.py`.

### Workspace Cleanup

- Removed local generated/build/cache/sample-data items from the project root:
  - `build` (~414 MB)
  - `build_release` (~4.2 GB)
  - root/source `__pycache__` folders
  - `.codegraph`
  - local sample dataset folder `2` (~4.9 GB)
  - local sample archive `Example.zip` (~106 MB)
- Preserved source files, tests, workers, packaging scripts, DeepCADRT model files, git metadata, and the current portable release at `dist\NewLight_Analysis`.
- Left `dist\NewLight_Analysis` intact because it is the latest portable build for other-computer testing.
- Updated `.gitignore` to ignore `.codegraph`, the local sample dataset folder `2`, and `Example.zip` if they reappear.
- Left the pre-existing tracked deletion state for old `dist\NewLight_Analysis` manual files unchanged.
- Correction after user feedback: validation sample data must be treated as protected. Future cleanup must not delete or move any validation samples, even when they are untracked or large, unless the user explicitly names them for removal.

### Portable EXE Rebuild

- Rebuilt the portable app with `cmd /c build_exe.bat /nopause`.
- Output folder: `E:\WorkSpace\NewLight_Analysis\dist\NewLight_Analysis`.
- Verified `dist\NewLight_Analysis\check_backends.bat`: bundled Python imports OK; NeuroSeg3 real model smoke OK; CaImAn and DeepCAD-RT backend entry checks OK.
- Confirmed bundled runtime resources include `_internal\NewLight_Worker.exe`, `DeepCADRT_Model\E_02_Iter_6416.pth`, NeuroSeg3 `yolov8s-seg.pt`, DeepCAD-RT source, NeuroAlign source, and worker scripts.

### External Stimulus Input Sampling Rate

- Inspected `E:\WorkSpace\NewLight_Analysis\2\data_user input.txt`: it has four tab-separated columns (`E-phys`, `Respiration`, `Stim. Marker`, `(empty)`) and 3,120,000 numeric samples.
- Read the same folder's protocol recording time as 130 s, so the external input sampling rate is inferred as 24,000 Hz for this dataset.
- Updated stimulus loading to handle multi-column text/CSV files with headers, automatically select the most pulse-like TTL column, and infer `Stim Hz` from the folder protocol when possible.
- For the inspected dataset, the selected column is `E-phys`; trigger detection finds 30 pulses starting at sample 53,029, mapping to video frames 88, 208, 329, ... at 40 Hz.
- Added regression coverage for multi-column `data_user input.txt`-style files, column selection, inferred stimulus sampling rate, and trigger detection.
- Verified Python compilation and `python -m unittest tests.test_stimulus_input tests.test_two_photon_converter tests.test_baseline`.

## 2026-05-29

### Source Launcher And Dist-Only EXE Build

- Restored root `run_NewLight_Analysis.bat` to a source-only launcher: it runs `launch.py` from the project root, preferring `conda run -n caiman_latest python`, and no longer probes for packaged EXEs.
- Updated `build_exe.bat` so portable build output is prepared directly under `dist\NewLight_Analysis`; packaged launchers are generated only inside `dist`, and `build_release` is no longer deleted/recreated by this build path.
- Updated `build_full_release.bat` so full release launchers are generated separately instead of copying the root source launcher.
- Rebuilt with `cmd /c build_exe.bat /nopause`; output is `dist\NewLight_Analysis\NewLight_Analysis.exe`.
- Verified root launcher content is source-only, dist launcher content starts the packaged EXE, and `dist\NewLight_Analysis\check_backends.bat` passes bundled Python, NeuroSeg3, CaImAn, and DeepCAD-RT checks.

### Multi-Channel Grayscale Default And Optional Pseudocolor

- Changed channel handling so loaded channels stay as grayscale channel movies by default; RGB pseudocolor is composed only for display or save when the user selects a non-gray channel color.
- Added `Add Channel Data` in the Data tab for appending movie files, two-photon folders, or direct `.tdms` files into Ch1-Ch5 channel slots.
- Added five square channel color buttons in the View panel. Loaded channels default to gray, unloaded slots are black, and each loaded slot can be set to green/red/yellow/blue/purple/gray or deleted from its color popup. The popup `Delete` button uses the main UI button color instead of a red warning style.
- Changed two-photon conversion to stop generating default `converted_pseudocolor.avi` / channel AVI files; it now keeps temporary grayscale memmaps and lets `Save Current Movie` stream the selected grayscale or pseudocolor output on demand.
- Verified Python compilation, channel pseudocolor RGB composition, pseudocolor AVI saving, and a Tk GUI channel-render smoke test.

### NeuroSeg3 Packaged Runtime Fix

- Reproduced the packaged NeuroSeg3 failure with a real smoke image and bundled `NewLight_Worker.exe`; the error was PyTorch 2.6+ rejecting the older YOLO `.pt` checkpoint because `torch.load()` now defaults to `weights_only=True`.
- Updated `workers/run_neuroseg3.py` to load trusted NeuroSeg3 YOLO checkpoints with the legacy `weights_only=False` behavior when that PyTorch argument exists.
- Strengthened `check_backends.bat` so NeuroSeg3 validation creates a temporary image, loads the bundled `yolov8s-seg.pt`, runs prediction, and verifies a `.npz` mask output instead of only checking `--help`.
- Rebuilt the portable release with `conda run -n caiman_latest cmd /c build_exe.bat /nopause`.
- Verified `build_release\NewLight_Analysis\check_backends.bat`: bundled Python imports OK; NeuroSeg3 real model smoke OK; CaImAn and DeepCAD-RT help checks OK.

## 2026-05-14

### Portable EXE Build Script Refresh

- Updated `NewLight_Analysis.spec` so the portable EXE bundle includes recent runtime resources: `PACKAGING.md`, `NeuroAlign_atlas_registration_help.txt`, `NeuroAlign_atlas_registration_summary.json`, and `neuroalign_step_worker.py`.
- Added `/nopause` / `--no-pause` support to `build_exe.bat` and `build_full_release.bat` for unattended Codex builds.
- Updated `check_backends.bat` to locate bundled backend workers and the DeepCAD-RT model under PyInstaller's `_internal` runtime resource folder.
- Rebuilt the portable EXE with `conda run -n caiman_latest cmd /c build_exe.bat /nopause`.
- Output: `build_release\NewLight_Analysis\NewLight_Analysis.exe` and `build_release\Run_NewLight_Analysis.bat`.
- Verified Python compilation, release resource layout, and EXE startup smoke test. Release backend check found CaImAn and DeepCAD-RT OK; NeuroSeg3 still fails in the external `neuroseg3` conda environment because its `ultralytics` install is missing `cfg\default.yaml`.

### Save Current Movie Dialog

- Changed `Save Current Movie` from silent `result.<ext>` output to a standard Save As dialog.
- The dialog opens in the loaded movie's folder, suggests `result.avi`, `result.tif`, or `result.tiff` from the input type, and lets the user change both folder and filename.
- Canceling the dialog now exits without running DeepCAD-RT or writing any output; confirmed save behavior still uses the current processed movie and the DeepCAD blend when enabled.

## 2026-05-11

### Built-in Auto ROI Seed Estimate

- Made the toolbar coordinate readout white for better contrast on the dark canvas background.
- Added cursor-seeded area estimation to `Built-in Auto ROI` so the current image pixel position can prefill a rough `Min area` / `Max area` suggestion.
- The area suggestion uses the connected component around the mouse position as a heuristic, then lets the dialog remain editable.

### NeuroSeg3 Confidence Manual Input

- Replaced the NeuroSeg3 detection-confidence slider with a plain numeric input so sub-0.01 values such as `0.002` can be entered directly.
- Kept the mask pixel cutoff fixed at `0.50` and left the weights chooser / fallback toggle in place.
- Updated the project notes to reflect that this ROI backend may need unusually low confidence values on the current dataset.

### NeuroSeg3 ROI Dialog Simplification

- Replaced the plain-text NeuroSeg3 ROI parameter prompt with a dedicated dialog that uses a detection-confidence slider and quick preset buttons.
- Kept the mask pixel cutoff fixed at `0.50` in the GUI so users only tune the primary model confidence during ordinary ROI runs.
- Added a weight-path chooser and a checkbox-style fallback toggle to make the workflow less error-prone than the original yes/no text entry.

### Display Resize Binding Fix

- Restored TkAgg's native canvas resize handling by moving the app-specific redraw hook to Matplotlib `resize_event`.
- Kept the main image auto-fit and centering logic on top of the backend resize path, so the display now follows the actual visible canvas instead of only changing the rendered buffer.
- Documented the resize binding rule in the project handoff to avoid replacing the backend `<Configure>` handler again.

## 2026-05-10

### Portable Application Build

- Rebuilt the portable application from the current `main` branch using the `caiman_latest` conda environment:

  ```bash
  conda run -n caiman_latest cmd /c build_exe.bat
  ```

- Pre-build checks passed:

  ```bash
  python -m py_compile E:\WorkSpace\NewLight_Analysis\NewLight_Analysis.py E:\WorkSpace\NewLight_Analysis\analysis_core.py
  conda run -n caiman_latest python -c "import PyInstaller, openpyxl; print('build deps ok')"
  ```

- Generated portable app entry points:

  ```text
  E:\WorkSpace\NewLight_Analysis\build_release\Run_NewLight_Analysis.bat
  E:\WorkSpace\NewLight_Analysis\build_release\NewLight_Analysis\NewLight_Analysis.exe
  ```

- Build note: this run generated the portable application folder only; no Inno Setup installer was rebuilt in this step.

## 2026-05-09

### Context Safety And New Chat Handoff

- Added a task-completion context-safety self-check to `PROJECT_HANDOFF.md`.
- Documented the 80% background/context threshold for proactive handoff refresh.
- Documented the 70% post-compression distortion threshold for recommending a new chat.
- Added a new-chat startup checklist that tells the next assistant which project files, git commands, and records to inspect first.

### Heatmap Colorbar Placement

- Changed heatmap preview/AVI colorbar rendering from an overlay on the right edge of the image to a separate appended right-side panel.
- Updated AVI writing to infer output dimensions from the rendered first frame, so videos with a colorbar can be wider without cropping or covering image data.

### Heatmap Only AVI Mode

- Added a `Heatmap only` option to the heatmap AVI dialog.
- When enabled, preview and exported AVI frames remove the raw grayscale background and render heatmap values on a white background.
- `ROI only` continues to mask the heatmap region when both options are enabled; ROI-excluded pixels remain white.

## 2026-05-08

### Repository Initialization And Project Records

- Initialized Git tracking for the NewLight_Analysis project root.
- Added `.gitignore` to avoid committing generated build artifacts, IDE state, Python caches, temporary files, and large imaging data.
- Added `PROJECT_HANDOFF.md` as the standing handoff summary for future continuation.
- Added this `WORK_LOG.md` as the running project record.

### Display / Toolbar Cleanup

- Restored Matplotlib's interactive navigation toolbar under the main canvas.
- Removed the duplicate custom `Fit View / Zoom In / Zoom Out` row because the navigation toolbar covers those interactions.
- Kept ROI-specific controls in their own row.
- Verified Python syntax with:

  ```bash
  python -m py_compile E:\WorkSpace\NewLight_Analysis\NewLight_Analysis.py E:\WorkSpace\NewLight_Analysis\analysis_core.py
  ```

### Current Known Focus

- Main image display must remain fully visible, centered, and correct for non-square or mixed-resolution videos.
- Display-related behavior should be tested carefully after future preprocessing or ROI interaction changes.

### Packaging Build

- Installed build-time dependencies into the `caiman_latest` conda environment:

  ```bash
  conda run -n caiman_latest python -m pip install pyinstaller openpyxl
  ```

- Built the portable folder distribution with:

  ```bash
  conda run -n caiman_latest cmd /c build_exe.bat
  ```

- Generated portable app entry points:

  ```text
  E:\WorkSpace\NewLight_Analysis\build_release\Run_NewLight_Analysis.bat
  E:\WorkSpace\NewLight_Analysis\build_release\NewLight_Analysis\NewLight_Analysis.exe
  ```

- Generated the Inno Setup installer with:

  ```bash
  "D:\Inno Setup 6\ISCC.exe" "E:\WorkSpace\NewLight_Analysis\NewLight_Analysis_setup.iss"
  ```

- Installer output:

  ```text
  E:\WorkSpace\NewLight_Analysis\Output\NewLight_Analysis安装程序.exe
  ```

- Build note: this package was built from the `caiman_latest` environment, so the generated bundle is large because that environment includes heavy scientific and GPU-related dependencies.

### Heatmap AVI Controls

- Restored the heatmap AVI maximum display intensity control that mirrors the older `2cafe_analysis` `caxis_range` upper threshold behavior.
- Added `Max display` to the heatmap AVI dialog. `auto` keeps percentile-based scaling; a numeric value fixes the heatmap/colorbar upper limit.
- Restored a visible `dF/F` colorbar for heatmap preview and saved AVI frames.
- Added `Show colorbar` toggle to the heatmap AVI dialog.

### Cursor Readout / Built-in Auto ROI

- Forced the Matplotlib toolbar cursor readout to render in white on the dark theme so the live `x / y` coordinate display stays readable.
- Updated `Built-in Auto ROI` to present `Min area` and `Max area` explicitly as pixel-area values (`px^2`).
- When the mouse is hovering on image content, the app now logs both the estimated ROI area range and an equivalent cell diameter so users can convert a rough visual cell-size estimate into area bounds more easily.

### Built-in Auto ROI Sample Fill

- Added a dedicated `Built-in Auto ROI` dialog with a `Use last 2 ROIs` helper.
- The helper reads the last two drawn ROIs, treats them as size samples, and fills `Min area` / `Max area` from those sample areas.
- This is meant to replace brittle single-point seed estimates on noisy or ring-like images where the thresholded connected-component size can be misleading.

### NeuroAlign Atlas Notes

- Added `NeuroAlign_atlas_registration_summary.json` in the repo root as a handoff note for `build_atlas_from_lines_autocomplete.py` and `atlas_registration_merged_bilateral_midline.py`.
- The summary records the effective registration defaults, the README-recommended trial config, and the first tuning order to try for better accuracy.
- It also notes a stale docstring command in the atlas builder (`build_atlas_from_lines_final.py`) so the entry-point text can be cleaned up later.

### NeuroAlign ROI Integration

- Added ROI-panel buttons for `Atlas Reference Builder` and `NeuroAlign`, placed below the two automatic ROI buttons.
- Added focused parameter dialogs for both workflows, each with a `Help` button that opens a user-friendly NeuroAlign parameter guide.
- Added `NeuroAlign_atlas_registration_help.txt` because the previous JSON handoff was useful for developers but too dense for end users.
- Added atlas JSON loading via `analysis_core.process_atlas_json`, so generated or warped atlas JSON files can become current ROIs directly.
- Updated `Load ROI .npz` to `Load ROI / Atlas` because the loader now accepts `.npz`, atlas image files, and atlas JSON files.
- NeuroAlign runs through the `caiman_latest` backend environment; installed `python-igraph` and `leidenalg` there for the Leiden graph clustering step.
- Added `NeuroAlign_runs/` to `.gitignore` for generated registration outputs.
- Updated the shared conda worker runner to force UTF-8 text capture so NeuroAlign's Chinese/status output does not trip Windows GBK encoding.

### NeuroAlign ROI Integration Validation

- Continued the interrupted integration pass and rechecked the final GUI/backend contract before committing.
- Verified `NewLight_Analysis.py` and `analysis_core.py` compile with `python -m py_compile`.
- Verified `analysis_core.process_atlas_json` imports `2cafe_analysis/NeuroAlign/atlas_regions_raw.json` into 26 ROI masks at a 500 x 500 target shape.
- Verified the `caiman_latest` backend can import `cv2`, `numpy`, `scipy`, `skimage`, `matplotlib`, `sklearn`, `igraph`, and `leidenalg`.
- Smoke-tested main Tk GUI construction after adding the new ROI controls.
- Ran the Atlas Reference Builder through the same backend wrapper and confirmed it created `NeuroAlign_runs/test_builder_final/atlas_regions_raw.json`.

### NeuroAlign Atlas Path / Error Display Fix

- Fixed NeuroAlign launch so the GUI passes `--video`, `--atlas_json`, and `--outdir` explicitly alongside the generated config file.
- This avoids the registration script's argparse default `output/atlas_regions_raw.json` overriding the atlas path saved in the config bundle.
- Shortened the bottom status label to a one-line summary so long worker errors no longer stretch into the main image display area.
- Worker failure popups now show a concise summary and leave the full traceback/details in the bottom `Run Log`.
- Re-ran `python -m py_compile NewLight_Analysis.py analysis_core.py` and confirmed the registration parser receives the explicit atlas path.

### NeuroAlign Preview Wizard

- Replaced the one-shot NeuroAlign dialog with a three-step preview wizard: outer contour preview, clustering preview, and final atlas preview.
- The wizard keeps the selected video, atlas JSON, output directory, and tunable parameters in `NewLight_user_settings.json`; this file is ignored by git.
- `Rebuild` reruns NeuroAlign with the current parameters and refreshes the active preview. `Next` moves through the stages, and `Use Result` imports `warped_atlas_regions.json` into the main video ROI overlay.
- Added a custom outer fitting preview `outer_fit_preview.png` with the current mean/projection image rendered at 30% opacity, plus subject outer contour, affine atlas outer contour, and atlas midline.
- Added a custom clustering preview `cluster_on_affine_preview.png` that overlays Leiden clusters with the affine atlas boundary and intentionally hides the mean image.
- Exposed more stage-specific tuning controls for mask/outer/midline fit, clustering, and final TPS/adaptive search.

### NeuroAlign True Step Worker

- Added `neuroalign_step_worker.py` so NeuroAlign rebuilds are truly staged instead of running the full registration pipeline for every preview.
- Step 1 / `outer` now runs video preprocessing, subject mask extraction, outer affine fitting, and saves cached intermediates such as `preprocessed_video.npy`, `mean_img.npy`, `subject_mask.npy`, `affine_atlas_regions.json`, and `affine_atlas_label_map.npy`.
- Step 2 / `cluster` now reuses the cached preprocessed video and subject mask, computes only the Leiden label map, and saves `leiden_label_map.npy` plus clustering preview inputs.
- Step 3 / `final` now reuses the cached label map and subject mask, then runs only inner matching / TPS / final atlas export.
- The GUI now calls the step worker with `--stage outer`, `--stage cluster`, or `--stage final` depending on the active wizard page.
- Added missing defaults for clustering parameters so Step 2 no longer opens with blank parameter fields.
- The wizard now replaces blank values from older saved settings with current defaults so stale local settings cannot keep Step 2 empty.
- Rebuilding Step 1 clears stale downstream cluster/final outputs, and rebuilding Step 2 clears stale final outputs, so old files no longer make a partial rebuild look like a full pipeline run.
- Verified Python compilation, Tk wizard construction, cluster default values, and `caiman_latest` worker import/help.

### NeuroAlign Step 2 Preview Fallback

- Fixed the Step 2 preview fallback so it no longer searches for `subject_inner_boundaries.png` before clustering has been rebuilt.
- When Step 2 opens immediately after Step 1, the wizard now reuses generated Step 1 previews such as `outer_fit_preview.png` until the user clicks `Rebuild` for clustering.
- If no clustering preview exists yet, the caption now says to rebuild Step 2 instead of showing a misleading missing-file path.

### NeuroAlign Step 3 Preview Fallback

- Fixed the Step 3 preview fallback so it no longer reports missing `final_warp_overlay.png` before the final stage has been rebuilt.
- When Step 3 opens immediately after Step 2, the wizard now shows `cluster_on_affine_preview.png` until the user clicks `Rebuild` for final atlas generation.
- If Step 2 output is also unavailable, Step 3 falls back to Step 1 previews such as `outer_fit_preview.png`.

### NeuroAlign Wizard Navigation / Log Cleanup

- Added a `Back` button to the NeuroAlign wizard. It is disabled on Step 1 and moves Step 3 -> Step 2 or Step 2 -> Step 1.
- Suppressed `FutureWarning` output inside `neuroalign_step_worker.py` so skimage deprecation messages no longer clutter the Run Log.
- Added GUI-side backend log cleanup for known OpenCL vendor `temp.txt` noise and FutureWarning blocks while preserving real error lines.

### NeuroAlign Midline-Locked Outer Affine

- Investigated the case where `midline_profile_overlay.png` correctly identified the bilateral fissure, but the Step 1 red atlas contour still appeared slanted or off-midline.
- Found that the old outer affine stage only received one averaged subject midline x value; the full detected midline/fissure profile did not stay active during the contour-refinement loop.
- Added a NewLight-side runtime patch in `neuroalign_step_worker.py` that replaces NeuroAlign's outer affine estimator with a weighted fit using landmark, contour, and detected midline anchor points.
- The new fit reports contour error, midline error, rotation, shear, and midline-anchor count in the Run Log, making Step 1 easier to debug.
- Kept the rejected preview-TPS experiment out of the final code path because it over-deformed internal atlas polygons and would be misleading in the Step 1 preview.
- Validation on `NeuroAlign_runs/neuroalign_20260513_105405` Step 1: `mean contour error = 13.672 px`, `midline error = 3.998 px`, `rotation = -0.95 deg`, `shear = 0.000`, `midline anchors = 12`.

### View Panel Cleanup

- Removed the `Corr` projection option from the Data tab `View` panel.
- Removed the `Show dF/F Heatmap` button from the same `View` panel.
- Kept the underlying correlation / heatmap code and Analysis-tab heatmap AVI workflow intact.
- Verified with `python -m py_compile NewLight_Analysis.py analysis_core.py neuroalign_step_worker.py`.
- Smoke-tested Tk GUI construction and confirmed `Corr` / `Show dF/F Heatmap` are no longer present in widget text.

### DeepCAD-RT View Denoise Integration

- Continued the interrupted DeepCAD-RT integration in the Data tab `View` panel.
- Added a `DeepCAD-RT` toggle and `Weight` field that blend the current raw display with a cached DeepCAD-RT denoised movie/projection.
- Added async preview denoising so the UI can keep working while the backend runs.
- Added DeepCAD-aware saving: when the toggle is enabled, `Save Current Movie` writes the blended raw/denoised movie.
- Added `workers/run_deepcadrt.py` to call `DeepCAD-RT/DeepCAD_RT_pytorch/deepcad.test_collection.testing_class` through the `deepcadrt` conda environment.
- Added model-path validation before writing temporary input data. The default `.pth` model download folder is `E:\WorkSpace\DeepCAD-RT\DeepCAD_RT_pytorch\pth\ModelForPytorch\DownloadedModel`.
- If `DownloadedModel` exists as a file or has no `.pth` files, the app now reports that it must be replaced with a folder containing downloaded `.pth` models.
- Verified `python -m py_compile NewLight_Analysis.py analysis_core.py workers/run_deepcadrt.py`.
- Verified `workers/run_deepcadrt.py --help` and a GUI smoke test with `DeepCAD-RT` present while `Corr` / `Show dF/F Heatmap` remain absent.

### DeepCAD-RT Project Model / Packaging Prep

- Switched NewLight's default DeepCAD-RT model from the external DeepCAD download/cache path to the project-local model file `DeepCADRT_Model\E_02_Iter_6416.pth`.
- Kept the external DeepCAD-RT code/env at `E:\WorkSpace\DeepCAD-RT\DeepCAD_RT_pytorch`; only the default `.pth` model is now carried by the NewLight project for easier packaging.
- Updated `workers/run_deepcadrt.py` so an explicit single `.pth` path is accepted and converted to DeepCAD-RT's required model-folder contract.
- Updated `NewLight_Analysis.spec` to include `DeepCADRT_Model` in the PyInstaller onedir bundle.
- Updated `build_exe.bat` to fail early if the project-local `.pth` model is missing.
- Added `build_full_release.bat` for a future full portable + optional Inno Setup installer build. This script was written but not executed.

### DeepCAD-RT Overlap / Result Output Fix

- Fixed a Windows `WinError 123` failure in `workers/run_deepcadrt.py`. DeepCAD-RT builds an internal output folder name from `datasets_path`; passing an absolute Windows path such as `C:\Users\...` put an illegal `:` into that folder name. The worker now runs inside its temporary directory and passes relative `datasets` / `results` paths to DeepCAD-RT.
- `analysis_core.run_deepcadrt_denoise(..., overlap=...)` passes the backend DeepCAD-RT patch `overlap_factor`; the GUI keeps the user-facing `Weight` field as a raw/denoised display and export blend ratio.
- Added stale-result protection for async DeepCAD preview runs: if the movie changes while a worker is running, the old worker result is ignored when it returns.
- Changed `Save Current Movie` output behavior to write `result.tif`, `result.tiff`, or `result.avi` into the same folder as the loaded source when the source is TIF/TIFF/AVI. Unsupported source video extensions fall back to `result.tif`.
- Added `analysis_core.save_movie`, including AVI writing through OpenCV MJPG at the current Movie Hz. TIFF output preserves float stacks; AVI output is scaled to 8-bit using a 1-99 percentile display range.
- Verified `python -m py_compile NewLight_Analysis.py analysis_core.py workers\run_deepcadrt.py`, `conda run -n deepcadrt python workers\run_deepcadrt.py --help`, Tk GUI construction, and a small TIFF/AVI save-read smoke test.

### DeepCAD-RT Model Fmap Auto-Match

- Investigated the `size mismatch for Network_3D_Unet` error when loading `DeepCADRT_Model\E_02_Iter_6416.pth`.
- Confirmed the checkpoint's first convolution has shape `[16, 1, 3, 3, 3]`, while DeepCAD-RT builds only `[8, 1, 3, 3, 3]` when `fmap=16` because its `DoubleConv` halves the first encoder channel count.
- Updated `workers/run_deepcadrt.py` to inspect the selected `.pth` file and infer the required DeepCAD `fmap` automatically. The project-local model now infers `fmap=32`.
- Restored the Data tab `Weight` field to the original raw/denoised blend behavior with default `0.5`; `Weight` is not the backend `overlap_factor`.
- Verified `python -m py_compile NewLight_Analysis.py analysis_core.py workers\run_deepcadrt.py`, `conda run -n deepcadrt python workers\run_deepcadrt.py --help`, direct `infer_required_fmap(...) == 32`, and Tk GUI construction showing `Weight` but not `Overlap`.

### Session Temp Preview Outputs

- Added a per-run session temp directory created under the OS temp folder and deleted on app close.
- Moved DeepCAD-RT preview/save intermediates, NeuroSeg3 worker inputs/masks, and CaImAn worker TIFFs into that session temp directory instead of writing `NewLight_temp` beside the source movie.
- DeepCAD-RT preview remains a display/save overlay only. It no longer temporarily replaces `state.movie`, because large movies made that approach too heavy and it confused later preprocessing.
- Kept formal output tied to Data -> `Save Current Movie`: without that button, DeepCAD preview files remain temporary and are cleaned up with the app session.
- Weight edits are now monitored while typing; if the value changes, the current view redraws immediately without rerunning DeepCAD.
- Current preprocessing buttons are still destructive/stacking operations on `state.movie`: `Save Current Movie` saves the processed current movie, and multiple preprocessing operations do stack in order. A future non-destructive pipeline/config refactor should convert these into recorded operations that are reapplied for preview and full-movie export.
- Verified Python compilation, session temp cleanup on close, and a small GUI smoke test for DeepCAD display overlay / Weight redraw / save blending.

### Full Bundled Backend Release

- Continued the interrupted packaging pass and converted the PyInstaller build from a GUI-only app plus external conda/workspace assumptions into a bundled runtime with `NewLight_Analysis.exe` and console `NewLight_Worker.exe`.
- `analysis_core.py` now resolves runtime resources through PyInstaller `_MEIPASS` when frozen and falls back to the source workspace during development.
- Bundled runtime resources now include `workers`, `DeepCADRT_Model\E_02_Iter_6416.pth`, NeuroSeg3 local source/weights/config/utils, DeepCAD-RT `deepcad` source, NeuroAlign source, NeuroAlign help/summary files, and `PACKAGING.md`.
- Added `worker_launcher.py`; frozen backend jobs now run through `NewLight_Worker.exe` instead of requiring `conda run` on target machines.
- Added a minimal project-local `csbdeep.utils.normalize` compatibility module because DeepCAD-RT imports it from display helpers, but the full `csbdeep` dependency is unnecessary for NewLight's inference path.
- Added PyInstaller data fixes for CaImAn dependencies: `hdmf` / `pynwb` schema files and `ipyparallel\cluster\shellcmd_receive.py`, which is read from disk at runtime.
- Updated `check_backends.bat` so release validation uses bundled `NewLight_Worker.exe` when present.
- Built the full portable release with `conda run -n caiman_latest cmd /c build_exe.bat /nopause`.
- Final output folder: `E:\WorkSpace\NewLight_Analysis\build_release\NewLight_Analysis`.
- Verified `check_backends.bat`: bundled Python imports OK; NeuroSeg3, CaImAn, and DeepCAD-RT worker help checks OK.
- Verified deep frozen backend imports through `NewLight_Worker.exe`: `ultralytics`, `caiman`, `igraph`, `leidenalg`, `deepcad.test_collection`, `atlas_registration_merged_bilateral_midline`, and `csbdeep.utils.normalize`.
- Verified frozen GUI-side backend dispatch by importing `analysis_core` through `NewLight_Worker.exe -c` and calling `run_conda_worker(...)`; it resolved `APP_EXEC_DIR` to the release folder, `APP_RESOURCE_DIR` to `_internal`, and successfully launched a bundled worker help command.
- Verified GUI startup smoke: `NewLight_Analysis.exe` stayed alive for 8 seconds and was then closed.
- Confirmed bundled model/resource files include the DeepCAD-RT `.pth` and NeuroSeg3 `.pt/.onnx/.engine` weights under `_internal`.
- Inno Setup `ISCC.exe` was not found on this machine, so an installer `.exe` was not generated; the complete portable folder is ready, and `build_full_release.bat` will build the installer automatically once Inno Setup is installed.

### Worker Layout Polish

- Moved the bundled backend executable from the release root into `_internal\NewLight_Worker.exe` so the top-level folder exposes only `NewLight_Analysis.exe` to users.
- Changed the worker executable icon from the app icon to PyInstaller's console/tool icon, making it visually distinct if a user opens `_internal`.
- Updated frozen worker discovery in `analysis_core.run_conda_worker(...)` and `check_backends.bat` to prefer `_internal\NewLight_Worker.exe`.
- Rebuilt with `conda run -n caiman_latest cmd /c build_exe.bat /nopause`.
- Verified the top-level release folder contains `NewLight_Analysis.exe`, `_internal`, `check_backends.bat`, and `setup_caiman_latest.bat`, with no top-level `NewLight_Worker.exe`.
- Verified `_internal\NewLight_Worker.exe` runs backend help checks, deep backend imports still pass, GUI startup smoke still passes, and bundled model/resource files remain present under `_internal`.

### Packaged User Manual

- Added a complete Chinese user manual to the packaged output folder `dist\NewLight_Analysis`.
- Generated six real UI screenshots from the Tk application with synthetic example data: Data, Preprocess, ROI, Analysis, Heatmap AVI, and NeuroAlign wizard.
- Wrote the manual in Markdown, DOCX, and PDF formats:
  - `dist\NewLight_Analysis\NewLight_Analysis_User_Manual.md`
  - `dist\NewLight_Analysis\NewLight_Analysis_User_Manual.docx`
  - `dist\NewLight_Analysis\NewLight_Analysis_User_Manual.pdf`
  - screenshots in `dist\NewLight_Analysis\manual_assets\`
- Documented daily workflow, installation/runtime notes, Data/Preprocess/ROI/Analysis controls, export files, troubleshooting, and paper-methods wording.
- Included formulas for projection, DeepCAD-RT blending, trigger mapping, preprocessing, dF/F extraction, ROI trace averaging, trace baseline correction, peak detection, correlation, heatmap rendering, atlas-image ROI, atlas reference building, and NeuroAlign scoring.
- Verified the DOCX structure with `python-docx`: 103 non-empty paragraphs, 5 tables, and 6 embedded images.
- Converted the DOCX to PDF with local Microsoft Word COM automation and verified the PDF has 9 pages with extractable text.

### Stimulus Event Average / Split Analysis Exports

- Removed the Data-tab `Export Analysis` one-shot report button from the GUI.
- Removed the Data-tab `Trial Average` button so stimulus-response analysis lives in the Analysis tab.
- Added `Stimulus Event Average` to the Analysis tab. It asks for pre-event seconds, post-event seconds, event-heatmap window start/end seconds, and optional top fluorescence percent.
- The new event analysis uses current ROI traces and detected/generated stimulus frames, then exports:
  - one per-ROI stimulus-aligned response plot with individual trials in gray, the mean in black, and the stimulus onset as a red dashed line
  - a mean trace CSV for all ROIs
  - a compressed NPZ containing all aligned trial traces
  - a whole-brain stimulus-aligned mean dF/F heatmap
  - an optional top x% fluorescence heatmap when the user enters a positive top-percent value
  - a JSON summary with timing, trigger count, ROI count, movie shape, and output paths
- Added Analysis-tab export buttons that split the old report behavior into user-selectable actions:
  - `Export Traces CSV`
  - `Export Trace Plot PNG`
  - `Export ROI Statistics`
  - `Export Correlation`
  - `Export dF/F Heatmap PNG`
  - `Export ROI Snapshot`
  - `Export Summary JSON`
- Added reusable core helpers for event-aligned blocks/means, per-ROI event plots, event heatmaps, trace CSV export, ROI statistics export, correlation export, ROI snapshot export, and summary JSON export.
- `extract_traces` now accepts `show_window=False` so export actions can compute traces without forcing a trace-preview popup.
- Verified `python -m py_compile NewLight_Analysis.py analysis_core.py`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py neuroalign_step_worker.py workers\run_deepcadrt.py`.
- Smoke-tested the core event exporter on synthetic data: it generated 7 files including 2 ROI plots, full heatmap, top 10% heatmap, mean CSV, trials NPZ, and summary JSON.
- Smoke-tested GUI construction and confirmed `Export Analysis` / `Trial Average` are absent while the new Analysis export buttons are present.

### Packaged Manual Refresh After Rebuild

- Updated `dist\NewLight_Analysis\NewLight_Analysis_User_Manual.docx` after the latest rebuild so it matches the new Analysis-tab workflow.
- Refreshed the manual text to remove old `Export Analysis` and `Trial Average` references.
- Added documentation for `Stimulus Event Average`, including pre/post event windows, event heatmap start/end seconds, optional `Top fluorescence %`, skipped edge events, and generated output files.
- Added documentation for the split Analysis export buttons, including `Export Trace Plot PNG`.
- Re-exported `dist\NewLight_Analysis\NewLight_Analysis_User_Manual.pdf` from the updated DOCX with Microsoft Word COM automation.
- Verified the updated DOCX contains 112 non-empty paragraphs, 5 tables, and 6 embedded images; the PDF has 11 pages and contains the new stimulus-event section.

### Hidden Backend Console Windows

- Added `analysis_core.hidden_subprocess_kwargs()` to hide Windows console windows for backend subprocess calls.
- Applied the hidden subprocess settings to `analysis_core.run_conda_worker(...)`, which is the shared launch path for DeepCAD-RT, NeuroSeg3, CaImAn, NeuroAlign, and frozen `NewLight_Worker.exe` jobs.
- Applied the same hidden settings to the NeuroSeg3 CUDA status probe.
- This addresses the black console window appearing when enabling DeepCAD-RT preview from the GUI.
- Verified `python -m py_compile analysis_core.py NewLight_Analysis.py`.
- Verified a lightweight `run_conda_worker('caiman_latest', '-c', ...)` call returns successfully with hidden-window kwargs active.

### Workspace Cleanup

- Performed a conservative workspace cleanup without permanent deletion.
- Moved generated/cache/runtime output folders to the recoverable quarantine folder `E:\WorkSpace_cleanup_20260521_145153`.
- Moved items:
  - `NewLight_Analysis\build`
  - `NewLight_Analysis\build_release`
  - `NewLight_Analysis\Output`
  - `NewLight_Analysis\NewLight_temp`
  - `NewLight_Analysis\NeuroAlign_runs`
  - `NewLight_Analysis\__pycache__`
  - `NewLight_Analysis\csbdeep\__pycache__`
  - `NewLight_Analysis\workers\__pycache__`
  - `logs`
- Preserved core source, model, packaging scripts, handoff records, and the current `dist\NewLight_Analysis` portable release/manual folder.
- Post-cleanup size check: `E:\WorkSpace\NewLight_Analysis` is about 3.65 GB, mostly from the preserved `dist` release folder; the quarantine folder is about 5.89 GB.

### dF/F Baseline Frame Window

- Changed Protocol baseline inputs from seconds to frame units in the GUI: `Base start frame` and `Base dur frames`.
- Added `analysis_core.baseline_from_frames(...)`.
- dF/F baseline behavior is now:
  - `Base dur frames = 0`: use the full-movie 25th percentile baseline.
  - `Base dur frames > 0`: use the mean image over frames `[Base start frame, Base start frame + Base dur frames)`, clipped to the movie length.
- Invalidated cached baseline/dF/F/traces when baseline frame parameters change, so trace extraction, dF/F heatmaps, heatmap AVI generation, and exports use the current Protocol settings.
- Added `tests\test_baseline.py` to lock the two baseline behaviors.
- Verified `conda run -n caiman_latest python -m unittest tests.test_baseline`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py`.

### Two-Photon Folder Converter

- Changed the Data-tab open action from `Open Movie` to `Open Source`.
- `Open Source` now lets the user choose either a movie file or a two-photon data folder.
- Added built-in conversion for folders containing `protocol*.txt` and `*.tdms` files.
- The converter reads the protocol for frame size, frame rate, recording time, and recorded channels, then streams TDMS `int16` image frames into a temporary analysis movie.
- TDMS image values are shifted by `+32768` to match the LabVIEW thumbnail/TIFF convention and keep dF/F baselines positive.
- Ch1 is mapped to green and Ch2 to red in a temporary pseudocolor AVI. If a dataset only contains Ch1, the red channel remains blank.
- The GUI displays temporary pseudocolor AVI frames for converted folders while preserving a grayscale analysis movie for ROI, dF/F, heatmaps, and exports.
- `Save Current Movie` now defaults to `result.avi` and enforces AVI output. For an unmodified converted folder movie, it copies the temporary pseudocolor AVI to the chosen save path.
- Added regression coverage in `tests\test_two_photon_converter.py` for protocol parsing, Ch1-green/Ch2-red mapping, synthetic TDMS restoration, and AVI writing.
- Verified the real sample folder `E:\WorkSpace\Image format converter Folder （new）\20260424_A04` is recognized as a two-photon folder with 600x600 frames, 40 Hz, 2400 expected frames, Ch1 only, and 2400 TDMS image slots.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_baseline tests.test_two_photon_converter`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py`.

### Frozen OpenCV Loader Portability

- Diagnosed the target-machine OpenCV failure:
  `ImportError: ERROR: recursion is detected during loading of "cv2" binary extensions`.
- Root cause: the PyInstaller bundle copied conda OpenCV's `cv2\config.py` and `cv2\config-3.11.py` with build-machine absolute paths such as `D:/anaconda3/envs/caiman_latest/...`; this worked on the build PC but failed on other computers and made the OpenCV loader re-import `cv2` recursively.
- Added `tools\patch_frozen_cv2.py` to rewrite frozen OpenCV config files to self-contained paths under the bundle's `_internal` folder.
- Updated `NewLight_Analysis.spec`, `build_exe.bat`, and `build_full_release.bat` so future builds automatically patch those frozen OpenCV loader paths.
- Patched the current `dist\NewLight_Analysis` portable folder in place.
- Verified the current frozen worker imports `numpy`, `scipy`, `cv2`, `tifffile`, `pandas`, and `matplotlib`; `cv2.__version__` reports `4.13.0`.
- Verified bundled backend help entry points for NeuroSeg3, CaImAn, and DeepCAD-RT still launch through `_internal\NewLight_Worker.exe`.
- Verified `conda run -n caiman_latest python -m py_compile tools\patch_frozen_cv2.py NewLight_Analysis.py analysis_core.py`.

### Build Script Python Selection Fix

- Diagnosed a direct `build_exe.bat` failure where the script used the PATH Python (`Python312`) instead of the project build environment, causing PyInstaller to fail before project analysis with `ModuleNotFoundError: No module named 'pkg_resources'`.
- Updated `build_exe.bat` and `build_full_release.bat` to prefer `conda run -n caiman_latest python` automatically, while still falling back to PATH Python if conda is unavailable.
- Fixed Windows batch control flow by using `call conda ...`; direct `conda` calls inside another `.bat` transfer control and can make the script end after the environment probe.
- Added a build preflight that installs `setuptools<81` when `pkg_resources` is missing, because newer setuptools builds can omit that compatibility module while PyInstaller/altgraph still imports it.
- Added a dependency preflight for the selected build Python before cleaning/building.
- Re-ran `cmd /c build_exe.bat /nopause`; build succeeded and produced `build_release\NewLight_Analysis\NewLight_Analysis.exe`.
- Verified the release worker imports `numpy`, `scipy`, `cv2`, `tifffile`, `pandas`, and `matplotlib`, with OpenCV `4.13.0`.
- Verified `build_release\NewLight_Analysis\check_backends.bat` reports bundled Python, NeuroSeg3, CaImAn, and DeepCAD-RT backend checks OK.

### Packaged DeepCAD-RT cuDNN Runtime Fix

- Reproduced the packaged DeepCAD-RT/CUDA failure with `_internal\NewLight_Worker.exe -c "import torch; print(torch.backends.cudnn.version())"`; the frozen worker failed with `Invalid handle. Cannot load symbol cudnnGetVersion`.
- Confirmed the source `caiman_latest` environment returned cuDNN version `92101`, so the problem was packaging rather than the two-photon folder converter or DeepCAD model.
- Found that the portable bundle contained only `cudnn64_9.dll`, while conda's cuDNN 9 runtime also needs split DLLs such as `cudnn_ops64_9.dll`, `cudnn_graph64_9.dll`, `cudnn_adv64_9.dll`, and the engine DLLs.
- Updated `NewLight_Analysis.spec` to explicitly collect CUDA/cuDNN runtime DLLs from the build environment's `Library\bin`.
- Updated `check_backends.bat` so the bundled Python check now imports `torch` and prints both `torch.version.cuda` and `torch.backends.cudnn.version()`.
- Removed the modal DeepCAD-RT preview error popup; preview failures now remain in the bottom status line and Run Log.
- Replaced generated launcher echo lines with a robust `run_NewLight_Analysis.bat` template and copy it both beside the release folder and inside `build_release\NewLight_Analysis`.
- Re-ran `cmd /c build_exe.bat /nopause`; build succeeded.
- Verified the rebuilt bundle includes cuDNN split DLLs, `nvrtc`, `cufftw`, `cusolverMg`, and `caffe2_nvrtc`.
- Verified `_internal\NewLight_Worker.exe` reports PyTorch `2.10.0`, CUDA `13.0`, cuDNN `92101`, and `torch.cuda.is_available() == True`.
- Verified `build_release\NewLight_Analysis\check_backends.bat` passes bundled Python, NeuroSeg3, CaImAn, and DeepCAD-RT checks.
- Verified `run_NewLight_Analysis.bat` launches the packaged app from both `build_release` and `build_release\NewLight_Analysis`.

### Two-Photon Channel Display And Export

- Updated two-photon folder conversion to keep Ch1 and Ch2 as separate temporary channel movies in addition to the analysis movie.
- The converter now writes temporary per-channel AVIs (`converted_ch1.avi`, `converted_ch2.avi` when Ch2 exists) and a pseudocolor preview AVI.
- GUI display now rebuilds RGB pseudocolor frames/projections from the current channel movies, so preprocessing operations such as smoothing, background subtraction, bleach correction, contrast enhancement, and built-in rigid motion preserve red/green display instead of falling back to grayscale.
- Preprocessing operations are applied to each converted channel movie; the analysis movie is recombined from the processed channels afterward.
- Undo restores the converted channel movies alongside the analysis movie.
- `Save Current Movie` now exports dual-channel two-photon sources as separate AVI files named from the selected base path, for example `result_ch1.avi` and `result_ch2.avi`, instead of saving the merged pseudocolor AVI.
- Added `analysis_core.pseudocolor_rgb(...)` for display and kept `pseudocolor_bgr(...)` for OpenCV AVI writing.
- Updated `tests\test_two_photon_converter.py` for RGB/BGR channel mapping and generated per-channel AVI/channel movie outputs.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_two_photon_converter tests.test_baseline`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py`.
- Rebuilt the portable app with `cmd /c build_exe.bat /nopause`; output is `build_release\NewLight_Analysis\NewLight_Analysis.exe`.
- Verified bundled `check_backends.bat` still passes and bundled `analysis_core` exposes the new pseudocolor display helper.

### Source UI Background Visibility Fix

- Diagnosed why launching with `run_NewLight_Analysis.bat` appeared unchanged after adding `background.png`: the batch launcher was correctly running `launch.py` from source, but Tk/ttk frames, notebooks, label frames, and the Matplotlib preview canvas are opaque and covered the root-level background layer.
- Added `ui_background.BackgroundPane`, a reusable `tk.Frame` subclass that renders `background.png` directly inside large visible panes with centered cover-crop resizing and optional dark tinting for readability.
- Changed the left sidebar and right work area from opaque `ttk.Frame` containers to `BackgroundPane`, preserving the existing margins and control layout.
- Added an empty-preview background renderer so the large video display area also shows the selected background image before a movie is loaded; startup and resize now call `redraw(preserve_view=False)` when there is no movie image.
- Added regression checks in `tests\test_background_image.py` and `tests\test_gui_static.py` so future UI changes keep visible background panes and the empty preview background.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_background_image tests.test_gui_static`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py ui_background.py tests\test_background_image.py tests\test_gui_static.py`.

### Logo Starfield Quieting

- Reduced the animated logo starfield from 34 points to 24 points.
- Changed star radii from integer 1-2 px dots to smaller 0.45-0.65 px dots.
- Raised the bright-pulse threshold and slowed pulse speed so fewer points flash at once.
- Removed the temporary high-brightness radius growth and reduced rare sparkle cross-lines from 10 px spans to 4 px spans.
- Added `tests\test_gui_static.py` coverage to keep the logo starfield using small, quiet points.
- Verified `conda run -n caiman_latest python -B -m unittest tests.test_gui_static`.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py tests\test_gui_static.py`.

## 2026-07-21

### Motion Mode Controls And Built-in Rigid Reference Fix

- Confirmed from the installed CaImAn source that `piecewise` mode runs rigid
  template generation first and then piecewise-rigid local correction.
- Changed the CaImAn `Mode` parameter from an unrestricted text entry to a
  readonly `rigid / piecewise` combobox; the default is now `piecewise`.
- Reproduced the Built-in reference bug with a synthetic movie: when the first
  four reference frames were all offset by 4 px, they received zero shift and
  later stable frames were shifted toward the incorrect opening position.
- Confirmed there was no frame omission or original-frame splice. The root
  cause was that a raw mean of the first N frames defined the output coordinate
  system.
- Replaced the ambiguous `Template frames` control with `Reference mode`,
  zero-based `Reference start frame`, `Reference frame count`, and
  `Max rigid shift px`.
- Automatic mode now selects a low-motion window near the movie's dominant
  median position. Manual mode uses the requested start/count interval.
- Built-in correction now aligns the selected interval to a middle anchor,
  builds a median template, and then estimates a final shift for every frame,
  including the selected reference frames.
- Added Run Log diagnostics for selected interval, anchor, median absolute
  dy/dx, and maximum absolute dy/dx.
- Added `tests\test_rigid_motion.py` for unstable openings, displaced stable
  openings, manual interval behavior, and correction of frames inside the
  reference interval.
- Changed CaImAn output handling so its required worker TIFF files remain
  session-scoped: the input TIFF is deleted immediately, while the corrected
  result is retained as `CaImAn\caiman_preview.tif` until the application closes
  and is also loaded as the current software preview.
- CaImAn no longer reports a temporary path as a saved user result. The Run Log
  now tells the user to use `Save Current Movie` to keep the preview; Undo can
  restore the previous movie state.
- Filtered the harmless Conda OpenCL activation noise (`Access is denied`,
  missing `temp.txt`) from the application log. The environment's OpenCL vendor
  directory is read-only for the current user, but CaImAn completes normally.
- Preserved the display source across CaImAn completion. A frame view reloads
  the same frame from the corrected movie; a projection view recomputes the
  selected projection instead of unconditionally replacing a frame with Mean.
- The Run Log reports the session preview TIFF path so the user can inspect it
  directly. Permanent output still requires `Save Current Movie`.
- Added `tests\test_caiman_motion.py` to verify result loading, immediate input
  cleanup, and retention of the session preview TIFF.
- Exposed CaImAn `Max shift px`, `Patch stride px`, `Patch overlap px`, and
  `Max local deviation px` beside the existing mode selector. Defaults are now
  `piecewise / 12 / 48 / 24 / 5` for the current two-photon data scale.
- Forwarded all four numeric settings through `analysis_core.run_caiman_motion`
  to `workers\run_caiman.py` instead of relying on hidden worker defaults.
- Added worker diagnostics for the actual parameter values, rigid and local
  median/max absolute y/x shifts, and the fraction of estimates touching the
  configured displacement limit.
- Verified the real worker on a 30-frame synthetic shifted movie: it reported
  maximum rigid shift 7.6 px, maximum local shift 7.6 px, and zero limit hits
  with `max_shift=12` and `max_deviation=5`.

## 2026-07-22

### Complete Chinese Localization

- Localized the main window, parameter panel, dialogs, file pickers, status
  messages, Run Log text, validation errors, NeuroAlign help, analysis windows,
  and Matplotlib chart labels into Chinese.
- Preserved model and scientific names while adding functional descriptions:
  `CaImAn 运动矫正/去抖动`, `DeepCAD-RT 深度学习降噪`,
  `NeuroSeg3 自动 ROI 分割`, and `NeuroAlign 脑图谱配准`.
- Added `ui_text_zh.py` as the Chinese display catalog for model names,
  preprocess actions, translated choices, and ROI statistics headings.
- Replaced display-text routing with stable preprocess action IDs. Chinese
  combobox choices map back to the original `piecewise`, `rigid`, `auto`,
  `manual`, `odd`, and `even` backend values.
- Set the left sidebar to a stable 300 px width and the parameter panel to
  290 px. Sidebar action buttons share one centered style and the longest
  model/function name remains fully visible.
- Localized the Matplotlib navigation toolbar tooltips while preserving its
  callback names and localized ROI statistics headings without changing the
  exported dataframe schema.
- Added `tests\test_chinese_localization.py` and updated GUI static tests to
  verify Chinese labels, model-name conventions, internal action routing,
  choice mapping, and stable layout dimensions.
- Verified the complete test suite: 44 tests passed.
- Verified a real Tk window at 1412x862 requested size; the parameter panel
  rendered at 290 px and the preprocess page showed uniform, untruncated
  action buttons.
- The EXE was not rebuilt in this update. Source launch through
  `run_NewLight_Analysis.bat` uses the Chinese interface immediately.

## 2026-07-23

### Combobox Background Integration

- Styled all `ttk.Combobox` controls so their input field, arrow area, and
  dropdown list match the dark parent panel instead of using the Windows
  default white background.
- Kept readable dark-theme hover, selection, disabled-text, border, and arrow
  colors. Tk/ttk does not provide true per-pixel widget transparency, so panel
  color matching is the supported visual-transparency implementation.
- Added a GUI static regression test covering the combobox field and dropdown
  list background configuration.

### Fast Motion Correction

- Renamed the visible `内置刚性运动矫正` action to `快速运动矫正` while
  preserving its stable internal action ID.
- Left the existing two-pass rigid algorithm unchanged. `柔性强度 = 0`
  returns the rigid movie and shifts exactly, without entering local
  estimation.
- Added optional constrained local correction using overlapping patch phase
  correlation, median vector filtering, dense-field interpolation, spatial
  smoothing, and one linear image warp after rigid correction.
- Exposed `柔性强度 (0=关闭)`, `局部块尺寸 (px)`, and
  `最大局部形变 (px)` with defaults `0.0`, `96`, and `3.0`.
- Expanded the parameter description with the recommended `0.2-0.5` strength
  range, speed/stability tradeoffs, deformation-risk warning, and guidance to
  use CaImAn piecewise-rigid correction for stronger complex motion.
- Added local grid, dy/dx displacement, and limit-hit diagnostics to the Run
  Log. Residual template translation is retained because local deformation can
  bias the first-stage whole-frame estimate.
- Added numerical regression tests for rigid compatibility, synthetic local
  deformation improvement, clipping/finite output, and small-image fallback,
  plus GUI localization and routing tests.
- Benchmarked a 20-frame synthetic `195 x 410` movie at about 0.46 seconds in
  the current development environment with a `4 x 8` local grid.

### Responsive Single-Task Queue

- Added `task_queue.py`, which owns one FIFO background worker for the current
  dataset. Tk-only callbacks commit results after each worker exits, then the
  next queued task starts. This keeps window repainting, pan/zoom, parameter
  editing, and logs responsive while preserving movie-operation order.
- Migrated imports, two-photon conversion, stimulus loading, ROI/atlas work,
  preprocessing, motion correction, DeepCAD-RT, NeuroSeg3, NeuroAlign stages,
  dF/F and trace analysis, heatmap AVI, and export/save paths to the shared
  queue. Direct worker-thread creation is now centralized.
- Added a persistent `当前数据任务流` panel below Parameters. Pending items use
  white text, the active item has a green border, completed items use
  light-gray text, and the final completed item is outlined blue when idle.
  `取消当前任务` requests cooperative cancellation while retaining later tasks.
- Primary dataset loads reset visible history only after the new data is
  active; the load task and later queued work remain visible. Results from an
  older movie identity are ignored rather than overwriting a new import.
- Moved `试次平均` into the queue as one task. It derives missing stimulus
  triggers, baseline, dF/F traces, and trial averages off the Tk thread before
  opening its plot. This fixes the old asynchronous race where it could request
  trigger detection and immediately conclude that no triggers existed.
- Added `tests\test_task_queue.py` for FIFO ordering, main-thread completion
  ordering, cancellation, and history reset. Added static coverage that keeps
  trial averaging on the queue.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py task_queue.py`.
- Verified `conda run -n caiman_latest python -m pytest -q`: `52 passed`.
- The Conda/OpenCL `Access is denied` / missing `temp.txt` activation messages
  still appear in the development shell but have exit code 0 and do not affect
  queue tests or application behavior.

## 2026-07-24

### Projection-Aware ROI Interaction

- ROI interaction no longer forces the canvas to a mean image. Selecting
  `圆形 ROI`, `自由绘制 ROI`, or `点击删除 ROI` refreshes the canvas using the
  currently selected `视图` projection: `均值`, `最大值`, `标准差`, or
  `25% 分位`.
- The ROI tools wait for this refresh to finish before accepting a canvas
  click, preventing a newly drawn ROI from being placed on a stale image.
- Added static regression coverage that prevents ROI mode changes from
  assigning the view back to `mean`.
- Important environment detail: start commands with `conda run -n
  caiman_latest ...` (or activate that environment) rather than directly
  executing its `python.exe`. Direct execution omits `Library\\bin` from
  `PATH`, which makes NumPy's MKL backend terminate during import with Windows
  exception `0xC06D007F`.
- Updated the Chinese preprocess-label test for the new `显示调节` action.
- Verified with `conda run -n caiman_latest --no-capture-output python -m
  py_compile NewLight_Analysis.py analysis_core.py ui_text_zh.py task_queue.py`.
- Verified the full suite with the same activated environment: `56 passed`.

### Scrollable Parameter Panel

- Replaced the fixed, clipping `Parameters` content frame with a dedicated
  Canvas-backed vertical scroll area and visible right-side scrollbar.
- Kept `当前数据任务流` outside that scroll area, so it remains fixed below the
  editable parameters while long motion-correction configurations scroll.
- Added mouse-wheel support while the pointer is over the parameter area and
  reset the scroll position to the top whenever a parameter panel is opened or
  cleared.
- Kept numeric values as precise text inputs rather than replacing them with
  coarse numeric sliders; the new scrollbar exposes all fields and the
  `恢复默认` / `运行` / `清空` controls.
- Reduced parameter-label wrapping width to account for the visible scrollbar
  and avoid horizontal clipping.
- Added GUI static regression coverage for the independent parameter scrollbar
  and scroll-reset methods.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py task_queue.py`.
- Verified `conda run -n caiman_latest python -m pytest -q`: `53 passed`.

### Embedded Configuration Panels

- Extended the right-side `参数` panel into a reusable embedded form surface:
  text fields, readonly choices, checkboxes, file/folder path rows with a
  `浏览` button, grouped actions, colour swatches, expandable help text, and
  in-panel validation/progress feedback are now supported.
- System file/folder pickers remain native Windows dialogs only when the user
  explicitly selects `浏览` or a file/folder source action. Other configuration
  interaction no longer creates a separate `Toplevel` window.
- Moved open/add data source selection, channel pseudo-colour selection,
  built-in automatic ROI, NeuroSeg3, Atlas Reference Builder, the three-stage
  NeuroAlign workflow, and heatmap AVI settings into the parameter panel.
- NeuroAlign stage previews and heatmap frame previews now render in the main
  image area. Closing either workflow restores the prior movie frame or
  projection; accepting a final NeuroAlign result restores the movie before
  importing its ROI map.
- Added static regression coverage that prevents the migrated entry points
  from calling their legacy dialog classes and protects embedded path,
  checkbox, and action controls.
- Verified `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py task_queue.py`.
- Verified `conda run -n caiman_latest python -m pytest -q`: `55 passed`.
## 2026-07-27

### Invalid Start Frames and Automatic Movie FPS

- Added `无效起始帧数` to the `实验协议` panel. The accepted range is
  `0 <= N < movie frame count`.
- DeepCAD-RT now sends only `movie[N:]` to the non-causal 3D denoising model,
  then restores `movie[:N]` pixel-for-pixel at the front of the result. This
  prevents later anatomical structure from leaking backward into acquisition
  startup/noise frames while preserving the original frame count and timeline.
- DeepCAD preview/save caches include `N`. Changing `N` invalidates the old
  cache and queues a fresh preview instead of silently reusing incompatible
  output.
- Baseline, mean/max/std/25th-percentile projections, ROI trace extraction,
  event averages, and analysis/export paths exclude the invalid prefix from
  baseline/projection statistics. An explicit baseline window starts at
  `max(baseline_start_frame, N)` and keeps its requested duration where frames
  remain.
- Movie FPS is written back to the protocol field on every primary import.
  AVI/MP4/MOV/MKV use the container FPS; two-photon folders use `Image frame
  rate`; TIFF uses ImageJ `fps`, ImageJ `finterval`, OME `TimeIncrement`, then
  a nearby `protocol*.txt`, in that order. TIFF without rate metadata falls
  back to `10 Hz` and still requires user confirmation.
- Added regression coverage in `tests/test_baseline.py`,
  `tests/test_deepcadrt_short_movie.py`, `tests/test_movie_fps.py`, and
  `tests/test_gui_static.py`.
- Verified `conda run -n caiman_latest --no-capture-output python -m pytest -q`:
  `70 passed`. No EXE was rebuilt and no sample data was removed or moved.

### Dual ROI Engines: CaImAn and Authorized NeuSuite

- Replaced the visible `内置自动 ROI` and generic COCO `NeuroSeg3 自动 ROI 分割`
  actions with `CaImAn 识别分割` and `快速 ROI 分割`. Both use the embedded
  right-side parameter panel and the single FIFO task controller.
- Added `roi_engines.py`, a versioned NPZ contract that validates image shape,
  names, independent boolean instances, JSON metadata, and aligned numeric
  arrays without importing either model backend. Empty instances are rejected
  on load; overlapping irregular instances remain independent.
- Added `workers/run_caiman_roi.py`. It sets
  `MKL_THREADING_LAYER=SEQUENTIAL` and `KERAS_BACKEND=torch` before scientific
  imports, excludes invalid start frames, runs patch CNMF/CNMF-E from a CaImAn
  memory map, evaluates SNR/spatial-correlation/CNN quality, thresholds each
  spatial component with `threshold_spatial_components(maxthr=...)`, restores
  footprints in Fortran order, and exports masks, traces, scores, and summary.
- Added `workers/run_neusuite_roi.py`. It imports the authorized custom runtime
  through `method.ultralytics`, aliases checkpoint paths from `ultralytics` to
  that package, reads `results[0].masks.data` per instance, restores each mask
  with nearest-neighbor interpolation, and filters by restored pixel area.
- Added the project-local CPU CaImAn environment definition and setup script.
  `.conda_envs/newlight_caiman` passed direct NumPy/Torch/Keras/CaImAn imports;
  controlled CNN resources are in `CaImAn_Resources/model`.
- Added `setup_neusuite_runtime.bat` and an offline pure-source fallback for
  `einops`, `efficientnet_pytorch`, and `dill`. The fast worker uses the
  CUDA-enabled `neuroseg3` environment while dependency fallback lives in
  `NeuSuite_RuntimeDeps`; it does not load NeuSuite's incompatible Python 3.10
  `.pyc` files.
- Real retained-sample validation used `eye/data/2/A01/result.avi` read-only.
  Fast ROI returned 38 independent `540x512` masks with areas 53-599 px^2 and
  confidence 0.264-0.716. CaImAn on a 120-frame central crop, excluding five
  startup frames, returned 64 `192x192` masks and aligned `64x115` traces plus
  SNR, spatial-correlation, and CNN arrays.
- Updated `NewLight_Analysis.spec` to package the authorized NeuSuite model and
  custom runtime, `NeuSuite_RuntimeDeps`, and CaImAn CNN resources, and to stop
  packaging the generic NeuroSeg3 COCO assets. No EXE was built in this update.
- Full pytest passes with `102 passed`; Python compilation and a Tk app
  construction smoke test pass. The known Conda/OpenCL `temp.txt` activation
  noise remains harmless. No validation sample was deleted, moved, or changed.

## 2026-07-28

### Unified ROI Colors and Embedded ROI List

- Added a stable index-based ROI palette in `analysis_core.py`. ROI colors no
  longer depend on the total ROI count, so adding a later ROI does not recolor
  the existing ones.
- Applied the same color source to ROI image outlines and labels, exported
  dF/F curves, exported trial-average curves, the interactive dF/F window, and
  the interactive trial-average window. Stimulus-aligned single-ROI figures
  intentionally retain gray trials, a black mean, and a red dashed stimulus
  marker as previously specified.
- Added `显示 ROI 列表` to the ROI drawing toolbar. It opens an embedded table
  in the right-side parameter panel with a color swatch, ROI name, and mask
  area in pixels; no additional popup window is created.
- The visible ROI table refreshes immediately after ROI import/replacement,
  drawing, deletion, or clearing. An empty state is displayed when there are
  no ROI masks.
- Added `tests/test_roi_colors.py` and GUI static coverage for the shared
  palette, trace colors, embedded table, toolbar action, and mutation refresh.
- A Tk smoke test confirmed that a visible two-row ROI list refreshes to one
  row after deleting the last ROI. Full source validation passes with `111
  passed`. No EXE was rebuilt and no sample data was changed.

### Adaptive ROI Guidance Design and Plan

- Confirmed the design for iterative user-guided ROI fitting shared by
  `快速 ROI 分割` and `CaImAn 识别分割`. The feature is calibration over cached
  candidates, not model-weight training.
- Current ROI masks are protected examples. The planned boundary refinement is
  local and free-form; examples cannot disappear, merge, split, or jump to
  another structure. Protected examples that fail the active quality preset
  remain in output with a trailing `*` quality marker.
- The plan combines quality presets, NeuSuite learned confidence, CaImAn SNR /
  spatial correlation / CNN quality, fixed low-compute convolution responses,
  shape, local contrast, and temporal features. Manual examples receive more
  fitting weight than loaded or model-generated examples.
- Fast ROI area autofill is specified as `0.9 x smallest` and `1.1 x largest`
  for two or more examples. With one example, only the maximum changes and the
  existing minimum is retained.
- Candidate banks are session-local and reusable after the user adds missed
  ROIs. Movie/preprocessing/model-generation changes invalidate them; ROI-only
  changes trigger a cheap refit. ROI revisions prevent stale background tasks
  from overwriting newly drawn examples.
- Added the reviewed design at
  `docs/superpowers/specs/2026-07-28-adaptive-roi-guidance-design.md` and a
  seven-task TDD plan at
  `docs/superpowers/plans/2026-07-28-adaptive-roi-guidance.md`.
- This entry records planning only. Production code and tests have not yet been
  changed for adaptive fitting; the source baseline remains `111 passed`.

### Adaptive ROI Guidance Implementation

- Implemented user-guided calibration for both `快速 ROI 分割` and
  `CaImAn 识别分割`. This selects/refines cached candidates and never updates
  NeuSuite, CaImAn, or CNN model weights.
- Added `高召回 / 均衡 / 高精度 / 自定义` presets. Fixed preset values are
  Fast confidence `0.10 / 0.25 / 0.40`; CaImAn SNR `1.5 / 2.0 / 2.5`; spatial
  correlation `0.70 / 0.80 / 0.90`; CNN score `0.70 / 0.90 / 0.99`; and robust
  similarity limits `3.0 / 2.3 / 1.7`.
- Fast area autofill preserves both values with no ROI, changes only maximum
  with one ROI, and uses `round(0.9 * smallest)` / `round(1.1 * largest)` with
  multiple ROIs. CaImAn uses the median equivalent diameter of current masks.
- Existing ROIs are protected and refined locally within `2-12 px`. They are
  never removed, merged, split, or moved to another cell. Weak protected masks
  remain with exactly one trailing `*` and aligned provenance metadata.
- Added weighted median/MAD fitting over shape, contrast, fixed Gaussian/Sobel/
  LoG responses, temporal activity, NeuSuite confidence, and CaImAn quality.
- Added permissive worker modes. Fast generates candidates down to confidence
  `0.05`; CaImAn exports every non-empty component with aligned traces, SNR,
  spatial correlation, CNN score, component index, and preset-accepted flag.
- Fast and CaImAn candidate banks are separate and session-local. Signatures
  include movie generation, shape, invalid frames, relevant projection/window,
  model identity, and generation settings. ROI/preset-only changes reuse banks;
  movie/preprocessing/model-generation changes invalidate them. Movie and ROI
  revision checks prevent stale background output from overwriting user edits.
- Tk smoke ran two Fast adaptive fits around a manual ROI update; the worker
  ran once, the second fit reused its bank, metadata stayed aligned, and no
  duplicate `**` name was produced.
- Protected sample `eye/data/2/A01/result.avi` stayed read-only and unchanged
  (`800 x 540 x 512`, `10 Hz`). The final read-only smoke used an
  `80 x 256 x 256` Fast crop and returned 9 candidates; two adaptive passes
  returned the same result from that bank. A `50 x 128 x 128` CaImAn crop
  returned 35 candidates with aligned traces, SNR, spatial correlation, CNN,
  component-index, and preset-accepted arrays. SHA-256 remained
  `48106b31ba131d1c7dcb80bb1e745349844e7b936150100008df4d423917fad5`.
- Real Fast inference exposed missing `py-cpuinfo`. Added version `9.0.0` to
  runtime requirements, offline copy, and setup verification. CaImAn now maps
  empty optional quality output to aligned NaN values while still rejecting
  non-empty misaligned arrays.
- Review hardening added normalized-centroid candidate matching so shifted
  masks from the same cell cannot be appended twice. Matched model masks now
  aid protected-boundary refinement and active-preset quality marking.
- Low-quality status is recomputed on every adaptive pass, so a successful or
  more permissive rerun can remove an obsolete `*`. Stable `base_name` values
  now survive ordinary add/delete operations.
- Automatic full-frame ROI creation now uses `set_rois()` and increments
  `roi_revision`. Candidate-mode artifacts must include every required aligned
  quality array; missing arrays fail closed instead of receiving ideal scores.
- Candidate cache identities now include NeuSuite weights, runtime source and
  supplemental dependencies, plus the CaImAn environment metadata and CNN
  resources.
- Model-generated protected ROIs that are absent from the current permissive
  bank remain present but are marked as not reproduced. CaImAn runtime identity
  now follows the same local-prefix or named-environment fallback used by its
  worker wrapper.
- Final verification: `169 passed`; focused adaptive verification is
  `100 passed`; compilation, Tk state smoke, retained-sample smoke, and
  `git diff --check` passed. No EXE was built and no validation sample was
  moved, deleted, or overwritten.

### ROI List Selection Highlight

- Connected the embedded ROI list to the main image overlay. Selecting a row
  immediately keeps that ROI boundary in its assigned color at `3 px`
  thickness until another ROI is selected.
- The selected ROI number is also enlarged and bolded. Other ROI outlines keep
  their existing stable colors and `1 px` thickness.
- Closing/replacing the ROI list or changing the ROI collection clears the
  highlight, preventing stale indices.
- Added overlay rendering and GUI binding regressions plus a real Tk selection
  smoke test. Final verification: `171 passed`; focused tests `41 passed`;
  compilation and `git diff --check` passed. No EXE was built.

### Independent Invalid-Edge Crop

- Added `自动裁剪无效边缘` as an independent preprocessing action. It is not
  embedded in either Fast Motion Correction or CaImAn motion correction.
- The estimator samples at most 96 frames and detects only contiguous outer
  bands that are stably duplicated or spatially empty. Low-information movies
  fail conservatively to the full frame, and the result keeps at least a
  `16 x 16` region.
- The fitted rectangle is drawn over the main preview with outside shading,
  four edge handles and four corner handles. Users can drag the rectangle,
  edges, or corners, then refit, confirm, or cancel from the embedded parameter
  panel without opening a dialog.
- Confirmation runs through the global FIFO queue and crops the current
  temporary movie plus every loaded channel with identical exclusive bounds.
  The imported source path/file is never written. Permanent output still
  requires the existing Save Current Movie action.
- Existing ROI masks are cropped with the same bounds; masks that become empty
  are removed while names and metadata stay aligned. This crop operation stores
  ROI snapshots in its undo entry, so Undo restores movie, channels, colors,
  ROI masks, names, and metadata together.
- Added nine pure-core crop/estimation tests plus independent-entry, embedded
  interaction, FIFO/state-alignment, cancellation, undo, and localization
  regressions. A real Tk smoke fitted `(4, 3, 67, 62)`, dragged one edge and the
  full rectangle, cropped a two-channel movie and ROIs, verified the source
  array unchanged, then restored all spatial state with Undo.
- Review hardening requires every automatic trim depth to be supported by at
  least 95% of sampled frames, reads the active movie
  when a queued fit actually starts, preserves confirmation locking across
  panel changes, and reports missing input only in the embedded panel. The real
  Tk drag/crop/undo workflow is now an automated behavioral regression.
- Final verification: `188 passed`; focused crop/GUI/localization tests `63 passed`; key
  source compilation, Tk smoke, and `git diff --check` passed. Tests used
  `.conda_envs/newlight_caiman/python.exe` because the named `caiman_latest`
  environment currently crashes while importing NumPy native libraries. No
  EXE was built and no validation sample was read, moved, deleted, or written.

### dF/F Peak Marker Window

- Extended the existing `峰值检测` analysis from a text-only count message to
  a dedicated `dF/F 峰值检测` graph window.
- The FIFO analysis operation now retains every exact index returned by
  `core.detect_trace_peaks()` together with the processed dF/F traces, ROI
  names, and movie sampling rate. The plotted marker count therefore matches
  the existing `Peak_Count` algorithm exactly; no detection threshold changed.
- The graph shows one ROI at a time through a readonly ROI selector, avoiding
  unreadable vertical offsets when many ROIs have different amplitudes. The
  selector and plot title display that ROI's peak count, while the trace keeps
  the same stable color as its ROI overlay.
- Each detected peak is marked at the exact
  `(peak_time, dF/F[peak])` coordinate with a high-contrast circular point.
  Non-finite or non-positive movie frame rates are rejected before detection
  or plotting instead of producing invalid time coordinates.
- Added the translated Matplotlib toolbar so users can pan, zoom, reset, and
  save the peak graph. The old text-only message box was removed; a compact
  per-ROI count summary remains in the run log.
- Hardened the shared FIFO analysis wrapper while adding this window. Movie,
  ROI, protocol, trigger, and trace-processing snapshots are now captured by a
  main-thread `on_start` hook when the operation actually reaches the front of
  the queue. Completion rejects results if the movie identity, ROI revision,
  or protocol/trace signature changed, preventing old traces from being
  written into newer data. ROI-dependent exports declare that dependency even
  when they do not extract traces.
- A queued trace task that reaches a new movie without ROI now creates the
  formal `Global_ROI` through the normal ROI mutation path before snapshotting;
  it no longer writes a local-only global trace into otherwise empty ROI state.
- Headless analysis exports now construct `Figure` objects with
  `FigureCanvasAgg` directly. Importing the Tk GUI can no longer make background
  PNG/chart exports accidentally create a Tk window through Matplotlib's global
  backend.
- Configured portable Chinese font fallbacks for Matplotlib (`Microsoft YaHei`,
  `SimHei`, `Arial Unicode MS`, then `DejaVu Sans`) so the new graph title and
  axes do not render as missing glyphs.
- Added operation/plot and FIFO snapshot regressions. A real Tk window smoke
  selected ROI-A then ROI-B, preserving their exact `3 / 2` peak indices and
  reporting zero missing-glyph warnings. Final verification: `199 passed, 1
  skipped`; source compilation and `git diff --check` passed. The skipped test
  is the pre-existing full-app auto-crop Tk smoke: this Conda prefix
  intermittently reports a different Tcl/Tk support file as unreadable even
  though each reported file exists and is readable. The dedicated peak-window
  Tk smoke passed in the same environment. No EXE was built and no validation
  sample was used.

## 2026-07-31

### Default Maximized Main Window

- The main window now keeps `1440x920` as its initial fallback geometry and
  schedules `_maximize_main_window()` with `after_idle` so Tk completes its
  first layout before requesting the Windows `zoomed` state.
- Hidden test roots remain withdrawn instead of being forced visible. Platforms
  that reject `state("zoomed")` receive a guarded `attributes("-zoomed", True)`
  fallback.
- Added static and behavioral regression coverage. A real Tk launch reported
  `state=zoomed` with an actual `2194x1163` window. No sample data, models, or
  EXE output were changed.

### Persistent Reusable Processing Workflows

- Added `workflow_core.py`, defining the UTF-8 declarative
  `.nlworkflow.json` format (`NewLight Workflow`, version `1`) and strict
  validation for application marker, non-empty ordered steps, supported
  function IDs, parameter objects, and JSON-compatible values. Chinese labels,
  duplicate actions, and exact ordering survive save/load round trips.
- Extended `AppTask` and `TaskController.enqueue_task()` with copied
  `workflow_step`, `workflow_run_id`, and `workflow_is_last` metadata without
  changing the existing single-worker FIFO behavior.
- Added workflow descriptors to nine movie-processing actions: CaImAn motion,
  fast motion correction, image line-shift correction, Gaussian smoothing,
  median filtering, background subtraction, bleach correction, contrast
  enhancement, and vessel-artifact removal. Manual use and replay share the
  same production methods and parameter normalization paths.
- Added `load_roi` as a reusable workflow action. Manual NPZ, Atlas JSON, and
  atlas-image loading now enters the FIFO with a descriptor containing the
  normalized ROI file path and format; Atlas JSON/images also retain the
  submitted `min_area`. Replay uses the stored values without reopening a file
  or parameter dialog, validates NPZ mask shape against the current movie, and
  stops later same-run steps if the file is missing or incompatible.
- Added `保存当前工作流`. It collects supported completed/running/queued entries
  from the current dataset task history, preserves duplicates and order, skips
  failed/cancelled/unsupported or descriptor-less entries, and reports saved
  and skipped counts. It stores no movie input/output paths, movie data, ROI
  masks, or executable code; `load_roi` stores only its external file reference.
- Added `执行工作流`. It validates the entire file before submission, applies it
  to the currently loaded dataset, and preserves the descriptor on replayed
  tasks so they can be saved again. All steps use one workflow run ID.
- Added stop-on-failure/cancellation behavior. A failed or user-cancelled step
  prevents later same-run workers from touching data, while unrelated manual
  tasks continue through the FIFO. Only the final successful step marks a run
  completed.
- Increased the current-data task canvas from `185` to `250 px` and placed two
  equal-width workflow controls below it. Real Tk checks at `1440x920` and
  `1100x760` confirmed the canvas and both buttons remain visible and the file
  dialog cancel paths are harmless.
- Version 1 intentionally excludes movie imports/channel additions,
  saves/exports, manual ROI tools,
  interactive auto-crop, display-only controls, DeepCAD-RT cache preview, ROI
  segmentation, peak detection, and analysis outputs. Their interaction/path
  or non-chain semantics require separate replay contracts before inclusion.
- Added focused schema, metadata, capture, filtering, replay, invalid-file,
  FIFO failure/cancellation, completion, and UI placement regressions. Future
  user manuals must document the JSON extension, supported/excluded actions,
  current-data execution, preserved order/duplicates, no embedded paths, stop
  behavior, task statuses, and the need to save the processed movie separately.
- Final verification passed in separate clean processes: `235 passed` with
  `tests/test_peak_detection_plot.py` excluded, followed by `11 passed` in the
  peak/Tk module (`246 passed` total). The touched Python files compiled,
  `git diff --check` passed, and real Tk smoke passed at `1440x920` and
  `1100x760`. The portable EXE was not rebuilt for this source feature.

### Continuous ROI Numbering After Deletion

- Added deletion-specific sequence renumbering for system-generated ROI names.
  Deleting an earlier ROI now decrements the numeric suffix of following names
  in the same sequence, for example `AtlasROI1, AtlasROI2, AtlasROI3` becomes
  `AtlasROI1, AtlasROI2` after deleting the former first item.
- Supported generated prefixes are `ROI`, `AtlasROI`, `Fast_ROI`,
  `CaImAn_ROI`, and `NS3_ROI`. Renumbering is deliberately limited to the
  deleted prefix and deletion path; arbitrary loaded/custom region names remain
  unchanged, and ordinary name synchronization still preserves imported names.
- The update changes metadata `base_name` before `sync_roi_names()`, preserving
  low-quality flags and their displayed `*` marker while keeping masks, names,
  metadata, colors, and ROI list rows aligned.
- Added behavioral regression tests for deleting the first generated ROI,
  deleting a middle generated ROI, preserving low-quality metadata, and
  protecting custom names.
- Verification passed: `77` focused ROI/UI tests, the complete suite split into
  `203` non-peak tests plus `11` peak/Tk tests (`214` total), source
  compilation, and `git diff --check`. A real Tk Treeview smoke deleted
  `AtlasROI1` from four entries and read back the visible sequence
  `AtlasROI1, AtlasROI2, AtlasROI3`. No EXE was rebuilt.

## 2026-07-30

### ROI List Clear Action and Parameter Panel Cleanup

- Removed the generic `清空` footer from embedded parameter/property panels.
  It previously called `clear_parameter_panel()` and only replaced the panel
  contents with a placeholder, so its label incorrectly suggested that it
  cleared the feature's data. Panels with an explicit `cancel_command` still
  show `取消` where cancellation has real workflow meaning.
- Added a dedicated `清空全部 ROI` action to `show_roi_list()`. It calls the
  existing `clear_rois()` mutation path, clearing masks, names, quality
  metadata, extracted traces, and incrementing `roi_revision`; the visible ROI
  list then refreshes to its empty state.
- Added regression coverage for both UI responsibilities. A real Tk click
  smoke verified two ROI records were removed together with metadata/traces,
  revision changed once, the empty ROI list stayed visible, and an ordinary
  property panel contained no generic clear button.
- Final verification: the non-peak suite passed `200` tests and the peak/Tk
  module passed `11` tests in its own process (`211` total); source compilation
  and `git diff --check` passed. One combined-process run reached the known
  local Conda Tcl/Tk second-interpreter issue (`tcl_findLibrary` / transient
  `tk.tcl` read failure) before entering the peak test. The affected test passed
  independently, and the complete application UI click smoke passed. No EXE
  was rebuilt for this source-only UI change.

## 2026-07-29

### Portable EXE Rebuild After Peak ROI Navigation

- Reviewed `build_exe.bat` and `NewLight_Analysis.spec` after adding synchronized
  peak-ROI navigation. No new PyInstaller hidden import was needed because the
  existing TkAgg backend collection covers the toolbar and mouse-wheel event
  changes, while `roi_engines.py` and `task_queue.py` are reached through the
  normal import graph.
- Hardened `build_exe.bat` before it deletes the previous release: it now checks
  for the NeuSuite model, bundled NeuSuite runtime dependencies, CaImAn
  resources, and the complete CaImAn/ROI packaging dependency set. Updated the
  completion text to describe NeuSuite instead of the removed NeuroSeg3 bundle.
- Ran `build_exe.bat /nopause` with the `caiman_latest` Python 3.11.15 and
  PyInstaller 6.20.0. PyInstaller, COLLECT, and the frozen OpenCV loader patch
  completed successfully. The portable release is
  `dist/NewLight_Analysis/NewLight_Analysis.exe`.
- Release verification found 13,596 files totaling 4,360,781,440 bytes. It
  includes `NewLight_Worker.exe`, the DeepCAD-RT `.pth`, NeuSuite `.pt`,
  NeuSuite runtime dependencies, CaImAn resources, NeuroAlign, DeepCAD-RT
  source, and patched OpenCV configs. The frozen worker imported all core
  dependencies, the frozen peak Tk navigation smoke passed, and the packaged
  GUI remained alive for a 20-second startup smoke before controlled shutdown.
- PyInstaller reported optional warnings for TensorBoard, Intel/MS MPI, CuPy,
  and unused compatibility imports. None are used by the verified NewLight
  paths; the frozen core import and startup checks passed. No installer was
  generated in this run. Validation samples were untouched.

### Configurable Peak Percentile and ROI Peak Navigation

- Changed the `峰值检测` action to open the embedded right-side parameter
  panel before queueing analysis. The panel exposes `最低峰值分位数 (%)`,
  defaults to `25`, validates the inclusive range `0-100`, and remembers the
  last successfully submitted value in `NewLight_user_settings.json`.
- `analysis_core.detect_trace_peaks()` now computes a per-ROI minimum height
  `Q_p = percentile(dF/F, p)`. A detected point must satisfy both
  `dF/F_peak >= Q_p` and the existing standard-deviation-based prominence and
  0.5-second minimum-distance rules. Raising `p` removes more low peaks;
  lowering it keeps more small peaks.
- The selected percentile is carried with the queued result, shown in the peak
  window title, and included in the run log. Each ROI still uses the exact peak
  indices returned by the core detector.
- The same saved percentile is used by the interactive ROI statistics table,
  ROI statistics export, and complete analysis export, so `Peak_Count` matches
  the markers shown by the peak window. The core API keeps `None` as its
  compatibility default, preserving the former prominence/distance-only
  behavior for callers that do not opt into a percentile.
- ROI-statistics and complete-export tasks declare
  `depends_on_peak_settings=True`. The FIFO `on_start` hook captures the latest
  saved percentile when each task actually begins, carries it through the
  operation context, and includes it in the completion signature. A later
  setting change rejects the stale result instead of applying an old count.
- Added `PeakPlotToolbar` for the peak graph. Back and Forward now select the
  previous and next ROI instead of acting as unused Matplotlib view-history
  controls. Scrolling up/down over the peak canvas performs the same previous/
  next selection; toolbar buttons, mouse wheel, and the ROI combobox stay in
  sync and wrap between the first and last ROI. The main viewer toolbar and
  its scroll behavior are unchanged.
- Removed the peak selector's temporary local `StringVar`. Its Tcl variable
  was deleted when the window factory returned, which could clear the initial
  selection even though `current(0)` had been called. The readonly combobox now
  owns its displayed value and reliably opens on the first ROI.
- Regression coverage verifies the embedded pre-run panel, percentile
  filtering and validation, persistence, legacy core behavior, ROI-statistics
  consistency, exact result propagation, toolbar callbacks, wheel direction,
  and first/last ROI wrapping. A real Tk workflow changed the value from `25`
  to `75`, ran the FIFO task, and opened
  `dF/F 峰值检测 - 最低分位 75%`.
- Final verification after ROI navigation: `209 passed`; focused peak tests
  passed five consecutive runs, Python compilation passed, and
  `git diff --check` reported no whitespace errors. No EXE was built and no
  validation sample was used.
## 2026-08-03 - Animated first-run initialization window

- Optimized `neural_starlight.gif` from 3072 x 2048, 50 frames, about 95.8 MB into `neural_starlight_startup.gif` at 720 x 480, 25 frames, five seconds, about 3.67 MB. Kept the original development asset unchanged.
- Produced and user-approved `docs/previews/initialization-splash.html`; final design uses centered product identity and a bottom three-column row with version, live status, and a 44 x 44 sequential eight-dot bubble loader.
- Added `initialization_splash.py` with Pillow GIF decoding, Tk frame animation, bubble animation, thread-safe progress updates, screen centering, resource fallback, and idempotent cleanup.
- Added progress and dialog-visibility callbacks to `machine_setup.py` for backend verification, boot-state read, display-adapter detection, CUDA verification, driver installation, and completion.
- Integrated the splash into frozen first-run startup in `launch.py`. Source launches and completed machine setup states bypass it. A dedicated `SplashUnavailableError` permits a no-splash fallback without rerunning failed setup work.
- Added optimized GIF collection to `NewLight_Analysis.spec`; packaging tests explicitly reject collection of the original large GIF.
- Verification at this checkpoint: focused setup/splash/packaging suite `30 passed`; real Tk delayed-operation smoke completed in about 1.14 seconds; no real GPU detection, driver installation, ProgramData state mutation, or reboot was performed.
- Final regression: non-peak suite `265 passed, 1 skipped`; isolated peak/Tk suite `11 passed`; Python compilation and `git diff --check` passed. The optimized GIF was verified as 720 x 480, 25 frames, 5000 ms, infinite loop.
- Rebuilt the portable release successfully. `dist/NewLight_Analysis/NewLight_Analysis.exe` was produced at 2026-08-03 15:42:34 with size 80,992,523 bytes. Independent frozen backend verification returned exit code 0; the release contains the 3,850,873-byte optimized GIF, does not contain the original GIF, and contains zero legacy setup/source-launch BAT files.
## 2026-08-03 - Preserve DeepCAD-RT through channel coloring

- Reproduced the reported behavior from source inspection: channel pseudocolor preview returned raw channel RGB before the DeepCAD cache branch, and pseudocolor save returned before all DeepCAD save branches.
- Confirmed that ordinary preprocessing already updates each `converted_channel_movie`; the structural bypass was specific to cache-based DeepCAD rendering/saving rather than a general pseudocolor failure.
- Added `analysis_core.blend_channel_movies()` with strict channel-count and shape validation.
- Added `deepcad_denoised_channels` and changed DeepCAD preview generation to process each available grayscale channel independently. The combined denoised analysis movie is derived from those outputs.
- Changed pseudocolor frame and projection rendering to blend raw and corresponding denoised channel data before RGB composition. Cache keys now include denoised channel identities and weight.
- Extended pseudocolor AVI/TIFF writers with optional per-frame DeepCAD overlays, avoiding a full resident blended movie.
- Updated pseudocolor save and separate grayscale channel save routing so DeepCAD is applied before output mapping. Saving before preview cache completion now runs the same per-channel model path and fills the cache afterward.
- Focused verification reached `78 passed` before full-suite validation. A direct real-model smoke attempt was terminated by the terminal host timeout and produced no result; it is not counted as successful evidence.
- Final source regression after the routing fix: non-peak suite `272 passed, 1 skipped`; isolated peak/Tk suite `11 passed`; Python compilation and `git diff --check` passed. `example/twophone.avi` remained unchanged at SHA-256 `3FDA062903E7F1AD8FF79F26857CC6F3C73C23D3F76094FDAB6622710AAD27BA`.
- Rebuilt the portable release after the fix. `dist/NewLight_Analysis/NewLight_Analysis.exe` was produced at 2026-08-03 16:43:05 with size 80,997,193 bytes. Independent frozen backend verification returned exit code 0; NeuSuite, CaImAn, and DeepCAD-RT loaded, the optimized startup GIF remained bundled, and the release root contained zero legacy BAT files.

## 2026-08-03 - CaImAn multi-scale cell-size ROI segmentation

- Replaced the previous single-diameter default with `范围自适应（推荐）`: minimum, geometric-middle, and maximum representative cell diameters are processed as independent CaImAn candidates. `快速单尺度` preserves the former single-diameter run for compatibility and rapid tests.
- Added `从当前 ROI 填入直径范围`. It estimates equivalent diameters from hand-drawn ROI masks, applies small margins when both small and large examples exist, and changes only the maximum when a user supplies one example.
- Added `roi_adaptation.caiman_multiscale_diameters()` to skip scales with identical effective `gSig`. Added a pure multiscale fusion routine that only merges genuine spatial duplicates, retains the higher CaImAn quality candidate, and keeps all mask-aligned arrays plus scale provenance.
- Added `analysis_core.merge_caiman_multiscale_roi_results()`, which writes a combined NPZ/JSON artifact with effective scales, per-ROI `scale_diameter`/`scale_gsig`, source artifact paths, and cross-scale duplicate count.
- Integrated multiscale execution into both ordinary and adaptive CaImAn paths. Runs remain sequential within the existing single FIFO task worker; cancellation is checked between scales. The GUI reports effective scale count at queue time and reports scales plus removed duplicates at completion.
- Added focused regression cases for range inference, `gSig` deduplication, quality-aware duplicate replacement, preservation of adjacent correlated cells, merged artifact provenance, and GUI exposure. Verification: `55 passed` for ROI adaptation/backend wrapper tests and `44 passed` for GUI static tests. Python compilation and `git diff --check` also passed. The persistent OpenCL `temp.txt` message originates from the local CaImAn Conda environment cleanup after successful execution; it is not a test failure.

### Follow-up: strange default result on twophone sample

- Inspected the user's still-live session artifacts instead of tuning from the screenshot alone. The three default scales returned `24/7/8` candidates at `8/12/18 px`; the merged output contained 36 ROIs after only three duplicate removals.
- Confirmed the apparent corner-like shapes were real, contiguous CaImAn masks rather than a contour-rendering defect. The 24 masks from the `8 px` scale had areas `24-75 px^2`, SNR `0.52-1.13`, and mostly near-zero spatial correlation, while CNN scores were almost all `0.9-1.0`.
- Traced this to CaImAn's metric-union selection and the application's multiscale union: CNN-only small-scale passes were considered accepted and ranked highly, even though they had no temporal or spatial support.
- Changed the derived default range from `0.67x-1.5x` to `1.0x-2.0x` the legacy diameter (`12-24 px` for the normal `12 px` default), including one-time recognition and migration of the previously generated `8-18 px` pair.
- Added multiscale non-CNN evidence gating for direct runs. A component now needs configured SNR, configured spatial correlation, or reproduction at another scale. Adaptive candidate mode remains unfiltered until its established adaptive quality-selection stage; fast single-scale compatibility remains unchanged.
- Replayed fusion against the exact existing artifacts: 27 CNN-only candidates were rejected, three duplicates were merged, and the result fell from 36 to 9 ROIs with retained areas `105-469 px^2`; no `8 px` component survived. Focused regression passed `102` tests.

### Follow-up: CaImAn run button did nothing

- Reproduced the click path with a direct GUI handler test. `_run_caiman_roi_from_panel()` raised `NameError: default_min is not defined` before protocol application, settings persistence, or task queue submission.
- Moved legacy/default-range calculation into `_caiman_diameter_defaults(saved)` and reused it during both panel creation and execution. The regression test now proves a valid range-mode submission calls `enqueue_task()` once.
- Added a parameter-action exception boundary so unexpected callback failures are visible in the right-side feedback and run log with traceback instead of being silently swallowed by Tk.
- Focused regression passed `125` tests after updating the refactored static contract.

### Follow-up: adaptive fit failed with `NoneType.masks`

- Traced the reported background exception to `_enqueue_adaptive_roi()`. A misplaced `else` attached the CaImAn generation block to `if not reused`; a normal first run (`reused=False`) therefore left `bank=None` and immediately failed in `adapt_candidate_bank()`.
- Restored the intended nested engine branch and moved `_candidate_bank_from_result()` to the shared cache-miss path after either backend completes.
- Added a functional cache-miss regression that executes the actual queued worker closure and verifies backend invocation, candidate-bank construction, and adaptive selection.
- Focused regression passed `126` tests across workflow GUI behavior, GUI static contracts, ROI adaptation, and backend wrappers.

## 2026-08-03 - NeuroAlign uses the current processed video stream

- Traced the screenshot error to `_collect_neuroalign_panel_values()`, which called `float()` on the valid comma-separated `tps_smooth_candidates` value `12,8,5,3,1`.
- Added typed NeuroAlign configuration parsing. Integer controls remain integers, scalar controls become floats, and TPS smoothness candidates remain a validated normalized comma-separated list.
- Removed the registration-video selector and legacy saved video value from the active right-side NeuroAlign panel. Registration input is now always the current in-memory analysis movie rather than `state.source_path`.
- Added a session-temporary, streaming AVI snapshot writer. It avoids allocating a full second rendered movie, preserves one intensity mapping across frames, prefers lossless FFV1, and falls back to MJPG where required by OpenCV.
- Bound the three-stage wizard to one movie object/generation and added stale-result rejection so stages cannot silently mix preprocessed and original movies.
- Added seven focused tests for parser behavior, panel fields, settings persistence, snapshot location/identity, worker backend routing, generation invalidation, and decoded AVI dimensions/content.
- Verification: NeuroAlign plus GUI static suite `51 passed`; workflow GUI suite `24 passed`; Python compilation and `git diff --check` passed before the documentation update. No EXE was built and no sample data was modified.

## 2026-08-04 - NeuroAlign central contour remained unmatched

- Rechecked the user's latest outer preview and the actual `example` run artifacts. The subject mask had two bilateral connected components, but the worker still called `largest_contour_from_mask()`, so the affine fit received only one hemisphere while the Atlas outer polygon represented both.
- Added `bilateral_outer_contour()` in `neuroalign_step_worker.py`. It joins the selected left/right components only at their natural top and bottom overlap rows, preserving the longitudinal fissure for the midline detector and leaving `subject_mask.npy` untouched.
- Offline replay on the current output improved the initial affine brain IoU from `0.354` to approximately `0.86`, reduced midline error from `15.457 px` to approximately `5 px`, and restored the transformed Atlas width from approximately `208 px` to approximately `418 px`.
- Added `tests/test_neuroalign_bilateral_contour.py` for bilateral coverage and non-mutation of the saved mask. Focused NeuroAlign/current-stream/GUI verification passed `53` tests; Python compilation and `git diff --check` passed. No EXE was built and no validation/sample data was deleted.

## 2026-08-04 - Hide stale Atlas Builder ROIs during NeuroAlign preview

- The latest screenshot showed the new bilateral outer fit was working (`mean contour error = 27.287 px`, `midline error = 5.890 px`), while colored Atlas regions remained at the upper-left.
- Traced those colored regions to the old ROIs already stored by Atlas Reference Builder. They were being drawn by the common main-view redraw layer on top of the NeuroAlign preview; they were not an untransformed Atlas output from the current stage.
- Updated `redraw()` to hide existing ROI overlays only for `neuroalign_preview`. Cancel/close restores the original view, and final acceptance still replaces the ROI list with the warped Atlas result.
- Added a GUI static regression for preview isolation. Focused NeuroAlign/current-stream/GUI verification passed `54` tests; no EXE was built and no sample data was modified.

## 2026-08-04 - Updated the user manual after NeuroAlign revisions

- Used the user's edited `docs/NewLight_Analysis_User_Manual.docx` as the source and applied local content updates rather than replacing the document structure.
- Updated release instructions, first-run administrator/CUDA behavior, current processed-video routing, session-scoped NeuroAlign snapshots, bilateral contour troubleshooting, old Atlas Builder ROI preview isolation, and the NeuroAlign FAQ.
- Final structural check: `301` paragraphs, `38` tables, `8` embedded visuals, and `22` rows in the FAQ table. The final file is `docs/NewLight_Analysis_User_Manual.docx`.
- The bundled DOCX renderer could not run because LibreOffice/`soffice` is absent on this machine. Existing missing image alt-text findings were left unchanged because this task was a content update, not an accessibility redesign. No EXE was built and no sample data was modified.

## 2026-08-04 - Repository cleanup and release preparation

- Protected local experiment data by adding `eye/` to `.gitignore`; existing `2/` and `example/` validation data remain untouched.
- Kept the portable release directory and the installer outside normal Git tracking. The installer is `Output/NewLight_Analysis_setup.exe` (SHA-256: `AED6D7EC02F9DE6414BD3BAD52DC3ACC1BB8EE45656DDD76A166E2EF73E1BA8A`).
- Excluded the uncompressed 100 MB startup GIF from GitHub tracking; the packaged startup asset is `neural_starlight_startup.gif`.
- Python compilation passed and the full `caiman_latest` test run passed: `307 passed, 15 subtests passed`. The CaImAn OpenCL cleanup message remains a non-fatal environment warning.
- Pushed branch `codex/dual-roi-engines` to `https://github.com/AzuRui/NewLight_Analysis.git`.
- GitHub Release upload was rejected because the installer is `2,396,163,952` bytes and GitHub limits a single release asset to less than `2,147,483,648` bytes. The empty temporary release was deleted. Use external artifact storage or split/reassemble assets for distribution.

## 2026-08-04 - Added build environment and EXE README

- Added `BUILD_README.md` with the Windows build prerequisites, Conda setup,
  CUDA/NVIDIA constraints, portable EXE workflow, installer workflow,
  backend verification, troubleshooting, and GitHub large-file limitation.
- Linked the build guide from `README.md` and added a packaging documentation
  contract test.

## 2026-08-04 - Chinese README and Git LFS guidance

- Rewrote the user-facing `README.md` in Chinese while preserving commands,
  paths, model names, algorithm names, and the user's recent build guidance.
- Added Git LFS guidance explaining pointers, storage/bandwidth quotas,
  collaborator requirements, Release separation, and why the current
  `2,396,163,952` byte installer still exceeds the common 2 GiB per-file limit.

## 2026-08-04 - PyInstaller dependency slimming experiment

- Added a conservative `slim_excludes` list to `NewLight_Analysis.spec` for
  unused Jupyter/Panel/Bokeh/PySide6/OpenVINO/PyAV/imagecodecs and optional NWB
  schema stacks.
- Built an isolated comparison package under ignored `dist_slim2_20260804`;
  portable size decreased from approximately `4.08 GB` to `3.75 GB`.
- Frozen verification passed for bundled Python, CUDA/cuDNN, NeuSuite, CaImAn,
  and DeepCAD-RT. No CUDA/PyTorch DLLs were removed.
- Inno Setup is unavailable on this machine, so the compressed installer size
  was not measured in this experiment. Measure it with
  `build_full_release.bat` on a machine with `ISCC.exe`.

## 2026-08-04 - Added slim2 Inno Setup packaging script

- Added `NewLight_Analysis_slim2_setup.iss` targeting the isolated
  `dist_slim2_20260804\NewLight_Analysis` package.
- Added `build_slim2_installer.bat` to validate the slim package, locate Inno
  Setup 6, and produce `Output\NewLight_Analysis_slim2_setup.exe`.
- Configured solid `lzma2/ultra64`, a separate compression process, maximum
  fast bytes, and two LZMA2 block threads. The installer was not built here
  because `ISCC.exe` is unavailable.

## 2026-08-04 - Split DeepCAD-RT into an optional CUDA addon

> Historical intermediate design. This was superseded later the same day by
> the complete GPU worker split below; the active install path is now
> `_internal\GPU_Addon` and the core contains no Torch/CUDA runtime.

- Removed DeepCAD-RT source and `DeepCADRT_Model\*.pth` from the core
  PyInstaller bundle. Shared Torch/CUDA DLLs remain because NeuSuite and other
  GPU backends load the same runtime libraries.
- Added a pinned GitHub Release URL and SHA-256 manifest. After NVIDIA/CUDA
  validation, first-run setup downloads, verifies, and safely extracts the
  addon into `_internal\DeepCADRT_Addon`.
- AMD/Intel and CPU-only systems skip the addon while retaining non-DeepCAD
  features. Download failure is reported without blocking the rest of the app.
- Simplified `build_deepcad_addon.bat` to package only DeepCAD source and model
  files, without requiring Conda or duplicating shared CUDA DLLs.
- Focused packaging and machine-setup verification passed: `36 passed`. No EXE
  or Inno Setup installer was built in this change.

## 2026-08-04 - Split the complete CUDA runtime into a GPU addon

- Changed the core PyInstaller spec to exclude Torch, TorchVision, timm,
  NeuSuite, and CUDA DLLs when `NEWLIGHT_BUILD_MODE=cpu`. The core keeps
  CaImAn/OpenCV CPU workflows and contains no Torch runtime.
- Added `NewLight_GPU_Worker.spec` and `build_gpu_addon.bat`. The GPU addon
  contains CUDA Torch/runtime DLLs, `NewLight_GPU_Worker.exe`, DeepCAD-RT source,
  and the trained model.
- Added multipart GPU addon downloads. The final 2,580,860,592-byte archive is split
  into two GitHub-compatible assets, reassembled and hash-verified during first
  startup before extraction to `_internal\GPU_Addon`.
- GPU worker build verification passed with Torch 2.10.0, CUDA available, and
  NVIDIA GeForce RTX 4080. The two Release assets were uploaded to the private
  `gpu-addon-v1` release. External users require a public asset host or an
  authenticated download mechanism.
- The final rebuilt core portable directory is 1,102,414,238 bytes (about
  1.027 GiB) and contains zero
  Torch/CUDA files. Focused packaging/backend verification passed: `60 passed`.
  No Inno installer was built in this change.
- 2026-08-05: Fixed split GPU addon DeepCAD-RT startup failure caused by the
  missing frozen `skimage.io` module. Replaced the only DeepCAD `skimage.io`
  writer use with `tifffile.imwrite` and added a runtime fallback in
  `workers/run_deepcadrt.py` for old addons. Verified the existing GPU worker
  can import `deepcad.data_process`; rebuilt the CPU portable package and
  verified the updated worker script was bundled. Added a build-script check
  so missing `check_backends.bat` fails the build instead of producing an
  incomplete directory.
- 2026-08-05: Fixed the subsequent split-addon DeepCAD failure
  `cv2 ... recursion is detected`. The addon had retained an absolute
  `D:/anaconda3/envs/caiman_latest` OpenCV loader path. Because NewLight runs
  DeepCAD headlessly, moved the optional movie-display cv2 import behind the
  display functions and installed a headless cv2 placeholder in the worker
  for compatibility with already-downloaded addons. Verified the full frozen
  import chain (`deepcad.test_collection`) in `NewLight_GPU_Worker.exe`, ran
  `tests/test_deepcadrt_short_movie.py` (`5 passed`), and rebuilt the CPU
  portable package and core installer.

- 2026-08-05: 修复拆解版核心包的三个 worker 依赖错误：CaImAn worker 在导入阶段
  安装无 Notebook 的 `IPython.display`/`ipywidgets`/`holoviews` 兼容层，CPU
  PyInstaller 核心恢复 CaImAn 必需依赖；`roi_engines.py` 显式进入 `_internal`。
  同时修复 GPU 独立 worker 对核心共享 ROI 模块的查找，并在 GPU 扩展安装和
  `build_full_exe.bat` 中自动同步该模块，兼容已有 GPU 扩展压缩包。
  最终冻结包导入测试和 CaImAn 刚性运动矫正烟雾测试通过，真实 `twophone.avi`
  CaImAn ROI 输出 14 个组件；全套测试 `303 passed`。重新生成：
  `dist\NewLight_Analysis` 和 `Output\NewLight_Analysis_Core_Setup_v1.0.1.exe`。

- 2026-08-05: 修复编译版无法启动的问题。`launch.py` 现在只在源码模式检查
  Python 包；PyInstaller 模式直接使用 `_internal` 内置依赖，避免将
  `openpyxl` 误报为缺失，也不再提示用户运行 `run_NewLight_Analysis.bat`。
  Inno Setup 同时排除 `run*.bat`、`build*.bat`、`setup*.bat`、`.spec` 和
  `.iss` 开发文件。新增启动回归测试后全套测试为 `304 passed`；冻结版进程
  启动验证通过，核心安装包重新生成于 2026-08-05 14:49。

- 2026-08-05: 修复其他电脑覆盖安装后 `cv2` 报
  `ImportError: DLL load failed ... 找不到指定的程序`。根因是 Inno Setup
  覆盖安装不会删除旧文件：旧包残留的 `cv2/config-3.11.py` 会优先于新包的
  `config-3.py` 被加载，从而把旧 `cv2.pyd` 与新 OpenCV DLL 混用。
  核心版和完整版安装脚本现在会在复制新文件前删除核心 `_internal\cv2`、
  根级 `opencv*.dll` 和 `opencv*.exe`，但保留 `_internal\GPU_Addon`。
  本地测试安装包提升为 `v1.0.2`；冻结 `cv2 5.0.0` 导入、后端检查和
  `304 passed` 均通过。核心安装包 SHA-256：
  `A4681B1A67036885FC1E2A4274960439DD46263EE7694A940D90E486DE8973B1`。

- 2026-08-06: 修复目标电脑 CaImAn 运动矫正与 ROI 分割在
  `CNMFParams` 初始化时找不到 `_internal\caiman\utils` 的问题。本机此前
  因工作目录是 Git 仓库，`get_caiman_version()` 从 `git rev-parse` 提前
  返回，掩盖了冻结目录缺失；目标电脑无 `.git` 后才触发文件扫描。
  新增 `CaImAn_Resources\RELEASE`（`Version:1.13.1`），冻结 worker 强制使用
  内置 `CAIMAN_DATA`。构建自检现在从非 Git 的 `%TEMP%` 目录实际初始化
  `CNMFParams`。运动 worker 的 `CAIMAN_TEMP` 同时改到用户临时目录，避免
  写入只读安装目录。非 Git 实测：分块运动矫正通过、CaImAn ROI 输出 14 个
  组件、资源目录未创建 temp；全套测试 `306 passed`。最终核心安装包提升为
  `NewLight_Analysis_Core_Setup_v1.0.3.exe`，439,312,353 bytes，SHA-256：
  `7781D2F2BEF28B10A94C48B771F5313E2CD746864808ED6E427B8025DBCA45A4`。
