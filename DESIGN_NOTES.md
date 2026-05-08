# NewLight_Analysis Design Notes

## NeuroSeg Choice

NeuroSeg3 is the better default backend for this integrated application.

- NeuroSeg2 is valuable as a legacy/reference implementation, but it is locked to Python 3.6, TensorFlow 1.15, and Keras 2.2.4.
- NeuroSeg3 uses Python 3.8, PyTorch 1.13.1, CUDA, and a YOLOv8-style segmentation pipeline. It is much easier to run as a worker backend and to convert its instance masks into CaImAn-compatible ROI masks.
- Keeping NeuroSeg3 isolated behind `conda run -n neuroseg3` means the experimenter does not need to understand the environment. The main app simply calls the backend.

## User-Friendly Deployment

The recommended deployment is not a single all-in-one conda environment. That would make CaImAn, NeuroSeg2, NeuroSeg3, CUDA, TensorFlow, PyTorch, and GUI dependencies fight each other.

Instead:

- The main app runs in a lightweight Python environment.
- NeuroSeg3 stays in `neuroseg3`.
- CaImAn latest stays in `caiman_latest`.
- The user launches only `run_NewLight_Analysis.bat`.
- Developers can verify optional backends with `check_backends.bat`.

This is simpler for experimenters because they do not see conda. It is also safer for developers because each algorithm keeps the dependency versions it needs.

## Feature Mapping

Current first version:

- File loading and image display from the LabVIEW/Python workflows.
- Stimulus/protocol fields inspired by `read protocol.vi` and the 2cafe trigger workflow.
- Mean/max/std/local-correlation views.
- Preprocessing module with parameter dialogs and undo.
- Motion correction via built-in rigid correction, with optional CaImAn worker.
- ROI drawing with circle and freehand modes.
- Automatic ROI with built-in thresholding and optional NeuroSeg3.
- Atlas/image ROI import for compatibility with pre-drawn maps.
- dF/F traces, baseline correction, trace plot with trigger markers, peak count, ROI correlation.
- Trial average around detected or interval-generated triggers.
- Heatmap display, heatmap PNG, and heatmap AVI export.
- ROI, trace, statistics Excel, heatmap, summary export.
- Vessel/artifact detection and suppression.

Planned follow-up:

- Direct CaImAn seeded CNMF from NeuroSeg ROI masks.
- Manual ROI merge/split table.
- Trial averaging and peri-stimulus heatmap.
- LabVIEW-style parameter presets and report templates.
- Packaged Windows installer or frozen executable.
