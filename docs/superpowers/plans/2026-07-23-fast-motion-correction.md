# Fast Motion Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the built-in correction to `快速运动矫正` and add an optional constrained local deformation stage after its unchanged rigid correction.

**Architecture:** Keep `rigid_motion_correction()` as the compatibility boundary. Add a focused local-warp helper and a `fast_motion_correction()` orchestrator in `analysis_core.py`; the GUI passes three new values into the orchestrator and reports its diagnostics. A zero flexible strength returns the rigid result without entering local estimation.

**Tech Stack:** Python 3.8, NumPy, SciPy ndimage/interpolation, scikit-image phase cross-correlation, Tk/ttk, unittest/pytest.

---

## File Map

- Modify `analysis_core.py`: local patch estimation, dense displacement warp, and fast-correction orchestration.
- Modify `ui_text_zh.py`: visible name, parameters, and user-facing explanation.
- Modify `NewLight_Analysis.py`: parse parameters, call the new core API, and log diagnostics.
- Modify `tests/test_rigid_motion.py`: numerical regression tests for compatibility and local correction.
- Modify `tests/test_gui_static.py`: static GUI routing and description coverage.
- Modify `tests/test_chinese_localization.py`: visible Chinese label coverage.
- Modify `WORK_LOG.md` and `PROJECT_HANDOFF.md`: implementation and maintenance constraints.

### Task 1: Core Behavioral Tests

**Files:**
- Modify: `tests/test_rigid_motion.py`
- Test: `tests/test_rigid_motion.py`

- [ ] **Step 1: Add a rigid-compatibility test**

Call `core.fast_motion_correction(..., flexible_strength=0)` and
`core.rigid_motion_correction(...)` with identical manual reference settings.
Assert exact equality of corrected movies and shifts, and matching reference
metadata.

- [ ] **Step 2: Add a synthetic local-deformation test**

Build a movie containing stable reference frames and frames warped by a smooth,
spatially varying displacement field. Run with a positive flexible strength,
small block size, and bounded local deformation. Assert that cropped MAE against
the stable reference decreases and that local correction is reported as active.

- [ ] **Step 3: Add validation and fallback tests**

Assert finite `float32` output with preserved shape, local shifts bounded by the
configured maximum, and safe rigid-only fallback for images too small to form a
2-by-2 patch grid.

- [ ] **Step 4: Run tests and verify RED**

Run:

```powershell
conda run -n caiman_latest python -m pytest tests/test_rigid_motion.py -q
```

Expected: failures because `analysis_core.fast_motion_correction` does not yet
exist.

### Task 2: Core Fast Motion Correction

**Files:**
- Modify: `analysis_core.py`
- Test: `tests/test_rigid_motion.py`

- [ ] **Step 1: Add patch-grid utilities**

Create deterministic patch starts that cover both image edges with 50 percent
overlap. Require at least two patch positions on each axis before local
correction can run.

- [ ] **Step 2: Add local displacement estimation**

For each patch, estimate `(dy, dx)` with phase correlation, reject textureless
or non-finite patches as zero, clip shifts to the configured maximum, preserve
valid residual template offsets, and median-filter isolated vectors.

- [ ] **Step 3: Add dense-field interpolation and warp**

Interpolate the regular patch grid to the complete image with nearest edge
extension, smooth the field spatially, multiply by flexible strength, and call
`ndimage.map_coordinates` with linear interpolation and nearest-edge handling.

- [ ] **Step 4: Add the public orchestrator**

Implement:

```python
def fast_motion_correction(
    movie,
    *,
    reference_mode="auto",
    reference_start=0,
    reference_frames=100,
    max_shift=15.0,
    flexible_strength=0.0,
    local_block_size=96,
    max_local_deformation=3.0,
):
    ...
```

It first calls `rigid_motion_correction()`. Strength zero returns that result
unchanged. Positive strength runs local correction and augments `info` with
`local_applied`, effective grid/block settings, absolute local-shift statistics,
and limit-hit fraction.

- [ ] **Step 5: Run core tests and verify GREEN**

Run the Task 1 command and expect all rigid/fast motion tests to pass.

### Task 3: Chinese UI and Routing

**Files:**
- Modify: `ui_text_zh.py`
- Modify: `NewLight_Analysis.py`
- Modify: `tests/test_gui_static.py`
- Modify: `tests/test_chinese_localization.py`

- [ ] **Step 1: Add failing GUI tests**

Assert that the visible label is `快速运动矫正`, the fields include defaults
`0.0 / 96 / 3.0`, the description explains `0` and `0.2-0.5`, and all values
are forwarded to `core.fast_motion_correction()`.

- [ ] **Step 2: Run GUI tests and verify RED**

Run:

```powershell
conda run -n caiman_latest python -m pytest tests/test_gui_static.py tests/test_chinese_localization.py -q
```

Expected: failures on the old label, missing fields, and old core call.

- [ ] **Step 3: Update the parameter catalog**

Keep action ID `builtin_rigid_motion`, change its label, expand its description,
and append:

```python
("flexible_strength", "柔性强度 (0=关闭)", 0.0)
("local_block_size", "局部块尺寸 (px)", 96)
("max_local_deformation", "最大局部形变 (px)", 3.0)
```

- [ ] **Step 4: Update GUI execution**

Clamp UI strength to `[0, 1]`, parse block size and deformation bound, call
`core.fast_motion_correction()`, retain the existing rigid diagnostics, and log
either rigid-only status or local grid/shift/limit statistics.

- [ ] **Step 5: Run GUI tests and verify GREEN**

Run the Task 3 test command and expect all tests to pass.

### Task 4: Records and Verification

**Files:**
- Modify: `WORK_LOG.md`
- Modify: `PROJECT_HANDOFF.md`

- [ ] **Step 1: Update records**

Record the visible rename, zero-strength compatibility invariant, local
algorithm, exposed defaults, diagnostics, and recommendation to use CaImAn for
stronger complex motion.

- [ ] **Step 2: Run the complete suite**

```powershell
$env:PYTHONIOENCODING='utf-8'
conda run -n caiman_latest python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Compile Python sources**

```powershell
conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py ui_text_zh.py workers/run_caiman.py
```

Expected: exit code 0.

- [ ] **Step 4: Check patch whitespace**

```powershell
git diff --check -- NewLight_Analysis.py analysis_core.py ui_text_zh.py tests/test_rigid_motion.py tests/test_gui_static.py tests/test_chinese_localization.py WORK_LOG.md PROJECT_HANDOFF.md
```

Expected: no whitespace errors. CRLF conversion warnings are acceptable.
