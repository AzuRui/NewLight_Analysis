# NewLight_Analysis

NewLight_Analysis is an integrated two-photon analysis front end for experimenters. It combines the expected workflow from the LabVIEW two-photon analysis software, the ROI and heatmap analysis style from `2cafe_analysis`, NeuroSeg-based automatic ROI selection, and CaImAn-style preprocessing.

The UI uses a dark neurosurgical imaging workstation style: low-glare panels, cyan/purple accents, and a subtle neural starfield header while keeping the imaging canvas high contrast for grayscale data inspection.

## Recommended Architecture

- Main app: plain Python/Tkinter, so users can launch it by double-clicking `run_NewLight_Analysis.bat`.
- NeuroSeg3 backend: called through `conda run -n neuroseg3`, isolated from the main app.
- CaImAn backend: designed for `conda run -n caiman_latest`, isolated from NeuroSeg and the main app.
- Built-in fallback algorithms are included for motion correction, filtering, vessel artifact detection, ROI drawing, dF/F extraction, heatmap export, trace plotting, and correlation.

This avoids forcing users to understand conda environments. The user sees one app; developers can maintain each algorithm in its own environment.

## Launch

```powershell
E:\WorkSpace\NewLight_Analysis\run_NewLight_Analysis.bat
```

or:

```powershell
cd E:\WorkSpace\NewLight_Analysis
python NewLight_Analysis.py
```

## First Version Features

- Load `.tif`, `.tiff`, `.avi`, `.mp4`, `.mov`, `.mkv` movies.
- Load stimulus `.txt/.csv/.dat` files, or generate triggers from fixed time intervals.
- Set movie frame rate, stimulus sample rate, baseline time window, and pre/post trigger windows from the GUI.
- Preview mean, max, standard deviation, and local correlation images.
- Drag the frame slider under the main viewer to inspect any frame after preprocessing.
- Preprocessing with parameter dialogs and undo:
  - CaImAn motion correction backend
  - built-in rigid motion correction
  - Gaussian smoothing
  - median filtering
  - background subtraction
  - bleaching correction
  - contrast enhancement
  - vessel/artifact detection
  - vessel/artifact suppression
- Acceleration panel:
  - detects CUDA status for the main Python process and the isolated NeuroSeg3 environment
  - uses CuPy automatically for supported array operations when available
  - falls back to CPU/NumPy when CuPy is unavailable
- ROI tools:
  - NeuroSeg3 auto ROI backend
  - manual NeuroSeg3 detection confidence input and selectable `.pt` weight path
  - automatic built-in ROI fallback when NeuroSeg3 returns zero masks
  - built-in auto ROI
  - atlas/image ROI import
  - center-circle ROI drawing
  - freehand ROI drawing
  - load/save ROI `.npz`
- Analysis:
  - dF/F trace extraction
  - optional `env_secant` baseline correction
  - adjustable dF/F moving-average window
  - stimulus trigger marking
  - trial average around triggers
  - peak counting
  - ROI correlation
  - ROI statistics table and Excel export
  - heatmap display
  - standalone heatmap AVI generation with live frame preview and cancel support
  - export CSV/XLSX/PNG/JSON/NPZ results

## Suggested Experimenter Workflow

1. Double-click `run_NewLight_Analysis.bat`.
2. Open a movie in the Data tab.
3. If the experiment has stimulation, open the stimulus file, fill the Protocol fields, then click `Detect Triggers`.
4. Run preprocessing operations as needed. Every preprocessing step is stored in the undo stack.
5. Create ROIs with `NeuroSeg3 Auto ROI`, atlas/image import, circle drawing, or freehand drawing.
6. Extract dF/F traces, inspect peak/correlation/trial-average views, then export the analysis.

`Export Analysis` does not create AVI videos automatically. Use `Analysis -> Generate Heatmap AVI` when a heatmap video is needed. The heatmap window previews the currently selected frame, updates when parameters or frame position change, and allows cancelling during video generation.

## NeuroSeg And CaImAn Choice

This version uses NeuroSeg3 as the preferred ROI backend. NeuroSeg2 is kept as a legacy/reference path because its Python 3.6 and TensorFlow 1.x requirements are hard to combine with modern CaImAn. CaImAn is kept in its own `caiman_latest` environment and is used for non-ROI preprocessing first, especially motion correction.

## NeuroSeg3 Parameters

`Detection conf` is YOLO's object-level confidence cutoff. A predicted ROI instance is kept only if the model confidence for that whole instance is above this value. Lower values keep more uncertain ROIs; higher values keep fewer, more confident ROIs. The GUI exposes this as a manual input because this dataset may need small values such as `0.002`.

`Mask pixel cutoff` is the pixel-level threshold applied inside each accepted instance mask. The GUI keeps it fixed at `0.50` so routine NeuroSeg3 ROI creation has one primary tuning control; the backend still accepts an explicit value for advanced debugging.

## Backend Notes

NeuroSeg3 is preferred over NeuroSeg2 for this integrated software because it uses a newer PyTorch/YOLOv8-based stack and is easier to isolate as a worker process. NeuroSeg2 remains valuable as a compatibility/reference path, but its Python 3.6 + TensorFlow 1.15 + Keras 2.2 stack should not be merged into a modern CaImAn environment.

CaImAn 1.13.1 should live in a separate environment such as:

```powershell
conda create -n caiman_latest -c conda-forge caiman=1.13.1 python=3.11 -y
```

The app will still run without `caiman_latest`; only the CaImAn motion correction button will fail with a clear backend error.

## CUDA Acceleration

The desktop client now checks available acceleration backends from the Preprocess tab.

- NeuroSeg3 runs in the isolated `neuroseg3` conda environment and can use CUDA through PyTorch when that environment sees the GPU.
- Main-app operations such as projection, dF/F, Gaussian smoothing, and ROI trace extraction can use CuPy when CuPy is installed in the Python environment that launches the desktop app.
- If CuPy is not installed, those operations automatically fall back to CPU/NumPy.
- CaImAn motion correction is left in the `caiman_latest` environment and may still be CPU/I/O bound depending on the CaImAn build.

For a packaged client, the practical high-value path is to keep NeuroSeg3 GPU-enabled and optionally provide a CuPy-enabled main runtime for large movies.
