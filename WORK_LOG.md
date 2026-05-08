# Work Log

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
