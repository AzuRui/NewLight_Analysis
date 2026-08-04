# First-Run GPU Setup Design

## Scope

The portable frozen application performs one machine initialization before its
first normal launch. Source launches remain developer-oriented and do not
require elevation. Remote control, licensing, expiry enforcement, and remote
permission changes are explicitly outside this implementation.

## Security and Privilege Boundary

- A missing or incomplete machine setup record requires an administrator
  launch. A non-administrator sees a blocking explanation and the application
  exits without self-elevating.
- A completed machine record allows future ordinary launches without UAC.
- Driver installation is reachable only through the explicit
  `check_backends.bat /install-gpu-driver` mode. Build-time and ordinary
  backend checks never install drivers or restart Windows.
- The machine record lives at
  `%ProgramData%\NewLight_Analysis\machine_setup_v1.json`. It records setup
  version and capability state, not authorization, remote-control credentials,
  user identity, or usage limits.

## Initialization Flow

1. The frozen GUI reads the versioned machine record before checking elevation.
2. If setup is complete, the GUI starts normally.
3. If setup is incomplete and the process is not elevated, a dialog requires
   the user to restart the EXE with **Run as administrator**, then exits.
4. An elevated first run executes `check_backends.bat /verify-only`. Missing
   bundled code, models, or native dependencies block initialization and show
   the captured diagnostic output.
5. Windows display adapters are queried through CIM. If any adapter is NVIDIA,
   the machine follows the NVIDIA path even when Intel or AMD integrated
   graphics are also present.
6. NVIDIA path:
   - If bundled PyTorch can already use CUDA, record `complete_cuda` and start.
   - Otherwise ask whether to automatically complete the GPU environment.
   - Confirmation invokes Windows Update through
     `check_backends.bat /install-gpu-driver`.
   - Only applicable, signed NVIDIA display-driver updates returned for the
     current machine are downloaded and installed. The full CUDA Toolkit is
     not installed because the portable release bundles CUDA/cuDNN runtime
     libraries.
   - A successful installation records `pending_restart`, asks whether to
     restart immediately, and exits. There is no countdown. Declining leaves
     Windows running; the next launch requires administrator validation again.
7. Non-NVIDIA path:
   - Record `complete_cpu_only`.
   - Warn that CUDA-only functions, especially DeepCAD-RT denoising, are
     unavailable. CPU-capable workflows remain available.
   - Start the application after the user dismisses the warning.

## Failure Handling

- Windows Update disabled, no network, no matching NVIDIA display update,
  download/install failure, or a still-unusable CUDA runtime does not create a
  completed record.
- Diagnostics are written under `%ProgramData%\NewLight_Analysis\logs` and
  summarized in the blocking dialog.
- A `pending_restart` record is never treated as complete. After reboot, an
  elevated launch re-runs verification and only writes `complete_cuda` when
  PyTorch reports CUDA available.
- Automated tests mock Windows Update and restart operations. Tests must never
  install a real driver or restart the test host.

## Packaging and Validation

- PyInstaller bundles `machine_setup.py` and the PowerShell driver installer.
- `build_exe.bat` continues calling verification-only backend checks.
- Retained movie smoke tests use the read-only file
  `example\twophone.avi`. Test cleanup may remove only generated temporary
  outputs, never this sample or the `example` directory.

