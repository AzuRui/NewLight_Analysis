# NewLight_Analysis Handoff

Last updated: 2026-05-14

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

## Current UI State

Recent display work restored the Matplotlib navigation toolbar under the main canvas. The redundant custom `Fit View / Zoom In / Zoom Out` row has been removed because the toolbar already covers home/reset, pan, zoom, and save interactions.

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
- `NewLightApp.session_temp_dir` is a per-run OS temp directory removed by `on_close` / `cleanup_session_temp`. DeepCAD-RT, NeuroSeg3, and CaImAn worker intermediates should use `temp_work_dir(...)`, not source-folder `NewLight_temp`, unless the user explicitly asks to preserve intermediates.
- DeepCAD preview is a display/save overlay only. It should not mutate or replace `state.movie`; preprocessing should operate on the current true movie, and DeepCAD display should re-run/cache against that movie after preprocessing changes.
- Current preprocessing buttons are destructive operations: each one mutates `state.movie`, pushes history, clears DeepCAD cache, recomputes baseline/projection, and subsequent preprocessing stacks on top of previous operations. `Save Current Movie` saves that current processed movie, plus DeepCAD blend if enabled/cache-ready.
- Future pipeline refactor idea: introduce a non-destructive preprocessing script/config (for example a JSON list of operations and parameters) that is reapplied for preview and for full-movie export. This would replace destructive mutation with recorded operations while keeping `Save Current Movie` as the point where the whole pipeline is rendered to disk.
- DeepCAD preview runs are token-guarded. If the user changes the loaded movie while a background denoise is running, the stale result is ignored instead of replacing the current cache.
- `Save Current Movie` opens a standard Save As dialog instead of silently writing a fixed output path. The dialog starts in the loaded movie's folder, suggests `result.<source extension>` for `.tif`, `.tiff`, and `.avi`, and falls back to `result.tif` for unsupported source video extensions. Canceling the dialog must not run DeepCAD-RT or write output.
- `analysis_core.save_movie` supports `.tif/.tiff` and `.avi`. TIFF keeps float stack data; AVI uses OpenCV MJPG at the current Movie Hz and converts to 8-bit by 1-99 percentile scaling.
- `NewLight_Analysis.spec` includes `DeepCADRT_Model`, `workers`, `csbdeep`, `neuroalign_step_worker.py`, `NeuroAlign_atlas_registration_help.txt`, `NeuroAlign_atlas_registration_summary.json`, `PACKAGING.md`, NeuroSeg3 source/weights/configs/utils, DeepCAD-RT `deepcad` source, NeuroAlign source, `hdmf` / `pynwb` data files, and `ipyparallel\cluster\shellcmd_receive.py`. These are runtime resources and should stay bundled.
- `build_exe.bat` / `build_full_release.bat` check that `DeepCADRT_Model\E_02_Iter_6416.pth` exists before building and accept `/nopause` or `--no-pause` for unattended runs. Do not run a build unless the user explicitly asks.
- Current portable EXE output path is `E:\WorkSpace\NewLight_Analysis\build_release\NewLight_Analysis\NewLight_Analysis.exe`; launcher path is `E:\WorkSpace\NewLight_Analysis\build_release\Run_NewLight_Analysis.bat`.
- In PyInstaller 6 onedir builds, data resources live under `build_release\NewLight_Analysis\_internal`. `check_backends.bat` detects that location before calling worker scripts or checking the bundled DeepCAD-RT model.
- Latest build on 2026-05-14 used `conda run -n caiman_latest cmd /c build_exe.bat /nopause`. Release validation passed: `check_backends.bat` reports bundled Python, NeuroSeg3, CaImAn, and DeepCAD-RT backend checks OK; a deeper `_internal\NewLight_Worker.exe` import check passed for `ultralytics`, `caiman`, `igraph`, `leidenalg`, `deepcad.test_collection`, `atlas_registration_merged_bilateral_midline`, and `csbdeep.utils.normalize`; frozen `analysis_core.run_conda_worker(...)` resolves `_internal\NewLight_Worker.exe` correctly; GUI startup smoke passed.
- `NewLight_Worker.exe` intentionally lives in `_internal` and uses a different console/tool icon from the main GUI. Do not move it back to the release root manually; the PyInstaller spec controls its runtime resource layout.
- Inno Setup `ISCC.exe` was not installed/found on the build machine during the latest pass, so `build_full_release.bat` would skip installer creation and leave the complete portable folder ready. Install Inno Setup 6 or put `ISCC.exe` on `PATH` to produce the installer from `NewLight_Analysis_setup.iss`.

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
