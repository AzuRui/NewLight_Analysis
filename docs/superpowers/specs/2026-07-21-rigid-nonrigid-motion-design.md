# Rigid and Non-rigid Motion Correction Design

Date: 2026-07-21

## Problem

The current built-in motion correction performs global translation only. Its
`Template frames` value means "use frames 0 through N-1 to calculate a mean
template". It does not mean "use frame N as the reference". Every movie frame,
including those used to form the template, is processed and returned; there is
no later splice that restores the original reference interval.

A raw mean is a poor template when its source frames move. Shifted anatomical
structures are averaged at different coordinates, producing blur rather than a
more stationary image. This can make phase correlation return small or
inconsistent shifts even though visible motion remains.

## Chosen Approach

Replace the built-in rigid-only action with a constrained two-stage pipeline:

1. Estimate and apply one global translation per frame.
2. Estimate overlapping local patch translations from the rigid-corrected
   frames, interpolate a smooth displacement field, and apply it as non-rigid
   correction.

This stays inside the packaged application and uses the existing NumPy, SciPy,
and scikit-image stack. CaImAn remains available as a separate backend. Dense
optical flow is not used because unconstrained per-pixel flow can warp cells and
alter quantitative calcium-image structure.

## Reference Template

The default mode is `auto`:

- Calculate low-resolution consecutive-frame translations.
- Search candidate windows of the requested reference length.
- Select the window with the lowest robust motion score.
- Within that window, choose a sharp, centrally located frame as the initial
  anchor instead of averaging unregistered frames.
- Rigidly align the selected window to the anchor.
- Build the refined template as the pixelwise median of the aligned window.
- Re-estimate the final global shift of every frame against the refined
  template.

Manual mode accepts a zero-based start frame and a frame count. It uses the same
anchor, alignment, and median-template process, but skips automatic window
selection. Start frame and frame count are separate values so a frame number is
never silently interpreted as a count.

All frames are corrected against the refined template. Frames in the reference
window are not discarded, copied unchanged, or restored later.

## Non-rigid Stage

The rigid-corrected frame is split into overlapping square patches. Each patch
shift is estimated against the corresponding template patch by phase
correlation. Local shifts are constrained relative to the global solution:

- Reject or neutralize patches with insufficient texture or invalid estimates.
- Clamp local displacement to the configured maximum.
- Blend overlapping patch estimates into full-resolution vertical and
  horizontal displacement fields.
- Smooth the fields spatially before warping the frame.
- Use interpolation with edge replication and preserve the movie as
  `float32` without display normalization.

The default patch geometry must work when the image is smaller than the nominal
patch size. In that case, dimensions and overlap are clamped to valid values.
If a movie is too small for a meaningful patch grid, the non-rigid field is zero
and the valid rigid result is retained.

## User Interface

Rename the action to `Rigid + Non-rigid (Built-in)` and expose only parameters
that materially affect the result:

- `Reference mode`: `auto` or `manual`
- `Reference start frame`: used by manual mode, zero-based
- `Reference frame count`: automatic window length or manual range length
- `Max rigid shift`: maximum global displacement in pixels
- `Patch size`: local registration patch width and height
- `Patch overlap`: overlap between adjacent patches
- `Max local shift`: maximum residual local displacement in pixels

The default reference mode is automatic. The template aggregation method is
fixed to median and the displacement-field smoothing remains an internal safe
default to avoid presenting parameters that usually make results less stable.

The operation runs in the existing background-worker mechanism so the Tk UI
does not appear frozen. On completion the Run Log reports:

- selected reference frame interval and anchor frame;
- number of processed frames and elapsed time;
- median and maximum absolute rigid displacement;
- median and maximum absolute non-rigid displacement;
- whether any patch estimates were rejected or clamped.

## Multi-channel Behavior

Motion is mechanical and must not be estimated independently for each color
channel. For multi-channel input:

1. Estimate the reference template, rigid shifts, and non-rigid fields from Ch1.
2. Apply exactly the same transforms to every loaded channel.
3. Rebuild the grayscale analysis movie from the corrected channel movies.

This preserves cross-channel registration and avoids repeating the expensive
estimation stage. Undo stores the pre-correction channel movies through the
existing history mechanism.

## Components and Interfaces

The core implementation is divided into independently testable operations:

- reference-window selection and anchor selection;
- rigid transform estimation;
- refined-template construction;
- local field estimation;
- transform application to one movie;
- orchestration returning corrected movie data and diagnostics.

The transform representation contains global shifts for every frame and local
displacement fields or patch-grid shifts sufficient to reproduce the same warp
on another channel. Estimation is therefore separated from application.

The GUI validates text parameters, snapshots history once, starts one worker,
and applies the returned corrected channel set only after successful completion.
An exception leaves the currently loaded movies unchanged and presents the
error through the existing error handling path.

## Testing

Tests are written before production changes and cover:

- the current parameter ambiguity: start frame and frame count select the
  intended interval;
- automatic selection prefers a stable synthetic interval;
- every output frame, including reference frames, is transformed;
- known global translations are reduced by rigid correction;
- known smooth local deformation is reduced after the non-rigid stage;
- transform replay applies identical geometry to a second channel;
- small and non-square images produce valid output with unchanged shape;
- invalid ranges and patch geometry produce clear validation errors;
- the GUI exposes the renamed action and all required fields;
- existing preprocessing, bit-depth, baseline, and display tests still pass.

Synthetic tests compare registration error to a known stationary source image;
they do not merely assert that output arrays differ from input arrays.

## Non-goals

- Rotation, scale changes, and Z-plane drift are not estimated.
- No unconstrained dense optical flow is introduced.
- This change does not remove or redesign the separate CaImAn backend.
- Motion correction does not normalize intensity or convert 16-bit data to
  8-bit.
