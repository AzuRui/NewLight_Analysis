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
