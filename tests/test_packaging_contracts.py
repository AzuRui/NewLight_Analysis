from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def test_pyinstaller_spec_collects_neusuite_timm_compatibility_modules():
    literals = _string_literals(ROOT / "NewLight_Analysis.spec")

    assert "timm.models.layers" in literals
    assert "timm.models.helpers" in literals
    assert "timm.models.registry" in literals


def test_backend_check_imports_the_real_neusuite_runtime():
    script = (ROOT / "check_backends.bat").read_text(encoding="utf-8")

    assert "import_neusuite_yolo" in script
    assert "NeuSuite runtime import OK" in script
    assert 'set "FAILED=1"' in script
    assert "exit /b %FAILED%" in script


def test_portable_build_runs_the_frozen_backend_check():
    script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")

    assert 'call "dist\\NewLight_Analysis\\check_backends.bat" /verify-only' in script
    assert "Frozen backend verification failed." in script


def test_frozen_entrypoint_enables_multiprocessing_freeze_support():
    entrypoint = (ROOT / "launch.py").read_text(encoding="utf-8")

    assert "multiprocessing.freeze_support()" in entrypoint


def test_frozen_gui_entrypoint_runs_machine_setup_gate():
    entrypoint = (ROOT / "launch.py").read_text(encoding="utf-8")

    assert "ensure_application_setup" in entrypoint
    assert "run_with_initialization_splash" in entrypoint
    assert "machine_setup.setup_is_complete" in entrypoint


def test_backend_script_separates_verification_from_driver_installation():
    script = (ROOT / "check_backends.bat").read_text(encoding="utf-8")

    assert 'if /I "%~1"=="/install-gpu-driver"' in script
    assert 'if /I "%~1"=="/verify-only"' in script
    assert "install_nvidia_driver.ps1" in script
    assert "goto :VERIFY_BACKENDS" in script
    assert 'if "%~1"=="" goto :SETUP_MACHINE' in script
    assert "ensure_first_run_setup" in script


def test_full_release_also_runs_verification_only_gate():
    script = (ROOT / "build_full_release.bat").read_text(encoding="utf-8")

    assert 'call "build_release\\NewLight_Analysis\\check_backends.bat" /verify-only' in script


def test_combined_build_entrypoint_prepares_environment_before_building():
    script = (ROOT / "build_portable_exe.bat").read_text(encoding="utf-8")

    assert "setup_build_environment.bat /nopause" in script
    assert "call build_exe.bat /nopause" in script


def test_build_environment_script_preserves_existing_cuda_environment():
    script = (ROOT / "setup_build_environment.bat").read_text(encoding="utf-8")

    assert "caiman_latest" in script
    assert "environment-build.yml" in script
    assert "CUDA packages will not be replaced" in script
    assert "pyinstaller" in script.lower()


def test_build_readme_documents_both_entrypoints_and_cuda_limit():
    readme = (ROOT / "BUILD_README.md").read_text(encoding="utf-8")

    assert "setup_build_environment.bat" in readme
    assert "build_portable_exe.bat" in readme
    assert "DeepCAD-RT" in readme
    assert "2 GiB" in readme


def test_release_builds_never_publish_legacy_setup_or_batch_launcher():
    portable = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
    full = (ROOT / "build_full_release.bat").read_text(encoding="utf-8")

    for script in (portable, full):
        assert "setup_caiman_latest.bat" not in script
        assert "run_NewLight_Analysis.bat" not in script


def test_nvidia_driver_installer_uses_applicable_windows_update_driver_only():
    script = (ROOT / "tools" / "install_nvidia_driver.ps1").read_text(encoding="utf-8")

    assert "Windows Update Agent" in script
    assert "Microsoft.Update.Session" in script
    assert "IsInstalled=0 and Type='Driver'" in script
    assert "NVIDIA" in script
    assert "DriverClass" in script
    assert "AcceptEula" in script
    assert "Download()" in script
    assert "Install()" in script
    assert "WindowsPrincipal" in script


def test_pyinstaller_bundles_machine_setup_and_driver_installer():
    spec = (ROOT / "NewLight_Analysis.spec").read_text(encoding="utf-8")

    assert "machine_setup.py" in spec
    assert "tools/install_nvidia_driver.ps1" in spec.replace("\\", "/")


def test_pyinstaller_bundles_only_optimized_initialization_gif():
    spec = (ROOT / "NewLight_Analysis.spec").read_text(encoding="utf-8")

    assert "('neural_starlight_startup.gif', '.')" in spec
    assert "('neural_starlight.gif', '.')" not in spec
