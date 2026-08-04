# Dual ROI Engines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the legacy threshold and generic COCO ROI actions with CaImAn source extraction and the authorized NeuSuite instance segmentation model while preserving arbitrary-shape masks and responsive UI behavior.

**Architecture:** The Tk process remains free of CaImAn, PyTorch, and custom Ultralytics imports. Two subprocess workers exchange versioned NPZ/JSON artifacts with `analysis_core.py`; pure validation helpers enforce mask shape, instance separation, metadata alignment, and failure-before-state-mutation. Both actions use the existing embedded parameter panel and single-task FIFO controller.

**Tech Stack:** Python 3.8+ main application, Tkinter, NumPy/NPZ, tifffile, subprocess, CaImAn 1.13 CNMF/CNMF-E, PyTorch, authorized NeuSuite Ultralytics fork, pytest/unittest, PyInstaller.

---

### Task 1: Pure ROI artifact contract

**Files:**
- Create: `roi_engines.py`
- Create: `tests/test_roi_engines.py`

- [ ] **Step 1: Write failing tests for arbitrary-shape instance masks**

Test `normalize_instance_masks()` with `(N,H,W)`, singleton `(H,W)`, float masks, overlapping instances, empty masks, wrong spatial dimensions, and empty instances. Assert boolean output, original instance count, preserved overlap, deterministic names, and explicit `ROIArtifactError` failures.

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `python -m pytest tests/test_roi_engines.py -q`

Expected: collection fails because `roi_engines` does not exist.

- [ ] **Step 3: Implement the minimal contract helpers**

Implement `ROI_ARTIFACT_VERSION`, `ROIArtifactError`, `normalize_instance_masks`, `save_roi_artifact`, and `load_roi_artifact`. Store masks as compressed boolean arrays and metadata as JSON text without importing either backend.

- [ ] **Step 4: Run the contract tests and verify GREEN**

Run: `python -m pytest tests/test_roi_engines.py -q`

Expected: all tests pass.

### Task 2: Worker command contracts

**Files:**
- Create: `tests/test_roi_worker_contracts.py`
- Create: `workers/run_caiman_roi.py`
- Create: `workers/run_neusuite_roi.py`

- [ ] **Step 1: Write failing parser and environment-order tests**

Assert the CaImAn worker exposes `--mode`, diameter, CNMF quality thresholds, footprint threshold, invalid-start frames, input/output/summary paths; assert MKL/Keras/CaImAn environment variables are configured before scientific imports. Assert the NeuSuite worker exposes projection image, weights/runtime roots, confidence, IoU, image size, area bounds, and output paths.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_roi_worker_contracts.py -q`

Expected: worker modules are missing.

- [ ] **Step 3: Implement parsers and failure-safe artifact writing**

Create lazy-import workers. The CaImAn worker runs CNMF/CNMF-E, thresholds each `A` column with `threshold_spatial_components(maxthr=...)`, reshapes with Fortran order, filters by CaImAn component quality, and emits masks plus SNR/r-value/CNN/trace metadata. The NeuSuite worker prepends its authorized runtime root, loads `segment_model.pt`, reads `results[0].masks.data` per instance, restores masks by nearest-neighbor resize, applies area limits, and never reconstructs instances from a merged PNG.

- [ ] **Step 4: Verify parser and pure helper tests GREEN**

Run: `python -m pytest tests/test_roi_worker_contracts.py tests/test_roi_engines.py -q`

Expected: all tests pass without importing CaImAn or torch in the test process.

### Task 3: Reproducible CaImAn environment

**Files:**
- Create: `environment-newlight-caiman.yml`
- Create: `setup_newlight_caiman.bat`
- Modify: `setup_caiman_latest.bat`

- [ ] **Step 1: Define the isolated environment**

Pin a compatible Python, NumPy, SciPy, OpenCV, tifffile, scikit-image, PyTorch/Keras backend, and CaImAn release. Configure the setup script to create/update `newlight_caiman`, verify direct NumPy import with `MKL_THREADING_LAYER=SEQUENTIAL`, locate both CaImAn CNN `.pkl` files, and run `workers/run_caiman_roi.py --help`.

- [ ] **Step 2: Build and smoke-test the environment**

Run: `setup_newlight_caiman.bat`

Expected: direct interpreter startup succeeds, CNMF imports, and both CNN model files are found. If environment creation is blocked by package/network state, retain the verified `caiman_latest` fallback with process-local MKL settings and document the limitation.

### Task 4: Main-process backend wrappers

**Files:**
- Modify: `analysis_core.py`
- Create: `tests/test_roi_backend_wrappers.py`

- [ ] **Step 1: Write failing wrapper tests**

Use temporary synthetic movies/images and fake worker executables to assert command construction, invalid-start forwarding, effective-movie export, selected projection export, output dimension validation, zero-ROI handling, metadata loading, and temporary artifact cleanup.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_roi_backend_wrappers.py -q`

Expected: `run_caiman_roi_segmentation` and `run_fast_roi_segmentation` are missing.

- [ ] **Step 3: Implement wrappers**

Resolve source-tree and frozen worker paths, write inputs only inside the current NewLight session directory, invoke workers without shell windows, clean backend logs, load versioned artifacts through `roi_engines.py`, reject shape/count mismatches, and return a result object without mutating application state.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/test_roi_backend_wrappers.py tests/test_roi_engines.py -q`

Expected: all tests pass.

### Task 5: Embedded parameter-panel UI and FIFO integration

**Files:**
- Modify: `NewLight_Analysis.py`
- Modify: `ui_text_zh.py`
- Modify: `tests/test_gui_static.py`

- [ ] **Step 1: Write failing static UI tests**

Assert the ROI sidebar contains `CaImAn 识别分割` and `快速 ROI 分割`, contains neither legacy action, uses `show_parameter_panel`, persists defaults in app variables/settings, calls `enqueue_task`, and applies `set_rois()` only after a non-empty validated success result.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_gui_static.py -q`

Expected: the new labels and methods are absent.

- [ ] **Step 3: Implement both parameter panels**

CaImAn fields: imaging mode, cell diameter, components per patch, background components, spatial/temporal subsampling, AR order, merge threshold, minimum SNR, spatial correlation, CNN toggle/thresholds, and footprint threshold. Fast fields: source projection, confidence, IoU, image size, minimum/maximum area. Keep values when switching panels and provide concise help text in the panel.

- [ ] **Step 4: Connect tasks and state mutation**

Snapshot current effective data on the UI thread, enqueue one backend call, keep the Tk loop responsive, display task-flow state, load masks through `set_rois()` on success, preserve existing ROI on zero result/error/cancel, refresh the overlay, and log backend summary paths.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_gui_static.py tests/test_task_queue.py tests/test_roi_backend_wrappers.py -q`

Expected: all tests pass.

### Task 6: Real backend validation with retained samples

**Files:**
- Retain unchanged: `eye/data/2/A01/result.avi`
- Create under session temp only: worker inputs and outputs

- [ ] **Step 1: Run Fast ROI against the retained sample projection**

Use the authorized `E:/WorkSpace/NeuSuite2p/segment_model.pt` and custom runtime. Verify non-zero independent masks, exact source dimensions, irregular boundaries, no circle/ellipse conversion, and stable runtime log.

- [ ] **Step 2: Run CaImAn ROI against a bounded sample segment**

Use the isolated environment or the MKL-fixed fallback. Verify CNMF finishes, returns component masks/traces and quality fields, uses invalid-start handling, and does not write outside the session directory.

- [ ] **Step 3: Run focused regression tests**

Run: `python -m pytest tests/test_roi_engines.py tests/test_roi_worker_contracts.py tests/test_roi_backend_wrappers.py tests/test_gui_static.py tests/test_task_queue.py -q`

Expected: all tests pass.

### Task 7: Packaging boundary and project records

**Files:**
- Modify: `NewLight_Analysis.spec`
- Modify: `WORK_LOG.md`
- Modify: `PROJECT_HANDOFF.md`

- [ ] **Step 1: Replace obsolete packaged ROI assets**

Remove the generic NeuroSeg3 ROI weights/runtime from the release data set. Add the authorized NeuSuite model/runtime and the new ROI workers. Keep the CaImAn backend isolated as a worker bundle boundary so the GUI process does not import its native stack; do not run a full release build in this task.

- [ ] **Step 2: Update work log and handoff**

Record architecture, paths, environment requirements, parameters, tests, retained sample policy, packaging status, known limitations, and exact files a new task must read first.

- [ ] **Step 3: Final verification**

Run the focused suite plus `git diff --check` and inspect `git diff --stat`. Confirm no sample data was deleted and no unrelated user changes were reverted.

