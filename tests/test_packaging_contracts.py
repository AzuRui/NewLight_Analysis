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
    literals = _string_literals(ROOT / "NewLight_GPU_Worker.spec")

    assert "timm.models.layers" in literals
    assert "timm.models.helpers" in literals
    assert "timm.models.registry" in literals


def test_backend_check_imports_the_real_neusuite_runtime():
    script = (ROOT / "check_backends.bat").read_text(encoding="utf-8")

    assert "GPU_WORKER" in script
    assert "run_neusuite_roi.py" in script
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


def test_pyinstaller_spec_excludes_unused_desktop_and_notebook_stacks():
    spec = (ROOT / "NewLight_Analysis.spec").read_text(encoding="utf-8")

    assert "slim_excludes" in spec
    for package in ("jupyterlab", "notebook", "panel", "bokeh", "PySide6", "openvino", "hdmf", "pynwb"):
        assert f"'{package}'" in spec


def test_slim2_inno_script_targets_experimental_package_with_high_ratio_compression():
    script = (ROOT / "NewLight_Analysis_slim2_setup.iss").read_text(encoding="utf-8")
    builder = (ROOT / "build_slim2_installer.bat").read_text(encoding="utf-8")

    assert "dist_slim2_20260804\\NewLight_Analysis" in script
    assert "Compression=lzma2/ultra64" in script
    assert "SolidCompression=yes" in script
    assert "LZMAUseSeparateProcess=yes" in script
    assert "build_slim2_installer.bat" not in builder
    assert "NewLight_Analysis_slim2_setup.iss" in builder


def test_core_spec_keeps_deepcad_out_of_the_core_datas_bundle():
    spec = (ROOT / "NewLight_Analysis.spec").read_text(encoding="utf-8")

    assert "gpu_addon_manifest.json" in spec
    assert "DeepCADRT_Model" not in spec.split("datas =", 1)[1].split("ipyparallel_spec", 1)[0]
    assert "DeepCAD_RT_pytorch" not in spec.split("datas =", 1)[1].split("ipyparallel_spec", 1)[0]
    assert "optional runtime addon" in spec


def test_deepcad_addon_builder_does_not_duplicate_shared_cuda_runtime():
    script = (ROOT / "build_deepcad_addon.bat").read_text(encoding="utf-8")

    gpu_script = (ROOT / "build_gpu_addon.bat").read_text(encoding="utf-8")

    assert "build_gpu_addon.bat" in script
    assert "NewLight_GPU_Worker.spec" in gpu_script
    assert "GPU_Addon_CUDA.zip.part" in gpu_script


def test_deepcad_manifest_has_pinned_release_hash():
    manifest = (ROOT / "gpu_addon_manifest.json").read_text(encoding="utf-8")

    assert "REPLACE_WITH_RELEASE_ASSET_SHA256" not in manifest
    assert "GPU_Addon_CUDA.zip.part01" in manifest
    assert "NeuSuite" in manifest
    assert "archive_sha256" in manifest


def test_core_build_excludes_torch_and_does_not_collect_cuda_binaries():
    build = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
    spec = (ROOT / "NewLight_Analysis.spec").read_text(encoding="utf-8")

    assert "caiman_latest" in build
    assert "NEWLIGHT_BUILD_MODE=cpu" in build
    assert "if build_mode == 'gpu'" in spec
    for package in ("torch", "torchvision", "timm"):
        assert f"'{package}'" in spec


def test_gpu_worker_has_a_separate_pyinstaller_spec():
    spec = (ROOT / "NewLight_GPU_Worker.spec").read_text(encoding="utf-8")
    builder = (ROOT / "build_gpu_addon.bat").read_text(encoding="utf-8")

    assert "NewLight_GPU_Worker" in spec
    assert "torch_cuda.dll" in spec
    assert "NewLight_GPU_Worker.spec" in builder
