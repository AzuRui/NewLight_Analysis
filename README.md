# NewLight_Analysis

NewLight_Analysis is an integrated two-photon analysis front end for experimenters. It combines the expected workflow from the LabVIEW two-photon analysis software, the ROI and heatmap analysis style from `2cafe_analysis`, CaImAn source extraction, and the authorized NeuSuite instance-segmentation model.

The UI uses a dark neurosurgical imaging workstation style: low-glare panels, cyan/purple accents, and a subtle neural starfield header while keeping the imaging canvas high contrast for grayscale data inspection.

## Recommended Architecture

- Main app: plain Python/Tkinter, so users can launch it by double-clicking `run_NewLight_Analysis.bat`.
- Fast ROI backend: the authorized `NeuSuite2p/segment_model.pt` and custom runtime run through the existing CUDA-enabled `neuroseg3` environment.
- CaImAn ROI backend: CNMF/CNMF-E runs through the project-local `.conda_envs/newlight_caiman` environment created by `setup_newlight_caiman.bat`.
- Both ROI workers return versioned NPZ artifacts containing independent arbitrary-shape masks; neither converts instances to circles, ellipses, or connected components from a merged PNG.
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

## User Manual

The detailed Chinese user manual is maintained at:

```text
docs\NewLight_Analysis_User_Manual.md
docs\NewLight_Analysis_User_Manual.docx
docs\NewLight_Analysis_User_Manual.pdf
```

Release builds copy these files into `dist\NewLight_Analysis`. The manual
contains numbered screenshot placeholders so project screenshots can be added
later without restructuring the operating instructions.

## First Version Features

- Load `.tif`, `.tiff`, `.avi`, `.mp4`, `.mov`, `.mkv` movies.
- Load stimulus `.txt/.csv/.dat` files, or generate triggers from fixed time intervals.
- Set movie frame rate, stimulus sample rate, baseline time window, and pre/post trigger windows from the GUI.
- Preview mean, max, standard deviation, and 25% percentile images.
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
  - `CaImAn 识别分割`: CNMF for two-photon data or CNMF-E for one-photon data, with quality scores and temporal traces
  - `快速 ROI 分割`: authorized NeuSuite projection-image instance segmentation
  - zero detections or worker failures preserve the current ROI set
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
5. Create ROIs with `CaImAn 识别分割`, `快速 ROI 分割`, atlas/image import, circle drawing, or freehand drawing.
6. Extract dF/F traces, inspect peak/correlation/trial-average views, then export the analysis.

`Export Analysis` does not create AVI videos automatically. Use `Analysis -> Generate Heatmap AVI` when a heatmap video is needed. The heatmap window previews the currently selected frame, updates when parameters or frame position change, and allows cancelling during video generation.

## ROI Engine Choice

Use `快速 ROI 分割` for interactive projection-based segmentation. Its useful controls are confidence, instance IoU, model input size, and restored-pixel area limits. The worker reads `results[0].masks.data` directly and preserves overlapping instances.

Use `CaImAn 识别分割` when temporal calcium activity should participate in source extraction. Cell diameter is converted to `gSig = max(1, round(diameter / 4))`; component quality is filtered with temporal SNR, spatial correlation, and the optional CaImAn CNN score. The footprint threshold is relative to each component peak.

## Backend Notes

Create the isolated CaImAn environment and controlled CNN resources with:

```powershell
setup_newlight_caiman.bat
```

Prepare the small pure-Python NeuSuite runtime dependencies with `setup_neusuite_runtime.bat`. The script can copy them from the authorized NeuSuite bundle when PyPI is unavailable.

## CUDA Acceleration

The desktop client now checks available acceleration backends from the Preprocess tab.

> **Important - DeepCAD-RT requires CUDA:** DeepCAD-RT denoising has no CPU
> fallback in NewLight_Analysis. It can run only on a CUDA-capable NVIDIA GPU
> with a compatible NVIDIA driver. Bundling the `.pth` model and CUDA runtime
> libraries does not make DeepCAD-RT usable on a CPU-only computer. Other
> functions may support CPU execution as described below, but that does not
> apply to DeepCAD-RT.

- NeuSuite fast ROI runs in the isolated `neuroseg3` conda environment and can use CUDA through PyTorch when that environment sees the GPU.
- Main-app operations such as projection, dF/F, Gaussian smoothing, and ROI trace extraction can use CuPy when CuPy is installed in the Python environment that launches the desktop app.
- If CuPy is not installed, those operations automatically fall back to CPU/NumPy.
- CaImAn motion correction is left in the `caiman_latest` environment and may still be CPU/I/O bound depending on the CaImAn build.

For a packaged client, the practical high-value path is to keep NeuroSeg3 GPU-enabled and optionally provide a CuPy-enabled main runtime for large movies.
