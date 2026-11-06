"""Guards for the assets that have to end up inside the published package.

The user manual shipped next to ``NewLight_Analysis.exe`` used to be committed
under ``dist/``, and the CPU build script deletes ``dist`` before PyInstaller
runs.  Every rebuild therefore removed the manual from the tree, and a package
built without restoring it by hand simply had no manual.  The asset now lives in
``Release_Assets`` and the build script copies it into ``dist``; these tests keep
both halves of that arrangement honest.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
MANUAL_ASSET = REPOSITORY_ROOT / "Release_Assets" / "NewLight_Analysis_User_Manual.pdf"
CPU_BUILD_SCRIPT = REPOSITORY_ROOT / "build_cpu_exe.bat"
CPU_INSTALLER_SCRIPT = REPOSITORY_ROOT / "build_cpu_installer.bat"
BUILD_ENVIRONMENT_SPEC = REPOSITORY_ROOT / "environment-newlight-caiman.yml"


def test_packaged_manual_is_tracked_outside_the_build_output() -> None:
    assert MANUAL_ASSET.is_file(), f"{MANUAL_ASSET} must stay committed; it is packaged into every build"
    assert MANUAL_ASSET.read_bytes().startswith(b"%PDF-")
    # A truncated manual has shipped before; a real one is well past a few kilobytes.
    assert MANUAL_ASSET.stat().st_size > 100_000


def test_no_release_asset_is_committed_inside_dist() -> None:
    """``dist`` is removed on every rebuild, so nothing may be tracked there."""
    if not (REPOSITORY_ROOT / ".git").exists():
        pytest.skip("source distribution without a git checkout")
    listing = subprocess.run(
        ["git", "ls-files", "dist"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert listing.stdout.strip() == "", "tracked files under dist/ are deleted by build_cpu_exe.bat"


@pytest.mark.skipif(not CPU_BUILD_SCRIPT.is_file(), reason="local build scripts are not published")
def test_build_script_copies_the_manual_and_refuses_to_lose_it() -> None:
    text = CPU_BUILD_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    assert r"Release_Assets\NewLight_Analysis_User_Manual.pdf" in text
    assert r"dist\NewLight_Analysis\NewLight_Analysis_User_Manual.pdf" in text
    assert text.lower().count("if not exist") >= 3, "each copy step must be checked before packaging continues"

    installer = CPU_INSTALLER_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    assert r"dist\NewLight_Analysis\NewLight_Analysis_User_Manual.pdf" in installer, (
        "the installer step must fail loudly when dist has no manual"
    )


@pytest.mark.skipif(not CPU_INSTALLER_SCRIPT.is_file(), reason="local build scripts are not published")
def test_cpu_installer_refuses_to_pack_the_gpu_addon() -> None:
    """Inno Setup copies everything under ``dist``, addon included.

    ``check_backends.bat /update-gpu`` puts a ~3.7 GB ``_internal\\GPU_Addon`` into the
    portable tree while a build is being verified.  Packing it would turn the CPU core
    setup program from a few hundred megabytes into a multi-gigabyte download, so the
    installer step has to stop instead of shipping it.
    """
    text = CPU_INSTALLER_SCRIPT.read_text(encoding="utf-8", errors="ignore")

    guard = text.index(r'if exist "dist\NewLight_Analysis\_internal\GPU_Addon"')
    compile_step = text.index("%ISCC%")
    assert guard < compile_step, "the addon guard must run before Inno Setup is invoked"
    section = text[guard:compile_step]
    assert "goto :FAILED" in section, "the addon guard must stop the installer, not just warn"
    assert "GPU addon" in section, "the failure message must name what has to be removed"


def test_excel_dependency_is_declared_for_the_build_environment() -> None:
    """``openpyxl`` is not a pandas dependency, so nothing else pulls it into the env.

    PyInstaller reports a hidden import it cannot find only in its warning file, so a
    build environment without it ships an exe whose Excel export fails on the user's
    machine; the published v1.0.1 package did exactly that.
    """
    text = BUILD_ENVIRONMENT_SPEC.read_text(encoding="utf-8")

    assert re.search(r"^\s*-\s*openpyxl\b", text, re.MULTILINE), (
        "environment-newlight-caiman.yml must install openpyxl for the packaging build"
    )


@pytest.mark.skipif(not CPU_BUILD_SCRIPT.is_file(), reason="local build scripts are not published")
def test_build_script_preflights_every_required_runtime_module() -> None:
    import launch

    text = CPU_BUILD_SCRIPT.read_text(encoding="utf-8", errors="ignore")

    for name in launch.REQUIRED:
        assert f"'{name}'" in text, f"{name} is required at runtime but never preflighted"
    assert "MISSING build dependencies" in text, "the preflight must name what is absent"
