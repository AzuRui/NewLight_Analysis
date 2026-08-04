# NewLight_Analysis Handoff

Last updated: 2026-08-03

## Project

NewLight_Analysis is a Tkinter desktop GUI for two-photon / neurosurgical imaging analysis. The main workflow is:

1. Load movie data.
2. Configure movie/stimulus timing protocol.
3. Preview frames or projections.
4. Run preprocessing such as motion correction, smoothing, filtering, background subtraction, bleach correction, contrast enhancement, and vessel artifact handling.
5. Define or import ROIs.
6. Extract dF/F traces, run statistics, trial averages, correlations, and heatmap export.

## Main Files

- `NewLight_Analysis.py`: main Tkinter GUI, canvas display, controls, ROI drawing, workflow callbacks.
- `analysis_core.py`: movie I/O, preprocessing, ROI masks, dF/F, statistics, plotting, exports, CaImAn/NeuroSeg3 helpers.
- `launch.py`: startup gate.
- `run_NewLight_Analysis.bat`: launcher.
- `build_exe.bat`, `build_full_release.bat`, `NewLight_Analysis.spec`, `NewLight_Analysis_setup.iss`: packaging.
- `README.md`, `DESIGN_NOTES.md`, `PACKAGING.md`: user/developer notes.

## New Chat Startup Checklist

When a new chat takes over this project, read this file first. Then inspect these items before making changes:

- `Invalid Start Frames and FPS State (2026-07-27)` below: current DeepCAD
  prefix-exclusion and automatic frame-rate contract.
- `WORK_LOG.md`: latest completed work and decisions.
- `git status --short --branch`: whether the working tree is clean.
- `git log --oneline --decorate -5`: recent checkpoints and rollback targets.
- `NewLight_Analysis.py`: especially GUI state, display canvas, ROI controls, heatmap AVI dialog, and workflow callbacks.
- `analysis_core.py`: especially movie I/O, dF/F, ROI processing, heatmap rendering, and export functions.
- `NewLight_Analysis.spec`, `build_exe.bat`, `build_full_release.bat`, `NewLight_Analysis_setup.iss`: packaging path if the task involves compiling or installer generation.

Recommended new-chat instruction:

```text
Please continue the NewLight_Analysis project. First read E:\WorkSpace\NewLight_Analysis\PROJECT_HANDOFF.md and E:\WorkSpace\NewLight_Analysis\WORK_LOG.md, then inspect git status/log before changing files.
```

## Context Safety Policy

At the end of every substantial task, perform a context-safety self-check:

1. If background/context usage is above 70%, update `PROJECT_HANDOFF.md` and `WORK_LOG.md` before starting the next task so the next step can continue from compact, explicit records instead of relying on a long chat.
2. If context compression is needed, do it after a task finishes, not in the middle of reasoning or while a code change is half-complete.
3. After compression, if estimated information distortion or loss is above 70%, tell the user to open a new chat and instruct the new chat to read this handoff file first.
4. If a new chat is opened, the handoff source of truth is this file plus `WORK_LOG.md`, not the memory of the previous conversation.

## Portable Packaging Dependency Contract (2026-08-03)

- Read this section before changing `NewLight_Analysis.spec`, `launch.py`,
  `build_exe.bat`, `check_backends.bat`, the NeuSuite bundle, or the shared
  frozen Worker.
- The authorized NeuSuite custom runtime still imports the deprecated timm
  compatibility entry points `timm.models.layers`, `timm.models.helpers`, and
  `timm.models.registry`. All three must remain explicit PyInstaller hidden
  imports until that external runtime is migrated to current `timm.layers` /
  `timm.models` APIs. A top-level `timm` hidden import is not sufficient.
- `launch.py` must call `multiprocessing.freeze_support()` before dispatching
  the GUI or `NewLight_Worker.exe`. Without it, frozen subprocesses reinterpret
  `--multiprocessing-fork` as a worker script path and exit with code 2. This
  can silently reduce or break model and algorithm multiprocessing even when
  a main process appears to finish.
- `check_backends.bat` is a release gate, not an informational helper. It must
  return nonzero if core imports, the real NeuSuite runtime import, Fast ROI
  model/runtime files, CaImAn motion/ROI resources, or DeepCAD-RT worker/model
  checks fail. `build_exe.bat` must call it before printing `Build complete`.
- Current regression coverage is in `tests/test_packaging_contracts.py` and
  `tests/test_roi_worker_contracts.py`. The 2026-08-03 focused result was
  `21 passed`.
- The 2026-08-03 portable build used Python 3.11.15, PyInstaller 6.20.0,
  PyTorch CUDA 13.0, and cuDNN 92101. The release is
  `dist\NewLight_Analysis\NewLight_Analysis.exe`; the backend executable stays
  under `dist\NewLight_Analysis\_internal\NewLight_Worker.exe`.
- Verification went beyond imports: the frozen Worker ran NeuSuite Fast ROI
  with `--device cpu` on one read-only frame from
  `eye\data\2\A01\result.avi` and returned 15 ROI instances. Never delete or
  modify this or another retained validation sample during cleanup.
- Expected nonfatal build/runtime warnings currently include timm compatibility
  deprecations, DCNv3 AMP decorator deprecations, unused Intel/MS MPI DLLs, and
  the local Conda OpenCL exit-hook `temp.txt` message. Do not classify them as
  fatal when the release gate and real inference smoke both return code 0, but
  investigate any new missing module, DLL, nonzero child process, or absent
  output artifact.

## First-Run Machine Setup Contract (2026-08-03)

- Read `machine_setup.py`, `launch.py`, `check_backends.bat`, and
  `tools\install_nvidia_driver.ps1` before changing startup, privilege, driver,
  or future machine-permission behavior. The detailed design is
  `docs\superpowers\specs\2026-08-03-first-run-gpu-setup-design.md`.
- Only frozen GUI launches enforce first-run initialization. Source
  `run_NewLight_Analysis.bat` remains usable without administrator rights.
  Frozen Worker dispatch must occur before the setup gate so backend child
  processes never open setup dialogs.
- The version-1 machine file is
  `%ProgramData%\NewLight_Analysis\machine_setup_v1.json`. `complete_cuda`,
  `complete_cpu_only`, and `pending_restart` all permit the GUI to open.
  `pending_restart` means only that GPU capability has not been revalidated;
  it is not a startup gate. Do not store future remote credentials,
  authorization, identity, or expiry data in this file without a separate
  security design.
- First initialization must be explicitly administrator-launched. The program
  intentionally does not self-elevate. After a complete record exists, daily
  launches use ordinary permissions. Future administrator-based remote
  permission management is a separate goal and is not implemented here.
- NVIDIA detection uses adapter names and PNP `VEN_10DE`; any NVIDIA device in
  a mixed-GPU system selects the NVIDIA path. Empty WMI/CIM results, unsupported
  GPUs, declined installation, and driver-install failures all record CPU mode
  and permit startup. They disable only CUDA-specific features.
- The CPU core does not include PyTorch CUDA/cuDNN. Those files are in the
  optional `_internal\GPU_Addon`. The installer may ask Windows Update Agent
  for an applicable signed NVIDIA display driver, but it does not install CUDA
  Toolkit. GTX 960 and other old hardware may remain CPU-only when the bundled
  Torch/CUDA worker no longer supports the device.
- `check_backends.bat` modes are security boundaries: no argument runs first
  setup, `/verify-only` may only inspect the release, and
  `/install-gpu-driver` is the only mutating path. `build_exe.bat` and
  `build_full_release.bat` must always call `/verify-only`.
- A successful driver installation writes `pending_restart` with the current
  Windows boot marker and asks whether to restart immediately, with no
  countdown. Declining restart still opens the GUI in CPU mode. Every frozen
  launch inspects `_internal\GPU_Addon`; when present it validates the GPU
  worker, and when a `complete_cuda` machine lacks it the downloader retries.
  No GPU inspection, download, driver, or CUDA failure may block the GUI.
- Tests must mock services and never call live Windows Update or `shutdown`.
  Retained video smoke tests now use only read-only
  `example\twophone.avi`. Never clean, overwrite, move, or delete files under
  `example` during validation.
- 2026-08-03 evidence: final serial source suite `269 passed`; frozen
  backends passed; frozen Worker read three `twophone.avi` frames at
  `(3, 195, 410)`, 40 FPS, with unchanged SHA-256; no ProgramData setup record,
  driver installation, or restart was produced on the development machine.
- Release directories must never contain `setup_caiman_latest.bat` or
  `run_NewLight_Analysis.bat`. Users start only `NewLight_Analysis.exe`.
  Project-root `run_NewLight_Analysis.bat` remains source-only, and root
  `setup_caiman_latest.bat` remains an optional compatibility redirect; do not
  copy either one in `build_exe.bat` or `build_full_release.bat`.

## Current ROI View Behavior (2026-07-24)

- ROI interaction must preserve the active `视图` choice. Entering `圆形 ROI`,
  `自由绘制 ROI`, or `点击删除 ROI` regenerates the selected projection rather
  than forcing a mean image. Supported choices are `均值`, `最大值`, `标准差`,
  and `25% 分位`.
- `on_mode_changed()` records `projection_mode`, queues
  `queue_movie_view_refresh()`, and blocks ROI clicks using
  `roi_view_refresh_pending` until the new projection is on the canvas. Do
  not reinstate an implicit `projection_mode.set("mean")` or a direct frame
  display for ROI interaction.
- On Windows, never validate by directly executing
  `D:\\anaconda3\\envs\\caiman_latest\\python.exe` unless `Library\\bin`
  has been added to `PATH`. That bypasses Conda activation and can make NumPy
  MKL terminate during its BLAS self-check with `0xC06D007F`. Use `conda run
  -n caiman_latest --no-capture-output python ...` or activate the Conda
  environment first; `analysis_core` imports normally with that activation.
  On 2026-07-24, source compilation and the complete test suite both passed
  this way (`56 passed`).

## DeepCAD-RT Short Videos (2026-07-27)

- Keep `workers\run_deepcadrt.py`'s short-movie temporal padding. The upstream
  DeepCAD-RT stitcher only writes the leading part of a single time patch.
  Without padding, a movie at or below the configured `patch_t` can have its
  trailing output frames left as zeros.
- `pad_short_movie_for_temporal_stitching()` edge-pads an input no longer than
  one time patch to `patch_t + temporal_stride`, then the worker crops its
  output back to the original number of frames. This creates both leading and
  trailing time windows and covers every original frame.
- `analysis_core.preserve_invalid_denoised_frames()` is an independent guard:
  nonempty source frame plus all-zero DeepCAD-RT output means the source frame
  is restored before preview/export blending. Do not remove this fallback.
- The 19-frame `eye\data\20260723_A04\bin10.tif` case was verified on the
  GPU: no zero output frames remained and high-frequency content reduced to
  `2.4%` of raw. It required 128 patches rather than 64, so short recordings
  can take about twice as long as the old, invalid implementation.
- Regression coverage is in `tests\test_deepcadrt_short_movie.py`; full suite
  status after this repair: `59 passed`.

## Environment Notes

Known working candidate environments from prior checks:

- `neuroseg3`
- `caiman_latest`
- `deepcadrt`

The `base` environment was not suitable for GUI work because `cv2` failed to import with a DLL load error. `openpyxl` was missing in checked environments, while `pandas` was present in `neuroseg3` and `caiman_latest`.

NewLight's bundled/default DeepCAD-RT model file is:

```text
E:\WorkSpace\NewLight_Analysis\DeepCADRT_Model\E_02_Iter_6416.pth
```

The old DeepCAD-RT `pth\ModelForPytorch\DownloadedModel` path is a download/cache convention in the external DeepCAD-RT project, not the default model used by NewLight. For packaging, keep the trained `.pth` inside `NewLight_Analysis\DeepCADRT_Model`; the PyInstaller spec bundles that folder.

The current packaged release no longer expects target machines to have the original
`E:\WorkSpace\NeuroSeg3`, `E:\WorkSpace\DeepCAD-RT`, or
`E:\WorkSpace\2cafe_analysis\NeuroAlign` folders for normal bundled workflows.
The release folder includes `_internal\NewLight_Worker.exe`, worker scripts,
NeuroSeg3 source/weights/configs, DeepCAD-RT source, NeuroAlign source, the
DeepCAD-RT model, and small runtime compatibility/data files needed by
CaImAn/DeepCAD-RT.

DeepCAD-RT actual denoising still requires CUDA-capable NVIDIA GPU hardware and a
compatible driver on the target machine. The model and Python code are bundled;
the GPU driver stack is still a machine-level dependency.

This is a hard runtime requirement, not an acceleration preference:

- DeepCAD-RT has no CPU fallback in the current application.
- A packaged model, PyTorch, CUDA DLLs, and worker executable do not make it
  runnable on a CPU-only computer.
- A target computer needs a CUDA-capable NVIDIA GPU and compatible NVIDIA
  driver for DeepCAD-RT inference.
- Other NewLight functions that support CPU execution must not be used to imply
  that DeepCAD-RT also supports CPU execution.

## Current UI State

Recent display work restored the Matplotlib navigation toolbar under the main canvas. The redundant custom `Fit View / Zoom In / Zoom Out` row has been removed because the toolbar already covers home/reset, pan, zoom, and save interactions.

The main window is now a three-zone layout:

- left function tabs / controls
- a fixed-width `Parameters` panel
- the main workspace containing the image canvas, Matplotlib toolbar, ROI action row, frame slider, and Run Log

The `Parameters` panel lives between the left function tabs and the image workspace and uses `PARAM_PANEL_WIDTH = 270`, matching the left control column width. The image canvas and Run Log are both in the workspace column to the right of this panel. Display fitting should continue to use the canvas size from the workspace column only, so the image remains centered and aspect-preserved in the remaining visible area.

The ROI action row remains below the navigation toolbar:

- Undo
- Inspect
- Circle ROI
- Freehand ROI
- Delete ROI
- Cancel Freehand
- Delete Last ROI
- status text

Frame slider and run log are below that.

The Data tab `View` panel now only exposes `Mean`, `Max`, and `Std` projection modes. The older `Corr` projection entry and `Show dF/F Heatmap` button were removed from this panel; correlation and heatmap export code still exists elsewhere for Analysis/export workflows.

The same `View` panel also includes a `DeepCAD-RT` toggle and `Weight` input. `Weight` is a raw/denoised blend ratio for preview and saving, default `0.5`, and is clamped to `0.0-1.0`. It is not DeepCAD-RT's backend `overlap_factor`. When enabled, the app runs DeepCAD-RT denoising in the background, stores intermediates in session temp, and blends the cached denoised result only at display/save time. It must not temporarily replace `state.movie`. Saving the current movie while the toggle is enabled exports the blended raw/denoised movie.

The Data tab now also exposes an `Import depth` selector with `Auto`, `16-bit`, and `8-bit`. TIFF imports preserve native 16-bit values in `Auto` / `16-bit` mode and only quantize to 8-bit when the user explicitly asks for it. The core analysis path still runs in `float32`; the bit-depth choice mainly affects how TIFF data are imported and how TIFF output is written.

Simple parameter prompts now render inside the `Parameters` panel through `show_parameter_panel` / `param_dialog` instead of opening small modal popups. Preprocess buttons load their editable parameters into this panel and then run from the panel's `Run` button. Current exposed Preprocess panel parameters include Image Shift `row_parity`, Enhance Contrast `clip_limit`, Detect Vessels overlay `alpha`, and Remove Vessel Artifact `threshold`.

The heatmap AVI dialog now includes:

- `Max display`: fixed maximum heatmap intensity, equivalent to the old `2cafe_analysis` c-axis upper threshold. `auto` keeps percentile scaling.
- `Show colorbar`: toggles the visible `dF/F` colorbar in preview and generated AVI frames. When enabled, the colorbar is rendered in a separate right-side panel appended to the frame so it does not cover the image data.

## Display Fitting Behavior

- The main image view auto-fits the current visible canvas size while preserving the image aspect ratio.
- Window resize and maximize keep the image centered instead of pinning it to the upper-left corner.
- Custom resize logic must not replace TkAgg's own `<Configure>` handler. The canvas now keeps the backend resize binding intact and listens to Matplotlib `resize_event` for redraws.
- The image display uses the current view window ratio when zoomed or panned, so the visible area stays centered and proportionally scaled to the available space.
- `Heatmap only`: removes the original grayscale frame background and renders heatmap values on a white background. If `ROI only` is enabled, non-ROI pixels remain white.

## Display Issue Context

The user previously reported that a 500 x 500 movie was not displayed fully, often appearing around 425 x 450 in the visible area after adjustments or preprocessing. The key requirements are:

- display the full image without cropping
- respect non-square / varying video resolutions
- keep the image centered
- avoid unwanted view resets during ordinary interaction
- when a full reset is intended, make it explicit and reliable

The current code uses Matplotlib axes display in `NewLight_Analysis.py`, especially:

- `on_canvas_resize`
- `fit_view`
- `apply_view_limits`
- `zoom_view`
- `_full_image_limits`
- `_image_axes_position`
- `_apply_image_axes`
- `redraw`
- `_on_axes_limits_changed`

If display debugging resumes, inspect those functions first.

## ROI / Atlas Context

Requirements already discussed:

- If no ROI is selected when extracting traces, use a full-frame global ROI automatically.
- Atlas ROI import should accept image files such as PNG/JPG/TIF, similar to `2cafe_analysis`.
- `load_roi` currently accepts both `.npz` ROI files and image atlas files.
- `atlas_roi` directly imports an atlas image.
- Atlas image parsing is implemented in `analysis_core.process_atlas_image`.
- NeuroSeg3 ROI now uses a dedicated dialog with manual detection-confidence input, a weights path chooser, and a fallback checkbox.
- The GUI keeps NeuroSeg3 mask pixel cutoff fixed at `0.50` for routine use; the backend call still accepts a separate mask threshold if that ever needs to be exposed again.
- Practical NeuroSeg3 confidence values may be much smaller than the usual human-friendly range; `0.002` was observed as a useful starting point for the current dataset.
- Packaged NeuroSeg3 uses a compatibility shim in `workers/run_neuroseg3.py` for PyTorch 2.6+ because older YOLO `.pt` checkpoints need `torch.load(..., weights_only=False)`. If NeuroSeg3 fails again in the current portable output, first run `dist\NewLight_Analysis\check_backends.bat`; it now performs a real temporary-image model prediction, not only a `--help` launch check.
- The toolbar coordinate readout is themed white for readability on the dark background.
- `Built-in Auto ROI` now seeds its `Min area` / `Max area` defaults from the current mouse pixel position when that point lies over image content; the estimate uses local connected-component area as a rough guide.
- The built-in auto ROI dialog labels these fields as `px^2`, and the log now reports an approximate cell area and equivalent diameter so a rough visual cell-size estimate can be converted into the area range more directly.
- `Built-in Auto ROI` also has a `Use last 2 ROIs` helper. It reads the last two drawn ROIs, treats them as size samples, and fills `Min area` / `Max area` from their measured pixel areas.
- This exists because the single-click seed estimator can be very unstable on noisy, ring-like, or heterogeneous images and often returns odd tiny ranges that create strange ROIs.
- `NeuroAlign_atlas_registration_summary.json` now lives in the `NewLight_Analysis` repo root. It summarizes the atlas-builder output contract, the registration pipeline, the effective defaults, the README-recommended trial config, and the first tuning steps to try.
- The merged registration script's defaults are more conservative than the README's strongest recommendation, so the summary explicitly calls out the knobs that matter most: `brain_mask_percentile`, `midline_anchor_count`, `midline_anchor_weight`, `outer_anchor_weight`, `tps_smooth`, `min_inner_ctrl_for_tps`, `max_ctrl_shift_px`, and `adaptive_search_quantile_*`.
- The atlas-builder docstring still mentions the old `build_atlas_from_lines_final.py` run command; it should be updated when the file is touched next.
- The ROI tab now includes `Atlas Reference Builder` and `NeuroAlign` below `NeuroSeg3 Auto ROI` and `Built-in Auto ROI`.
- `Atlas Reference Builder` calls `2cafe_analysis/NeuroAlign/build_atlas_from_lines_autocomplete.py`, saves `atlas_regions_raw.json`, remembers that path, and tries to import it as a preview ROI set.
- `NeuroAlign` calls `2cafe_analysis/NeuroAlign/atlas_registration_merged_bilateral_midline.py` through the `caiman_latest` backend environment, then imports `warped_atlas_regions.json` as the current ROI set.
- `NeuroAlign_atlas_registration_help.txt` is the end-user help text opened by the new Help buttons; keep the JSON summary as developer handoff context.
- `analysis_core.process_atlas_json` converts atlas-region JSON polygons into ROI masks resized to the current frame shape.
- Installed `python-igraph` and `leidenalg` into `caiman_latest`; without them NeuroAlign cannot compute Leiden label maps from video.
- `NeuroAlign_runs/` is ignored by git because it contains generated registration outputs.
- `analysis_core.run_conda_worker` now forces UTF-8 capture to avoid Windows GBK crashes from backend output text.
- Last validation for this integration passed: Python compile, atlas JSON to 26 ROI masks at 500 x 500, NeuroAlign backend imports, Tk GUI construction, and an Atlas Reference Builder run that created `NeuroAlign_runs/test_builder_final/atlas_regions_raw.json`.
- NeuroAlign launch must pass `--atlas_json` explicitly. The registration script's parser has a non-None default of `output/atlas_regions_raw.json`, so relying only on the generated config bundle can make it ignore the selected atlas file.
- Long worker errors should stay in `Run Log`; the main status label is intentionally reduced to a one-line summary to avoid visually overflowing into the image display area.
- NeuroAlign now opens a three-step preview wizard instead of the old one-shot dialog. The steps are outer contour, clustering, and final atlas. `Rebuild` reruns the backend with current parameters; `Use Result` imports `warped_atlas_regions.json` into the main ROI overlay.
- The wizard writes user choices to ignored local file `NewLight_user_settings.json`, so reopening the button restores the last closed parameters instead of resetting to defaults.
- The outer preview is custom-rendered as `outer_fit_preview.png` with the current mean/projection image at 30% opacity plus subject/atlas contour and midline overlays.
- The clustering preview is custom-rendered as `cluster_on_affine_preview.png`, using Leiden labels plus affine atlas boundaries without the mean image.
- `neuroalign_step_worker.py` is the staged backend used by the wizard. It imports `2cafe_analysis/NeuroAlign/atlas_registration_merged_bilateral_midline.py` inside `caiman_latest` and exposes true `outer`, `cluster`, and `final` stages.
- Step 1 writes cached intermediates (`preprocessed_video.npy`, `mean_img.npy`, `subject_mask.npy`, `affine_atlas_regions.json`, `affine_atlas_label_map.npy`) and does not compute Leiden clusters or final warp.
- Step 2 reuses the cached preprocessed video and mask to compute only `leiden_label_map.npy`; it does not run final atlas registration.
- Step 3 reuses `leiden_label_map.npy` and `subject_mask.npy` to run inner matching / TPS / final atlas export. If users skip an earlier step, the worker intentionally errors with a missing-intermediate message.
- The step worker deletes stale downstream files when rerunning earlier stages: Step 1 clears old cluster/final outputs; Step 2 clears old final outputs. This prevents old files in the output directory from looking like they were regenerated by the current stage.
- Step 2 cluster parameters now have explicit GUI defaults from `neuroalign_recommended_cfg`: `functional_unit_mm`, `resolution`, `compactness`, `min_n_segments`, `max_n_segments`, `min_cluster_size_superpixels`, `sparsity_percentile`, `symmetry_reward`, `distance_decay_scale`, and `inner_max_pairs_per_hemi`.
- Blank values from old `NewLight_user_settings.json` snapshots are replaced with current defaults when the wizard opens.
- Step 2 preview fallback now uses Step 1 outputs such as `outer_fit_preview.png` or `outer_registration_overlay.png`; it no longer probes for `subject_inner_boundaries.png` before clustering has been rebuilt.
- Step 3 preview fallback now uses Step 2 `cluster_on_affine_preview.png` before final rebuild; if that is unavailable it falls back to Step 1 previews instead of reporting missing `final_warp_overlay.png`.
- NeuroAlign wizard has a `Back` button for Step 3 -> Step 2 and Step 2 -> Step 1 navigation.
- `neuroalign_step_worker.py` suppresses `FutureWarning` output, and `NewLight_Analysis.clean_backend_log` removes known OpenCL vendor `temp.txt` noise while preserving real errors.
- The Step 1 outer-affine fit is patched at runtime by `neuroalign_step_worker.install_midline_locked_outer_affine`. This keeps detected midline anchors active during affine refinement instead of using only a single averaged midline x value, and logs contour error, midline error, rotation, shear, and anchor count.
- On the 2026-05-13 test run `NeuroAlign_runs/neuroalign_20260513_105405`, the updated Step 1 reported `mean contour error = 13.672 px`, `midline error = 3.998 px`, `rotation = -0.95 deg`, `shear = 0.000`, `midline anchors = 12`.
- A preview-only TPS idea was tested and rejected because it over-deformed atlas polygons; keep Step 1 preview tied to the stable affine result unless a more constrained local preview warp is designed later.
- `workers/run_deepcadrt.py` is the DeepCAD-RT backend worker. It runs inside the `deepcadrt` conda environment, feeds a temporary TIFF stack into `deepcad.test_collection.testing_class`, then returns a denoised TIFF.
- `analysis_core.run_deepcadrt_denoise` performs a preflight model check before writing temporary input data. By default it passes `DeepCADRT_Model\E_02_Iter_6416.pth` to the worker; the worker wraps a single `.pth` file into DeepCAD-RT's required `pth_dir + denoise_model` folder contract.
- The worker must pass relative `datasets` and `results` paths to DeepCAD-RT while running from its own temporary directory. Do not change this back to absolute Windows paths: DeepCAD-RT builds output folder names from `datasets_path`, and `C:\...` introduces an illegal colon that triggers `WinError 123`.
- DeepCAD backend `overlap_factor` is passed as `--overlap` from `analysis_core.run_deepcadrt_denoise`; the GUI `Weight` field does not control it.
- The project-local model `E_02_Iter_6416.pth` requires DeepCAD testing `fmap=32`. `workers/run_deepcadrt.py` infers this automatically from the checkpoint's first convolution shape. If a future model hits `Network_3D_Unet` size mismatch, check `infer_required_fmap` before blaming the model file.
- Packaged DeepCAD-RT/PyTorch CUDA needs the full cuDNN 9 split runtime. `NewLight_Analysis.spec` explicitly collects CUDA/cuDNN DLLs from the build environment's `Library\bin`, including `cudnn*.dll`, `nvrtc*.dll`, `cufftw*.dll`, `cusolverMg*.dll`, and `caffe2_nvrtc.dll`. If a packaged build reports `Invalid handle. Cannot load symbol cudnnGetVersion`, check for missing cuDNN split DLLs in `_internal` and run `_internal\NewLight_Worker.exe -c "import torch; print(torch.backends.cudnn.version())"`.
- `NewLightApp.session_temp_dir` is a per-run OS temp directory removed by `on_close` / `cleanup_session_temp`. DeepCAD-RT, NeuroSeg3, and CaImAn worker intermediates should use `temp_work_dir(...)`, not source-folder `NewLight_temp`, unless the user explicitly asks to preserve intermediates.
- DeepCAD preview is a display/save overlay only. It should not mutate or replace `state.movie`; preprocessing should operate on the current true movie, and DeepCAD display should re-run/cache against that movie after preprocessing changes.
- Current preprocessing buttons are destructive operations: each one mutates `state.movie`, pushes history, clears DeepCAD cache, recomputes baseline/projection, and subsequent preprocessing stacks on top of previous operations. `Save Current Movie` saves that current processed movie, plus DeepCAD blend if enabled/cache-ready.
- Future pipeline refactor idea: introduce a non-destructive preprocessing script/config (for example a JSON list of operations and parameters) that is reapplied for preview and for full-movie export. This would replace destructive mutation with recorded operations while keeping `Save Current Movie` as the point where the whole pipeline is rendered to disk.
- DeepCAD preview runs are token-guarded. If the user changes the loaded movie while a background denoise is running, the stale result is ignored instead of replacing the current cache.
- `Save Current Movie` opens a standard Save As dialog instead of silently writing a fixed output path. The dialog starts in the loaded movie's folder, suggests `result.<source extension>` for `.tif`, `.tiff`, and `.avi`, and falls back to `result.tif` for unsupported source video extensions. Canceling the dialog must not run DeepCAD-RT or write output.
- `analysis_core.save_movie` supports `.tif/.tiff` and `.avi`. TIFF keeps float stack data; AVI uses OpenCV MJPG at the current Movie Hz and converts to 8-bit by 1-99 percentile scaling.
- `NewLight_Analysis.spec` includes `DeepCADRT_Model`, `workers`, `csbdeep`, `neuroalign_step_worker.py`, `NeuroAlign_atlas_registration_help.txt`, `NeuroAlign_atlas_registration_summary.json`, `PACKAGING.md`, NeuroSeg3 source/weights/configs/utils, DeepCAD-RT `deepcad` source, NeuroAlign source, `hdmf` / `pynwb` data files, and `ipyparallel\cluster\shellcmd_receive.py`. These are runtime resources and should stay bundled.
- Frozen OpenCV must be patched after PyInstaller collection. Conda OpenCV writes absolute build-machine paths into `cv2\config.py` and `cv2\config-3.x.py`; if those paths remain in `_internal\cv2`, target machines can fail with `ERROR: recursion is detected during loading of "cv2" binary extensions`. `tools\patch_frozen_cv2.py` rewrites the frozen config files so `BINARIES_PATHS` points to `_internal` and `PYTHON_EXTENSIONS_PATHS` points to `_internal\cv2\python-3.x`. `NewLight_Analysis.spec`, `build_exe.bat`, and `build_full_release.bat` all run this patch.
- `build_exe.bat` / `build_full_release.bat` check that `DeepCADRT_Model\E_02_Iter_6416.pth` exists before building and accept `/nopause` or `--no-pause` for unattended runs. They prefer `conda run -n caiman_latest python` automatically; all conda calls inside the batch files must use `call conda ...` so control returns to the script. The scripts install `setuptools<81` if `pkg_resources` is missing, because PyInstaller/altgraph still needs that compatibility module. Do not run a build unless the user explicitly asks.
- Root `run_NewLight_Analysis.bat` is a source-only development launcher. It always runs `launch.py` from the project root, preferably through the `caiman_latest` conda environment, and must not probe for or launch packaged EXEs.
- `build_exe.bat` writes the portable app directly under `dist\NewLight_Analysis` and generates the packaged EXE launcher only inside that dist folder. It no longer copies the root source launcher into packaged output and no longer refreshes `build_release`.
- `build_full_release.bat` may still create `build_release` / installer output, but it generates packaged launchers from echo blocks instead of copying the root source launcher.
- Current portable EXE output path is `E:\WorkSpace\NewLight_Analysis\dist\NewLight_Analysis\NewLight_Analysis.exe`; packaged launcher path is `E:\WorkSpace\NewLight_Analysis\dist\NewLight_Analysis\run_NewLight_Analysis.bat`.
- In PyInstaller 6 onedir builds, data resources live under `dist\NewLight_Analysis\_internal`. `check_backends.bat` detects that location before calling worker scripts or checking the bundled DeepCAD-RT model.
- Latest build on 2026-05-29 used `cmd /c build_exe.bat /nopause`. Release validation passed from `dist\NewLight_Analysis`: bundled Python OK, NeuroSeg3 real model smoke OK, and CaImAn / DeepCAD-RT backend checks OK.
- `NewLight_Worker.exe` intentionally lives in `_internal` and uses a different console/tool icon from the main GUI. Do not move it back to the release root manually; the PyInstaller spec controls its runtime resource layout.
- Inno Setup `ISCC.exe` was not installed/found on the build machine during the latest pass, so `build_full_release.bat` would skip installer creation and leave the complete portable folder ready. Install Inno Setup 6 or put `ISCC.exe` on `PATH` to produce the installer from `NewLight_Analysis_setup.iss`.

## Packaged User Manual

Mandatory DeepCAD-RT documentation rule:

- Every future user-manual revision must prominently state that DeepCAD-RT
  requires a CUDA-capable NVIDIA GPU and a compatible driver, and that there is
  no CPU fallback.
- Repeat this warning in at least four visible places: the quick-start/system
  requirements area, the DeepCAD-RT function description, troubleshooting,
  and any hardware/backend compatibility table.
- Do not use the broad wording "GPU functions fall back to CPU" for
  DeepCAD-RT. Clearly separate it from CPU-capable processing and ROI paths.
- The warning must remain in the durable documentation source and be copied
  into release manuals after each build, because `build_exe.bat` deletes the
  old `dist` directory before PyInstaller runs.

Current detailed manual state (2026-07-31):

- The durable Markdown source is
  `docs\NewLight_Analysis_User_Manual.md`; do not maintain the release copy as
  the only source.
- `tools\build_user_manual.py` converts the Markdown source to a styled DOCX
  using `python-docx`.
- The current manual has 20 sections, 52 tables, 15 numbered image
  placeholders, formulas, parameter defaults, troubleshooting, method-writing
  templates, and explicit CPU/CUDA compatibility guidance.
- Generated source-side artifacts are
  `docs\NewLight_Analysis_User_Manual.docx` and
  `docs\NewLight_Analysis_User_Manual.pdf`.
- `build_exe.bat` copies the Markdown, DOCX, and PDF from `docs` into
  `dist\NewLight_Analysis` after PyInstaller recreates the release directory.
- The 26-page DOCX was exported through Microsoft Word to PDF and every page
  was raster-reviewed. Tables, code/formula blocks, callouts, page numbers, and
  all 15 image placeholders rendered without clipping or overlap.

The packaged output folder now includes a complete Chinese user manual:

- `E:\WorkSpace\NewLight_Analysis\dist\NewLight_Analysis\NewLight_Analysis_User_Manual.md`
- `E:\WorkSpace\NewLight_Analysis\dist\NewLight_Analysis\NewLight_Analysis_User_Manual.docx`
- `E:\WorkSpace\NewLight_Analysis\dist\NewLight_Analysis\NewLight_Analysis_User_Manual.pdf`
- UI screenshots under `E:\WorkSpace\NewLight_Analysis\dist\NewLight_Analysis\manual_assets\`

The screenshots were generated from the real Tk application using synthetic example data and cover:

- Data tab
- Preprocess tab
- ROI tab
- Analysis tab
- Generate Heatmap AVI dialog
- NeuroAlign wizard

The manual explains installation/runtime expectations, the full user workflow, each major control, output files, troubleshooting, and paper-methods wording. It also records formulas for:

- movie projection
- DeepCAD-RT raw/denoised blending
- stimulus trigger mapping and interval triggers
- preprocessing operations
- dF/F and ROI trace extraction
- trace baseline correction and smoothing
- peak detection, Pearson correlation, ROI statistics, and trial average
- heatmap normalization / overlay / colorbar behavior
- atlas image ROI import
- Atlas Reference Builder line-to-region extraction
- NeuroAlign affine, midline/inner-boundary, and final warp scoring

Validation notes:

- DOCX structure check passed with 103 non-empty paragraphs, 5 tables, and 6 embedded images.
- The DOCX was converted to a 9-page PDF with local Microsoft Word COM automation.
- LibreOffice/Poppler were not present, so no separate raster page render was produced.

## Stimulus Event Analysis / Split Exports

The old Data-tab `Export Analysis` one-shot report button has been removed. The old Data-tab `Trial Average` button has also been removed. Analysis outputs are now split into independent user-selected buttons in the Analysis tab:

- `Export Traces CSV`
- `Export Trace Plot PNG`
- `Export ROI Statistics`
- `Export Correlation`
- `Export dF/F Heatmap PNG`
- `Export ROI Snapshot`
- `Export Summary JSON`

Stimulus-response analysis now lives in the Analysis tab as `Stimulus Event Average`.

Stimulus input loading details:

- `Open Stimulus` uses `analysis_core.read_stimulus_file_info(...)`.
- Text/CSV stimulus files may be single-column numeric files or multi-column files with headers, such as two-photon `data_user input.txt`.
- For multi-column inputs, the loader scores columns by pulse-like TTL behavior and gives a small name bonus for labels containing `stim`, `trigger`, `marker`, or `ttl`. This avoids blindly selecting `Stim. Marker` when another column has the actual high-voltage trigger pulses.
- If the stimulus file is in a two-photon folder with `protocol*.txt`, the loader infers `Stim Hz` as `numeric sample count / Recording time` and writes that value into the Protocol `Stim Hz` field. Users can still override it manually if the protocol timing is not valid.
- In the inspected sample `E:\WorkSpace\NewLight_Analysis\2`, `data_user input.txt` has 3,120,000 samples and protocol recording time is 130 s, giving 24,000 Hz. The selected trigger column is `E-phys`, and 30 pulses map to 40 Hz video frames starting near 88, 208, 329, ...

Expected workflow:

1. Load a movie.
2. Load a stimulus file or set interval triggers.
3. Apply protocol / detect triggers, or let `Stimulus Event Average` regenerate the same trigger frames from the current protocol fields.
4. Draw/load ROIs or allow trace extraction to create the full-frame global ROI.
5. Click `Stimulus Event Average`.
6. Enter:
   - pre-event seconds
   - post-event seconds
   - heatmap window start seconds relative to stimulus
   - heatmap window end seconds relative to stimulus
   - optional top fluorescence percent
7. Choose an output folder.

Event outputs:

- per-ROI PNG figures named like `{source}_stimulus_event_001_ROI1.png`; individual trials are gray, mean response is black, and stimulus onset is a red dashed line
- `{source}_stimulus_event_mean_traces.csv`
- `{source}_stimulus_event_trials.npz`
- `{source}_stimulus_event_heatmap.png`
- optional `{source}_stimulus_event_heatmap_top_{x}pct.png` when `top_percent > 0`
- `{source}_stimulus_event_summary.json`

Core functions added in `analysis_core.py`:

- `event_aligned_blocks`
- `event_aligned_mean`
- `plot_event_aligned_roi`
- `save_event_heatmap`
- `export_event_aligned_response`
- split-export helpers: `save_traces_csv`, `save_roi_statistics_table`, `save_correlation_outputs`, `save_roi_snapshot_outputs`, and `save_summary_json`

GUI functions added in `NewLight_Analysis.py`:

- `stimulus_event_average`
- `event_trigger_frames`
- `ensure_traces`
- split-export methods matching the new Analysis buttons

Implementation notes:

- `extract_traces(show_window=False)` is used by export actions to avoid forcing a popup trace preview.
- Event heatmaps compute dF/F from the current movie and baseline, align movie blocks around each valid stimulus frame, average those movie blocks, then average the selected relative-time window into one spatial heatmap.
- Top x% fluorescence heatmap masks all pixels below the `(100 - x)` percentile of that event heatmap. If x is 0, blank, or non-positive, the top-percent heatmap is skipped.
- The event analysis requires valid trigger frames that fit fully inside the selected pre/post window. Incomplete edge events are skipped.
- Validation passed for Python compilation, core synthetic-data export, and GUI button presence/absence. `conda run` still prints the known OpenCL vendor `temp.txt` noise; it did not fail the checks.

Packaged manual refresh:

- After the 2026-05-15 rebuild, `dist\NewLight_Analysis` retained only `NewLight_Analysis_User_Manual.docx` from the manual set.
- `NewLight_Analysis_User_Manual.docx` was updated to document the new Analysis-tab stimulus event workflow and split export buttons.
- `NewLight_Analysis_User_Manual.pdf` was regenerated from the updated DOCX.
- Validation after the refresh: DOCX has 112 non-empty paragraphs, 5 tables, and 6 embedded images; PDF has 11 pages and contains the stimulus-event section.

## Backend Console Window Handling

DeepCAD-RT preview, NeuroSeg3, CaImAn, NeuroAlign, and frozen worker calls all go through `analysis_core.run_conda_worker(...)`.

On Windows, `analysis_core.hidden_subprocess_kwargs()` now supplies `CREATE_NO_WINDOW` and `STARTUPINFO` / `SW_HIDE` settings to backend `subprocess.run(...)` calls. Keep new backend launches on the `run_conda_worker(...)` path so GUI users do not see black console windows during background processing.

The NeuroSeg3 CUDA status probe also uses the same hidden subprocess settings.

## dF/F Baseline Semantics

Protocol baseline inputs are frame-based, not second-based:

- `Base start frame`: the first movie frame used for the baseline window.
- `Base dur frames`: the number of frames in that window.

dF/F baseline behavior:

- If `Base dur frames` is `0`, NewLight uses the full-movie 25th percentile image as the baseline.
- If `Base dur frames` is greater than `0`, NewLight uses the mean image over frames `[Base start frame, Base start frame + Base dur frames)`, clipped to the movie length.

Implementation notes:

- The core entry point is `analysis_core.baseline_from_frames(...)`.
- `AnalysisState` stores `baseline_start_frame` and `baseline_duration_frames`.
- When these Protocol values change, cached baseline/dF/F/traces are invalidated, and dF/F traces, dF/F heatmaps, heatmap AVI generation, stimulus-event heatmaps, and split exports recompute from the current baseline.
- `analysis_core.baseline_from_seconds(...)` remains only as a compatibility wrapper.
- Regression coverage lives in `tests\test_baseline.py`.

## Two-Photon Folder Import / Conversion

The Data tab uses `Open Source` instead of a file-only movie opener.

Supported source choices:

- movie file: existing TIFF/AVI/MP4/MOV/MKV loading behavior
- two-photon data folder: folder containing `protocol*.txt` and a `.tdms` imaging file
- direct `.tdms` file: treated as its parent folder

Folder conversion behavior:

- Protocol values are read from `protocol*.txt` using `analysis_core.read_two_photon_protocol(...)`.
- TDMS image segments are streamed directly by `analysis_core.iter_tdms_image_slots(...)`; no `nptdms` dependency is required.
- Each TDMS image slot is restored as a `height x width` `int16` frame.
- The analysis movie stores `float32(frame + 32768)`, matching the LabVIEW thumbnail/TIFF offset convention and keeping dF/F baseline values positive.
- If protocol channels and TDMS slot count indicate Ch1/Ch2 frame interleaving, adjacent slots are read as Ch1 and Ch2 for each time point.
- Two-photon conversion automatically runs interlacing image-shift correction after channel memmaps are written. It estimates the horizontal odd-line correction shift from Ch1 with a default `+/-10 px` search range, applies the same shift to all channels, and rebuilds the grayscale analysis movie from the corrected channels. Exposed edge pixels after shifting are filled from the nearest valid row edge, not `0`, because converted two-photon data uses a `+32768` offset and zero-fill crushes display contrast.
- Ch1-Ch5 are stored as grayscale channel movies; all channels default to gray in the UI.
- No default `converted_pseudocolor.avi` is generated. Pseudocolor is composed only for the current display frame/projection or while saving.
- A temporary `converted_movie.npy` memmap is used as the grayscale analysis movie to avoid holding an extra RGB movie in RAM.
- Temporary conversion files live under the session temp directory and are removed on app close.

GUI/runtime notes:

- The Data tab has `Add Channel Data`. It accepts movie files, two-photon folders, or direct `.tdms` files and appends loaded channels into the next Ch1-Ch5 slots. A two-channel two-photon folder appended after Ch1/Ch2 becomes Ch3/Ch4.
- The View panel has five square channel color buttons. Loaded channels start gray; unloaded channels are black. Clicking a loaded channel opens six color swatches: green, red, yellow, blue, purple, and gray, plus a `Delete` button for removing that channel and shifting later channels forward.
- Display and `Save Current Movie` remain grayscale while every loaded channel is gray. If any loaded channel is assigned a non-gray color, current-frame display, projection display, and save output are composed on demand from the current channel colors.
- The main application window uses `background.png` as a full-window background layer with centered cover-crop resizing. The background is bundled into the EXE through `NewLight_Analysis.spec`.
- Tk/ttk widgets are opaque, so a root-only background can be fully hidden by the sidebar, work area, notebook, and Matplotlib preview canvas. To keep the background visibly active in source and packaged launches, the left sidebar and right work area use `ui_background.BackgroundPane`, and the empty movie preview area draws `background.png` until movie data is loaded.
- Root `run_NewLight_Analysis.bat` remains a source-only launcher. If the background appears unchanged when using it, first verify that the current source contains `BackgroundPane` and `draw_empty_preview_background`; the batch file itself should still run `launch.py` through `caiman_latest` and should not launch the packaged EXE.
- The Preprocess tab has a manual `Image Shift` button. It estimates the interlacing shift from Ch1 when channels are loaded and applies the same correction to all channels; for single movies it estimates and corrects the current movie directly.
- Movie-altering preprocessing operations are applied to each converted channel movie when present, and the analysis movie is recombined from the processed channels. This preserves red/green display after smoothing, background subtraction, bleach correction, contrast enhancement, built-in rigid motion, and undo.
- CaImAn motion still operates on the analysis movie only; after it finishes, the result is treated as a single gray Ch1 movie unless a dedicated channel-aware CaImAn path is added later.
- `Save Current Movie` enforces AVI output. With all channel buttons gray it saves the current grayscale analysis movie; with any non-gray channel button it streams a pseudocolor AVI according to the current swatches.
- Regression coverage lives in `tests\test_two_photon_converter.py` and `tests\test_interlacing_shift.py`.

Sample validation:

- `E:\WorkSpace\Image format converter Folder （new）\20260424_A04` is recognized as a two-photon folder.
- Its protocol reports 600x600, 40 Hz, 60 s, 2400 expected frames, and Ch1 only.
- Its TDMS contains 2400 image slots, matching the protocol. Ch2 thumbnail is blank in this sample because Ch2 PMT voltage is 0.

## Workspace Cleanup State

The latest cleanup was performed on 2026-06-30.

Removed from the project root:

- `build`
- `build_release`
- root/source `__pycache__` folders
- `.codegraph`
- local sample dataset folder `2`
- local sample archive `Example.zip`

Preserved items:

- source files, tests, workers, bundled compatibility modules, DeepCADRT model files, PyInstaller/Inno Setup scripts, project documentation, git metadata, and the current `dist\NewLight_Analysis` portable release folder
- external development dependencies under `E:\WorkSpace`, including `2cafe_analysis`, `DeepCAD-RT`, `CaImAn`, `NeuroSeg3`, and the external two-photon converter reference folder

Notes:

- `dist\NewLight_Analysis` is intentionally kept because it is the latest portable build for other-computer testing and accounts for most of the remaining project size.
- If the user later wants a strict source-only tree, confirm first and then move or delete `dist\NewLight_Analysis`.
- `.codegraph`, `2`, and `Example.zip` are now ignored if recreated locally.
- Validation sample data is protected. Do not delete, move, or clean sample folders/files used for verification, even if they are large and untracked, unless the user explicitly names those samples for removal.
- The old tracked manual files under `dist\NewLight_Analysis` were already deleted in the working tree before this cleanup and were left in that state.

A conservative cleanup was performed on 2026-05-21. No files were permanently deleted. Generated/cache/runtime folders were moved out of the workspace to:

```text
E:\WorkSpace_cleanup_20260521_145153
```

Moved items:

- `NewLight_Analysis\build`
- `NewLight_Analysis\build_release`
- `NewLight_Analysis\Output`
- `NewLight_Analysis\NewLight_temp`
- `NewLight_Analysis\NeuroAlign_runs`
- Python `__pycache__` folders under `NewLight_Analysis`, `csbdeep`, and `workers`
- top-level `logs`

Preserved items:

- source files, workers, bundled compatibility modules, DeepCADRT model files, PyInstaller/Inno Setup scripts, project documentation, git metadata, and the current `dist\NewLight_Analysis` portable release/manual folder
- external development dependencies under `E:\WorkSpace`, including `2cafe_analysis`, `DeepCAD-RT`, `CaImAn`, and `NeuroSeg3`

If the user later wants a stricter source-only tree, confirm first and then move or delete `dist\NewLight_Analysis`; it currently accounts for most of the remaining `NewLight_Analysis` size.

## Git / Record Policy

This project is now managed as a Git repository at `E:\WorkSpace\NewLight_Analysis`.

For future updates:

1. Keep changes scoped.
2. Update `WORK_LOG.md` for every meaningful code change.
3. Update this handoff file when architecture, workflow, environment, major bugs, or current known issues change.
4. Run at least a syntax check for Python edits:

   ```bash
   python -m py_compile NewLight_Analysis.py analysis_core.py
   ```

5. Commit source and record updates together when the change is stable.
6. Finish each task with the context-safety self-check described above.

## Motion Correction State (2026-07-21)

- `CaImAn Motion` and `Rigid Motion (Built-in)` are intentionally separate.
- CaImAn mode is a readonly choice. `piecewise` is the default and already
  performs rigid template generation followed by piecewise-rigid correction;
  `rigid` performs global translation only.
- CaImAn exposes `Max shift px`, `Patch stride px`, `Patch overlap px`, and
  `Max local deviation px`; current defaults are `12`, `48`, `24`, and `5`.
  The effective patch size is stride plus overlap. Every value is forwarded to
  the worker command line.
- The worker reports rigid/local median and maximum absolute y/x shifts plus
  `at_limit_fraction`. A non-trivial limit fraction means the search range is
  clipping estimates and should usually be increased before judging quality.
- Fast Motion Correction keeps the existing two-pass aligned-median rigid
  stage and optionally follows it with constrained local deformation.
- Its `auto` reference mode searches for a stable interval near the
  dominant movie position. `manual` mode uses the zero-based start frame and
  frame count shown in the Parameters panel.
- Every frame is passed through final registration, including frames used to
  construct the template. There is no output splice that restores original
  reference frames. One anchor can remain unchanged by definition because
  motion correction has no external absolute coordinate.
- Fast Motion Correction logs the selected interval, anchor, and rigid absolute
  dy/dx statistics. When local correction runs, it also logs effective block
  size/grid, local dy/dx statistics, and the deformation-limit hit fraction.
- Core regression coverage is in `tests\test_rigid_motion.py`; GUI choice and
  parameter coverage is in `tests\test_gui_static.py`.
- CaImAn still processes only the grayscale analysis movie and returns one gray
  channel. Shared-transform multi-channel CaImAn correction remains future
  work.
- CaImAn requires intermediate TIFF files for its worker. `caiman_input.tif` is
  deleted immediately; the corrected result remains at the Run Log's
  `CaImAn\caiman_preview.tif` path until application close and is loaded as the
  current in-memory preview. Permanent output still requires `Save Current
  Movie`; Undo restores the preceding state.
- CaImAn completion preserves the active display type: a frame view displays
  the same frame index from the corrected movie, while a projection view is
  recomputed from the corrected movie.
- Do not treat `Access is denied`, `The system cannot find the file specified`,
  or the missing OpenCL `vendors\temp.txt` message as a CaImAn failure when the
  worker returns success. They come from Conda's Khronos OpenCL activation
  script attempting to write inside a read-only environment folder, and are
  filtered from the application Run Log.

## Chinese UI State (2026-07-22)

- The source application now uses Chinese for all user-visible controls,
  dialogs, file pickers, application-generated logs, validation errors, help
  text, analysis windows, and chart labels.
- Model and scientific names stay recognizable: `CaImAn 运动矫正/去抖动`,
  `DeepCAD-RT 深度学习降噪`, `NeuroSeg3 自动 ROI 分割`, and
  `NeuroAlign 脑图谱配准`. ROI, dF/F, FPS, CUDA, AVI, TIFF, JSON, px, TPS,
  Leiden, CPU, and GPU remain unchanged where they are technical terms.
- `ui_text_zh.py` owns shared Chinese model/action labels. Preprocess functions
  must route by stable internal action ID, never by a Chinese display label.
- Readonly choices show Chinese but map back to English backend values before
  processing. Do not pass translated values to workers or saved settings.
- The sidebar has a stable width of 300 px and uses `Sidebar.TButton`; the
  parameter panel is 290 px. Keep these constraints when adding longer names.
- `tests\test_chinese_localization.py` protects localization and routing.
- The portable EXE has not been rebuilt since this localization. Run
  `build_exe.bat` only after source verification when a Chinese portable build
  is requested.

## Combobox Visual State (2026-07-23)

- All `ttk.Combobox` controls use the global `TCombobox` style configured in
  `apply_dark_theme()`; this includes the field, arrow area, and popup list.
- Tk/ttk widgets cannot be truly transparent on Windows. The application uses
  `THEME["panel"]` for the field and popup background to visually merge each
  combobox with its parent panel.
- Keep popup selection on `THEME["panel_2"]` and text/arrow colors readable.
  New comboboxes should reuse `TCombobox` rather than introduce a white or
  platform-default custom style.

## Fast Motion Correction State (2026-07-23)

- The visible action is `快速运动矫正`; keep internal action ID
  `builtin_rigid_motion` for stable routing and parameter-panel state.
- `analysis_core.rigid_motion_correction()` remains the unchanged rigid-only
  implementation. `analysis_core.fast_motion_correction()` calls it first and
  adds local correction only when flexible strength is positive.
- `柔性强度 = 0` is a tested compatibility invariant: output pixels and rigid
  shifts exactly match direct rigid correction.
- Current local defaults are strength `0.0`, block size `96 px`, and maximum
  local deformation `3.0 px`. The UI clamps strength to `0-1`; the description
  recommends `0.2-0.5` for mild local motion.
- The local stage uses overlapping patch phase correlation, displacement
  clipping, neighborhood median filtering, dense interpolation/smoothing, and
  a single linear warp with nearest-edge handling.
- Do not subtract the local grid's median residual. Local deformation can bias
  whole-frame phase correlation, so the second stage must be allowed to remove
  a remaining template offset after rigid correction.
- Images smaller than `32 px` on either axis safely return the rigid result.
  CaImAn piecewise-rigid remains the recommended path for stronger or complex
  local motion.
- Regression coverage is in `tests/test_rigid_motion.py`,
  `tests/test_gui_static.py`, and `tests/test_chinese_localization.py`.

## Responsive Task Queue State (2026-07-23)

- `task_queue.py` is the single source of truth for long-running work.
  `TaskController` executes one FIFO worker outside Tk and applies each result
  from `NewLightApp._poll_worker()` on the Tk thread before launching the next
  task.
- New long-running workflows must use `NewLightApp.enqueue_task()` or its
  `run_worker()` compatibility wrapper. A worker receives `cancel_event`, must
  not touch Tk widgets, and returns plain results for a main-thread callback.
  File/parameter dialogs must complete before a task is queued.
- `取消当前任务` is cooperative: it requests cancellation of the active task but
  preserves waiting tasks. CPU/native/CUDA calls may only stop at their next
  safe loop or process boundary.
- The `当前数据任务流` panel is below Parameters. Its contract is: pending white
  text; active white text plus green outline; completed light-gray text; and,
  when idle, the final completed item with a blue outline. Failed/cancelled
  entries remain visible as history.
- Dataset-changing callbacks call `reset_history_for_new_dataset()` after new
  data becomes active. Result callbacks compare the movie object identity and
  ignore stale results rather than overwriting a later import.
- The queue covers imports, two-photon conversion, stimulus loading,
  preprocessing, model workflows, ROI/atlas jobs, dF/F and trace calculations,
  heatmap AVI, save/export paths, and automatic post-load previews. Before
  adding expensive work, search for a queued equivalent rather than adding a
  direct `threading.Thread` or a Tk-thread computation.
- `show_trial_average()` is intentionally one queued operation. It computes
  missing triggers, baseline, traces, and trials in the worker, avoiding both
  UI blocking and the former asynchronous trigger-detection race. Its plot is
  created only in the success callback.
- `ensure_baseline_image()` is a legacy synchronous helper with no active call
  sites. Do not introduce it for new user actions; use
  `queue_movie_view_refresh()` or `queue_analysis_operation()` instead.
- Current validation: `conda run -n caiman_latest python -m pytest -q`
  (`52 passed` on 2026-07-23), plus
  `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py task_queue.py`.
- Do not rebuild the portable EXE for queue/UI source changes unless explicitly
  requested. Do not delete or move validation sample data, including local
  sample folders, unless the user explicitly names it.

## Scrollable Parameter Panel State (2026-07-24)

- The editable part of the `参数` panel is now a Canvas-backed vertical scroll
  area, with a dedicated visible right-side `ttk.Scrollbar`. Long configurations
  such as `快速运动矫正` must be reachable by dragging the scrollbar or using the
  mouse wheel while the pointer is over the parameter area.
- `当前数据任务流` intentionally remains outside the scrollable area and stays
  visible below it. Do not put task-flow widgets into `parameter_content`.
- New/cleared parameter panels call `_reset_parameter_scroll_position()` so
  every action begins at its title/description. Parameter label wrapping uses
  `PARAMETER_TEXT_WIDTH`, which reserves room for the scrollbar.
- Keep scientific numeric fields as text entries unless a feature explicitly
  needs a bounded numeric control. The vertical scrollbar is for revealing
  fields and action buttons without sacrificing values such as `0.5` or `3.0`.
- Regression coverage is in `tests/test_gui_static.py`; the full suite passed
  with `53 passed` on 2026-07-24. The portable EXE was not rebuilt.

## Embedded Configuration Panel State (2026-07-24)

- User preference: every configuration/choice interaction must use the
  right-side `参数` panel. The only permitted popup windows are native Windows
  file and folder selectors opened by an explicit browse/select action. Keep
  visual result views in the main image area rather than creating a modal
  parameter dialog.
- `NewLightApp.show_parameter_panel()` now accepts legacy field tuples plus
  dictionary fields for `checkbox`, `path`, `readonly`, `note`, `action`,
  `buttons`, and `color_palette`. It also provides expandable help and
  `set_parameter_feedback()` for inline validation/progress messages.
- Migrated entry points: `open_movie`, `add_channel_data`,
  `choose_channel_color`, `auto_roi`, `neuroseg3_roi`,
  `atlas_reference_builder`, `neuroalign`, and `generate_heatmap_avi`.
  The old dialog classes remain only as inactive legacy code; do not route new
  controls through them.
- NeuroAlign now stores its stage/session data in
  `self._neuroalign_panel_state`, renders previews in the main image area, and
  restores the original frame/projection when closed or finalized. Heatmap AVI
  uses `self._heatmap_panel_state` with the same preview/restoration behavior.
- RGB previews are handled safely in `redraw()` by using a grayscale copy only
  for ROI-overlay generation.
- Current validation: `conda run -n caiman_latest python -m py_compile
  NewLight_Analysis.py task_queue.py` and `conda run -n caiman_latest python
  -m pytest -q` (`55 passed`). Conda may print the known OpenCL `temp.txt`
  activation warning with exit code 0; it is not a test/application failure.
- Do not rebuild the EXE for this source-only UI change unless explicitly
  requested. Do not delete or move user/sample data.

## Invalid Start Frames and FPS State (2026-07-27)

- `AnalysisState.invalid_start_frames` is the single protocol value for an
  unusable acquisition prefix. The UI field is `无效起始帧数`; values must be
  non-negative and less than the current movie frame count.
- DeepCAD-RT is intentionally run on `movie[N:]`, never on the full movie when
  `N > 0`. The original prefix is concatenated back unchanged. Do not replace
  this with output-frame masking: DeepCAD uses non-causal temporal patches, so
  preventing backward structure leakage requires excluding those frames from
  model input.
- Keep `deepcad_cache_invalid_start_frames` in cache validity checks. Any code
  path that invokes `run_deepcadrt_denoise()` must pass the protocol value for
  both preview and save workflows.
- Baseline and projection helpers accept `invalid_start_frames`. Explicit
  baseline windows begin at `max(configured baseline start, N)`; duration-zero
  baselines use the 25th percentile of `movie[N:]`. Keep this argument wired
  through preprocessing refreshes and analysis workers.
- `analysis_core.load_movie()` detects frame rate in this order: video
  container FPS; TIFF ImageJ `fps`; TIFF ImageJ `finterval`; OME-TIFF
  `TimeIncrement`; nearby `protocol*.txt` `Image frame rate`; finally `10 Hz`.
  There is no reliable way to infer the true rate from pixels alone, so a TIFF
  that has none of these sources must remain a user-confirmed fallback.
- Key files to inspect before changing this behavior:
  `analysis_core.py`, `NewLight_Analysis.py`, `tests/test_baseline.py`,
  `tests/test_deepcadrt_short_movie.py`, `tests/test_movie_fps.py`, and
  `tests/test_gui_static.py`.
- Current source validation is `70 passed` via the activated `caiman_latest`
  Conda environment. The portable EXE was not rebuilt for this source change.

## Dual ROI Engines State (2026-07-27)

- Active implementation branch: `codex/dual-roi-engines`. Read these files
  first in a new task:
  `docs/superpowers/specs/2026-07-27-dual-roi-engines-design.md`,
  `docs/superpowers/plans/2026-07-27-dual-roi-engines.md`, `roi_engines.py`,
  `workers/run_caiman_roi.py`, `workers/run_neusuite_roi.py`, the ROI methods in
  `NewLight_Analysis.py`, and the ROI wrappers near the end of
  `analysis_core.py`.
- Visible ROI actions are now `CaImAn 识别分割` and `快速 ROI 分割`. The old
  built-in threshold and generic COCO NeuroSeg3 methods/classes remain only as
  inactive compatibility code and have no sidebar button. Do not reconnect
  them without an explicit request.
- `ROIBackendResult` is the main-process handoff. A worker result is accepted
  only after `load_roi_artifact()` verifies version, dimensions, names, masks,
  and JSON metadata. GUI callbacks preserve existing ROI on zero detections,
  worker failure, corrupt output, cancellation, or stale movie identity.
- CaImAn source environment is project-local:
  `.conda_envs/newlight_caiman`. Recreate it with
  `setup_newlight_caiman.bat`; package downloads use project-local
  `.conda_pkgs` so admin access to `D:\anaconda3\pkgs` is unnecessary. The
  environment is CPU-focused because patch CNMF is CPU/I/O bound. Required CNN
  files are `CaImAn_Resources/model/cnn_model.pkl` and
  `cnn_model_online.pkl`.
- The CaImAn worker must keep patch input memory-mapped. Direct ndarray fitting
  with non-null `rf/stride` raises `You need to provide a memory mapped file as
  input if you use patches`. Invalid frames are removed before memmap creation.
  Footprint masks use each accepted `A_thr` column reshaped with `order='F'`;
  never convert them to circles/ellipses or merge overlapping instances.
- Fast ROI source assets are authorized:
  `E:/WorkSpace/NeuSuite2p/segment_model.pt` and
  `E:/WorkSpace/NeuSuite2p/method/ultralytics`. The checkpoint requires the
  worker-local `ultralytics -> method.ultralytics` module alias. It runs through
  the existing CUDA-enabled `neuroseg3` environment. Missing pure packages are
  prepared by `setup_neusuite_runtime.bat` into `NeuSuite_RuntimeDeps`; never
  append all of `NeuSuite2p/_internal`, because its Python 3.10 `.pyc` files
  cause bad-magic failures under Python 3.8.
- Fast ROI must continue to consume `results[0].masks.data` directly and resize
  every instance separately with nearest-neighbor interpolation. Do not use a
  merged output PNG followed by connected-component extraction.
- Confirmed defaults: Fast ROI `imgsz=960`, confidence `0.25`, IoU `0.70`, area
  `20-4000 px^2`. CaImAn two-photon defaults include cell diameter `12 px`,
  `K=4`, `nb=2`, `ssub=2`, `tsub=2`, `p=1`, merge `0.85`, SNR `2.0`, spatial
  correlation `0.85`, CNN enabled at `0.99/0.1`, footprint threshold `0.20`.
- Packaging metadata now includes NeuSuite custom assets/dependencies and
  CaImAn CNN resources and excludes the old generic NeuroSeg3 data. A full EXE
  was deliberately not built. Before the next release build, run the focused
  tests, inspect `NewLight_Analysis.spec`, then perform a frozen fast/CaImAn
  worker smoke test on a copy/session temp output.
- Current source validation is `102 passed` with
  `conda run -n caiman_latest --no-capture-output python -m pytest -q`.
- Real validation source `eye/data/2/A01/result.avi` is protected and was used
  read-only. All local validation/sample folders are permanent unless the user
  explicitly names one for deletion. Never include them in workspace cleanup.
- If conversation context usage exceeds 80%, update this handoff and start a
  new task before implementation detail is lost. A new task can continue by
  reading this section plus the design/plan paths above.

## ROI Color and List State (2026-07-28)

- `analysis_core.roi_color_rgb()`, `roi_color_uint8()`, and
  `roi_color_hex()` are the single source of ROI display colors. The mapping
  is deterministic by zero-based ROI index and independent of ROI count. Use
  these helpers for any future ROI-specific plot, legend, overlay, or table;
  do not reintroduce Matplotlib's default color cycle or an ROI-count-based
  colormap.
- Shared colors are currently wired into `draw_roi_overlay()`,
  `plot_traces()`, `plot_trial_average()`, `NewLightApp.show_trace_window()`,
  and `NewLightApp._show_trial_average_window()`. Keep
  `plot_event_aligned_roi()` unchanged unless the user revises its explicit
  gray-trials/black-mean/red-stimulus design.
- The bottom image toolbar action `显示 ROI 列表` calls `show_roi_list()` and
  renders a `roi_table` field through `show_parameter_panel()`. The table lives
  in the right parameter area and shows color, current ROI name, and pixel
  area. It must not become a `Toplevel` popup.
- `active_parameter_panel_id == "roi_list"` identifies the visible list.
  `set_rois()`, `mark_rois_changed()`, and `clear_rois()` call
  `refresh_roi_list_if_visible()` so imports, automatic/manual additions, and
  deletions update the table immediately. Preserve this refresh path in future
  ROI mutation methods.
- Regression coverage is in `tests/test_roi_colors.py` and
  `tests/test_gui_static.py`. Current validation is `111 passed`, plus a Tk
  smoke test confirming list refresh from two rows to one. No EXE was rebuilt;
  validation samples remain protected and unchanged.

## Adaptive ROI Guidance Plan (2026-07-28)

- Read these two documents before implementing:
  `docs/superpowers/specs/2026-07-28-adaptive-roi-guidance-design.md` and
  `docs/superpowers/plans/2026-07-28-adaptive-roi-guidance.md`.
- This feature is approved but not implemented. Do not infer that candidate
  caching, ROI provenance, boundary refinement, or adaptive worker modes exist
  yet. The current verified baseline is still `111 passed`.
- The approved behavior is: both fast ROI and CaImAn provide quality presets
  and a user-example adaptive action; all current ROI masks are protected;
  their boundaries are locally refined; similar missed candidates are added;
  low-quality protected masks remain and display/export with one trailing `*`.
- Fast area autofill uses all current valid masks: two or more examples fill
  `0.9 x minimum` and `1.1 x maximum`; one example changes only the maximum.
- The adaptation is not weight training. Use NeuSuite confidence plus a fixed
  low-cost convolution descriptor, and use CaImAn's SNR, spatial correlation,
  CNN score, traces, and footprints. Keep the adaptation logic backend-neutral
  in the planned `roi_adaptation.py` module.
- Candidate banks must remain session-temporary and be invalidated by source,
  preprocessing, projection/model-generation inputs, not by example-only ROI
  edits. A separate ROI revision check blocks stale fitted output from
  replacing newly drawn masks.
- Follow the written plan in TDD order. Preserve all validation samples,
  especially `eye/data/2/A01/result.avi`, and do not build the EXE unless the
  user separately requests it after source verification.

## Adaptive ROI Guidance Implemented State (2026-07-28)

- The planning-only section above is superseded: adaptive ROI guidance is now
  implemented on `codex/dual-roi-engines`. In a new task, read the design and
  plan above, then `roi_adaptation.py`, both `workers/run_*_roi.py` files, ROI
  wrappers in `analysis_core.py`, and ROI panel/adaptive methods in
  `NewLight_Analysis.py`.
- ROI masks, names, and metadata are aligned. Every ROI mutation increments
  `roi_revision`. Metadata stores `source`, `protected`, `low_quality`,
  `quality_reasons`, and stable `base_name`. Low-quality protected ROIs remain
  and show/export with one `*`; only user deletion removes them.
- Both panels expose four presets and `根据当前 ROI 自适应拟合并运行`. Preset
  values are Fast confidence `0.10 / 0.25 / 0.40`; CaImAn SNR
  `1.5 / 2.0 / 2.5`; spatial correlation `0.70 / 0.80 / 0.90`; CNN
  `0.70 / 0.90 / 0.99`; similarity `3.0 / 2.3 / 1.7`. Custom uses current
  visible fields. This is calibration, not weight training.
- Fast area autofill and CaImAn diameter suggestion follow the exact rules in
  the design. Protected boundaries use the bounded `2-12 px` local activity
  refinement and preserve identity on every failure path.
- `self.roi_candidate_banks` has separate Fast/CaImAn banks.
  `self.movie_generation` invalidates them when import, undo, channels,
  preprocessing, image shift, vessel removal, or motion correction replaces
  the movie. ROI edits and final thresholds do not invalidate candidates.
- Adaptive FIFO tasks snapshot movie identity/generation, ROI masks/metadata,
  `roi_revision`, protocol, preset, and engine settings. A stale task may cache
  candidates after an ROI edit but must not apply fitted output.
- Fast candidate mode uses confidence `0.05` and aligned `scores` /
  `source_indices`. CaImAn candidate mode exports aligned `traces`, `snr`,
  `r_values`, `cnn_scores`, `component_indices`, and `preset_accepted`. Empty
  optional quality arrays become NaN arrays; non-empty mismatches are errors.
- The `neuroseg3` source runtime also requires `py-cpuinfo==9.0.0`. Recreate
  runtime dependencies with `setup_neusuite_runtime.bat`; its offline fallback
  copies Python source from NeuSuite without importing incompatible bytecode.
- Protected validation sample remains `eye/data/2/A01/result.avi` (`800` frames,
  `540 x 512`, `10 Hz`). Final read-only smoke results: 9 Fast candidates from
  an `80 x 256 x 256` crop with repeatable adaptive reuse; 35 CaImAn candidates
  from a `50 x 128 x 128` crop with all six exported arrays aligned. The source
  SHA-256 remained `48106b31ba131d1c7dcb80bb1e745349844e7b936150100008df4d423917fad5`.
  Never clean sample data.
- Candidate matching combines IoU and normalized centroid distance. A matched
  model mask contributes to protected-boundary refinement and quality status,
  but is never appended as a duplicate. Protected low-quality state is
  recomputed under the active preset, so an obsolete trailing `*` can clear.
- ROI `base_name` is stable through add/delete operations. Automatic global ROI
  creation uses the central mutation path and increments `roi_revision`.
- Candidate-mode worker artifacts fail closed when required quality arrays are
  missing. Cache identities fingerprint Fast weights/runtime/dependencies and
  CaImAn environment metadata/resources.
- A protected Fast/CaImAn ROI absent from the current permissive bank remains
  present and is marked `当前模型候选中未复现`. CaImAn cache identity resolves
  whichever local-prefix or named environment its worker actually selects.
- Current verification is `169 passed`; focused adaptive tests are `100 passed`;
  key source/worker compile checks and Tk state smoke pass.
  No EXE was built. The Conda OpenCL `temp.txt` text remains harmless when the
  command exits with code 0.

## ROI List Selection Highlight (2026-07-28)

- `show_roi_list()` supplies stable zero-based indices to the embedded
  `roi_table`. `<<TreeviewSelect>>` calls `select_roi_from_list(index)`.
- The selected ROI remains highlighted in its assigned color with a `3 px`
  boundary and larger label. Normal ROI boundaries remain `1 px`; there is no
  flashing, color switching, or timed callback.
- Highlight state is held only by `highlighted_roi_index`. Leaving the ROI-list
  panel or mutating the ROI list clears the selection safely.
- `analysis_core.draw_roi_overlay()` accepts optional `highlighted_index`;
  default callers and exported snapshots remain unchanged.
- Current source verification is `171 passed`, with `41 passed` in the focused
  ROI color/GUI suite and a successful real Tk selection smoke test. No EXE was
  rebuilt.

## Independent Invalid-Edge Crop (2026-07-28)

- `ui_text_zh.py::PREPROCESS_PANEL_SPECS["auto_crop_edges"]` registers the
  independent `自动裁剪无效边缘` preprocessing tool. Keep it separate from
  both motion-correction implementations.
- Read these locations first when changing the feature:
  `analysis_core.py::estimate_stable_crop_bounds`, `crop_movie_bounds`, and
  `crop_spatial_mask`; then `NewLight_Analysis.py::show_auto_crop_edges_panel`,
  `refit_auto_crop_edges`, `confirm_auto_crop_edges`, the three canvas event
  handlers, `draw_auto_crop_overlay`, `push_history`, and `undo`.
- Bounds are `(x0, y0, x1, y1)` with exclusive `x1/y1`. The estimator samples
  up to 96 frames, measures adjacent row/column duplication plus empty outer
  bands, keeps only trim depths supported by at least 95% of sampled frames,
  and returns full-frame bounds on low-information input. Manual interaction
  enforces at least `16 px` per axis.
- Fitting and confirmation both use the single FIFO controller. Fit results are
  guarded by a token plus movie identity. Confirm captures immutable bounds,
  source identity, channels, ROI masks/names/metadata, protocol, and projection
  settings before queueing; stale movie results are ignored.
- Confirmation modifies only session state. It synchronously crops every
  loaded channel, rebuilds the analysis movie, crops and filters ROIs, clears
  incompatible dF/F/trace/DeepCAD/render caches, invalidates ROI candidate
  banks through `mark_movie_changed()`, and resets the fitted view. It never
  writes the imported source file.
- Crop history entries opt into `include_rois=True`; older four-field history
  entries remain backward compatible. Undo restores the extra ROI snapshot only
  when those fields exist.
- Regression coverage is in `tests/test_auto_crop_edges.py`,
  `tests/test_auto_crop_gui.py`, `tests/test_gui_static.py`, and
  `tests/test_chinese_localization.py`. Run tests
  with `.conda_envs/newlight_caiman/python.exe -m pytest -q`; the named
  `caiman_latest` environment currently aborts in NumPy native initialization.
- Review hardening covers transient-edge rejection, fit-after-FIFO replacement,
  pending-confirmation panel changes, no-input embedded feedback, and a real Tk
  drag/crop/undo workflow.
- Verified state: `188 passed`, focused `63 passed`, source compilation and a
  real Tk drag/crop/undo smoke passed. No EXE was built. All validation samples,
  especially `eye/data/2/A01/result.avi`, remain protected and untouched.

## dF/F Peak Marker Window (2026-07-28)

- `NewLight_Analysis.py::peak_detection()` still runs through
  `queue_analysis_operation(..., need_traces=True)` and still uses
  `analysis_core.detect_trace_peaks()` without changing prominence or minimum
  distance. It now keeps each ROI's exact peak indices instead of discarding
  them after counting.
- `NewLight_Analysis.py::show_peak_detection_window()` draws the processed dF/F
  trace with the same `core.roi_color_hex()` mapping used elsewhere. A readonly
  combobox selects one ROI at a time and includes its count. Peak markers use
  the exact `t[peaks]` and `trace[peaks]` coordinates, so marker positions and
  `Peak_Count` are the same detection result; there is no vertical offset.
- The plot title includes the selected ROI's count, the run log records a
  compact all-ROI count summary, and `ImageToolbar` provides translated
  reset/pan/zoom/save controls. The old peak-count `messagebox.showinfo()` path
  has been removed. Detection and plotting reject non-finite or non-positive
  FPS values.
- `TaskController` supports a main-thread `on_start` hook.
  `queue_analysis_operation()` uses it to snapshot the movie, ROI
  masks/names/revision, protocol values, FPS, trigger frames, acceleration, and
  trace-processing settings only when the task reaches the front of the FIFO.
  Its completion handler rejects a changed movie identity, ROI revision, or
  protocol/trace signature before updating cached baseline/traces. Preserve
  these guards when changing shared analysis behavior.
- ROI-dependent operations that do not extract traces must pass
  `depends_on_rois=True`. Trace operations imply that dependency. If a trace
  operation starts without ROI, the main-thread start hook creates the formal
  `Global_ROI` before snapshotting so ROI and trace state remain aligned.
- Chart/image exports in `analysis_core.py` use `_export_figure()` and
  `FigureCanvasAgg`; do not return them to `pyplot.subplots()`. The GUI module
  selects `TkAgg` globally, and pyplot figures would otherwise make background
  exports depend on Tk initialization.
- The module-level Matplotlib fallback font list now prefers common Windows CJK
  fonts. Keep `DejaVu Sans` last for non-CJK fallback and keep
  `axes.unicode_minus=False` for minus-sign display.
- Regression coverage is in `tests/test_peak_detection_plot.py` and
  `tests/test_analysis_queue_snapshot.py`. A real Tk graph smoke switched from
  ROI-A to ROI-B, retained their exact `3 / 2` peak indices, and produced zero
  missing-glyph warnings. Final source verification is `199 passed, 1 skipped`,
  with source compilation and `git diff --check` also passing. The skip is the
  existing full-app auto-crop Tk smoke: this local Conda Tcl/Tk prefix
  intermittently reports a different support file as unreadable although the
  reported files exist and can be read. The dedicated peak-window Tk smoke
  passes in the same environment. No EXE was built and samples were untouched.

## ROI Renumbering After Deletion (2026-07-31)

- `delete_roi_at()` captures the deleted metadata `base_name`, removes the
  mask/metadata pair, then calls `shift_roi_sequence_after_deletion()` before
  the shared `mark_rois_changed()` synchronization path.
- Following names in the same generated sequence move down by one. Recognized
  prefixes are `ROI`, `AtlasROI`, `Fast_ROI`, `CaImAn_ROI`, and `NS3_ROI`.
  Custom/imported names that do not match these exact generated forms must not
  be rewritten. Low-quality metadata and the display `*` remain attached to the
  corresponding mask.
- Behavioral regression coverage is in `tests/test_roi_deletion.py`. Keep this
  logic deletion-specific; globally renumbering inside `sync_roi_names()` would
  destroy intentional names loaded from atlas JSON/NPZ files.
- Current verification is `214` tests across clean Tk processes. A real ROI
  list Treeview smoke also confirms the displayed sequence closes immediately
  after deleting the first atlas ROI. The portable EXE predates this change.

## ROI List Clear Semantics (2026-07-30)

- Embedded parameter/property panels no longer receive a generic `清空`
  footer. That former control only called `clear_parameter_panel()` and did not
  clear feature data. Explicit workflow cancellation remains available through
  `cancel_command`, rendered as `取消`.
- `show_roi_list()` owns a dedicated `清空全部 ROI` action wired to
  `clear_rois()`. Keep it on the shared ROI mutation path so masks, names,
  metadata, traces, `roi_revision`, overlays, and the visible list remain
  synchronized. Do not replace it with `clear_parameter_panel()`.
- Regression coverage is in `tests/test_gui_static.py`; a real Tk smoke also
  invokes the button and verifies the complete state transition. Verification
  passed as `200` non-peak tests plus `11` peak/Tk tests in a clean process. A
  combined-process attempt hit the existing local Conda Tcl/Tk second-root
  initialization failure; this occurs before application logic and the same Tk
  test passes independently. The portable EXE predates this 2026-07-30 change.

## Latest Portable Build (2026-07-29)

- `build_exe.bat` now preflights the DeepCAD-RT model, NeuSuite model/runtime,
  CaImAn resources, and the full Python packaging dependency set before
  removing the previous `build` and `dist` directories. It selects the
  `caiman_latest` environment when available; the successful build used Python
  3.11.15 and PyInstaller 6.20.0.
- The current portable output is
  `dist/NewLight_Analysis/NewLight_Analysis.exe`; the complete directory is
  approximately 4.36 GB. It contains the frozen backend worker and all checked
  DeepCAD-RT, NeuSuite, CaImAn, and NeuroAlign resources.
- Post-build verification: frozen core imports passed, OpenCV 4.13 loaded from
  the patched bundle, frozen peak toolbar/wheel navigation passed, and the GUI
  remained running through a 20-second startup smoke. PyInstaller's TensorBoard,
  MPI, CuPy, and compatibility-import warnings are optional-path warnings, not
  failures in the verified application paths. No installer was built.

## Peak Percentile Parameter (2026-07-29)

- `NewLight_Analysis.py::peak_detection()` now only opens the embedded
  `peak_detection` parameter panel. `run_peak_detection(values)` validates and
  submits the task. Do not restore direct execution from the sidebar button.
- The user-facing field is `最低峰值分位数 (%)`, stored as
  `user_settings["peak_detection"]["min_percentile"]`; default `25`, valid
  range `0 <= p <= 100`.
- `analysis_core.detect_trace_peaks(..., min_percentile=p)` uses
  `Q_p = percentile(finite dF/F samples, p)` as the SciPy `find_peaks` minimum
  height. The existing prominence `std(trace) * prominence_scale` and minimum
  distance `0.5 * fs` remain active, so this is an additional low-peak filter,
  not a replacement for prominence. Its API default is `None`, preserving the
  former prominence/distance-only behavior for external or legacy callers.
- Within NewLight, `configured_peak_percentile()` supplies the saved value to
  peak plotting, interactive ROI statistics, ROI-statistics export, and full
  analysis export. Keep these paths aligned so `Peak_Count` equals the number
  of markers produced from the same processed traces.
- Statistics/export tasks pass `depends_on_peak_settings=True` to
  `queue_analysis_operation()`. The shared start hook puts the current value in
  `context["peak_min_percentile"]` and in the analysis signature; do not return
  to pre-queue closure capture, which can mix old peak settings with new data.
- The peak window receives the submitted percentile and displays it in the
  title. `PeakPlotToolbar` maps Back/Forward to the previous/next ROI, and a
  mouse-wheel event over the peak canvas performs the same selection. These
  controls and the ROI combobox share one wrapped index, so moving backward
  from the first ROI selects the last and moving forward from the last selects
  the first. Keep the main application toolbar and main viewer scroll behavior
  unchanged.
- Do not reintroduce a function-local `StringVar` for the peak ROI combobox.
  When that Python variable was collected after window creation, Tcl cleared
  the displayed selection. The combobox now stores its selection directly and
  opens reliably on ROI 1.
- Regression coverage is in `tests/test_peak_detection_plot.py`. The real Tk
  smoke covers the parameter-panel workflow and synchronized peak-ROI
  navigation. Source verification before the latest portable rebuild was
  `209 passed`; no sample data was used.

## Reusable Processing Workflows (2026-07-31)

- Read this section before changing the current-data task list, preprocessing
  submission paths, or workflow file compatibility. Core file I/O and schema
  validation are in `workflow_core.py`; FIFO metadata is in `task_queue.py`;
  GUI collection/replay is in `NewLight_Analysis.py` near
  `_build_task_flow_panel()`, `current_reusable_workflow_steps()`,
  `save_current_workflow()`, `execute_workflow()`, and `enqueue_task()`.
- The `当前数据任务流` canvas is `250 px` high. Two equal-width controls are
  directly below it: `保存当前工作流` and `执行工作流`. The existing
  `取消当前任务` control remains in the status row. Both workflow controls
  were checked in real Tk windows at `1440x920` and `1100x760`.
- Workflow files use the `.nlworkflow.json` extension, UTF-8 text, indented
  JSON, format marker `NewLight Workflow`, schema version `1`, application
  marker `NewLight_Analysis`, an ISO timestamp, and an ordered `steps` array.
  Each step contains `function`, Chinese `name`, and a JSON object named
  `parameters`. Duplicate steps and exact user-submitted parameter values are
  preserved in order. Files are declarative data and must never contain or
  execute Python code.
- Version 1 supports these function IDs: `caiman_motion`,
  `builtin_rigid_motion`, `image_shift`, `gaussian_smooth`, `median_filter`,
  `background_subtract`, `bleach_correction`, `enhance_contrast`, and
  `remove_vessel_artifact`, plus `load_roi`. Their Chinese names come from
  `PREPROCESS_PANEL_SPECS` where applicable; `load_roi` is labelled `载入 ROI`.
- Saving reads the current dataset's FIFO history. Supported descriptors in
  `COMPLETED`, `RUNNING`, or `QUEUED` state are retained. Failed, cancelled,
  cancelling, descriptor-less, malformed, or unsupported tasks are skipped
  and the saved/skipped counts are logged. If no reusable step exists, no file
  dialog opens. The default directory is the current source file's folder, or
  the source folder itself for folder datasets.
- A workflow stores no movie pixels, ROI masks, stimulus data, movie input path,
  output path, temporary path, save action, or export destination. The one
  input-artifact exception is `load_roi`: it stores the selected ROI/atlas file
  path, format, and (for atlas JSON/images) `min_area`; the referenced file must
  still exist when the workflow is replayed.
  `执行工作流` first requires a currently loaded movie, validates the complete
  JSON document before queueing anything, then applies all steps to that
  current dataset through the same `run_preprocess_action()` paths used by
  manual operation. A file saved in one session therefore remains available
  after restart and can run on a different dataset.
- One generated workflow run ID links replayed tasks while the existing global
  single-worker FIFO remains authoritative. A worker or completion-callback
  error marks that run failed; user cancellation marks it cancelled. Later
  tasks from that run raise `TaskCancelled` before touching movie data. The
  failed state is not overwritten by skipped-task cancellations, and unrelated
  manual tasks continue normally. The final successful task marks the run
  completed. Replayed tasks retain descriptors, so their history can be saved
  as another workflow.
- Deliberately excluded from version 1: loading/adding movie channels, saving
  and exporting, manual ROI interaction, interactive automatic edge cropping,
  preview-only display adjustment and vessel preview, DeepCAD-RT preview/cache,
  ROI segmentation, peak detection, and analysis outputs. These either depend
  on a file destination, require user interaction, do not replace the movie
  consumed by the next step, or produce analyses rather than a reusable movie
  preprocessing chain. Do not add them without defining deterministic replay
  and path/interaction policy plus a schema-version review.
- Future detailed user manuals must show the two task-flow buttons and explain:
  file extension and portability; supported and excluded functions; that order
  and duplicates are preserved; that execution targets the currently loaded
  data; that movie paths and pixel data are not embedded; that `load_roi`
  references an external ROI file; how failed/cancelled steps stop later
  workflow steps; how task colors/statuses indicate queued, running,
  completed, failed, and skipped work; and that permanent movie output still
  requires the normal save command after processing.
- Regression coverage is in `tests/test_workflow_core.py`,
  `tests/test_workflow_gui.py`, `tests/test_task_queue.py`, and
  `tests/test_gui_static.py`. Final verification passed as `235` non-peak tests
  plus `11` peak/Tk tests (`246` total), with touched Python compilation,
  `git diff --check`, and real Tk smoke at `1440x920` and `1100x760`. The
  portable EXE predates this source change and was not rebuilt as part of this
  implementation.

## Default Window State (2026-07-31)

- `NewLightApp.__init__()` keeps `1440x920` as the fallback geometry and calls
  `root.after_idle(_maximize_main_window)`. The helper requests Tk's Windows
  `zoomed` state after the first layout, so the normal application starts
  maximized while preserving the fallback size if the platform cannot
  maximize.
- The helper returns without changing a root whose state is `withdrawn`; this
  is intentional for headless/hidden Tk tests. If `state("zoomed")` is not
  accepted, it tries `attributes("-zoomed", True)` under a TclError guard.
- The real startup smoke verified `state=zoomed` and `2194x1163` on the current
  machine. Keep this delayed call when adjusting the main layout; calling
  maximize before widgets/layout initialization can produce incorrect canvas
  sizing.
## Frozen Initialization Splash (2026-08-03)

- The portable EXE now shows an animated initialization window while first-run backend, adapter, CUDA, and optional NVIDIA driver checks execute. Source launches and machines whose setup state is already complete do not show the splash.
- The splash implementation is isolated in `initialization_splash.py`; `launch.py` only decides whether the setup gate needs the splash.
- The background packaged into `_internal` is `neural_starlight_startup.gif`: 720 x 480, 25 frames, five-second loop, about 3.67 MB. Do not package the original approximately 95.8 MB `neural_starlight.gif`.
- The accepted layout centers `xhr.ico`, `NewLight Analysis`, and `神经影像分析平台`. Its bottom row has three equal regions: version at left, live setup status at center, and a 44 x 44 eight-dot sequential bubble loader at right.
- `machine_setup.ensure_first_run_setup()` and `ensure_application_setup()` accept optional `progress` and `dialog_visibility` callbacks. They remain UI-framework independent and preserve all previous setup return semantics.
- Native administrator, error, install, and restart dialogs hide the splash before opening and restore it afterward only if setup continues. Tk updates are marshalled to the main thread through a queue.
- `SplashUnavailableError` is the only launch fallback trigger. Setup-operation exceptions must never rerun setup, because doing so could repeat an external action such as driver installation.
- Regression coverage is in `tests/test_initialization_splash.py`, `tests/test_machine_setup.py`, and `tests/test_packaging_contracts.py`. The focused suite reached `30 passed`; a real Tk delayed-operation smoke returned `True` and closed normally.
## DeepCAD-RT With Channel Pseudocolor (2026-08-03)

- Read this section before changing channel colors, DeepCAD preview caches, or movie export routing.
- Root cause of the former no-effect bug: `display_image_for_render()` returned `converted_color_image()` before consulting the separate DeepCAD cache, and `save_current_movie()` returned from its pseudocolor branch before its DeepCAD branch. The checkbox and model could run successfully while both preview and export still read the raw channel movies.
- The required pipeline is now fixed as: raw grayscale channel -> channel preprocessing -> per-channel DeepCAD output -> raw/DeepCAD weight blend -> pseudocolor composition -> display controls -> preview/export.
- Multi-channel DeepCAD is deliberately run once per grayscale channel, in FIFO order. Do not apply a denoised maximum/composite movie back onto each channel; that destroys channel identity and can create cross-channel color artifacts.
- `deepcad_denoised_movie` remains the combined analysis cache. `deepcad_denoised_channels` stores the independent channel outputs used by pseudocolor preview and channel export. `deepcad_cache_is_current()` validates both layers when channel data exists.
- Pseudocolor preview blends only the current frame or current projection; it must not allocate a permanent full blended channel movie. Pseudocolor AVI/TIFF export blends each frame immediately before color composition.
- Changing DeepCAD weight is part of the channel render cache key. Weight changes must immediately produce a different preview without rerunning the model.
- Save behavior covers both states: an existing channel cache is reused; if Save is requested before the cache exists, the save task runs DeepCAD per channel, writes the requested output, then fills the preview cache.
- Regression coverage is in `tests/test_pseudocolor_deepcad.py`, including weight endpoints, channel identity, GUI frame routing, independent per-channel model calls, and TIFF overlay-before-color output.

## CaImAn ROI Cell-Size Range (2026-08-03)

- CaImAn ROI segmentation no longer needs to force every cell through one diameter prior. The right-side parameter panel now defaults to `范围自适应（推荐）`, with minimum and maximum cell diameters; `快速单尺度` retains the legacy one-diameter behavior for reproducibility and faster trials.
- In range mode, `roi_adaptation.caiman_multiscale_diameters()` derives minimum, geometric-middle, and maximum representative sizes. It deduplicates scales by the actual CaImAn prior `gSig = max(1, round(diameter / 4))`, so close diameter values do not launch redundant workers.
- CaImAn jobs remain sequential in the existing FIFO task worker. Each effective scale is run independently, then `analysis_core.merge_caiman_multiscale_roi_results()` saves a combined artifact and summary rather than making the GUI manage raw worker artifacts.
- Fusion keeps arbitrary CaImAn footprint shapes. Candidates are only treated as duplicate when their spatial IoU is at least `0.60`, or when IoU is at least `0.35` and their temporal traces correlate at least `0.85`; a correlated adjacent cell without spatial overlap is retained. When duplicates compete, the accepted/CNN/spatial-correlation/SNR quality ordering retains the stronger component.
- `从当前 ROI 填入直径范围` converts hand-drawn ROI areas to equivalent diameters. With two or more examples it fills a small/large range with modest margins; with one example it follows the existing UI convention and updates only the maximum. The adaptive CaImAn action applies the same range fitting before queuing.
- The merged result stores `scale_diameter`, `scale_gsig`, `multiscale_duplicate_count`, the effective scales, and source artifacts. Completion logs the scales and number of removed cross-scale duplicates. This is specific to CaImAn ROI segmentation and does not affect CaImAn motion correction.
- Regression coverage added in `tests/test_roi_adaptation.py`, `tests/test_roi_backend_wrappers.py`, and `tests/test_gui_static.py`. Focused verification passed `55` ROI logic/backend tests plus `44` GUI static tests. The local CaImAn environment can emit an unrelated OpenCL `temp.txt` cleanup warning after successful tests; preserve the explicit `PYTHONIOENCODING=utf-8` test invocation when calling through `conda run` on this machine.

### Default-range and CNN-only false-positive correction

- A real default run on `example/twophone.avi` exposed an unsafe interaction: the former automatically derived `8-18 px` range produced `24/7/8` candidates at `8/12/18 px`. The 24 small-scale candidates had areas `24-75 px^2`, temporal SNR only about `0.52-1.13`, and spatial correlations mostly near zero, but CNN scores around `0.9-1.0`. CaImAn selects the union of SNR, spatial-correlation, and CNN passes (subject to low rejection floors), so CNN alone admitted these scale-specific false positives.
- The default range now derives as `1.0x-2.0x` the legacy diameter: the legacy `12 px` default becomes `12-24 px`. The exact previously generated `8-18 px` default pair is migrated on the next panel open and persisted after the next run; genuinely custom ranges remain editable.
- Direct multiscale fusion now requires non-CNN evidence. A candidate is retained when temporal SNR meets the configured minimum, spatial correlation meets its configured minimum, or the component is independently reproduced at another effective `gSig`. CNN remains useful for CaImAn classification and quality ordering, but cannot by itself flood a multiscale union. Single-scale compatibility mode keeps native CaImAn selection behavior, and adaptive candidate-bank generation intentionally remains unfiltered because its later adaptive quality stage owns selection.
- Re-merging the exact reported `8/12/18 px` artifacts with the corrected rule reduced `36` displayed ROIs to `9`: `27` CNN-only low-quality candidates were removed, `3` cross-scale duplicates were merged, all retained areas were `105-469 px^2`, and no `8 px` false-positive component remained.
- The multiscale summary now records `multiscale_quality_rejected_count`; the run log reports this count separately from duplicate removal. Focused regression after this correction passed `102` tests across GUI static checks, ROI adaptation, and backend wrappers.

### CaImAn run-button silent failure correction

- The first default-range correction accidentally left `default_min` and `default_max` as locals of `caiman_roi()` while `_run_caiman_roi_from_panel()` referenced them as fallback values. Clicking either CaImAn run action raised `NameError` before `enqueue_task()`. Tk did not surface that callback exception in the embedded UI, so the task list and feedback appeared unchanged.
- `_caiman_diameter_defaults(saved)` is now a shared static helper used by both panel construction and run-time parameter parsing. A direct handler regression test verifies that saved range settings reach `enqueue_task()`.
- `run_parameter_action()` now catches unexpected callback exceptions, writes a concise error to the parameter feedback and run log, and logs the traceback. Future parameter-submission defects must not appear as a dead button.
- Focused verification after this correction passed `125` tests across workflow GUI behavior, GUI static contracts, ROI adaptation, and backend wrappers.

### Adaptive ROI cache-miss branch correction

- The first multiscale integration mis-indented the CaImAn branch in `_enqueue_adaptive_roi()`: its `else` bound to `if not reused` instead of `if engine == "fast"`. On a cache miss, the CaImAn backend was skipped and `bank=None` reached `adapt_candidate_bank()`, producing `'NoneType' object has no attribute 'masks'`. The same structure also prevented the fast engine from building a bank on its first adaptive run.
- The corrected structure is `if not reused: if fast: run fast backend; else: run CaImAn scale(s); then build CandidateBank`. Cache-hit behavior remains unchanged and bypasses backend generation.
- A functional regression executes the queued adaptive worker closure on a CaImAn cache miss, verifies the backend is called once, confirms a `(1, H, W)` candidate bank is produced, and confirms fitting returns a selected candidate before any finish callback runs.
- Focused ROI/GUI verification after this correction passed `126` tests.

## NeuroAlign Current-Stream Registration (2026-08-03)

- Read this section before changing NeuroAlign inputs, staged execution, or configuration parsing.
- NeuroAlign registration now always uses the current in-memory `state.movie`, including preprocessing already applied in the application. The right parameter panel no longer exposes or persists a separate registration-video path; Atlas JSON and output directory remain user-selectable.
- On the first staged rebuild, the app captures the current movie object, movie generation, and frame rate. A worker streams it to `session_temp_dir/neuroalign_inputs/current_stream_*.avi`; the file is removed with the normal session cleanup when the app closes. The writer uses lossless FFV1 when available and MJPG only as an OpenCV compatibility fallback.
- All three stages reuse that one snapshot. If the current movie or its generation changes during the wizard, the app rejects the mixed run and asks the user to reopen NeuroAlign. A completed worker result is also discarded if it belongs to an older movie generation.
- The reported `could not convert string to float: '12,8,5,3,1'` came from treating every non-integer configuration value as one float. `parse_neuroalign_cfg_values()` now parses integer keys, ordinary floats, and comma-separated float-list keys separately; `tps_smooth_candidates` remains a normalized list string for the backend's `parse_float_list()`.
- Regression coverage is in `tests/test_neuroalign_current_movie.py`. Focused NeuroAlign plus GUI static tests passed `51` tests, and workflow GUI regression passed `24` tests. The local Conda OpenCL `temp.txt` cleanup message can still appear after a successful pytest process and is unrelated to NeuroAlign.

### NeuroAlign bilateral outer contour correction (2026-08-04)

- A real outer-stage run still showed the red Atlas contour at roughly half the subject width. The saved subject mask contained two valid components (`68,256` and `66,896` pixels), while the worker passed only `largest_contour_from_mask(subject_mask)` to the bilateral Atlas fit.
- `neuroalign_step_worker.bilateral_outer_contour()` now selects the dominant left/right components, connects them only at their natural superior and inferior overlap rows, and extracts one bilateral contour. The longitudinal fissure remains available to the separate midline profile detector; the saved subject mask is unchanged.
- Do not interpret the old `outer_anchor_weight` or `outer_anchor_count` as a fix for this specific failure. They affect later staged/TPS controls; the old initial affine was already working from a single hemisphere.
- The sample's offline re-evaluation improved initial outer IoU from about `0.354` to about `0.86` and reduced midline error from about `15.5 px` to about `5 px`. The red contour should now be checked again at stage 1 before proceeding to clustering.
- Regression coverage is in `tests/test_neuroalign_bilateral_contour.py`; the focused contour/current-stream/GUI suite passed `53` tests. No sample file was modified and no EXE was built.

### NeuroAlign preview isolates stale ROI overlays (2026-08-04)

- When Atlas Reference Builder completed before NeuroAlign, its generated ROIs remained in `state.roi_masks`. The main redraw routine then painted those old, source-resolution ROI boundaries on top of the NeuroAlign preview, making them appear in the upper-left while the new preview itself was correctly aligned.
- `redraw()` now suppresses the existing ROI overlay only while `display_source[0] == "neuroalign_preview"`. Closing the wizard restores the prior movie/ROI view; accepting the final NeuroAlign result still replaces the ROI list through `_finish_neuroalign()`.
- Regression coverage is in `tests/test_gui_static.py`; the focused NeuroAlign/current-stream/GUI suite passed `54` tests after this change.

### User manual revision (2026-08-04)

- Updated `docs/NewLight_Analysis_User_Manual.docx` in place from the user's current edited version rather than regenerating the manual.
- Added current first-run administrator/CUDA behavior, release-directory distinction between source `run_NewLight_Analysis.bat` and the portable EXE, current-stream NeuroAlign input, session AVI snapshots, bilateral contour troubleshooting, stale Atlas Builder ROI preview isolation, and three new NeuroAlign FAQ entries.
- Preserved the existing 38 tables and 8 embedded visuals. Structural verification found 301 paragraphs, 22 FAQ rows, and all newly added topics in the final document.
- LibreOffice/`soffice` is not installed on this machine, so the required DOCX-to-PNG visual render could not be completed. The existing document's image alt-text findings were not changed during this content-only revision.

## DeepCAD-RT Optional GPU Addon (2026-08-04, Superseded)

> This section records the intermediate DeepCAD-only split. Do not implement
> against it. The active design is the complete GPU addon described in the
> following section, installed under `_internal\GPU_Addon`.

- Read this section before changing packaging, first-run CUDA setup, or
  DeepCAD paths. The core PyInstaller package intentionally excludes DeepCAD
  source and `DeepCADRT_Model\*.pth`.
- `build_deepcad_addon.bat` creates `DeepCADRT_CUDA_Addon.zip` containing a
  top-level `DeepCADRT_Addon` directory. Publish that exact ZIP to the GitHub
  Release URL in `deepcad_addon_manifest.json` and keep its SHA-256 synchronized
  with the manifest.
- On a frozen CUDA-capable launch, `machine_setup.ensure_deepcad_addon()`
  downloads and verifies the archive, rejects unsafe ZIP paths, and installs it
  under `_internal\DeepCADRT_Addon`. A download failure does not block ordinary
  analysis. AMD/Intel and CPU-only machines skip the addon.
- Do not remove `magma`, `cusolver`, `cusparse`, or related Torch/CUDA DLLs from
  the core package solely because DeepCAD uses them. A packaging experiment
  proved that NeuSuite/Torch imports also depend on this shared runtime.
- Focused packaging and machine-setup tests passed: `36 passed`. No EXE or Inno
  Setup installer was built for this change.

## Complete GPU Runtime Addon (2026-08-04)

- The core package is built from `caiman_latest`, but the core spec explicitly
  excludes Torch, TorchVision, timm, NeuSuite, and CUDA DLLs. It retains
  CaImAn/OpenCV CPU workflows and contains no Torch runtime.
- `NewLight_GPU_Worker.spec` builds a separate CUDA worker from
  `caiman_latest`. `build_gpu_addon.bat` stages its CUDA runtime, worker,
  DeepCAD source/model, NeuSuite runtime/model, and Torch under `GPU_Addon`.
- The GPU archive is larger than GitHub's single-asset limit, so the builder
  creates `.part01` and `.part02`. `machine_setup.ensure_gpu_addon()`
  downloads and verifies parts and the reconstructed archive before installing
  `_internal\GPU_Addon`.
- `gpu_addon_manifest.json` is the active manifest. The old
  `deepcad_addon_manifest.json` filename and `ensure_deepcad_addon` symbol are
  accepted only as backward-compatible fallbacks for older builds.
- `analysis_core.run_deepcadrt_denoise()` routes frozen DeepCAD execution to
  `GPU_Addon\NewLight_GPU_Worker.exe`; the CPU worker is not used for CUDA
  inference. Existing source-mode Conda behavior remains available.
- GPU worker verification passed for CUDA, DeepCAD, and NeuSuite. The final
  rebuilt core is 1,102,414,238 bytes (about 1.027 GiB) with zero Torch/CUDA
  files. Focused packaging and
  backend tests passed: `60 passed`; the Inno installer still needs to be built.
