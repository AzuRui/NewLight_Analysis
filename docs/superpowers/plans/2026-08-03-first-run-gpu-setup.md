# First-Run GPU Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-time elevated machine initialization that validates the portable backend, automatically installs an applicable NVIDIA display driver through Windows Update when approved, and records CPU-only capability on AMD/Intel machines.

**Architecture:** A testable Python state machine owns privilege, state, hardware classification, dialogs, and restart decisions. A narrowly scoped PowerShell script owns Windows Update COM operations, while `check_backends.bat` exposes verification and explicit driver-install modes without changing build behavior.

**Tech Stack:** Python 3.11, Tkinter dialogs, Windows ctypes/CIM, PowerShell 5.1 Windows Update Agent COM API, batch launchers, PyInstaller, pytest.

---

### Task 1: Machine Setup State Machine

**Files:**
- Create: `machine_setup.py`
- Create: `tests/test_machine_setup.py`

- [x] Write failing tests for versioned state paths, completed-state bypass,
  non-admin exit, NVIDIA CUDA success, NVIDIA install consent, restart choice,
  AMD/Intel CPU-only completion, and failed backend/driver checks.
- [x] Run `python -m pytest tests/test_machine_setup.py -q` and verify failures
  are caused by the missing module and behavior.
- [x] Implement atomic ProgramData JSON state, administrator detection, CIM
  adapter detection, bundled CUDA validation, backend command execution,
  dialogs, and explicit restart invocation.
- [x] Re-run the focused test module and require all cases to pass without
  executing real PowerShell installation or shutdown commands.

### Task 2: Explicit Windows Update Driver Installer

**Files:**
- Create: `tools/install_nvidia_driver.ps1`
- Modify: `check_backends.bat`
- Modify: `tests/test_packaging_contracts.py`

- [x] Write failing static contract tests requiring `/verify-only` and
  `/install-gpu-driver`, administrator enforcement, Windows Update search,
  NVIDIA display filtering, EULA acceptance, download/install result checks,
  and no installer call in default verification flow.
- [x] Implement the PowerShell script with applicable-driver filtering,
  ProgramData logging, deterministic exit codes, and captured diagnostics.
- [x] Add the explicit batch mode before normal backend verification. Preserve
  the existing nonzero aggregate behavior for all backend failures.
- [x] Run packaging contract tests and inspect scripts with PowerShell's parser.

### Task 3: Frozen Startup and Packaging Integration

**Files:**
- Modify: `launch.py`
- Modify: `NewLight_Analysis.spec`
- Modify: `build_exe.bat`
- Modify: `tests/test_packaging_contracts.py`

- [x] Write failing contracts proving source launches bypass setup, frozen GUI
  launches call the setup gate, the PowerShell script is bundled, and build
  verification uses `/verify-only`.
- [x] Integrate the gate after frozen Worker dispatch and before GUI imports.
- [x] Bundle the installer under `_internal\tools` and copy the updated batch
  helper to the release root.
- [x] Run focused startup/packaging tests and Python compilation.

### Task 4: Validation and Records

**Files:**
- Modify: `WORK_LOG.md`
- Modify: `PROJECT_HANDOFF.md`

- [x] Run the relevant pytest modules and `git diff --check`.
- [x] Read `example\twophone.avi` through the application movie loader or a
  frozen Worker smoke without modifying the source file.
- [x] Build the portable release and require the verification-only backend gate
  to pass; do not invoke the live driver-install mode on the development host.
- [x] Verify release files, frozen setup imports, and simulated first-run
  branches, then record exact commands/results and the retained-sample rule.
