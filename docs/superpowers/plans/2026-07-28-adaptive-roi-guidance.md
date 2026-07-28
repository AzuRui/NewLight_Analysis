# Adaptive ROI Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add quality presets and repeatable user-example-guided ROI refinement/selection to both fast ROI and CaImAn while preserving every current ROI and marking retained low-quality examples with `*`.

**Architecture:** A new backend-independent `roi_adaptation.py` module owns presets, ROI metadata, fixed convolution descriptors, protected-mask refinement, robust feature fitting, and candidate selection. Existing workers gain an opt-in permissive candidate mode; `NewLightApp` caches candidate banks per movie/configuration and applies the common adaptation layer through the existing single FIFO task controller. Current ROI masks remain the application state contract, with aligned metadata and a revision counter added for provenance and stale-result protection.

**Tech Stack:** Existing NewLight Python/Conda runtimes, NumPy, SciPy, scikit-image, OpenCV, Tkinter, CaImAn, authorized NeuSuite/Ultralytics runtime, pytest.

---

## File Map

- Create `roi_adaptation.py`: pure adaptation algorithms and data contracts; no Tk, worker subprocess, or filesystem UI code.
- Create `tests/test_roi_adaptation.py`: area, metadata, refinement, feature fit, retention, marking, and deduplication tests.
- Modify `analysis_core.py`: extend `AnalysisState`; expose permissive worker wrapper options.
- Modify `workers/run_neusuite_roi.py`: emit permissive fast candidate banks.
- Modify `workers/run_caiman_roi.py`: emit all non-empty CaImAn candidates and aligned quality arrays in candidate mode.
- Modify `NewLight_Analysis.py`: presets/actions, ROI metadata/revision maintenance, candidate cache, adaptive task orchestration, and ROI-list quality display.
- Modify `tests/test_roi_worker_contracts.py`: worker candidate-mode contracts.
- Modify `tests/test_roi_backend_wrappers.py`: wrapper flags and aligned result validation.
- Modify `tests/test_gui_static.py`: embedded controls, FIFO execution, stale revision, and cache behavior.
- Modify `WORK_LOG.md` and `PROJECT_HANDOFF.md`: implementation and continuation record after verification.

### Task 1: Presets, Area Suggestions, and ROI Metadata

**Files:**
- Create: `roi_adaptation.py`
- Create: `tests/test_roi_adaptation.py`

- [ ] **Step 1: Write failing tests for preset and area behavior**

```python
import numpy as np

from roi_adaptation import (
    QUALITY_PRESETS,
    display_roi_name,
    normalized_roi_metadata,
    suggest_area_range,
)


def square(area_side, shape=(40, 40)):
    mask = np.zeros(shape, dtype=bool)
    mask[2 : 2 + area_side, 3 : 3 + area_side] = True
    return mask


def test_two_examples_fill_smallest_and_largest_with_margins():
    result = suggest_area_range([square(10), square(4)], 20, 4000)
    assert result == (14, 110)


def test_one_example_only_replaces_maximum():
    result = suggest_area_range([square(10)], 20, 4000)
    assert result == (20, 110)


def test_no_example_keeps_current_area_range():
    assert suggest_area_range([], 20, 4000) == (20, 4000)


def test_low_quality_name_has_one_trailing_asterisk():
    metadata = normalized_roi_metadata({"base_name": "ROI3*", "low_quality": True}, "manual", "ROI3")
    assert display_roi_name(metadata) == "ROI3*"


def test_balanced_preset_is_explicit_and_bounded():
    preset = QUALITY_PRESETS["balanced"]
    assert preset.fast_confidence == 0.25
    assert preset.caiman_min_snr == 2.0
    assert preset.caiman_rval == 0.80
    assert preset.caiman_cnn == 0.90
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
$env:MKL_THREADING_LAYER='SEQUENTIAL'
conda run -n caiman_latest --no-capture-output python -m pytest tests/test_roi_adaptation.py -q
```

Expected: collection fails because `roi_adaptation` does not exist.

- [ ] **Step 3: Implement the minimal preset and metadata API**

Create `roi_adaptation.py` with these public definitions:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class QualityPreset:
    fast_confidence: float
    caiman_min_snr: float
    caiman_rval: float
    caiman_cnn: float
    similarity_limit: float


QUALITY_PRESETS = {
    "recall": QualityPreset(0.10, 1.5, 0.70, 0.70, 3.0),
    "balanced": QualityPreset(0.25, 2.0, 0.80, 0.90, 2.3),
    "precision": QualityPreset(0.40, 2.5, 0.90, 0.99, 1.7),
}

SOURCE_WEIGHTS = {"manual": 1.0, "loaded": 0.8, "atlas": 0.8, "fast": 0.6, "caiman": 0.6}


def suggest_area_range(masks, current_min, current_max):
    areas = sorted(int(np.count_nonzero(mask)) for mask in masks if np.any(mask))
    if not areas:
        return int(current_min), int(current_max)
    suggested_max = max(1, int(round(areas[-1] * 1.1)))
    if len(areas) == 1:
        return int(current_min), max(int(current_min), suggested_max)
    suggested_min = max(1, int(round(areas[0] * 0.9)))
    return suggested_min, max(suggested_min, suggested_max)


def normalized_roi_metadata(value, source, fallback_name):
    item = dict(value or {})
    base_name = str(item.get("base_name", fallback_name)).rstrip("*") or fallback_name
    return {
        "source": str(item.get("source", source)),
        "protected": bool(item.get("protected", False)),
        "low_quality": bool(item.get("low_quality", False)),
        "quality_reasons": list(item.get("quality_reasons", [])),
        "base_name": base_name,
    }


def display_roi_name(metadata):
    base = str(metadata["base_name"]).rstrip("*")
    return base + ("*" if metadata.get("low_quality") else "")
```

- [ ] **Step 4: Run Task 1 tests and verify GREEN**

Run the Step 2 command. Expected: all Task 1 tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add roi_adaptation.py tests/test_roi_adaptation.py
git commit -m "feat: add adaptive ROI preset primitives"
```

### Task 2: Protected Boundary Refinement and Feature Extraction

**Files:**
- Modify: `roi_adaptation.py`
- Modify: `tests/test_roi_adaptation.py`

- [ ] **Step 1: Add failing synthetic refinement tests**

Append tests that create a 30-frame movie with an irregular L-shaped active
region and a coarse square reference:

```python
from roi_adaptation import build_feature_table, refine_protected_mask


def synthetic_activity_movie():
    movie = np.zeros((30, 32, 32), dtype=np.float32)
    target = np.zeros((32, 32), dtype=bool)
    target[10:20, 10:13] = True
    target[17:20, 10:21] = True
    signal = np.sin(np.linspace(0, 4 * np.pi, movie.shape[0])).astype(np.float32)
    movie[:, target] = 10.0 + signal[:, None] * 4.0
    movie += np.random.default_rng(7).normal(0, 0.15, movie.shape).astype(np.float32)
    coarse = np.zeros((32, 32), dtype=bool)
    coarse[9:21, 9:21] = True
    return movie, target, coarse


def test_refinement_moves_coarse_mask_toward_irregular_activity():
    movie, target, coarse = synthetic_activity_movie()
    refined = refine_protected_mask(movie, movie.mean(axis=0), coarse)
    old_iou = np.count_nonzero(coarse & target) / np.count_nonzero(coarse | target)
    new_iou = np.count_nonzero(refined.mask & target) / np.count_nonzero(refined.mask | target)
    assert new_iou > old_iou
    assert refined.mask.any()


def test_refinement_failure_keeps_original_and_marks_low_quality():
    movie = np.zeros((20, 24, 24), dtype=np.float32)
    mask = square(5, shape=(24, 24))
    refined = refine_protected_mask(movie, movie.mean(axis=0), mask)
    np.testing.assert_array_equal(refined.mask, mask)
    assert refined.low_quality
    assert refined.reasons


def test_convolution_and_shape_features_are_finite():
    movie, _target, coarse = synthetic_activity_movie()
    table = build_feature_table(movie, movie.mean(axis=0), [coarse])
    assert table.shape[0] == 1
    assert np.isfinite(table.values).all()
    assert {"log_area", "solidity", "sobel_mean", "log_mean", "temporal_snr"}.issubset(table.columns)
```

- [ ] **Step 2: Run only the new tests and verify RED**

```powershell
conda run -n caiman_latest --no-capture-output python -m pytest tests/test_roi_adaptation.py -q
```

Expected: missing `build_feature_table` and `refine_protected_mask`.

- [ ] **Step 3: Implement refinement and descriptors**

Add dataclasses `RefinedROI` and `FeatureTable`. Implement helpers that:

```python
@dataclass(frozen=True)
class RefinedROI:
    mask: np.ndarray
    low_quality: bool
    reasons: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class FeatureTable:
    values: np.ndarray
    columns: tuple[str, ...]
```

Implementation requirements:

```python
def fixed_convolution_maps(projection):
    image = normalized_finite_image(projection)
    return {
        "gaussian_1": ndimage.gaussian_filter(image, 1.0),
        "gaussian_2": ndimage.gaussian_filter(image, 2.0),
        "sobel": np.hypot(ndimage.sobel(image, axis=0), ndimage.sobel(image, axis=1)),
        "log": np.abs(ndimage.gaussian_laplace(image, 1.2)),
    }
```

Define normalization in the same module so filtering never receives NaN or
infinite values:

```python
def normalized_finite_image(image):
    array = np.asarray(image, dtype=np.float32)
    finite = np.isfinite(array)
    if not np.any(finite):
        return np.zeros(array.shape, dtype=np.float32)
    low, high = np.percentile(array[finite], (1.0, 99.0))
    if high <= low:
        return np.zeros(array.shape, dtype=np.float32)
    return np.clip((np.where(finite, array, low) - low) / (high - low), 0.0, 1.0).astype(np.float32)
```

`refine_protected_mask()` must use a `2-12 px` dilated search region, pixelwise
correlation with the reference trace, local projection support, largest-overlap
connected component, closing/hole filling, and the `0.5-1.8x` area guard from
the design. It returns the original mask with a reason when any guard fails.

- [ ] **Step 4: Run Task 2 tests and verify GREEN**

Run the Step 2 command. Expected: all tests pass without runtime warnings.

- [ ] **Step 5: Commit Task 2**

```powershell
git add roi_adaptation.py tests/test_roi_adaptation.py
git commit -m "feat: refine protected ROI boundaries"
```

### Task 3: Robust Reference Fit and Candidate Selection

**Files:**
- Modify: `roi_adaptation.py`
- Modify: `tests/test_roi_adaptation.py`

- [ ] **Step 1: Add failing tests for protected retention and adaptive ranking**

```python
from roi_adaptation import CandidateBank, adapt_candidate_bank


def test_adaptation_retains_low_quality_reference_with_star_metadata():
    movie = np.zeros((20, 20, 20), dtype=np.float32)
    reference = square(4, shape=(20, 20))
    bank = CandidateBank.empty("fast", (20, 20))
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "balanced",
    )
    assert len(result.masks) == 1
    assert result.metadata[0]["protected"]
    assert result.metadata[0]["low_quality"]
    assert display_roi_name(result.metadata[0]) == "ROI1*"


def test_adaptation_adds_similar_candidate_and_rejects_distant_shape():
    movie = np.zeros((20, 20, 20), dtype=np.float32)
    reference = np.zeros((20, 20), dtype=bool)
    reference[2:6, 2:6] = True
    similar = np.zeros((20, 20), dtype=bool)
    similar[10:14, 10:14] = True
    too_large = np.zeros((20, 20), dtype=bool)
    too_large[8:18, 8:18] = True
    movie[:, reference | similar] = np.sin(np.linspace(0, 6, 20))[:, None] + 2.0
    bank = CandidateBank(
        "fast",
        np.stack([similar, too_large]),
        ("candidate-1", "candidate-2"),
        {"scores": np.array([0.9, 0.95], dtype=np.float32)},
        ("fast", 1),
        {"confidence": 0.05},
    )
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "balanced",
    )
    assert result.protected_count == 1
    assert result.selected_count == 1
    assert len(result.masks) == 2
    assert np.count_nonzero(result.masks[1]) == 16


def test_matching_candidate_is_not_duplicated_after_reference_refinement():
    movie = np.ones((20, 20, 20), dtype=np.float32)
    reference = np.zeros((20, 20), dtype=bool)
    reference[4:9, 4:9] = True
    overlap = reference.copy()
    bank = CandidateBank(
        "fast",
        overlap[None, ...],
        ("candidate-1",),
        {"scores": np.array([0.95], dtype=np.float32)},
        ("fast", 1),
        {"confidence": 0.05},
    )
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "balanced",
    )
    assert result.protected_count == 1
    assert result.selected_count == 0
    assert len(result.masks) == 1


def test_single_reference_uses_preset_scales_instead_of_zero_mad():
    movie = np.ones((20, 20, 20), dtype=np.float32)
    reference = np.zeros((20, 20), dtype=bool)
    reference[4:9, 4:9] = True
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        CandidateBank.empty("fast", (20, 20)),
        "balanced",
    )
    scales = np.asarray(result.fitted_parameters["feature_scales"], dtype=np.float32)
    assert np.isfinite(scales).all()
    assert np.all(scales > 0)
```

- [ ] **Step 2: Run the new tests and verify RED**

Run `python -m pytest tests/test_roi_adaptation.py -q` in `caiman_latest`.
Expected: missing candidate-bank and adaptation APIs.

- [ ] **Step 3: Implement candidate data contracts and robust fitting**

Add:

```python
@dataclass(frozen=True)
class CandidateBank:
    engine: str
    masks: np.ndarray
    names: tuple[str, ...]
    model_quality: dict[str, np.ndarray]
    source_signature: tuple
    generation_parameters: dict

    @classmethod
    def empty(cls, engine, image_shape):
        return cls(engine, np.zeros((0,) + tuple(image_shape), dtype=bool), (), {}, (), {})


@dataclass(frozen=True)
class AdaptiveROIResult:
    masks: tuple[np.ndarray, ...]
    metadata: tuple[dict, ...]
    fitted_parameters: dict
    protected_count: int
    selected_count: int
    low_quality_count: int
```

Implement weighted median/MAD using provenance weights, preset fallback scales
for one reference, IoU/centroid matching, robust feature distance, quality
bounds, and deterministic deduplication. Protected outputs remain first in
their original order; generated candidates follow score order. Every returned
mask must be an independent boolean array.

- [ ] **Step 4: Run Task 3 and all adaptation tests**

Expected: all `tests/test_roi_adaptation.py` tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add roi_adaptation.py tests/test_roi_adaptation.py
git commit -m "feat: fit ROI candidates to user examples"
```

### Task 4: ROI Provenance, Revisions, Persistence, and List Status

**Files:**
- Modify: `analysis_core.py:75-100`
- Modify: `NewLight_Analysis.py:2411-2433,3041-3064,3681-3725,3727-3785,4283-4301`
- Modify: `tests/test_gui_static.py`
- Modify: `tests/test_roi_adaptation.py`

- [ ] **Step 1: Add failing state and GUI tests**

Add assertions that:

```python
state = core.AnalysisState()
assert state.roi_metadata == []
assert state.roi_revision == 0
```

Static GUI tests must require `set_rois(..., metadata=None)`, manual source
metadata in `add_roi()`, aligned metadata removal in both delete paths,
revision increments, NPZ metadata save/load, and ROI-list quality text. Add a
direct test that `ROI4*` is displayed once when metadata says low quality.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
conda run -n caiman_latest --no-capture-output python -m pytest tests/test_roi_adaptation.py tests/test_gui_static.py -q
```

- [ ] **Step 3: Extend state and centralize ROI mutation**

Add to `AnalysisState`:

```python
roi_metadata: list[dict] = field(default_factory=list)
roi_revision: int = 0
```

Update `set_rois()` to normalize one metadata record per mask, update display
names through `display_roi_name()`, increment revision exactly once, and refresh
the list. `add_roi()` creates `source="manual"`; engine completion supplies
`source="fast"` or `source="caiman"`. Delete and clear operations mutate masks,
metadata, and names together. Save metadata as JSON text in the ROI NPZ and
load old files without metadata as `source="loaded"`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Also run a Tk smoke script that adds two masks, marks
one low quality, deletes one, and confirms all three aligned lists and the
revision counter remain correct.

- [ ] **Step 5: Commit Task 4**

```powershell
git add analysis_core.py NewLight_Analysis.py tests/test_gui_static.py tests/test_roi_adaptation.py
git commit -m "feat: track ROI provenance and quality"
```

### Task 5: Permissive Candidate Modes in Both Workers

**Files:**
- Modify: `workers/run_neusuite_roi.py`
- Modify: `workers/run_caiman_roi.py`
- Modify: `analysis_core.py:3021-3155`
- Modify: `tests/test_roi_worker_contracts.py`
- Modify: `tests/test_roi_backend_wrappers.py`

- [ ] **Step 1: Write failing worker-contract tests**

Require both parsers to expose `candidate_mode`. Fast candidate mode must use a
separate `candidate_confidence` default of `0.05`. CaImAn helpers must be tested
with accepted and rejected component indices to prove all non-empty candidates
and aligned `snr`, `r_values`, `cnn_scores`, `traces`, and component indices are
retained.

Wrapper tests must assert these exact flags:

```python
assert arg_value(args, "--candidate-confidence") == "0.05"
assert "--candidate-mode" in args
```

and verify that malformed quality-array lengths raise `ROIArtifactError` before
results reach the GUI.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
conda run -n caiman_latest --no-capture-output python -m pytest tests/test_roi_worker_contracts.py tests/test_roi_backend_wrappers.py -q
```

- [ ] **Step 3: Implement fast candidate mode**

Add parser arguments:

```python
parser.add_argument("--candidate-mode", action="store_true")
parser.add_argument("--candidate-confidence", type=float, default=0.05)
```

Use candidate confidence for `model.predict()` only in candidate mode. Keep the
broad area filter, export all aligned scores/source indices, and record both
generation and final-selection confidence in metadata. Do not alter standard
mode behavior.

- [ ] **Step 4: Implement CaImAn candidate mode**

After `evaluate_components()`, candidate mode selects every component index for
which the thresholded footprint is non-empty. Standard mode continues to use
`idx_components`. Export quality values from full arrays at the selected
indices. Record `preset_accepted` as an aligned boolean array so preset-only
selection remains reproducible.

- [ ] **Step 5: Wire and validate wrappers**

Add `candidate_mode=False` and `candidate_confidence=0.05` parameters to both
relevant core wrappers, pass flags to workers, and validate every model-quality
array against returned mask count.

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all worker/wrapper tests pass.

- [ ] **Step 7: Commit Task 5**

```powershell
git add workers/run_neusuite_roi.py workers/run_caiman_roi.py analysis_core.py tests/test_roi_worker_contracts.py tests/test_roi_backend_wrappers.py
git commit -m "feat: expose permissive ROI candidate banks"
```

### Task 6: Embedded Presets, Autofill, Candidate Cache, and Adaptive Runs

**Files:**
- Modify: `NewLight_Analysis.py:5590-5825`
- Modify: `tests/test_gui_static.py`
- Modify: `tests/test_roi_adaptation.py`

- [ ] **Step 1: Write failing GUI and cache tests**

Static tests must require both panels to contain a readonly `quality_preset`
choice and `根据当前 ROI 自适应拟合并运行`. Fast ROI must contain
`从当前 ROI 填入面积`. Require separate cache fields for `fast` and `caiman`, a
source-signature builder, `roi_revision` snapshots, and stale revision checks
before `set_rois()`.

Add direct lightweight tests around extracted pure helpers:

```python
from roi_adaptation import adaptive_result_is_current, candidate_source_signature


def test_same_source_signature_reuses_candidate_bank():
    first = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    second = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    assert first == second


def test_projection_or_movie_generation_change_invalidates_fast_bank():
    base = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    changed_movie = candidate_source_signature(
        "fast", 8, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    changed_projection = candidate_source_signature(
        "fast", 7, (128, 128), 5, "max", (10, 50), "weights-v1", {"image_size": 960}
    )
    assert base != changed_movie
    assert base != changed_projection


def test_reference_revision_does_not_change_bank_signature_but_blocks_stale_apply():
    before = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    after = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    assert before == after
    assert adaptive_result_is_current(7, 12, current_generation=7, current_roi_revision=12)
    assert not adaptive_result_is_current(7, 12, current_generation=7, current_roi_revision=13)
```

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
conda run -n caiman_latest --no-capture-output python -m pytest tests/test_gui_static.py tests/test_roi_adaptation.py -q
```

- [ ] **Step 3: Add quality preset application and area autofill actions**

Both panels use the existing dictionary `action` field type. Applying a preset
updates visible advanced fields through `self.parameter_vars`; changing an
advanced field does not silently rewrite it. Fast area autofill calls
`suggest_area_range()` and updates only the values specified by its zero/one/
multiple reference contract. CaImAn adaptive action derives equivalent diameter
from protected masks and reports the fitted value before enqueueing.

- [ ] **Step 4: Add candidate-bank caches and signatures**

Initialize:

```python
self.roi_candidate_banks = {"fast": None, "caiman": None}
self.movie_generation = 0
```

Increment movie generation whenever import or preprocessing replaces the movie.
Build immutable signatures containing the design-specified source and engine
generation fields. Store candidate artifacts only in the session temporary
directory.

Put signature normalization and stale-result checks in `roi_adaptation.py` so
they can be tested without Tk:

```python
def candidate_source_signature(
    engine,
    movie_generation,
    image_shape,
    invalid_start_frames,
    projection_mode,
    baseline_window,
    model_identity,
    generation_parameters,
):
    parameters = tuple(sorted((str(key), repr(value)) for key, value in generation_parameters.items()))
    return (
        str(engine),
        int(movie_generation),
        tuple(int(value) for value in image_shape),
        int(invalid_start_frames),
        str(projection_mode),
        tuple(int(value) for value in baseline_window),
        str(model_identity),
        parameters,
    )


def adaptive_result_is_current(
    source_generation,
    source_roi_revision,
    *,
    current_generation,
    current_roi_revision,
):
    return int(source_generation) == int(current_generation) and int(source_roi_revision) == int(current_roi_revision)
```

- [ ] **Step 5: Implement adaptive FIFO tasks**

At enqueue time snapshot movie identity/generation, ROI masks/metadata,
`roi_revision`, preset, and engine settings. The worker callback obtains or
generates the candidate bank, calls `adapt_candidate_bank()`, and returns cache
status plus fitted output. The Tk finish callback must check movie identity,
generation, and ROI revision before applying output. A stale fit logs a retry
message and preserves the current list.

Normal run applies presets without protected-reference fitting. Adaptive run
preserves/refines all current ROIs and adds selected candidates. Both remain
single queued tasks from the user's perspective.

- [ ] **Step 6: Run focused tests and Tk smoke verification**

Run Step 2, then a hidden Tk smoke test with monkeypatched worker wrappers:

1. seed one manual ROI;
2. invoke fast adaptive run and verify it remains first;
3. add a second manual ROI;
4. invoke adaptive run again and assert the candidate bank wrapper was called
   once while adaptation was called twice;
5. mark a protected ROI low quality and confirm its list name ends in `*`.

- [ ] **Step 7: Commit Task 6**

```powershell
git add NewLight_Analysis.py tests/test_gui_static.py tests/test_roi_adaptation.py
git commit -m "feat: add iterative adaptive ROI fitting"
```

### Task 7: Integration Validation and Project Records

**Files:**
- Modify: `WORK_LOG.md`
- Modify: `PROJECT_HANDOFF.md`
- Verify all files changed in Tasks 1-6

- [ ] **Step 1: Run focused adaptive ROI tests**

```powershell
$env:MKL_THREADING_LAYER='SEQUENTIAL'
conda run -n caiman_latest --no-capture-output python -m pytest tests/test_roi_adaptation.py tests/test_roi_worker_contracts.py tests/test_roi_backend_wrappers.py tests/test_gui_static.py -q
```

Expected: zero failures and no new warnings.

- [ ] **Step 2: Run the full suite**

```powershell
$env:MKL_THREADING_LAYER='SEQUENTIAL'
conda run -n caiman_latest --no-capture-output python -m pytest -q
```

Expected baseline before implementation: `111 passed`. Final count must be
greater than 111 with zero failures.

- [ ] **Step 3: Compile-check source and workers**

```powershell
conda run -n caiman_latest --no-capture-output python -m py_compile NewLight_Analysis.py analysis_core.py roi_adaptation.py workers/run_neusuite_roi.py workers/run_caiman_roi.py
```

- [ ] **Step 4: Run a retained-sample smoke test without modifying the sample**

Use `eye/data/2/A01/result.avi` read-only. Write all candidate and fitted
artifacts under `session_temp_dir`. Exercise fast candidate generation and at
least one cached refit. For CaImAn, use a bounded frame/spatial crop for worker
validation, then verify aligned masks and quality arrays. Never delete, move,
or overwrite the retained sample.

- [ ] **Step 5: Inspect changes**

```powershell
git diff --check
git status --short
```

Confirm no generated model output, candidate cache, sample data, or EXE build
artifact is staged.

- [ ] **Step 6: Update records**

Record the final test count, smoke-test dimensions/counts, preset values,
candidate-cache rules, ROI metadata contract, star semantics, and key files in
`WORK_LOG.md` and `PROJECT_HANDOFF.md`.

- [ ] **Step 7: Commit the verified feature**

```powershell
git add roi_adaptation.py analysis_core.py NewLight_Analysis.py workers/run_neusuite_roi.py workers/run_caiman_roi.py tests/test_roi_adaptation.py tests/test_roi_worker_contracts.py tests/test_roi_backend_wrappers.py tests/test_gui_static.py WORK_LOG.md PROJECT_HANDOFF.md docs/superpowers/specs/2026-07-28-adaptive-roi-guidance-design.md docs/superpowers/plans/2026-07-28-adaptive-roi-guidance.md
git commit -m "feat: adapt ROI segmentation to user examples"
```

Do not build the EXE unless the user separately requests a release build.
