# NewLight_Analysis Handoff

Last updated: 2026-05-09

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

## New Chat Startup Checklist

When a new chat takes over this project, read this file first. Then inspect these items before making changes:

- `WORK_LOG.md`: latest completed work and decisions.
- `git status --short --branch`: whether the working tree is clean.
- `git log --oneline --decorate -5`: recent checkpoints and rollback targets.
- `NewLight_Analysis.py`: especially GUI state, display canvas, ROI controls, heatmap AVI dialog, and workflow callbacks.
- `analysis_core.py`: especially movie I/O, dF/F, ROI processing, heatmap rendering, and export functions.
- `NewLight_Analysis.spec`, `build_exe.bat`, `NewLight_Analysis_setup.iss`: packaging path if the task involves compiling or installer generation.

Recommended new-chat instruction:

```text
Please continue the NewLight_Analysis project. First read E:\WorkSpace\NewLight_Analysis\PROJECT_HANDOFF.md and E:\WorkSpace\NewLight_Analysis\WORK_LOG.md, then inspect git status/log before changing files.
```

## Context Safety Policy

At the end of every substantial task, perform a context-safety self-check:

1. If background/context usage is above 80%, update `PROJECT_HANDOFF.md` and `WORK_LOG.md` before starting the next task so the next step can continue from compact, explicit records instead of relying on a long chat.
2. If context compression is needed, do it after a task finishes, not in the middle of reasoning or while a code change is half-complete.
3. After compression, if estimated information distortion or loss is above 70%, tell the user to open a new chat and instruct the new chat to read this handoff file first.
4. If a new chat is opened, the handoff source of truth is this file plus `WORK_LOG.md`, not the memory of the previous conversation.

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
