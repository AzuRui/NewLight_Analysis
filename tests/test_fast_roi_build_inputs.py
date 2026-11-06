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
