# Motion Controls and Rigid Reference Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CaImAn mode a constrained GUI choice and make built-in rigid correction align every frame to a stable, refined reference instead of treating the first N raw frames as the correct coordinate system.

**Architecture:** Extend the shared parameter panel field format with optional choices rendered by a readonly `ttk.Combobox`. Split rigid reference construction into testable window selection and two-pass template functions; the existing GUI caller receives diagnostics and logs the selected interval.

**Tech Stack:** Python 3, Tkinter/ttk, NumPy, SciPy, scikit-image, unittest.

---

### Task 1: Parameter Choice Controls

**Files:**
- Modify: `tests/test_gui_static.py`
- Modify: `NewLight_Analysis.py`

- [ ] **Step 1: Write the failing GUI source test**

Add a test that requires the CaImAn mode field to declare `("rigid", "piecewise")`, requires `ttk.Combobox`, and requires `state="readonly"`.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `conda run -n caiman_latest python -B -m unittest tests.test_gui_static.GuiStaticTests.test_caiman_mode_is_a_readonly_choice`

Expected: FAIL because the mode is currently rendered by a plain entry.

- [ ] **Step 3: Implement optional choices in the parameter panel**

Allow either `(key, label, default)` or `(key, label, default, choices)`. Render a readonly combobox for the latter and make Reset work through each widget's associated `StringVar`. Define CaImAn mode as:

```python
("mode", "Mode", "piecewise", ("rigid", "piecewise"))
```

- [ ] **Step 4: Run the focused GUI test and verify GREEN**

Run the command from Step 2 and expect `OK`.

### Task 2: Rigid Reference Regression Tests

**Files:**
- Create: `tests/test_rigid_motion.py`
- Modify: `analysis_core.py`

- [ ] **Step 1: Write failing synthetic motion tests**

Create textured synthetic movies using `scipy.ndimage.shift`. Test that manual `reference_start` and `reference_frames` select the requested interval, that moving frames inside the reference interval are aligned by the final pass, and that automatic mode selects a lower-motion interval after an unstable beginning.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `conda run -n caiman_latest python -B -m unittest tests.test_rigid_motion`

Expected: FAIL because the current function has no reference mode/start or diagnostics and uses one raw mean template.

- [ ] **Step 3: Implement reference-window selection and two-pass template refinement**

Add helpers that validate a 3D non-empty movie, calculate consecutive phase-correlation motion scores, choose the lowest-score window in auto mode, and use the middle frame of the selected interval as the initial anchor. Align interval frames to that anchor, construct a pixelwise median template, then estimate and apply final shifts for every movie frame.

Return diagnostics containing:

```python
{
    "reference_start": int,
    "reference_end": int,
    "anchor_frame": int,
    "template": np.ndarray,
}
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the command from Step 2 and expect all rigid-motion tests to pass.

### Task 3: Built-in Motion GUI Integration

**Files:**
- Modify: `tests/test_gui_static.py`
- Modify: `NewLight_Analysis.py`

- [ ] **Step 1: Write the failing integration source test**

Require Built-in fields for reference mode, start frame, frame count, and maximum shift, and require the GUI call to pass these values to the core function.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `conda run -n caiman_latest python -B -m unittest tests.test_gui_static.GuiStaticTests.test_builtin_rigid_exposes_reference_controls`

Expected: FAIL because only `Template frames` exists.

- [ ] **Step 3: Wire validated parameters and diagnostics**

Set Built-in defaults to auto mode, start 0, count 100, and max shift 15 px. Log the selected inclusive frame range, anchor, and median/max absolute dy/dx. Preserve the existing output shape and history behavior.

- [ ] **Step 4: Run focused GUI and rigid tests**

Run: `conda run -n caiman_latest python -B -m unittest tests.test_gui_static tests.test_rigid_motion`

Expected: all tests pass.

### Task 4: Documentation and Regression Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-07-21-rigid-nonrigid-motion-design.md`
- Modify: `WORK_LOG.md`
- Modify: `PROJECT_HANDOFF.md`

- [ ] **Step 1: Revise the design decision**

Record that CaImAn `piecewise` already performs rigid template generation before piecewise correction, while Built-in remains a quick rigid fallback with corrected reference selection.

- [ ] **Step 2: Update project records**

Document the exact parameter meanings, the reproduced root cause, and the verification commands.

- [ ] **Step 3: Run the full relevant regression suite**

Run:

```powershell
conda run -n caiman_latest python -B -m unittest tests.test_rigid_motion tests.test_gui_static tests.test_bit_depth tests.test_background_image tests.test_interlacing_shift tests.test_baseline
conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py tests\test_rigid_motion.py tests\test_gui_static.py
```

Expected: exit code 0 for both commands.
