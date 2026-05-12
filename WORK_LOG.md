# Work Log

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
