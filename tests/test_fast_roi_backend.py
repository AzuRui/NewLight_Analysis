"""Fast ROI must treat CUDA as an accelerator: pick the worker the machine can actually run."""

import subprocess as sp
from pathlib import Path

import numpy as np
import pytest

import analysis_core as core


def arg_value(args, name):
    return args[args.index(name) + 1]


def make_tree(tmp_path):
    """Fake an installed bundle: core model + workers, plus an optional GPU addon."""
    core_model = tmp_path / "internal" / "NeuSuite2p"
    (core_model / "method" / "ultralytics").mkdir(parents=True)
    (core_model / "segment_model.pt").write_bytes(b"core-weights")
    core_workers = tmp_path / "internal" / "workers"
    core_workers.mkdir(parents=True)
    (core_workers / "run_neusuite_roi.py").write_text("# core worker\n", encoding="utf-8")

    addon = tmp_path / "internal" / "GPU_Addon"
    (addon / "workers").mkdir(parents=True)
    (addon / "NewLight_GPU_Worker.exe").write_bytes(b"MZ")
    (addon / "workers" / "run_neusuite_roi.py").write_text("# gpu worker\n", encoding="utf-8")
    addon_model = addon / "NeuSuite2p"
    (addon_model / "method" / "ultralytics").mkdir(parents=True)
    (addon_model / "segment_model.pt").write_bytes(b"gpu-weights")

    return {
        "NEUSUITE_DIR": core_model,
        "NEUSUITE_DEFAULT_WEIGHTS": core_model / "segment_model.pt",
        "NEUSUITE_RUNTIME_ROOT": core_model / "method",
        "WORKER_DIR": core_workers,
        "GPU_ADDON_DIR": addon,
        "GPU_WORKER_EXE": addon / "NewLight_GPU_Worker.exe",
        "GPU_NEUSUITE_DEFAULT_WEIGHTS": addon_model / "segment_model.pt",
        "GPU_NEUSUITE_RUNTIME_ROOT": addon_model / "method",
    }


def use_bundle(monkeypatch, tmp_path, *, frozen=True, addon=True, cpu_model=True):
    for name, value in make_tree(tmp_path).items():
        monkeypatch.setattr(core, name, value)
    monkeypatch.setattr(core, "IS_FROZEN", frozen)
    if not addon:
        monkeypatch.setattr(core, "GPU_WORKER_EXE", tmp_path / "absent" / "NewLight_GPU_Worker.exe")
    if not cpu_model:
        monkeypatch.setattr(core, "NEUSUITE_DEFAULT_WEIGHTS", tmp_path / "absent" / "segment_model.pt")


class ExplodingSubprocess:
    """A GPU worker that is not installed must never be probed."""

    def __init__(self):
        self.calls = []

    def run(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("probed a GPU worker that is not installed")

    def __getattr__(self, name):
        raise AttributeError(name)


def test_source_run_forwards_the_requested_device_unchanged(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path, frozen=False)

    backend = core.fast_roi_backend("0", gpu_ready=True, cpu_ready=True, cuda_ready=True)

    assert backend["mode"] == "conda"
    assert backend["worker_exe"] is None
    assert backend["device"] == "0"
    assert Path(backend["script"]) == core.WORKER_DIR / "run_neusuite_roi.py"


def test_auto_with_gpu_and_cuda_uses_the_addon_worker(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)

    backend = core.fast_roi_backend("auto", gpu_ready=True, cpu_ready=True, cuda_ready=True)

    assert backend["mode"] == "gpu"
    assert Path(backend["worker_exe"]) == core.GPU_WORKER_EXE
    assert Path(backend["script"]) == core.GPU_ADDON_DIR / "workers" / "run_neusuite_roi.py"
    assert Path(backend["weights"]) == core.GPU_NEUSUITE_DEFAULT_WEIGHTS
    assert Path(backend["runtime_root"]) == core.GPU_NEUSUITE_RUNTIME_ROOT
    assert "GPU" in backend["label"]


def test_auto_without_addon_falls_back_to_the_bundled_cpu_model(monkeypatch, tmp_path):
    """The original defect: without the CUDA addon fast ROI refused to run at all."""
    use_bundle(monkeypatch, tmp_path, addon=False)

    backend = core.fast_roi_backend("auto")

    assert backend["mode"] == "cpu"
    assert backend["worker_exe"] is None
    assert backend["device"] == "cpu"
    assert Path(backend["script"]) == core.WORKER_DIR / "run_neusuite_roi.py"
    assert Path(backend["weights"]) == core.NEUSUITE_DEFAULT_WEIGHTS
    assert Path(backend["runtime_root"]) == core.NEUSUITE_RUNTIME_ROOT
    assert "CPU" in backend["label"]


def test_installed_addon_without_cuda_device_also_falls_back_to_cpu(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)

    backend = core.fast_roi_backend("auto", gpu_ready=True, cpu_ready=True, cuda_ready=False)

    assert backend["mode"] == "cpu"
    assert backend["worker_exe"] is None
    assert "CUDA" in backend["reason"]


def test_explicit_cpu_never_reaches_the_gpu_worker(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)

    backend = core.fast_roi_backend("cpu", gpu_ready=True, cpu_ready=True, cuda_ready=True)

    assert backend["mode"] == "cpu"
    assert backend["worker_exe"] is None
    assert backend["device"] == "cpu"
    assert Path(backend["weights"]) == core.NEUSUITE_DEFAULT_WEIGHTS


def test_explicit_device_that_needs_cuda_fails_loudly(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)

    with pytest.raises(RuntimeError, match="CUDA"):
        core.fast_roi_backend("0", gpu_ready=True, cpu_ready=True, cuda_ready=False)

    with pytest.raises(RuntimeError, match="CUDA"):
        core.fast_roi_backend("0", gpu_ready=False, cpu_ready=True, cuda_ready=False)


def test_missing_cpu_model_with_no_addon_reports_actionable_error(monkeypatch, tmp_path):
    """An old bundle with neither the core model nor the addon must say what to do."""
    use_bundle(monkeypatch, tmp_path, addon=False, cpu_model=False)

    with pytest.raises(FileNotFoundError, match="update-gpu"):
        core.fast_roi_backend("auto", gpu_ready=False, cpu_ready=False, cuda_ready=False)

    with pytest.raises(FileNotFoundError):
        core.fast_roi_backend("cpu", gpu_ready=False, cpu_ready=False, cuda_ready=False)


def test_cpu_ready_requires_weights_and_vendored_runtime(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)
    assert core.fast_roi_cpu_ready() is True

    (tmp_path / "internal" / "NeuSuite2p" / "segment_model.pt").unlink()
    assert core.fast_roi_cpu_ready() is False


def test_cuda_probe_is_skipped_when_the_addon_is_absent(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path, addon=False)
    fake = ExplodingSubprocess()
    monkeypatch.setattr(core, "subprocess", fake)
    core._FAST_ROI_CUDA_CACHE.clear()

    assert core.fast_roi_cuda_available() is False
    assert fake.calls == []


def probe_subprocess(monkeypatch, core, stdout: str):
    fake = ExplodingSubprocess()
    fake.run = lambda *a, **k: (fake.calls.append(a), sp.CompletedProcess(list(a[0]), 0, stdout, ""))[1]
    monkeypatch.setattr(core, "subprocess", fake)
    monkeypatch.setattr(core, "hidden_subprocess_kwargs", lambda: {})
    core._FAST_ROI_CUDA_CACHE.clear()
    return fake


def test_cuda_probe_tolerates_loader_noise(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)
    probe_subprocess(monkeypatch, core, "importing native libs...\nTrue\n")
    assert core.fast_roi_cuda_available() is True

    core._FAST_ROI_CUDA_CACHE.clear()
    probe_subprocess(monkeypatch, core, "warning: no driver\nFalse\n")
    assert core.fast_roi_cuda_available() is False

    core._FAST_ROI_CUDA_CACHE.clear()
    probe_subprocess(monkeypatch, core, "")
    assert core.fast_roi_cuda_available() is False


def test_cuda_probe_caches_one_subprocess_answer(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)
    fake = probe_subprocess(monkeypatch, core, "True\n")

    assert core.fast_roi_cuda_available() is True
    assert core.fast_roi_cuda_available() is True
    assert len(fake.calls) == 1
    core._FAST_ROI_CUDA_CACHE.clear()
    assert core.fast_roi_cuda_available(refresh=True) is True
    assert len(fake.calls) == 2
    core._FAST_ROI_CUDA_CACHE.clear()


def capture_worker():
    calls = []

    def run(environment, script, args, cwd=None, timeout=None, worker_exe=None):
        calls.append(
            {
                "environment": environment,
                "script": script,
                "args": list(args),
                "cwd": cwd,
                "timeout": timeout,
                "worker_exe": worker_exe,
            }
        )
        return sp.CompletedProcess([script], 0, "worker ok", "")

    return calls, run


def install_backend_result(monkeypatch):
    def fake_load(artifact_path, summary_path, expected_shape, log, *args, **kwargs):
        return core.ROIBackendResult(
            masks=np.zeros((1,) + tuple(expected_shape), dtype=bool),
            names=["cell_0"],
            metadata={},
            arrays={},
            log=log,
            artifact_path=Path(artifact_path),
            summary_path=Path(summary_path),
        )

    monkeypatch.setattr(core, "_load_roi_worker_result", fake_load)


def test_run_fast_roi_runs_the_core_worker_on_cpu_when_cuda_is_absent(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)
    monkeypatch.setattr(core, "fast_roi_cuda_available", lambda **kwargs: False)
    calls, run = capture_worker()
    monkeypatch.setattr(core, "run_conda_worker", run)
    install_backend_result(monkeypatch)

    result = core.run_fast_roi_segmentation(np.zeros((8, 8), dtype="float32"), str(tmp_path / "session"))

    assert len(calls) == 1
    call = calls[0]
    assert call["worker_exe"] is None
    assert call["script"] == str(core.WORKER_DIR / "run_neusuite_roi.py")
    assert arg_value(call["args"], "--weights") == str(core.NEUSUITE_DEFAULT_WEIGHTS.resolve())
    assert arg_value(call["args"], "--runtime-root") == str(core.NEUSUITE_RUNTIME_ROOT.resolve())
    assert arg_value(call["args"], "--device") == "cpu"
    assert "CPU" in result.log


def test_run_fast_roi_runs_the_addon_worker_and_honours_an_explicit_device(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)
    monkeypatch.setattr(core, "fast_roi_cuda_available", lambda **kwargs: True)
    calls, run = capture_worker()
    monkeypatch.setattr(core, "run_conda_worker", run)
    install_backend_result(monkeypatch)

    core.run_fast_roi_segmentation(
        np.zeros((8, 8), dtype="float32"), str(tmp_path / "session"), device="0", candidate_mode=True
    )

    call = calls[0]
    assert Path(call["worker_exe"]) == core.GPU_WORKER_EXE
    assert call["script"] == str(core.GPU_ADDON_DIR / "workers" / "run_neusuite_roi.py")
    assert arg_value(call["args"], "--weights") == str(core.GPU_NEUSUITE_DEFAULT_WEIGHTS.resolve())
    assert arg_value(call["args"], "--runtime-root") == str(core.GPU_NEUSUITE_RUNTIME_ROOT.resolve())
    assert arg_value(call["args"], "--device") == "0"
    assert "--candidate-mode" in call["args"]


def test_run_fast_roi_reports_a_missing_worker_script(monkeypatch, tmp_path):
    use_bundle(monkeypatch, tmp_path)
    monkeypatch.setattr(core, "fast_roi_cuda_available", lambda **kwargs: True)
    (tmp_path / "internal" / "GPU_Addon" / "workers" / "run_neusuite_roi.py").unlink()

    with pytest.raises(FileNotFoundError, match="worker 脚本缺失"):
        core.run_fast_roi_segmentation(np.zeros((8, 8), dtype="float32"), str(tmp_path / "session"))
