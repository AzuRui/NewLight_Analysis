# NewLight_Analysis Handoff

Last updated: 2026-05-08

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
- `build_exe.bat`, `NewLight_Analysis.spec`, `NewLight_Analysis_setup.iss`: packaging.
- `README.md`, `DESIGN_NOTES.md`, `PACKAGING.md`: user/developer notes.

## Environment Notes

Known working candidate environments from prior checks:

- `neuroseg3`
- `caiman_latest`
- `deepcadrt`

The `base` environment was not suitable for GUI work because `cv2` failed to import with a DLL load error. `openpyxl` was missing in checked environments, while `pandas` was present in `neuroseg3` and `caiman_latest`.

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

