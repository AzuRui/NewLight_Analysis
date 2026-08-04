# NewLight Analysis Initialization Splash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a responsive animated initialization splash that remains visible while the frozen application checks its packaged backends, display adapters, CUDA availability, and optional NVIDIA driver setup.

**Architecture:** A focused `initialization_splash.py` module owns all Tk animation and thread marshalling. `launch.py` runs the existing setup gate through this controller only in frozen mode, while `machine_setup.py` exposes progress notifications without depending on Tk. The optimized GIF is the sole packaged splash background.

**Tech Stack:** Python 3.11, Tkinter, Pillow/ImageTk, threading/queue, PyInstaller, pytest

---

## File Map

- Create `initialization_splash.py`: splash layout, GIF playback, dashed-ring animation, progress queue, worker lifecycle, and fallback rendering.
- Create `docs/previews/initialization-splash.html`: browser visual preview using the same assets and geometry as the Tk implementation.
- Modify `launch.py`: invoke setup through the splash controller for frozen GUI launches.
- Modify `machine_setup.py`: emit initialization stages through an optional progress callback.
- Modify `NewLight_Analysis.spec`: package `neural_starlight_startup.gif` and exclude the original large GIF.
- Modify `tests/test_machine_setup.py`: verify progress stages and preserve existing setup behavior.
- Create `tests/test_initialization_splash.py`: verify resource resolution, fallback behavior, task completion, and cleanup.
- Modify `tests/test_packaging_contracts.py`: enforce optimized splash packaging and reject original GIF packaging.
- Modify `PROJECT_HANDOFF.md` and `WORK_LOG.md`: record behavior, resources, test commands, and packaging constraints.

### Task 1: Browser Visual Preview

- [ ] Create `docs/previews/initialization-splash.html` with a fixed 720 x 480 stage, cover-fit animated background, centered logo/title/subtitle, and a three-column bottom row containing version, status, and an eight-dot sequential bubble loader.
- [ ] Start a local static server from the repository and inspect the preview at desktop and narrow widths.
- [ ] Confirm that the title and logo do not overlap the neural image or spinner and that the spinner remains visible throughout the GIF loop.

### Task 2: Progress Contract

- [ ] Add a failing test in `tests/test_machine_setup.py` that passes `progress=events.append` and expects ordered stages for backend, adapter, CUDA, and completion paths.
- [ ] Run `python -m pytest tests/test_machine_setup.py -q` and verify the new test fails because no progress callback exists.
- [ ] Add `ProgressCallback = Callable[[str], None]`, a no-op-safe emitter, and optional `progress` parameters to `ensure_first_run_setup()` and `ensure_application_setup()`.
- [ ] Emit user-facing stages immediately before each potentially slow operation and a terminal stage on successful completion.
- [ ] Run `python -m pytest tests/test_machine_setup.py -q` and verify all tests pass.

### Task 3: Splash Controller

- [ ] Add failing lifecycle tests in `tests/test_initialization_splash.py` using fake roots and fake setup functions; assert progress is marshalled, return values propagate, exceptions are captured, and teardown runs exactly once.
- [ ] Run `python -m pytest tests/test_initialization_splash.py -q` and verify failure because the module does not exist.
- [ ] Implement `initialization_splash.py` with `SplashWindow` and `run_with_initialization_splash()` boundaries. Decode the 25 GIF frames once, animate through `after()`, draw eight circular dots whose size and opacity pulse sequentially in the bottom-right region, and poll a thread-safe queue.
- [ ] Resolve resources from `_internal` for frozen builds and the project directory for source/test execution. Fall back to a static dark background and text when GIF or icon loading fails.
- [ ] Close the root in one idempotent cleanup path for success, false return, and exception; surface unexpected exceptions after cleanup.
- [ ] Run `python -m pytest tests/test_initialization_splash.py -q` and verify all tests pass.

### Task 4: Launch Integration and Dialog Focus

- [ ] Add a failing static contract test proving `launch.py` uses the splash runner for frozen application setup and retains `multiprocessing.freeze_support()` and worker routing.
- [ ] Modify `launch.py` so source launches preserve their current direct behavior while frozen setup runs through `run_with_initialization_splash()`.
- [ ] Add dialog hooks to the setup services so the splash hides before native modal dialogs and resumes only when another long task follows a confirmation.
- [ ] Run the focused launch and machine-setup tests and verify success, failure, cancellation, CPU-only, CUDA-ready, and pending-restart results.

### Task 5: Packaging Contract

- [ ] Add assertions to `tests/test_packaging_contracts.py` requiring `('neural_starlight_startup.gif', '.')` and forbidding `('neural_starlight.gif', '.')`.
- [ ] Modify `NewLight_Analysis.spec` to package only the optimized startup GIF.
- [ ] Run `python -m pytest tests/test_packaging_contracts.py -q` and verify all contracts pass.

### Task 6: Documentation and Verification

- [ ] Record the startup lifecycle, optimized asset, source/frozen distinction, and packaging rule in `PROJECT_HANDOFF.md` and `WORK_LOG.md`.
- [ ] Run `python -m py_compile launch.py machine_setup.py initialization_splash.py`.
- [ ] Run the focused splash, setup, and packaging tests, then the established split project test suites.
- [ ] Run `git diff --check` and inspect only task-related diffs.
- [ ] Build with `cmd /c build_exe.bat /nopause`, run `dist\NewLight_Analysis\check_backends.bat /verify-only`, and confirm the release root still excludes `setup_caiman_latest.bat` and `run_NewLight_Analysis.bat`.
- [ ] Launch the frozen executable with a clean test state on a non-production test path, confirm the animated splash appears during delayed checks, and verify it closes before the main window or any modal failure dialog.
