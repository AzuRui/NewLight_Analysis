# Dual ROI Engines Design

Date: 2026-07-27

## Goal

Replace the existing threshold-based automatic ROI action and the incorrectly
deployed generic COCO NeuroSeg3 action with two complementary ROI engines:

- `CaImAn 识别分割`: high-accuracy calcium-source extraction from the current
  effective movie using CaImAn CNMF or CNMF-E.
- `快速 ROI 分割`: fast projection-image instance segmentation using the
  authorized NeuSuite model.

Both engines return independent, arbitrary-shape boolean masks through the
existing `set_rois()` path. Neither engine approximates an ROI with a rectangle,
circle, or ellipse.

## Confirmed Baseline

- `analysis_core.auto_roi_from_image()` is Gaussian smoothing, Otsu thresholding,
  morphology, and connected components. It is fast but not a learned neuronal
  detector.
- The default `NeuroSeg3/weights/segmentation/yolov8s-seg.pt` contains the stock
  COCO 80-class names and is not a trained neuronal model. Its unusually low
  useful confidence threshold is therefore not scientifically meaningful.
- `NeuSuite2p/segment_model.pt` is an authorized single-class `spine` instance
  segmentation model with local custom architecture code and genuine irregular
  instance masks. Its stored in-domain mask recall is about 0.78.
- The installed `caiman_latest` environment contains CaImAn 1.13.1 and can fit a
  CNMF model. Direct interpreter startup currently crashes in MKL unless the
  process uses the conda activation path or sets `MKL_THREADING_LAYER=SEQUENTIAL`.
- NewLight currently invokes CaImAn only for motion correction; it has no CNMF
  source-extraction worker or ROI conversion path.

## Chosen Architecture

The application uses two isolated external workers. The Tk process never
imports CaImAn, PyTorch, or the NeuSuite custom Ultralytics runtime.

```text
NewLight Tk process
  |-- CaImAn ROI request: temporary TIFF + JSON parameters
  |     `-- newlight_caiman Python -> NPZ masks/quality/traces + JSON summary
  |
  `-- Fast ROI request: temporary projection PNG + JSON parameters
        `-- NeuSuite worker -> NPZ instance masks/scores + JSON summary
```

The worker boundary keeps native and ML dependencies out of the main process,
prevents UI blocking, and permits each worker to be packaged separately later.
Launching or scraping the NeuSuite2p GUI is explicitly out of scope.

## CaImAn Environment

Create a dedicated `newlight_caiman` environment rather than modifying or
depending permanently on `caiman_latest`.

- Python major/minor: 3.11.
- CaImAn: 1.13.1.
- Dependency versions are recorded in a checked-in conda environment file and
  an explicit post-install package lock after the environment passes the probe.
- `MKL_THREADING_LAYER=SEQUENTIAL` is set in the worker environment before any
  NumPy import.
- `KERAS_BACKEND=torch` is set before importing CaImAn component evaluation.
- `CAIMAN_DATA` points to a worker-controlled resource directory containing the
  matching `cnn_model.pkl` and `cnn_model_online.pkl` files. The installed
  CaImAn package already supplies matching pickle models under its shared data
  directory; setup copies those files without modifying the user's old
  `C:/Users/<user>/caiman_data` directory.
- `CAIMAN_TEMP` points to the current NewLight session directory so memmaps and
  intermediate files follow the application's cleanup policy.

Development launch resolves the environment interpreter directly and supplies
the required environment variables. It does not use `conda run` when the
interpreter is available, avoiding activation noise and the OpenCL vendor-file
messages. A diagnostic command performs, in order:

1. NumPy import and matrix operation.
2. CaImAn, CNMF, and component-evaluation import.
3. Matching CNN model discovery and load.
4. A two-component synthetic CNMF fit.

The existing `caiman_latest` environment remains untouched as a fallback until
the new environment passes all probes.

## CaImAn ROI Engine

### Input

The engine receives the current effective single-channel movie, after all
committed preprocessing and motion-correction tasks. It preserves float/native
dynamic range instead of converting the movie to display-oriented 8-bit data.
Protocol invalid starting frames are excluded before fitting. Frame rate comes
from the current protocol/video metadata.

The default mode is two-photon CNMF. One-photon CNMF-E is available through a
mode selector because its background and initialization assumptions differ.

### Two-Photon Defaults

- Initialization: `greedy_roi`.
- Background components: `nb=2`.
- Initial components per patch: `K=4`.
- Spatial and temporal subsampling: `ssub=2`, `tsub=2`.
- Temporal autoregressive order: `p=1`.
- Merge threshold: `merge_thr=0.85`.
- Quality: `min_SNR=2.0`, `rval_thr=0.85`, `use_cnn=True`,
  `min_cnn_thr=0.99`, `cnn_lowest=0.1`.
- Footprint threshold: `maxthr=0.20`.

The user supplies expected cell diameter in pixels. The worker derives the
CaImAn half-size `gSig` from half that diameter. Patch radius and overlap are
derived from `gSig` unless advanced values are explicitly enabled.

### One-Photon Defaults

- Initialization: `corr_pnr`.
- `K=None`, `nb=0`, `min_corr=0.8`, `min_pnr=10`.
- Temporal autoregressive order: `p=1`.
- Merge threshold: `merge_thr=0.70`.
- Quality: `min_SNR=2.5`, `rval_thr=0.85`, `use_cnn=False`.
- Ring background and patch defaults follow CaImAn's CNMF-E demo parameters.

### Output Conversion

The worker evaluates components, retains accepted component indexes, and calls
CaImAn's spatial-component thresholding with the configured `maxthr`. Each
accepted column in `A_thr` is reshaped in Fortran order to the original image
dimensions and converted to an independent boolean mask. The conversion then:

- keeps the largest connected region belonging to the component;
- fills only enclosed holes;
- applies configured minimum and maximum area filters;
- never fits a geometric primitive;
- preserves overlapping components as separate masks.

The NPZ result contains `masks`, `names`, `snr`, `r_values`, `cnn_scores`, and
CaImAn temporal traces. A JSON summary records parameters, accepted/rejected
counts, elapsed time, warnings, and environment versions. NewLight uses the
masks as its canonical ROI representation; CaImAn traces are retained as
provenance but do not silently replace the application's trace calculation.

## Fast ROI Engine

### Runtime

The worker loads the authorized `NeuSuite2p/segment_model.pt` with the matching
custom Ultralytics 8.0.202 runtime. It must not import the stock PyPI
Ultralytics package as a substitute because the checkpoint depends on custom
`PConvX`, `ADownSPD`, `RepNCSPELAN4_CAA`, and
`RepNCSPELAN4_ScConv` modules.

### Input and Defaults

The default input is the projection currently selected in View, including the
protocol-scoped mean projection behavior. The engine receives the scientific
grayscale projection before display pseudocolor and display-only contrast
adjustments.

- `imgsz=960`.
- `conf=0.25`.
- `iou=0.70`.
- Minimum ROI area: 20 pixels.
- Maximum ROI area: 4000 pixels.

The worker reads `results[0].masks.data` before masks are merged for display.
Each instance is resized to the original projection dimensions with
nearest-neighbor interpolation, thresholded, area-filtered, and returned as a
separate boolean mask. It never reconstructs instances from a combined binary
PNG, because connected components can split one instance or merge touching
instances.

## User Interface

Remove the visible actions for `内置自动 ROI` and `NeuroSeg3 自动 ROI 分割`.
Add, in the same ROI section:

- `CaImAn 识别分割`
- `快速 ROI 分割`

Selecting either action renders its controls in the existing right-side
parameter panel. No ordinary parameter dialog opens. File selection dialogs
remain native dialogs where a path is genuinely required.

### CaImAn Controls

Always visible:

- Imaging mode: `双光子 CNMF` or `一光子 CNMF-E`.
- Expected cell diameter in pixels.
- Minimum/maximum ROI area.
- Minimum temporal SNR.
- Minimum spatial correlation.
- Merge threshold.
- Footprint threshold.
- Run command.

Advanced controls:

- Initial components per patch.
- Patch radius and stride.
- Spatial/temporal subsampling.
- Temporal AR order.
- CNN quality-filter toggle and threshold.

### Fast Controls

- Detection confidence.
- Inference size.
- NMS IoU.
- Minimum/maximum ROI area.
- Projection source, defaulting to the current View selection.
- Run command.

Controls retain their last values for the current application session. Both
commands enqueue a single task through the existing task controller. Running,
queued, completed, failed, and cancelled states use the current task-flow UI.
Only the Tk main-thread success callback calls `set_rois()` and redraws the
view.

## Error Handling and Cleanup

- Missing movie, channel, projection, model, environment, or CNN data produces
  a localized actionable error in the parameter panel and run log.
- A zero-component result is reported as a valid empty result and does not
  erase existing ROIs without explicit confirmation.
- Worker nonzero exit, malformed NPZ, shape mismatch, NaN footprint, or an ROI
  count above a defensive limit is rejected before state mutation.
- Temporary TIFF, PNG, memmap, NPZ, and JSON files live under the current
  NewLight session directory and are removed on normal completion, failure,
  cancellation, and application exit.
- User-owned sample data and explicit saved outputs are never part of cleanup.

When no ROI is committed, existing analysis behavior continues to treat the
full frame as the implicit global ROI. Automatic segmentation does not create
a synthetic full-frame ROI entry.

## Packaging Boundary

This implementation round validates source-mode workers and prepares build
metadata; it does not rebuild the application. A later packaging pass creates
separate CaImAn and NeuSuite worker executables under `_internal`, bundles the
authorized model and required CaImAn data, and includes license notices for
CaImAn GPL-2 and the custom Ultralytics AGPL-3.0-derived runtime. Packaging must
not require end users to install Python or conda.

## Tests and Acceptance Criteria

### Environment Tests

- Direct worker launch imports NumPy without native crash.
- CNMF, CNMF-E, component evaluation, and the CNN classifier load.
- A synthetic movie returns two nonempty components and temporal traces.

### Unit Tests

- CaImAn sparse footprints convert to original-size arbitrary masks in Fortran
  order.
- Disconnected noise, enclosed holes, area filters, and overlapping components
  follow the documented rules.
- NeuSuite instance masks preserve instance identity and resize without shape
  drift.
- Invalid starting frames are excluded and current frame rate is propagated.

### Integration Tests

- Both actions execute through the task queue without blocking the Tk event
  loop.
- Both engines return masks through `set_rois()` and retain arbitrary contours.
- Existing ROI deletion, freehand editing, trace calculation, save/load, and
  implicit global-ROI behavior continue to work.
- A retained workspace sample is used for end-to-end comparison; validation
  samples are not deleted.
- Static UI tests confirm the two old actions are gone and the two new Chinese
  labels and parameter panels are present.

### Scientific Result Reporting

The run log reports component count, accepted/rejected quality counts, area
distribution, runtime, source frames, excluded invalid frames, and all relevant
thresholds. No engine is described as finding every anatomical neuron. CaImAn
results represent temporally supported calcium sources; Fast ROI results
represent projection-image candidates.

## Non-Goals

- Training or fine-tuning the NeuSuite model in this implementation round.
- Claiming anatomical synapse identification from unresolved low-resolution
  pixels.
- Automatically unioning CaImAn and Fast ROI results without a later explicit
  merge/review design.
- Rebuilding the portable EXE or installer before source-mode validation.
