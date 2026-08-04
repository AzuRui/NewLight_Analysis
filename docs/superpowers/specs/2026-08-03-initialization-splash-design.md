# NewLight Analysis Initialization Splash Design

## Goal

Show immediate, continuous visual feedback while the frozen application performs its first-run backend, display-adapter, CUDA, and optional driver checks. Users must not mistake the hidden checks for a failed launch.

## Visual Design

- Use `neural_starlight_startup.gif` as a 720 x 480 animated background. It is a startup-optimized derivative of the original 3072 x 2048 GIF and keeps the five-second loop while reducing the packaged asset from about 95.8 MB to about 3.67 MB.
- Center the product identity: the existing software logo, `NewLight Analysis`, and the subtitle `神经影像分析平台`.
- Use one bottom row divided into three equal regions: application version on the left, current initialization status in the center, and a loading animation on the right.
- Build the loading animation from eight gray-white circular dots. The dots enlarge and fade in sequence around the ring, matching the supplied bubble-loading reference instead of rotating a dashed outline.
- Do not show a company logo or company name.
- Keep the splash undecorated and non-interactive. Existing confirmation, error, administrator, and restart dialogs remain ordinary modal dialogs.

## Runtime Design

- Create a small Tk splash controller owned by `launch.py` before frozen machine setup begins.
- Run `machine_setup.ensure_application_setup()` on a worker thread so Tk can continue advancing the GIF and rotating the dashed ring.
- Extend the setup service boundary with an optional progress callback. Emit stable user-facing stages before backend verification, adapter detection, CUDA verification, and driver installation.
- Marshal progress updates back to the Tk event loop. Do not update Tk widgets directly from the worker thread.
- Close the splash before displaying any modal question or error so dialogs are visible and receive focus. Restore or recreate the splash when a long operation continues after a confirmation.
- Always destroy the splash in a `finally` path on success, failure, cancellation, exception, or restart request.
- Source launches continue to bypass first-run machine setup and therefore do not show this initialization splash.

## Packaging

- Bundle only `neural_starlight_startup.gif`; the 95.8 MB source GIF remains a development asset and is not added to the portable release.
- Reuse the existing `xhr.ico` product logo.
- Preserve the existing packaging contracts: worker placement, hidden imports, `/verify-only` build validation, and exclusion of legacy launch/setup BAT files from the release root.

## Error Handling

- If the GIF or logo cannot be loaded, show a dark static splash with the same title, spinner, and status text.
- If Tk cannot create the splash, continue through the existing setup flow instead of preventing application startup.
- Unexpected setup exceptions close the splash and produce a visible initialization error.

## Verification

- Unit-test setup progress emission without requiring a real GPU, administrator token, driver installation, or reboot.
- Test splash lifecycle behavior with fake setup services: success, backend failure, CPU-only completion, cancelled driver installation, and exception.
- Verify the optimized GIF dimensions, frame count, loop duration, and packaging entry.
- Run the existing machine-setup and packaging-contract suites, Python compilation, and `git diff --check`.
- Perform a frozen smoke test that confirms the splash appears while a deliberately delayed fake check runs and disappears when it completes.
