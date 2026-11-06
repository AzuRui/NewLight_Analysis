r"""Build-input guards for the CPU fast-ROI path.

PyInstaller freezes only what its static graph can reach, so the CPU inference stack
that the vendored NeuSuite Ultralytics runtime imports at run time is invisible to it.
Every one of these guards corresponds to a piece that silently disappears if someone
"cleans up" the build inputs:

* `slim_excludes` in the spec drops `torchvision`/`timm`, and the packaged worker then
  fails with ``No module named 'timm'`` for every user, exactly like the openpyxl case.
* The NeuSuite2p weights and runtime live outside the repository; `rmdir /s /q dist`
  in `build_cpu_exe.bat` deletes the only local copy when it is taken from an installed
  addon, so staging into NewLight_BuildCache is part of the build, not an ad-hoc step.
* `setup_newlight_caiman.bat` installs timm with ``--no-deps`` on purpose: letting pip
  resolve timm's dependencies replaces the conda CPU torch/torchvision pair with a pip
  build, and the bundled torch versions then no longer match their native libraries.
"""

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "NewLight_Analysis.spec"

if not SPEC.is_file():
    # /NewLight_Analysis.spec is git-ignored (see .gitignore), so this module only
    # applies on a machine that actually builds the portable package.
    pytest.skip(
        "NewLight_Analysis.spec is not present; it is ignored by git and only exists on build machines",
        allow_module_level=True,
    )


def spec_tree() -> ast.Module:
    return ast.parse(SPEC.read_text(encoding="utf-8"))


def spec_literal(name: str):
    for node in ast.walk(spec_tree()):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise AssertionError(f"{name} is not a literal assignment in {SPEC.name}")


def spec_list_items(name: str) -> list[object]:
    """hiddenimports/slim_excludes are literals; excludes is built as a list too."""
    return list(spec_literal(name))


def spec_function(name: str) -> str:
    for node in spec_tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(SPEC.read_text(encoding="utf-8"), node)
    raise AssertionError(f"{SPEC.name} no longer defines {name}()")


def run_spec_function(name: str, root: Path, workspace: Path):
    source = spec_function(name)
    namespace = {"Path": Path, "ROOT": root, "WORKSPACE": workspace, "SystemExit": SystemExit}
    exec(compile(source, f"<{name}>", "exec"), namespace)
    return namespace[name]


def make_neusuite(directory: Path) -> Path:
    (directory / "method" / "ultralytics").mkdir(parents=True)
    (directory / "segment_model.pt").write_bytes(b"weights")
    return directory


def test_spec_no_longer_excludes_the_cpu_inference_stack():
    excludes = spec_list_items("slim_excludes")

    assert "torchvision" not in excludes, "torchvision must stay in the bundle for CPU fast ROI"
    assert "timm" not in excludes, "timm must stay in the bundle for CPU fast ROI"


def test_spec_hiddens_imports_the_measured_cpu_closure():
    hidden = {str(item) for item in spec_list_items("hiddenimports")}

    # The vendored runtime is shipped as data, so these imports are not statically
    # reachable from the app; they are the measured non-stdlib closure of a CPU run.
    for name in ("torchvision", "timm", "requests", "tqdm"):
        assert name in hidden, f"{name} must be a hiddenimport or the worker cannot start"


def test_spec_packages_the_neusuite_model_and_runtime_deps():
    source = SPEC.read_text(encoding="utf-8")

    assert "'NeuSuite2p'" in source or '"NeuSuite2p"' in source
    assert "'NeuSuite_RuntimeDeps'" in source or '"NeuSuite_RuntimeDeps"' in source
    assert "NEUSUITE_CPU_SOURCE" in source and "NEUSUITE_RUNTIME_DEPS_SOURCE" in source


def test_model_source_resolver_prefers_the_dist_surviving_cache(tmp_path):
    staged = make_neusuite(tmp_path / "NewLight_BuildCache" / "NeuSuite2p")

    resolve = run_spec_function("_resolve_neusuite_cpu_source", tmp_path / "repo", tmp_path)

    assert resolve() == staged


def test_model_source_resolver_accepts_a_repo_local_copy(tmp_path):
    staged = make_neusuite(tmp_path / "repo" / "NeuSuite2p")

    resolve = run_spec_function("_resolve_neusuite_cpu_source", tmp_path / "repo", tmp_path)

    assert resolve() == staged


def test_model_source_resolver_rejects_a_copy_without_weights(tmp_path):
    empty = tmp_path / "cache" / "NeuSuite2p"
    (empty / "method" / "ultralytics").mkdir(parents=True)

    resolve = run_spec_function("_resolve_neusuite_cpu_source", tmp_path / "repo", tmp_path)
    with pytest.raises(SystemExit, match="stage_neusuite_cpu_source"):
        resolve()


def test_runtime_deps_resolver_needs_all_four_pure_python_packages(tmp_path):
    deps = tmp_path / "repo" / "NeuSuite_RuntimeDeps"
    for name in ("einops", "dill", "cpuinfo"):
        (deps / name).mkdir(parents=True)

    resolve = run_spec_function("_resolve_neusuite_runtime_deps", tmp_path / "repo", tmp_path)
    with pytest.raises(SystemExit, match="setup_neusuite_runtime"):
        resolve()

    (deps / "efficientnet_pytorch").mkdir()
    assert resolve() == deps


FAKE_RUNTIME = '''"""Stand-in for the vendored Ultralytics runtime that ships through datas."""
from pathlib import Path
import numpy as np
import timm
import wandb  # optional integration, must not be dragged into the package
from timm.models.layers import trunc_normal_
from timm.layers import DropPath
from timm.models import registry
from . import sibling
from method.ultralytics.utils import checks
from onnxruntime import InferenceSession
'''


def make_fake_runtime(root: Path, files: dict[str, str] | None = None) -> Path:
    runtime = root / "method" / "ultralytics"
    runtime.mkdir(parents=True)
    for name, text in (files or {"nn/block.py": FAKE_RUNTIME}).items():
        path = runtime / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def installed_only(*names: str):
    resolved = set(names)

    def resolve(name: str):
        return object() if name in resolved else None

    return resolve


def test_sweep_adds_the_deprecated_timm_shims_that_broke_fast_roi(tmp_path):
    # Reproduced 2026-11-06: nn/extra_modules/block.py does
    # "from timm.models.layers import trunc_normal_" and timm's own __init__ never
    # imports that legacy location, so the static graph missed it and the packaged
    # worker died with ModuleNotFoundError on every CPU-only machine.
    sweep = run_spec_function(
        "_vendored_runtime_hiddenimports", tmp_path / "repo", tmp_path
    )
    suite = make_fake_runtime(tmp_path / "repo" / "NeuSuite2p")

    added = sweep(suite, ["timm"], resolve_spec=installed_only("timm.models.layers", "timm.layers"))

    assert "timm.models.layers" in added
    assert "timm.layers" in added


def test_sweep_ignores_optional_integrations_and_uninstalled_packages(tmp_path):
    sweep = run_spec_function(
        "_vendored_runtime_hiddenimports", tmp_path / "repo", tmp_path
    )
    suite = make_fake_runtime(tmp_path / "repo" / "NeuSuite2p")
    everything = installed_only(
        "wandb", "onnxruntime", "numpy", "timm", "timm.models.layers",
        "timm.layers", "timm.models.registry", "pathlib",
    )

    added = sweep(suite, ["timm", "numpy"], resolve_spec=everything)

    for name in added:
        assert not name.startswith(("wandb", "onnxruntime")), (
            f"{name} is an optional Ultralytics integration; freezing it would bloat or break the build"
        )
        assert not name.startswith("pathlib"), "stdlib must stay out of hiddenimports"
    assert "timm" not in added and "numpy" not in added, (
        "names already in hiddenimports must not be duplicated"
    )
    assert added == sorted(set(added)), "the sweep output must stay deterministic"


def test_sweep_drops_modules_missing_from_the_build_environment(tmp_path):
    # Nothing is installed in the offline test interpreter, and an unresolvable
    # hiddenimport is what the openpyxl failure looked like: it must not be requested.
    sweep = run_spec_function(
        "_vendored_runtime_hiddenimports", tmp_path / "repo", tmp_path
    )
    suite = make_fake_runtime(tmp_path / "repo" / "NeuSuite2p")

    assert sweep(suite, ["timm"], resolve_spec=lambda name: None) == []


def test_spec_asks_for_the_vendored_runtime_sweep(tmp_path):
    source = SPEC.read_text(encoding="utf-8")

    assert "hiddenimports += _vendored_runtime_hiddenimports(NEUSUITE_CPU_SOURCE" in source, (
        "the fast ROI runtime import sweep must feed hiddenimports, not stay documentation"
    )
    assert "_vendored_runtime_hiddenimports" in {
        node.name for node in spec_tree().body if isinstance(node, ast.FunctionDef)
    }
