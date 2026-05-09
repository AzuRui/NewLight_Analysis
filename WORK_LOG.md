# Work Log

## 2026-05-09

### Context Safety And New Chat Handoff

- Added a task-completion context-safety self-check to `PROJECT_HANDOFF.md`.
- Documented the 80% background/context threshold for proactive handoff refresh.
- Documented the 70% post-compression distortion threshold for recommending a new chat.
- Added a new-chat startup checklist that tells the next assistant which project files, git commands, and records to inspect first.

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
