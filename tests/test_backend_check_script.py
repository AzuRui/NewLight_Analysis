r"""Guard rails for the packaged release gate `check_backends.bat`.

The gate runs the frozen workers the same way the installed application does, so the
paths and exit-code handling in the batch file are load bearing:

* `worker_launcher.py` resolves a *relative* script argument against `sys._MEIPASS`,
  which for the released flat GPU addon is the `GPU_Addon` folder itself.  Passing
  `GPU_Addon\workers\run_neusuite_roi.py` therefore looks for
  `GPU_Addon\GPU_Addon\workers\...` and falls back to the current directory, which in
  an installed package is the application root (the addon lives in `_internal`), so the
  check aborts with "Worker script not found" even on a healthy addon.
* A PyInstaller worker that cannot start its embedded interpreter exits with `-1`.
  `if errorlevel 1` is false for `-1`, so success must be tested as an exact zero.
"""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "check_backends.bat"
CORE = ROOT / "analysis_core.py"


def batch_text() -> str:
    return BATCH.read_text(encoding="utf-8")


def core_text() -> str:
    return CORE.read_text(encoding="utf-8")


def test_fast_roi_gpu_check_uses_absolute_addon_script_path():
    text = batch_text()

    assert 'set "GPU_ROI_SCRIPT=%RESOURCE_DIR%\\GPU_Addon\\workers\\run_neusuite_roi.py"' in text
    assert '"%GPU_WORKER%" "%GPU_ROI_SCRIPT%" --help' in text


def test_gpu_worker_is_never_handed_a_relative_addon_script():
    # A relative argument is resolved against the addon folder (sys._MEIPASS) and then
    # against the current directory; neither matches an installed package layout.
    for invocation in re.findall(r'"%GPU_WORKER%"\s+"([^"]+)"', batch_text()):
        assert invocation.startswith(("%GPU_ROI_SCRIPT%", "%RESOURCE_DIR%")), invocation


def test_addon_script_absence_reports_its_own_diagnostic():
    text = batch_text()

    assert 'if not exist "%GPU_ROI_SCRIPT%"' in text
    assert "GPU addon is out of date" in text


def test_backend_checks_require_an_exact_zero_exit_code():
    text = batch_text()

    assert "if errorlevel 1" not in text
    for variable in (
        "CORE_CHECK_RESULT",
        "ROI_CHECK_RESULT",
        "CAIMAN_CHECK_RESULT",
        "CAIMAN_ROI_RESULT",
        "DEEPCAD_CHECK_RESULT",
    ):
        assert f'set "{variable}=!ERRORLEVEL!"' in text, variable
        assert f'if not "!{variable}!"=="0"' in text, variable


def test_fast_roi_path_matches_frozen_dispatch():
    # The gate must exercise the same script the frozen application dispatches to.
    assert 'GPU_ADDON_DIR / "workers" / "run_neusuite_roi.py"' in core_text()


def test_setup_branch_streams_progress_to_the_console():
    # A silent 2.5 GB download looks like a hang; the setup branch has to forward every
    # machine_setup progress message to stdout as it happens.
    text = batch_text()

    assert "from machine_setup import ensure_first_run_setup" in text
    assert "progress=lambda" in text
    assert "flush=True" in text
    # Chinese stage text must not kill the run on a console that cannot encode it.
    assert "reconfigure" in text


def test_update_gpu_branch_reports_the_reason_for_a_failed_install():
    text = batch_text()

    assert 'if /I "%~1"=="/update-gpu" goto :UPDATE_GPU' in text
    assert ":UPDATE_GPU" in text
    assert "from machine_setup import ensure_gpu_addon" in text
    assert "[GPU] installed" in text
    assert "[GPU] message" in text
    assert "addon target directory" in text


def test_verify_branch_prints_the_paths_and_timings_it_checks():
    text = batch_text()

    assert "Paths checked by this script" in text
    assert "  GPU addon worker     : %GPU_WORKER%" in text
    assert "  GPU ROI script       : %GPU_ROI_SCRIPT%" in text
    assert "start !TIME!" in text
    assert "Verification exit code" in text


def test_interpreter_resolution_lives_in_one_subroutine():
    text = batch_text()

    assert text.count("conda run -n caiman_latest") == 1
    assert text.count("call :RESOLVE_PY") == 3


def test_unknown_option_exits_nonzero_while_help_exits_zero():
    # A mistyped option must never look like a passed check, but /help is a normal exit.
    text = batch_text()

    assert 'if /I "%~1"=="/help" goto :USAGE' in text
    assert 'set "OPTION_EXIT=64"' in text
    assert 'endlocal & exit /b %OPTION_EXIT%' in text
    # The unknown-option path is the only place that sets the failing code.
    assert text.count('set "OPTION_EXIT=') == 2
    assert "exit /b 64" not in text


def test_setup_branch_keeps_the_console_and_log_claims_separate():
    text = batch_text()

    assert "Every stage is printed below as it runs" in text
    # This run forwards progress to stdout, so it must not claim the machine log holds it.
    assert "The application logs its own setup stages to" in text
    assert "Progress is also appended to" not in text
