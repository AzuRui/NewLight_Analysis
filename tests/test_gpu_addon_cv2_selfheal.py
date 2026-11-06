r"""The GPU extension must repair its own OpenCV loader instead of failing every worker.

Reproduced 2026-11-06 on an installed copy: 快速 ROI died before reading a frame with

    ImportError: ERROR: recursion is detected during loading of "cv2" binary extensions.

The published ``GPU_Addon`` was frozen from ``D:/anaconda3/envs/caiman_latest`` without the
build script's cv2 patch step, so ``GPU_Addon/cv2/config.py`` and ``config-3.11.py`` still
name build-machine directories.  OpenCV's loader inserts those directories into ``sys.path``,
finds nothing, pops ``cv2`` from ``sys.modules``, re-imports the on-disk package, and the
recursion guard fires.  The addon does ship ``cv2/python-3.11/cv2.cp311-win_amd64.pyd`` and
``opencv_core4130.dll`` next to ``cv2/``; they are simply never consulted.

The core package cannot be affected the same way because ``build_cpu_exe.bat`` patches its
tree, so the durable fix lives on the addon side: ``tools/patch_frozen_cv2.py`` grew an
idempotent, non-raising runtime entry point, ``machine_setup`` calls it for an installed
addon, and ``analysis_core`` calls it again immediately before an addon worker is launched.
Repairing two small text files beats asking users to re-download a 2.4 GB addon.

These guards cover the parts that would silently regress:

* a repair that rewrites on every launch (must stay idempotent and silent when clean);
* a repair that raises when the addon directory is read-only (must never fail a task);
* the rewritten path actually resolving to the bundled extension and DLLs;
* the call sites, which are the only reason an already-installed broken addon gets fixed;
* the download manifest, which is what pins a freshly installed addon to the portable archive.
"""

import hashlib
import json
import os
import re
import runpy
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest

import analysis_core as core
import machine_setup


ROOT = Path(__file__).resolve().parents[1]
PATCHER_TOOL = ROOT / "tools" / "patch_frozen_cv2.py"
PATCHER_AVAILABLE = PATCHER_TOOL.is_file()

# tools/patch_frozen_cv2.py is git-ignored (.gitignore: "local release tools are not
# published"), so only the tests that read the tool itself are build-machine tests.  The
# wiring around it - machine_setup, analysis_core, the archive install step - is tracked
# code and runs everywhere against the stand-in below, which honours the same contract.
needs_patcher_tool = pytest.mark.skipif(
    not PATCHER_AVAILABLE,
    reason="tools/patch_frozen_cv2.py is ignored by git and only exists on build machines",
)

STUB_PATCHER = r'''"""Stand-in for the git-ignored tools/patch_frozen_cv2.py, same contract."""
import re
from pathlib import Path

LEAKED_PATH_PATTERN = re.compile(r"[A-Za-z]:[\\/]")
PORTABLE = "import os\n\nLOADER_DIR = os.path.dirname(os.path.abspath(__file__))\n"


def _locate(target):
    for candidate in (Path(target) / "_internal" / "cv2", Path(target) / "cv2", Path(target)):
        if (candidate / "__init__.py").is_file() and (candidate / "load_config_py3.py").is_file():
            return candidate
    return None


def ensure_portable_cv2_config(target):
    cv2_dir = _locate(target)
    if cv2_dir is None:
        return {"status": "not_installed", "cv2_dir": "", "patched": [], "reason": "no cv2 package"}
    if not list(cv2_dir.glob("python-*/cv2*.pyd")):
        return {"status": "no_extension", "cv2_dir": str(cv2_dir), "patched": [], "reason": "no pyd"}
    try:
        leaked = [
            path
            for path in sorted(cv2_dir.glob("config*.py"))
            if LEAKED_PATH_PATTERN.search(path.read_text(encoding="utf-8", errors="replace"))
        ]
        if not leaked:
            return {"status": "clean", "cv2_dir": str(cv2_dir), "patched": [], "reason": "portable"}
        for path in leaked:
            path.write_text(PORTABLE, encoding="utf-8", newline="\n")
    except OSError as exc:
        return {"status": "error", "cv2_dir": str(cv2_dir), "patched": [], "reason": str(exc)}
    return {
        "status": "repaired",
        "cv2_dir": str(cv2_dir),
        "patched": [str(path) for path in leaked],
        "reason": "rewrote leaked configs",
    }
'''


def patcher_source() -> str:
    """The real tool when this machine builds packages, otherwise the contract stand-in."""
    return PATCHER_TOOL.read_text(encoding="utf-8") if PATCHER_AVAILABLE else STUB_PATCHER

LEAKED_CONFIG_PY = (
    "import os\n"
    "\n"
    "BINARIES_PATHS = [\n"
    "    os.path.join('D:/anaconda3/envs/caiman_latest/Library', 'bin')\n"
    "] + BINARIES_PATHS\n"
)
LEAKED_VERSION_CONFIG = (
    "import os\n"
    "\n"
    "PYTHON_EXTENSIONS_PATHS = [\n"
    "    os.path.join('D:/anaconda3/envs/caiman_latest/Lib/site-packages/cv2', 'python-3.11')\n"
    "] + PYTHON_EXTENSIONS_PATHS\n"
)
LOADER_NAMES = ("config.py", "config-3.11.py")


def load_patcher() -> dict:
    """Load the tool the way the spec and machine_setup do: it is data, not a module."""
    return runpy.run_path(str(PATCHER_TOOL))


def make_cv2(directory: Path, *, leaked: bool = True, with_pyd: bool = True) -> Path:
    """Build a frozen cv2 loader package the way the published addon ships it."""
    (directory / "python-3.11").mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").write_text("# cv2 loader\n", encoding="utf-8")
    (directory / "load_config_py3.py").write_text("# loader\n", encoding="utf-8")
    if leaked:
        (directory / "config.py").write_text(LEAKED_CONFIG_PY, encoding="utf-8")
        (directory / "config-3.11.py").write_text(LEAKED_VERSION_CONFIG, encoding="utf-8")
    else:
        (directory / "config.py").write_text(
            "import os\n\nLOADER_DIR = os.path.dirname(os.path.abspath(__file__))\n\n"
            "BINARIES_PATHS = [os.path.dirname(LOADER_DIR), LOADER_DIR] + BINARIES_PATHS\n",
            encoding="utf-8",
        )
        (directory / "config-3.11.py").write_text(
            "import os\n\nLOADER_DIR = os.path.dirname(os.path.abspath(__file__))\n\n"
            'PYTHON_EXTENSIONS_PATHS = [os.path.join(LOADER_DIR, "python-3.11")]'
            " + PYTHON_EXTENSIONS_PATHS\n",
            encoding="utf-8",
        )
    if with_pyd:
        (directory / "python-3.11" / "cv2.cp311-win_amd64.pyd").write_bytes(b"MZ\x90\x00")
    return directory


def make_addon(root: Path, **kwargs) -> Path:
    """A GPU extension directory with its own cv2 package, like the real archive."""
    addon = root / "GPU_Addon"
    addon.mkdir(parents=True, exist_ok=True)
    (addon / "NewLight_GPU_Worker.exe").write_bytes(b"MZ")
    # The OpenCV DLLs sit next to cv2/ in the addon, exactly as the real zip has them.
    (addon / "opencv_core4130.dll").write_bytes(b"MZ\x90\x00")
    make_cv2(addon / "cv2", **kwargs)
    return addon


def make_bundle(root: Path, *, addon_kwargs: dict | None = None, ship_tool: bool = True) -> dict:
    """Fake an installed core package: ``_internal`` with the patcher tool, plus the addon."""
    resource_root = root / "_internal"
    resource_root.mkdir(parents=True, exist_ok=True)
    if ship_tool:
        tools = resource_root / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        (tools / "patch_frozen_cv2.py").write_text(patcher_source(), encoding="utf-8")
    addon_dir = make_addon(resource_root, **(addon_kwargs or {}))
    return {"resource_root": resource_root, "addon_dir": addon_dir}


def loader_paths(addon_dir: Path) -> list[Path]:
    return [addon_dir / "cv2" / name for name in LOADER_NAMES]


# --- tools/patch_frozen_cv2.py: the runtime entry point -----------------------


@needs_patcher_tool
def test_ensure_rewrites_leaked_configs_to_loader_relative_paths(tmp_path):
    bundle = make_bundle(tmp_path)
    patcher = load_patcher()

    result = patcher["ensure_portable_cv2_config"](bundle["addon_dir"])

    assert result["status"] == "repaired", result
    assert len(result["patched"]) == 2
    for path in loader_paths(bundle["addon_dir"]):
        text = path.read_text(encoding="utf-8")
        assert "LOADER_DIR" in text
        assert not patcher["LEAKED_PATH_PATTERN"].search(text), (
            f"{path.name} still names an absolute directory; that is what trips the guard"
        )


@needs_patcher_tool
def test_ensure_repairs_the_cv2_dir_the_addon_root_and_a_dist_root_alike(tmp_path):
    patcher = load_patcher()
    direct_parent = (tmp_path / "direct")
    make_cv2(direct_parent / "cv2")
    addon = make_addon(tmp_path / "addon")
    make_cv2(tmp_path / "dist" / "_internal" / "cv2")

    targets = [
        direct_parent,
        addon,
        tmp_path / "dist",
    ]
    for target in targets:
        assert patcher["ensure_portable_cv2_config"](target)["status"] == "repaired", target
    for cv2_dir in (
        direct_parent / "cv2",
        addon / "cv2",
        tmp_path / "dist" / "_internal" / "cv2",
    ):
        assert "LOADER_DIR" in (cv2_dir / "config.py").read_text(encoding="utf-8")


@needs_patcher_tool
def test_rewritten_loader_paths_resolve_to_the_bundled_extension_and_dlls(tmp_path):
    """What cv2's own loader does with these files, emulated on the rewritten text."""
    bundle = make_bundle(tmp_path)
    addon_dir = bundle["addon_dir"]
    load_patcher()["ensure_portable_cv2_config"](addon_dir)

    extensions = {"__file__": str(addon_dir / "cv2" / "config-3.11.py"), "PYTHON_EXTENSIONS_PATHS": []}
    exec(
        compile((addon_dir / "cv2" / "config-3.11.py").read_text(encoding="utf-8"), "config", "exec"),
        extensions,
    )
    binaries = {"__file__": str(addon_dir / "cv2" / "config.py"), "BINARIES_PATHS": []}
    exec(
        compile((addon_dir / "cv2" / "config.py").read_text(encoding="utf-8"), "config", "exec"),
        binaries,
    )

    extension_dir = Path(extensions["PYTHON_EXTENSIONS_PATHS"][0]).resolve()
    assert extension_dir == (addon_dir / "cv2" / "python-3.11").resolve()
    assert (extension_dir / "cv2.cp311-win_amd64.pyd").is_file()
    assert Path(binaries["BINARIES_PATHS"][0]).resolve() == addon_dir.resolve()
    assert (addon_dir / "opencv_core4130.dll").is_file()


@needs_patcher_tool
def test_ensure_is_idempotent_and_leaves_a_clean_tree_untouched(tmp_path):
    bundle = make_bundle(tmp_path)
    patcher = load_patcher()

    first = patcher["ensure_portable_cv2_config"](bundle["addon_dir"])
    contents = {path: path.read_bytes() for path in loader_paths(bundle["addon_dir"])}
    stamps = {path: path.stat().st_mtime_ns for path in loader_paths(bundle["addon_dir"])}

    second = patcher["ensure_portable_cv2_config"](bundle["addon_dir"])
    third = patcher["ensure_portable_cv2_config"](bundle["addon_dir"])

    assert first["status"] == "repaired"
    assert second["status"] == "clean", "a repaired addon must not be rewritten on every launch"
    assert third["status"] == "clean"
    for path, payload in contents.items():
        assert path.read_bytes() == payload
        assert path.stat().st_mtime_ns == stamps[path], "a clean run must not write"


@needs_patcher_tool
def test_ensure_reports_trees_it_cannot_fix_instead_of_raising(tmp_path):
    patcher = load_patcher()

    assert patcher["ensure_portable_cv2_config"](tmp_path)["status"] == "not_installed"
    without_pyd = make_addon(tmp_path / "a", with_pyd=False)
    assert patcher["ensure_portable_cv2_config"](without_pyd)["status"] == "no_extension"
    assert (without_pyd / "cv2" / "config.py").read_text(encoding="utf-8") == LEAKED_CONFIG_PY, (
        "without a bundled extension there is nothing portable to point at, so leave it alone"
    )


@needs_patcher_tool
def test_ensure_survives_a_read_only_addon(tmp_path):
    # Program Files installs are not writable without elevation, and the repair is a
    # convenience: it must never turn into a failed analysis task.
    bundle = make_bundle(tmp_path)
    configs = loader_paths(bundle["addon_dir"])
    for path in configs:
        os.chmod(path, stat.S_IREAD)
    try:
        result = load_patcher()["ensure_portable_cv2_config"](bundle["addon_dir"])
    finally:
        for path in configs:
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)

    assert result["status"] in {"unwritable", "error"}, result
    assert result["reason"]
    assert bundle["addon_dir"].joinpath("cv2/config.py").read_text(encoding="utf-8") == LEAKED_CONFIG_PY


@needs_patcher_tool
def test_build_time_entry_point_still_rewrites_and_raises(tmp_path):
    patcher = load_patcher()
    addon = make_addon(tmp_path / "built")

    patched = patcher["patch_frozen_cv2_config"](addon)

    assert [path.name for path in patched] == list(LOADER_NAMES)
    assert "LOADER_DIR" in (addon / "cv2" / "config.py").read_text(encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        patcher["patch_frozen_cv2_config"](tmp_path / "nothing")


# --- machine_setup: startup and install wiring --------------------------------


def test_machine_setup_repairs_an_installed_addon_and_reports_it(tmp_path):
    bundle = make_bundle(tmp_path)
    messages: list[str] = []

    result = machine_setup.ensure_gpu_addon_cv2_portable(
        bundle["resource_root"], bundle["addon_dir"], progress=messages.append
    )

    assert result["status"] == "repaired"
    assert any("OpenCV" in message for message in messages), messages
    assert "LOADER_DIR" in (bundle["addon_dir"] / "cv2" / "config.py").read_text(encoding="utf-8")


def test_machine_setup_stays_silent_when_the_addon_has_no_cv2(tmp_path):
    bundle = make_bundle(tmp_path)
    shutil.rmtree(bundle["addon_dir"] / "cv2")
    messages: list[str] = []

    result = machine_setup.ensure_gpu_addon_cv2_portable(
        bundle["resource_root"], bundle["addon_dir"], progress=messages.append
    )

    assert result["status"] == "not_installed"
    assert messages == [], "a CPU-only install must not gain a scary line in the setup log"


def test_machine_setup_stays_silent_when_the_addon_is_already_portable(tmp_path):
    bundle = make_bundle(tmp_path, addon_kwargs={"leaked": False})
    messages: list[str] = []

    result = machine_setup.ensure_gpu_addon_cv2_portable(
        bundle["resource_root"], bundle["addon_dir"], progress=messages.append
    )

    assert result["status"] == "clean"
    assert messages == []


def test_machine_setup_reports_a_missing_patcher_tool(tmp_path):
    bundle = make_bundle(tmp_path, ship_tool=False)
    messages: list[str] = []

    result = machine_setup.ensure_gpu_addon_cv2_portable(
        bundle["resource_root"], bundle["addon_dir"], progress=messages.append
    )

    assert result["status"] == "tool_missing"
    assert messages, "a missing tool is a packaging bug, so it must be visible"


class FakeAddonServices:
    """Only what inspect_gpu_addon probes; the driver path is irrelevant here."""

    def cuda_available(self):
        return machine_setup.CommandResult(True, "fake cuda")

    def display_adapters(self):
        return ["NVIDIA GeForce RTX 4080"]


def make_ready_addon(resource_root: Path, **kwargs) -> Path:
    addon = make_addon(resource_root, **kwargs)
    (addon / "DeepCAD-RT" / "DeepCAD_RT_pytorch" / "deepcad").mkdir(parents=True)
    (addon / "DeepCADRT_Model").mkdir()
    (addon / "DeepCADRT_Model" / "E_02_Iter_6416.pth").write_bytes(b"weights")
    (addon / "NeuSuite2p").mkdir()
    (addon / "NeuSuite2p" / "segment_model.pt").write_bytes(b"weights")
    (addon / "NeuSuite_RuntimeDeps").mkdir()
    return addon


def test_startup_inspection_repairs_the_addon_before_probing_cuda(tmp_path):
    application_dir = tmp_path / "application"
    resource_root = application_dir / "_internal"
    (resource_root / "tools").mkdir(parents=True)
    (resource_root / "tools" / "patch_frozen_cv2.py").write_text(patcher_source(), encoding="utf-8")
    addon = make_ready_addon(resource_root)

    ok, message = machine_setup.inspect_gpu_addon(application_dir, FakeAddonServices())

    assert ok, message
    assert "LOADER_DIR" in (addon / "cv2" / "config.py").read_text(encoding="utf-8")


def addon_archive(path: Path) -> str:
    """A minimal archive that satisfies _gpu_addon_ready, with a leaking cv2 loader."""
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("GPU_Addon/DeepCAD-RT/DeepCAD_RT_pytorch/deepcad/network.py", "# test\n")
        bundle.writestr("GPU_Addon/DeepCADRT_Model/test.pth", b"weights")
        bundle.writestr("GPU_Addon/NewLight_GPU_Worker.exe", b"worker")
        bundle.writestr("GPU_Addon/NeuSuite2p/segment_model.pt", b"weights")
        bundle.writestr("GPU_Addon/NeuSuite_RuntimeDeps/runtime.txt", b"runtime")
        bundle.writestr("GPU_Addon/cv2/__init__.py", "# cv2 loader\n")
        bundle.writestr("GPU_Addon/cv2/load_config_py3.py", "# loader\n")
        bundle.writestr("GPU_Addon/cv2/config.py", LEAKED_CONFIG_PY)
        bundle.writestr("GPU_Addon/cv2/config-3.11.py", LEAKED_VERSION_CONFIG)
        bundle.writestr("GPU_Addon/cv2/python-3.11/cv2.cp311-win_amd64.pyd", b"MZ\x90\x00")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_downloaded_addon_gets_repaired_during_install(tmp_path, monkeypatch):
    application_dir = tmp_path / "application"
    resource_root = application_dir / "_internal"
    (resource_root / "tools").mkdir(parents=True)
    (resource_root / "tools" / "patch_frozen_cv2.py").write_text(patcher_source(), encoding="utf-8")
    archive = tmp_path / "addon.zip"
    (resource_root / machine_setup.GPU_ADDON_MANIFEST).write_text(
        json.dumps({"url": archive.as_uri(), "sha256": addon_archive(archive)}), encoding="utf-8"
    )
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "program-data"))

    ok, message = machine_setup.ensure_gpu_addon(application_dir)

    assert ok, message
    config = resource_root / "GPU_Addon" / "cv2" / "config.py"
    assert "LOADER_DIR" in config.read_text(encoding="utf-8"), (
        "the published zip leaks build paths, so finishing the install must repair them"
    )


# --- analysis_core: never launch an addon worker on a leaked loader -----------


class _NullPipe:
    def close(self) -> None:
        pass


class FakeProcess:
    returncode = 0
    pid = 4242
    stdout = _NullPipe()
    stderr = _NullPipe()

    def communicate(self, timeout=None):
        return ("", "")

    def poll(self):
        return self.returncode


def recording_popen(events: list):
    def _popen(cmd, *args, **kwargs):
        events.append(("popen", str(cmd[0])))
        return FakeProcess()

    return _popen


def use_frozen_bundle(monkeypatch, tmp_path, **kwargs) -> dict:
    bundle = make_bundle(tmp_path / "bundle", **kwargs)
    monkeypatch.setattr(core, "IS_FROZEN", True)
    monkeypatch.setattr(core, "APP_RESOURCE_DIR", bundle["resource_root"])
    monkeypatch.setattr(core, "GPU_ADDON_DIR", bundle["addon_dir"])
    monkeypatch.setattr(
        core, "GPU_WORKER_EXE", bundle["addon_dir"] / "NewLight_GPU_Worker.exe"
    )
    monkeypatch.setattr(machine_setup, "setup_log_progress", lambda: (lambda message: None))
    return bundle


def repair_recorder(events: list, status: str = "repaired"):
    def _repair(resource_root, addon_dir=None, *, progress=None):
        events.append(("repair", Path(addon_dir).name))
        return {"status": status, "cv2_dir": str(addon_dir), "patched": [], "reason": ""}

    return _repair


def test_run_conda_worker_repairs_before_launching_the_gpu_worker(monkeypatch, tmp_path):
    bundle = use_frozen_bundle(monkeypatch, tmp_path)
    events: list[tuple[str, str]] = []
    monkeypatch.setattr(machine_setup, "ensure_gpu_addon_cv2_portable", repair_recorder(events))
    monkeypatch.setattr(core.subprocess, "Popen", recording_popen(events))

    core.run_conda_worker(
        "env", "run_neusuite_roi.py", [], worker_exe=bundle["addon_dir"] / "NewLight_GPU_Worker.exe"
    )

    assert events == [
        ("repair", "GPU_Addon"),
        ("popen", str(bundle["addon_dir"] / "NewLight_GPU_Worker.exe")),
    ], "the loader has to be portable before the worker imports cv2"


def test_run_conda_worker_leaves_the_core_worker_alone(monkeypatch, tmp_path):
    bundle = use_frozen_bundle(monkeypatch, tmp_path)
    core_worker = bundle["resource_root"] / "NewLight_Worker.exe"
    core_worker.write_bytes(b"MZ")
    events: list[tuple[str, str]] = []

    def fail(*args, **kwargs):
        raise AssertionError("the core cv2 tree is patched at build time; do not rescan per task")

    monkeypatch.setattr(machine_setup, "ensure_gpu_addon_cv2_portable", fail)
    monkeypatch.setattr(core.subprocess, "Popen", recording_popen(events))

    core.run_conda_worker("env", "run_caiman.py", [])

    assert events == [("popen", str(core_worker))]


def test_cuda_probe_repairs_before_spawning_the_gpu_worker(monkeypatch, tmp_path):
    bundle = use_frozen_bundle(monkeypatch, tmp_path)
    events: list[tuple[str, str]] = []

    def fake_run(cmd, *args, **kwargs):
        events.append(("probe", str(cmd[0])))
        return subprocess.CompletedProcess(cmd, 0, "True\n", "")

    monkeypatch.setattr(machine_setup, "ensure_gpu_addon_cv2_portable", repair_recorder(events))
    monkeypatch.setattr(core.subprocess, "run", fake_run)
    core._FAST_ROI_CUDA_CACHE.clear()

    assert core.fast_roi_cuda_available() is True
    assert events == [
        ("repair", "GPU_Addon"),
        ("probe", str(bundle["addon_dir"] / "NewLight_GPU_Worker.exe")),
    ]


def test_backend_status_probe_repairs_before_the_gpu_worker(monkeypatch, tmp_path):
    bundle = use_frozen_bundle(monkeypatch, tmp_path)
    events: list[tuple[str, str]] = []

    def fake_run(cmd, *args, **kwargs):
        events.append(("probe", str(cmd[0])))
        return subprocess.CompletedProcess(cmd, 0, "True\nRTX 4080\n", "")

    monkeypatch.setattr(machine_setup, "ensure_gpu_addon_cv2_portable", repair_recorder(events))
    monkeypatch.setattr(core.subprocess, "run", fake_run)

    status = core.cuda_status(check_neuroseg3=False)

    assert status["torch_cuda_available"] is True
    assert events[0] == ("repair", "GPU_Addon")


def test_source_runs_never_touch_the_addon_loader(monkeypatch, tmp_path):
    bundle = make_bundle(tmp_path / "bundle")
    monkeypatch.setattr(core, "IS_FROZEN", False)

    core.ensure_gpu_addon_cv2_portable(bundle["addon_dir"] / "NewLight_GPU_Worker.exe")

    assert (bundle["addon_dir"] / "cv2" / "config.py").read_text(encoding="utf-8") == LEAKED_CONFIG_PY


def test_repair_failure_cannot_break_the_worker(monkeypatch, tmp_path):
    bundle = use_frozen_bundle(monkeypatch, tmp_path)
    events: list[tuple[str, str]] = []

    def boom(*args, **kwargs):
        raise RuntimeError("patcher exploded")

    monkeypatch.setattr(machine_setup, "ensure_gpu_addon_cv2_portable", boom)
    monkeypatch.setattr(core.subprocess, "Popen", recording_popen(events))

    completed = core.run_conda_worker(
        "env", "run_neusuite_roi.py", [], worker_exe=bundle["addon_dir"] / "NewLight_GPU_Worker.exe"
    )

    assert completed.returncode == 0
    assert events == [("popen", str(bundle["addon_dir"] / "NewLight_GPU_Worker.exe"))]


@pytest.mark.skipif(
    not (ROOT / "NewLight_Analysis.spec").is_file(), reason="the spec only exists on build machines"
)
def test_spec_ships_the_patcher_for_the_frozen_runtime():
    source = (ROOT / "NewLight_Analysis.spec").read_text(encoding="utf-8")

    assert "('tools/patch_frozen_cv2.py', 'tools')" in source, (
        "machine_setup loads _internal/tools/patch_frozen_cv2.py at runtime"
    )


# --- gpu_addon_manifest.json: the republished, portable archive ----------------


def test_manifest_points_at_a_republishable_portable_archive():
    """machine_setup verifies every download against this file, so a typo is a failed install.

    ``LEAKED_ARCHIVE_SHA256`` is the 2026-08-04 archive whose cv2 loader names
    ``D:/anaconda3/envs/caiman_latest``; republishing it would put the reported
    "recursion is detected during loading of cv2" failure back into every fresh install.
    """
    leaked_archive_sha256 = "2b2aec07e6066295f29cb0672de98199331eeed654cc7b019f8bbb30d5823cb2"
    manifest = json.loads((ROOT / "gpu_addon_manifest.json").read_text(encoding="utf-8"))
    digest = re.compile(r"^[0-9a-f]{64}$")

    archive = str(manifest["archive_sha256"])
    assert digest.match(archive), archive
    assert archive != leaked_archive_sha256, "the leaked addon archive must not be republished"
    assert manifest["parts"], "the addon ships as split assets"
    for index, part in enumerate(manifest["parts"], start=1):
        assert digest.match(str(part["sha256"])), part
        assert part["url"] == (
            f"https://github.com/AzuRui/NewLight_Analysis/releases/download/"
            f"gpu-addon-v1/GPU_Addon_CUDA.zip.part{index:02d}"
        ), part["url"]
