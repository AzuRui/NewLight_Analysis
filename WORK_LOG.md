# Work Log

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
