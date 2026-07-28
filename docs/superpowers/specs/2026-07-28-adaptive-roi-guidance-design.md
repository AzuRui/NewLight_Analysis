# Adaptive ROI Guidance Design

## Goal

Make both `快速 ROI 分割` and `CaImAn 识别分割` progressively follow the
user's current ROI choices without training or modifying model weights. Existing
ROI masks are protected examples: their identities are preserved, their
boundaries are refined locally into free-form activity-aligned masks, and new
candidate ROIs are selected by similarity to those examples. Low-quality
protected ROIs remain in the result and receive a trailing `*` marker.

## User Workflow

1. The user may begin with manually drawn ROIs, ROIs from fast segmentation,
   loaded ROIs, or no ROIs.
2. Both ROI engines expose a `质量预设` choice: `高召回`, `均衡`, `高精度`, or
   `自定义`.
3. Fast ROI also exposes `从当前 ROI 填入面积`:
   - With two or more masks, the software finds the smallest and largest area,
     then fills `min_area = round(0.9 * smallest)` and
     `max_area = round(1.1 * largest)`.
   - With one mask, only `max_area = round(1.1 * area)` is changed. The current
     minimum is preserved.
   - With no masks, parameters are unchanged and inline feedback explains why.
4. `根据当前 ROI 自适应拟合并运行` uses the selected quality preset as a
   prior, reads the latest ROI list, refines every existing mask, fits adaptive
   quality/similarity thresholds, and appends matching missed candidates.
5. The user can draw additional missed ROIs and run adaptive fitting again.
   Cached candidates are re-ranked without repeating expensive inference when
   the movie and candidate-generation inputs have not changed.

The existing normal run button remains available. It applies the selected
quality preset without treating current ROIs as adaptive examples.

## Scientific Meaning

This workflow is not model training. It does not update CaImAn, NeuSuite, or
CNN weights. It is a reproducible calibration layer over model candidates:

- NeuSuite confidence supplies learned convolutional evidence.
- CaImAn supplies temporal SNR, spatial correlation, CNN score, and spatial
  footprints.
- A low-compute convolution descriptor supplies local image structure using a
  fixed filter bank computed once per projection: Gaussian responses at two
  scales, Sobel gradient magnitude, and Laplacian-of-Gaussian response.
- Shape, area, local contrast, and temporal activity features complement those
  model-specific values.

This combination provides the requested complement between low-cost repeated
fitting and convolution-informed similarity while avoiding unstable few-shot
weight fine-tuning from positive examples alone.

## Quality Presets

Presets define safe starting bounds. Adaptive fitting may relax or tighten
within the selected preset's bounded range, but it must record the final values
in result metadata.

| Preset | Fast final confidence | CaImAn min SNR | CaImAn spatial correlation | CaImAn CNN minimum | Similarity behavior |
| --- | ---: | ---: | ---: | ---: | --- |
| 高召回 | 0.10 | 1.5 | 0.70 | 0.70 | widest robust distance |
| 均衡 | 0.25 | 2.0 | 0.80 | 0.90 | default robust distance |
| 高精度 | 0.40 | 2.5 | 0.90 | 0.99 | narrow robust distance |
| 自定义 | current fields | current fields | current fields | current fields | current fields |

Adaptive candidate generation is intentionally more permissive than final
selection. Fast ROI may generate candidates down to confidence `0.05`.
CaImAn computes quality arrays for all non-empty initialized components before
the adaptive layer performs final selection.

## ROI State and Provenance

`AnalysisState` keeps aligned metadata for every ROI:

```python
{
    "source": "manual" | "fast" | "caiman" | "loaded" | "atlas",
    "protected": bool,
    "low_quality": bool,
    "quality_reasons": list[str],
    "base_name": str,
}
```

All ROIs present when adaptive fitting starts are protected. Provenance changes
only how strongly an example affects fitted parameters:

- manual: `1.0`
- loaded/atlas: `0.8`
- fast/CaImAn generated: `0.6`

Protected ROIs are never removed by quality filtering. A low-quality protected
ROI is displayed and exported as `<base_name>*`. The asterisk is a quality
warning, not part of the stable base identity. User deletion remains the only
way to remove a protected example.

Every ROI mutation increments `roi_revision`. An adaptive task snapshots that
revision. If the user changes ROIs while a task is running, the completed task
may retain its candidate cache but must not overwrite the newer ROI list.

## Protected Boundary Refinement

Each protected ROI is refined independently and remains one output ROI. It may
not split, merge with a neighbor, jump to another cell, or disappear.

1. Estimate equivalent diameter from mask area.
2. Dilate the original mask by a bounded search radius of approximately 25% of
   that diameter, clamped to `2-12 px`.
3. Compute the ROI mean temporal trace and each search pixel's correlation with
   that trace.
4. Combine temporal correlation, normalized local projection contrast, and
   fixed convolution responses into an activity-support image.
5. Threshold within the search region and keep only the connected component
   with the greatest overlap with the original mask.
6. Apply light closing/hole filling and clamp the refined area to
   `0.5-1.8` times the original area.
7. If refinement is empty, unstable, or outside those bounds, retain the
   original mask and add a low-quality reason.

When a model candidate overlaps the protected ROI, its free-form mask is an
additional boundary proposal. The accepted refinement remains constrained by
the same search region and identity rules.

## Candidate Features and Adaptive Fit

Every reference and candidate gets one normalized feature record:

- log area and equivalent diameter;
- eccentricity, solidity, compactness, and perimeter-to-area ratio;
- ROI projection mean, surrounding-ring mean, and local contrast;
- pooled Gaussian, Sobel, and Laplacian-of-Gaussian responses;
- temporal SNR and local trace consistency when movie data is available;
- NeuSuite confidence for fast candidates;
- CaImAn spatial correlation, SNR, and CNN score for CaImAn candidates.

Reference centers and scales use weighted median and median absolute deviation.
For a single reference, preset feature scales provide nonzero tolerances.
Candidate similarity is a bounded weighted robust distance. Model quality and
similarity are both required for generated candidates, while protected ROIs
are retained regardless of score.

Candidate masks are matched to protected masks by IoU and normalized centroid
distance. Matched candidates aid boundary refinement and parameter fitting but
are not appended a second time. Remaining candidates are sorted by adaptive
score and deduplicated against protected and already selected masks.

## Candidate Banks and Cache Invalidation

The application stores separate in-session candidate banks for fast ROI and
CaImAn. Each bank contains masks, model quality arrays, convolution/shape
features, generation parameters, and a source signature.

A bank is reusable only when all relevant inputs match:

- movie object/generation and spatial shape;
- invalid-start-frame protocol value;
- preprocessing result;
- projection mode and baseline projection window for fast ROI;
- model weights/runtime identity;
- candidate-generation parameters that alter model output;
- CaImAn mode, cell diameter, patch initialization, and subsampling controls.

Changing only examples, quality preset, or final selection thresholds does not
invalidate the bank. Session cleanup deletes the cache artifacts with the
existing session temporary directory.

## Worker Changes

### Fast ROI

The fast worker adds a candidate mode that uses a permissive confidence floor,
retains all area-valid instances, and exports aligned confidence/source-index
arrays. Learned model confidence is combined with the fixed convolution
descriptor in the main adaptation layer; no fragile hooks into private
NeuSuite network layers are required.

### CaImAn

The CaImAn worker evaluates all components, thresholds all spatial footprints,
and exports every non-empty candidate with aligned traces, SNR, spatial
correlation, CNN score, and the original component index. Existing preset-only
execution selects from this bank using the preset. Adaptive execution performs
the final protected-reference fit in the main process.

## UI and Feedback

Both embedded parameter panels provide:

- `质量预设` readonly selector;
- `根据当前 ROI 自适应拟合并运行` action;
- existing advanced fields for transparent inspection and custom mode;
- help text stating that fitting calibrates selection and does not train model
  weights.

Fast ROI additionally provides `从当前 ROI 填入面积`. CaImAn uses current ROI
areas to recommend/fill cell diameter during adaptive fitting.

Inline feedback reports:

- number and provenance of reference ROIs;
- whether a candidate bank was generated or reused;
- fitted area/diameter and quality thresholds;
- number of protected, newly selected, and low-quality protected ROIs;
- stale-result rejection if `roi_revision` changed.

The ROI list keeps its color/name/area display and adds quality status. Names
with low-quality state show a trailing `*`, with help text explaining that the
ROI was retained by user intent but did not meet the active quality preset.

## Error and Safety Rules

- No current ROI: adaptive action falls back to preset-only selection and says
  that no examples were available.
- One current ROI: robust preset scales prevent zero-variance fitting.
- Empty candidate bank: refined protected ROIs are still returned.
- Refinement failure: original protected mask is retained and marked `*`.
- Backend failure/cancellation/stale source: current ROI list remains intact.
- Concurrent ROI edits: candidate artifacts may be cached, but stale fitted
  output is not applied.
- Automatic fitting never changes model weights or writes outside the session
  temporary directory and normal user-selected result paths.

## Testing Strategy

1. Unit-test area autofill for zero, one, two, and multiple examples.
2. Unit-test provenance weights, star display names, metadata alignment, and
   ROI revision behavior.
3. Unit-test protected boundary refinement on synthetic irregular activity,
   including fallback and no-merge constraints.
4. Unit-test robust feature fitting with one and multiple examples, candidate
   ranking, protected retention, low-quality marking, and deduplication.
5. Contract-test both workers' permissive candidate outputs and aligned
   quality arrays without running heavy models.
6. GUI-test presets/actions, parameter autofill, cache feedback, and stale
   result rejection.
7. Run the full pytest suite, Python compilation, `git diff --check`, and a Tk
   smoke test covering draw -> adaptive fit -> add missed ROI -> cached refit.

No EXE build is part of this feature unless separately requested.
