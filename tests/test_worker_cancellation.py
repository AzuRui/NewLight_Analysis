"""取消任务必须能立刻释放被 worker 子进程占用的 GPU/CPU。

分析步骤跑在独立 worker 进程里，UI 的取消是协作式的（threading.Event）。
若 worker 只是阻塞在子进程上，事件永远不会被检查，进程会跑到自然结束。
run_conda_worker 因此登记活动 Popen，UI 取消时通过 terminate_active_workers()
终止整个进程树。
"""

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import analysis_core as core


SLEEP_SNIPPET = "import time; time.sleep({seconds})"


def start_registered_worker(seconds: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-c", SLEEP_SNIPPET.format(seconds=seconds)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **core.hidden_subprocess_kwargs(),
    )
    core._register_worker(proc)
    return proc


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    with core._WORKER_LOCK:
        leaked = list(core._ACTIVE_WORKERS)
    for proc in leaked:
        core._kill_process_tree(proc)
        proc.communicate()
    core._ACTIVE_WORKERS.clear()


def test_terminate_active_workers_kills_registered_process():
    proc = start_registered_worker(30)
    assert proc.poll() is None

    killed = core.terminate_active_workers()

    assert killed == 1
    assert proc.poll() is not None
    with core._WORKER_LOCK:
        assert not core._ACTIVE_WORKERS
    # 已经退出的进程不会被重复计入。
    assert core.terminate_active_workers() == 0


def test_terminate_active_workers_is_safe_without_any_worker():
    assert core.terminate_active_workers() == 0


def test_run_conda_worker_captures_output_and_leaves_no_registration(monkeypatch):
    monkeypatch.setattr(core, "IS_FROZEN", True)

    proc = core.run_conda_worker(
        "unused-env",
        "-c",
        ["import sys; print('worker-out'); sys.exit(0)"],
        worker_exe=Path(sys.executable),
    )

    assert proc.returncode == 0
    assert "worker-out" in proc.stdout
    with core._WORKER_LOCK:
        assert not core._ACTIVE_WORKERS


def test_run_conda_worker_registers_the_process_while_it_runs(monkeypatch):
    monkeypatch.setattr(core, "IS_FROZEN", True)
    seen = {}
    real_popen = subprocess.Popen

    class WatchingPopen(real_popen):
        def communicate(self, *args, **kwargs):
            # communicate() 在 run_conda_worker 登记之后调用。
            seen.setdefault("registered", self in core._ACTIVE_WORKERS)
            return super().communicate(*args, **kwargs)

    monkeypatch.setattr(core.subprocess, "Popen", WatchingPopen)

    core.run_conda_worker(
        "unused-env",
        "-c",
        ["print('registered-check')"],
        worker_exe=Path(sys.executable),
        timeout=60,
    )

    assert seen["registered"] is True
    with core._WORKER_LOCK:
        assert not core._ACTIVE_WORKERS


def test_terminating_during_run_conda_worker_returns_promptly(monkeypatch):
    """取消路径的核心回归：阻塞中的 worker 被终止后调用方必须马上返回。"""
    monkeypatch.setattr(core, "IS_FROZEN", True)
    outcome = {}

    def run():
        started = time.monotonic()
        try:
            outcome["proc"] = core.run_conda_worker(
                "unused-env",
                "-c",
                [SLEEP_SNIPPET.format(seconds=120)],
                worker_exe=Path(sys.executable),
                timeout=None,
            )
        except BaseException as exc:  # noqa: BLE001 - 只用于断言
            outcome["error"] = exc
        outcome["elapsed"] = time.monotonic() - started

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        with core._WORKER_LOCK:
            if core._ACTIVE_WORKERS:
                break
        time.sleep(0.05)
    else:
        pytest.fail("worker 进程未登记，取消无法释放它")

    time.sleep(0.5)
    core.terminate_active_workers()
    thread.join(timeout=15)

    assert not thread.is_alive(), "终止后调用方仍被阻塞"
    assert outcome.get("elapsed", 999) < 15
    assert "error" not in outcome, outcome.get("error")
    assert outcome["proc"].returncode != 0
