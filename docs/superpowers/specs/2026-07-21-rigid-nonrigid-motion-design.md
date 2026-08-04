# Motion Correction Design

Date: 2026-07-21

## Decision

NewLight keeps two motion-correction backends with distinct purposes:

- `Rigid Motion (Built-in)` is a lightweight global-translation correction
  available directly in the main application.
- `CaImAn Motion` is the advanced calcium-imaging backend. Its `piecewise`
  mode already runs rigid template generation first and then performs
  piecewise-rigid local correction.

NewLight does not add a second custom non-rigid implementation. CaImAn's tested
piecewise path is preferred over unconstrained dense optical flow or duplicated
patch-warp code that could distort cells.

## Confirmed Built-in Root Cause

The old Built-in implementation interpreted `Template frames = N` as "average
raw frames 0 through N-1". Every frame was present in the output loop, so no
reference frames were discarded and no original segment was spliced back.

However, those first N frames defined the output coordinate system. If the
whole reference segment was displaced by 4 px, its estimated shifts were zero
and later stable frames were moved 4 px toward the incorrect opening position.
An unregistered mean could also blur moving anatomy and weaken phase
correlation. This explains why reference frames appeared uncorrected.

## Built-in Reference Construction

Built-in rigid correction now supports `auto` and `manual` reference modes.

Automatic mode:

1. Estimate low-resolution translations between consecutive frames.
2. Reconstruct the relative frame-position trajectory.
3. Score candidate windows by internal motion and distance from the movie's
   dominant median position.
4. Select the lowest-scoring stable, representative window.

Manual mode uses a zero-based start frame and a frame count supplied by the
user.

Both modes use the same two-pass template construction:

1. Use the middle frame of the selected interval as an initial anchor.
2. Align every selected frame to that anchor.
3. Build a pixelwise median template from the aligned interval.
4. Re-estimate and apply a final shift to every movie frame, including all
   frames in the selected reference interval.

At least one coordinate anchor must be unchanged by definition when there is
no external anatomical reference. The important guarantee is that no interval
is skipped or restored from the source; moving frames inside the selected
interval receive non-zero final shifts when the refined template requires it.

## User Interface

The shared Parameters panel supports optional choice fields rendered as
readonly `ttk.Combobox` controls.

`CaImAn Motion` exposes:

- `Mode`: `rigid` or `piecewise`
- `Max shift px`: maximum global y/x search displacement
- `Patch stride px`: spacing between local patch starts
- `Patch overlap px`: overlap added to the stride; patch size is their sum
- `Max local deviation px`: allowed local displacement from the rigid estimate
- defaults: `piecewise / 12 / 48 / 24 / 5`

Typing arbitrary mode names is not possible.

The worker logs the actual values plus rigid/local median and maximum absolute
y/x shifts. `at_limit_fraction` reports how often an estimate reaches its
configured displacement limit and is the first diagnostic to inspect when
correction remains incomplete.

`Rigid Motion (Built-in)` exposes:

- `Reference mode`: `auto` or `manual`
- `Reference start frame`: zero-based, used only in manual mode
- `Reference frame count`: automatic window length or manual interval length
- `Max rigid shift px`: per-axis displacement limit

The Run Log reports the selected interval, anchor frame, median absolute dy/dx,
and maximum absolute dy/dx.

## CaImAn Behavior

The installed CaImAn `MotionCorrect.motion_correct_pwrigid(...)` implementation
calls `motion_correct_rigid()` when no template is supplied, then performs its
piecewise-rigid stage. Therefore:

- `rigid` corrects whole-frame translation only;
- `piecewise` performs the requested rigid-then-local workflow.

CaImAn remains a worker operation using temporary TIFF/mmap data. After the
corrected TIFF is read into memory, NewLight deletes its temporary input, keeps
the corrected TIFF as a session preview until application close, and logs that
preview path. The result replaces the current movie while preserving whether
the user was viewing a frame or projection. `Save Current Movie` is still
required for permanent output. In the current GUI CaImAn operates on the
grayscale analysis movie and returns one gray channel. Applying one CaImAn
transform to all original color channels is a separate future change and is not
claimed by this update.

## Tests

Regression coverage verifies:

- CaImAn mode is declared as a readonly `rigid/piecewise` choice.
- Manual start and count select the intended interval.
- Moving frames inside the manual reference interval are corrected.
- Automatic mode avoids an unstable opening.
- Automatic mode prefers the dominant movie position over a short, internally
  static but globally displaced opening.
- Output shape and `float32` type are preserved.
- Existing GUI, bit-depth, background, interlacing, and baseline behavior
  remains covered by the relevant test suite.

## Non-goals

- Built-in correction does not estimate rotation, scaling, local deformation,
  or Z-plane drift.
- Motion correction does not normalize intensity or convert 16-bit input to
  8-bit.
- This update does not remove or replace CaImAn.
