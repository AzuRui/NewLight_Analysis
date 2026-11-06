r"""Tracked build-input guards for CPU fast ROI.

`NewLight_Analysis.spec` is git-ignored, so the pieces of the CPU fast-ROI build that
must survive a fresh clone live here: the environment recipe, the staging script, the
build pre-flight, and the packaged release gate.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD_BAT = ROOT / "build_cpu_exe.bat"
FULL_BAT = ROOT / "build_full_exe.bat"
SETUP_BAT = ROOT / "setup_newlight_caiman.bat"
CHECK_BAT = ROOT / "check_backends.bat"
ENV_YML = ROOT / "environment-newlight-caiman.yml"
EXTRAS_TXT = ROOT / "requirements-build-extras.txt"
STAGER = ROOT / "tools" / "stage_neusuite_cpu_source.ps1"


def test_build_script_checks_the_new_dependencies_and_stages_the_model():
    text = BUILD_BAT.read_text(encoding="utf-8")

    for name in ("timm", "torchvision", "torch"):
        assert f"'{name}'" in text, f"{name} is missing from the build dependency pre-flight"
    assert "stage_neusuite_cpu_source.ps1" in text
    preflight = text.index("MISSING build dependencies")
    clean = text.index("if exist build rmdir")
    assert preflight < clean, "the model must be staged before dist is deleted"


def test_build_environment_declares_the_cpu_torch_pair():
    yml = ENV_YML.read_text(encoding="utf-8")

    assert "pytorch=*=cpu*" in yml
    assert "torchvision=*=cpu*" in yml, "torchvision must be pinned to the same CPU build family"
    extras = EXTRAS_TXT.read_text(encoding="utf-8")
    assert "timm==" in extras
    setup = SETUP_BAT.read_text(encoding="utf-8")
    assert "--no-deps -r requirements-build-extras.txt" in setup, (
        "timm must not pull a pip torch into the conda CPU environment"
    )
    assert "assert not torch.version.cuda" in setup


def test_stager_reads_the_addon_archive_and_verifies_the_result():
    text = STAGER.read_text(encoding="utf-8")

    assert "GPU_Addon_CUDA.zip" in text
    assert "Join-Path $RepoRoot 'GPU_Addon_CUDA.zip'" in text
    assert "ProgramData" in text, "the download cache is the fallback source"
    assert "segment_model.pt" in text and "method\\ultralytics" in text


def test_release_gate_checks_the_cpu_roi_path_and_offers_the_addon_install():
    text = CHECK_BAT.read_text(encoding="utf-8")

    assert "NeuSuite fast ROI CPU backend" in text
    assert "device='cpu'" in text, "the gate must exercise the CPU backend, not only --help"
    assert "run_fast_roi_segmentation" in text
    # Every variable used inside the parenthesised block has to be expanded lazily.
    block = text[text.index("NeuSuite fast ROI CPU backend") :]
    assert "set \"ROI_CPU_DIR=!TEMP!" in block
    assert "%ROI_CPU_DIR%" not in block
    assert "/update-gpu" in block, "a machine without any ROI backend must be told how to install the addon"


def test_full_build_patches_the_addon_opencv_loader():
    """The unified addon is frozen elsewhere, so its cv2 configs need the same patch step.

    Without this line a full build ships configs naming the machine that froze the addon;
    OpenCV's loader then re-imports cv2 and every GPU worker dies with
    "recursion is detected during loading of cv2 binary extensions" (2026-11-06 report).
    """
    if not FULL_BAT.is_file():
        pytest.skip("build_full_exe.bat is ignored by git and only exists on build machines")
    text = FULL_BAT.read_text(encoding="utf-8")

    addon_target = r'"%FULL_ROOT%\_internal\GPU_Addon"'
    assert "PATCH_PY" in text, "the patch step needs the same interpreter resolution as the build"
    assert f"tools\\patch_frozen_cv2.py {addon_target}" in text, (
        "the addon directory, not the core dist, is what needs patching here"
    )
    patch_line = text.index("tools\\patch_frozen_cv2.py")
    verify_line = text.index("Verifying complete portable backends")
    assert patch_line < verify_line, "patch before the gate, or the gate tests a broken loader"
    gate = text[patch_line:verify_line]
    assert "if errorlevel 1" in gate and ":BUILD_FAILED" in gate, (
        "a failed patch must stop the build instead of shipping the leak"
    )
