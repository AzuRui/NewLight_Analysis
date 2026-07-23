# Fast Motion Correction Design

Date: 2026-07-23

## Goal

Rename the built-in rigid correction feature to `快速运动矫正` and add an
optional, constrained local deformation stage after the existing rigid stage.
The current rigid algorithm, reference selection, and rigid-only output must
remain unchanged when flexible strength is zero.

CaImAn piecewise-rigid correction remains the higher-capability option for
larger or more complex local motion. Fast Motion Correction is the lightweight,
in-process option for modest local deformation without requiring the CaImAn
environment.

## User Interface

Keep the existing stable action ID `builtin_rigid_motion` to avoid breaking
internal routing and saved panel state. Change only its visible label to
`快速运动矫正`.

The parameter panel contains:

- `参考帧模式`: automatic or manual, unchanged.
- `参考起始帧`: unchanged and used in manual mode.
- `参考帧数量`: unchanged.
- `最大刚性位移 (px)`: unchanged.
- `柔性强度`: floating-point value from 0.0 to 1.0, default 0.0.
- `局部块尺寸 (px)`: integer, default 96.
- `最大局部形变 (px)`: non-negative floating-point value, default 3.0.

There is no separate rigid/flexible mode selector. `柔性强度 = 0` disables the
local stage and runs the existing rigid path only. Any positive strength enables
the local stage and scales the estimated local displacement field.

The parameter-panel description must explicitly state:

- `0` means rigid correction only and preserves the current behavior.
- `0.2-0.5` is the recommended flexible-strength range for mild local motion.
- Larger values permit stronger correction but increase deformation risk.
- Local block size controls spatial scale; smaller blocks follow finer motion
  but are slower and less stable.
- Maximum local deformation is a safety bound, not a target displacement.
- CaImAn piecewise-rigid correction is recommended for stronger or complex
  motion.

## Processing Pipeline

### Stage 1: Existing Rigid Correction

Call `rigid_motion_correction()` without changing its reference-window search,
aligned-median template construction, phase-correlation settings, shift limits,
or interpolation. This stage returns the rigid-corrected movie, global shifts,
and template metadata exactly as it does today.

When flexible strength is zero, return this movie immediately. This is the
compatibility invariant for the feature.

### Stage 2: Constrained Local Correction

When flexible strength is positive:

1. Use the rigid template as the local-registration reference.
2. Cover each rigid-corrected frame with overlapping square patches. Derive a
   stable stride from the selected block size so neighboring estimates overlap.
3. Estimate translation for every patch with phase cross-correlation.
4. Clip every local shift to `最大局部形变`.
5. Remove the robust median local translation from the patch grid so the local
   stage does not repeat the global rigid correction.
6. Suppress isolated vector outliers with neighborhood median filtering.
7. Interpolate and spatially smooth the sparse patch shifts into a dense,
   continuous displacement field.
8. Multiply that field by `柔性强度` and warp the rigid-corrected frame once,
   using linear interpolation and nearest-edge border handling.

The local stage must preserve frame count, image dimensions, and `float32`
output. It must not modify the rigid template or input movie in place.

## Parameter Validation

- Clamp flexible strength to `[0.0, 1.0]` in the UI processing path and reject
  non-finite values in the core function.
- Require a useful minimum block size and cap it to the image dimensions.
- Require maximum local deformation to be finite and non-negative.
- If the image is too small to form a meaningful local grid, return the rigid
  result and report that local correction was skipped.
- If a patch has insufficient texture or produces a non-finite estimate, use a
  zero local vector for that patch.

## Diagnostics

Keep the existing rigid reference interval and global dy/dx statistics. When
local correction runs, also log:

- effective local block size and grid dimensions;
- requested flexible strength and maximum local deformation;
- median and maximum absolute local dy/dx before strength scaling;
- fraction of local estimates touching the configured deformation limit.

When strength is zero, the log must clearly say that only rigid correction was
applied.

## Tests

Add regression coverage for:

- strength zero producing the same result, shifts, and rigid metadata as the
  existing rigid-only function;
- synthetic local deformation being reduced after rigid plus local correction;
- displacement clipping and finite output;
- output shape and dtype preservation;
- too-small images falling back safely to rigid-only output;
- Chinese label and parameter-panel description text;
- GUI routing of all three local parameters into the core function.

Run the complete test suite and Python syntax compilation after implementation.
The EXE is not rebuilt unless separately requested.

## Non-Goals

- Dense optical-flow or unrestricted elastic registration.
- Rotation, scaling, or three-dimensional registration.
- Replacing CaImAn or changing its parameters.
- Multi-channel shared-field correction in this change.
