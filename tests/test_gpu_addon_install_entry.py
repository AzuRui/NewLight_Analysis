"""The GPU addon must be installable from inside the app, not only from a batch file."""

import sys
import types
from pathlib import Path

import pytest

import NewLight_Analysis as app


class RecordingApp:
    """Minimal stand-in for the parts of NewLightApp the install entry touches."""

    def __init__(self):
        self.logs = []
        self.tasks = []

    def log(self, text):
        self.logs.append(str(text))

    def post_ui_callback(self, callback, *args):
        callback(*args)

    def enqueue_task(self, label, worker, finish, **kwargs):
        self.tasks.append({"label": label, "worker": worker, "finish": finish, "kwargs": kwargs})

    def fast_roi_backend_summary(self):
        return "NeuSuite 快速 ROI（CPU，核心包内置模型）"


class Dialogs:
    def __init__(self, answer=True):
        self.answer = answer
        self.infos = []
        self.errors = []

    def showinfo(self, title, message):
        self.infos.append((title, message))

    def showerror(self, title, message):
        self.errors.append((title, message))

    def askyesno(self, title, message):
        self.infos.append((title, message))
        return self.answer


@pytest.fixture
def addon_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(app.core, "GPU_WORKER_EXE", tmp_path / "absent" / "NewLight_GPU_Worker.exe")
    monkeypatch.setattr(app.core, "GPU_ADDON_DIR", tmp_path / "absent")


def stub_machine_setup(monkeypatch, results):
    module = types.ModuleType("machine_setup")

    def ensure_gpu_addon(application_dir, progress=None):
        results.append(Path(application_dir))
        progress("正在校验下载缓存")
        return True, "统一 GPU 扩展已安装。"

    module.ensure_gpu_addon = ensure_gpu_addon
    monkeypatch.setitem(sys.modules, "machine_setup", module)
    return module


def test_sidebar_wires_the_install_button_into_the_acceleration_panel():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

    assert 'text="安装 GPU 扩展"' in source
    assert "command=self.install_gpu_addon" in source
    # The button has to live in the existing 计算加速 box, next to the CUDA check.
    box = source[source.index('text="计算加速"') : source.index("for action_id, spec in PREPROCESS_PANEL_SPECS")]
    assert "检查 CUDA" in box and "安装 GPU 扩展" in box


def test_cuda_status_dialog_reports_which_backend_fast_roi_will_use():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

    assert 'f"快速 ROI：{self.fast_roi_backend_summary()}"' in source
    assert "def fast_roi_backend_summary" in source


def test_backend_summary_degrades_to_text_when_no_backend_is_available(monkeypatch):
    def explode(device="auto"):
        raise FileNotFoundError("未安装 GPU 扩展，且核心包缺少 CPU 模型")

    monkeypatch.setattr(app.core, "fast_roi_backend", explode)

    summary = app.NewLightApp.fast_roi_backend_summary(RecordingApp())
    assert "不可用" in summary


def test_already_installed_addon_is_reported_without_a_download(monkeypatch, addon_missing):
    monkeypatch.setattr(app.core, "GPU_WORKER_EXE", Path(sys.executable))
    dialogs = Dialogs()
    monkeypatch.setattr(app, "messagebox", dialogs)
    instance = RecordingApp()

    app.NewLightApp.install_gpu_addon(instance)

    assert instance.tasks == []
    assert any("已安装" in title_message[1] for title_message in dialogs.infos)


def test_declining_the_prompt_queues_nothing(monkeypatch, addon_missing):
    dialogs = Dialogs(answer=False)
    monkeypatch.setattr(app, "messagebox", dialogs)
    instance = RecordingApp()

    app.NewLightApp.install_gpu_addon(instance)

    assert instance.tasks == []
    assert any("已取消" in line for line in instance.logs)


def test_accepting_runs_the_installer_in_the_task_queue_and_logs_progress(monkeypatch, addon_missing):
    dialogs = Dialogs(answer=True)
    monkeypatch.setattr(app, "messagebox", dialogs)
    calls = []
    stub = stub_machine_setup(monkeypatch, calls)
    assert stub is not None
    instance = RecordingApp()

    app.NewLightApp.install_gpu_addon(instance)

    assert len(instance.tasks) == 1
    task = instance.tasks[0]
    assert task["kwargs"]["cancellable"] is False

    result = task["worker"](types.SimpleNamespace(is_set=lambda: False))
    assert result == (True, "统一 GPU 扩展已安装。")
    assert any("正在校验下载缓存" in line for line in instance.logs)

    task["finish"](result)
    assert any("安装完成" in line for line in instance.logs)
    assert any("快速 ROI 后端" in line for line in instance.logs)


def test_source_mode_uses_the_repository_as_the_install_target(monkeypatch, addon_missing):
    monkeypatch.setattr(app.core, "IS_FROZEN", False)
    dialogs = Dialogs(answer=True)
    monkeypatch.setattr(app, "messagebox", dialogs)
    calls = []
    stub_machine_setup(monkeypatch, calls)
    instance = RecordingApp()

    app.NewLightApp.install_gpu_addon(instance)
    instance.tasks[0]["worker"](types.SimpleNamespace(is_set=lambda: False))

    assert calls == [Path(app.core.PROJECT_DIR)]
