from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import machine_setup


@dataclass
class FakeServices:
    admin: bool = True
    adapters: list[str] = field(default_factory=lambda: ["NVIDIA GeForce RTX Test"])
    backend_ok: bool = True
    cuda_ok: bool = True
    install_ok: bool = True
    answers: list[bool] = field(default_factory=list)
    infos: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    install_calls: int = 0
    restart_calls: int = 0
    boot_marker: str = "boot-a"

    def is_admin(self):
        return self.admin

    def detect_display_adapters(self):
        return self.adapters

    def system_boot_marker(self):
        return self.boot_marker

    def verify_backends(self):
        return machine_setup.CommandResult(self.backend_ok, "backend diagnostic")

    def cuda_available(self):
        return machine_setup.CommandResult(self.cuda_ok, "cuda diagnostic")

    def install_nvidia_driver(self):
        self.install_calls += 1
        return machine_setup.CommandResult(self.install_ok, "driver diagnostic")

    def ask_yes_no(self, title, message):
        return self.answers.pop(0)

    def show_info(self, title, message):
        self.infos.append((title, message))

    def show_error(self, title, message):
        self.errors.append((title, message))

    def restart_windows(self):
        self.restart_calls += 1


def read_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_completed_machine_setup_bypasses_admin_and_checks(tmp_path):
    state_path = tmp_path / "machine_setup_v1.json"
    machine_setup.write_setup_state(state_path, "complete_cpu_only", ["AMD Radeon Test"])
    services = FakeServices(admin=False, backend_ok=False)

    assert machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert not services.errors


def test_first_frozen_start_requires_administrator(tmp_path):
    services = FakeServices(admin=False)
    state_path = tmp_path / "machine_setup_v1.json"

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert not state_path.exists()
    assert "管理员" in services.errors[0][1]


def test_backend_failure_does_not_complete_setup(tmp_path):
    services = FakeServices(backend_ok=False)
    state_path = tmp_path / "machine_setup_v1.json"

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert not state_path.exists()
    assert "backend diagnostic" in services.errors[0][1]


def test_nvidia_with_working_cuda_completes_setup(tmp_path):
    services = FakeServices(cuda_ok=True)
    state_path = tmp_path / "machine_setup_v1.json"

    assert machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    state = read_state(state_path)
    assert state["status"] == "complete_cuda"
    assert state["setup_version"] == machine_setup.SETUP_VERSION
    assert services.install_calls == 0


def test_nvidia_setup_reports_ordered_progress_stages(tmp_path):
    services = FakeServices(cuda_ok=True)
    state_path = tmp_path / "machine_setup_v1.json"
    events = []

    assert machine_setup.ensure_first_run_setup(
        tmp_path,
        state_path=state_path,
        services=services,
        progress=events.append,
    )

    assert events == [
        "正在验证分析后端...",
        "正在读取系统启动状态...",
        "正在检测图形设备...",
        "正在检查 CUDA 状态...",
        "运行环境检测完成",
    ]


def test_dialog_visibility_is_restored_after_native_dialog(tmp_path):
    services = FakeServices(admin=False)
    visibility = []

    assert not machine_setup.ensure_first_run_setup(
        tmp_path,
        state_path=tmp_path / "machine_setup_v1.json",
        services=services,
        dialog_visibility=visibility.append,
    )

    assert visibility == [False, True]


def test_mixed_graphics_with_nvidia_uses_nvidia_path(tmp_path):
    services = FakeServices(
        adapters=["Intel(R) Graphics", "NVIDIA GeForce RTX Test"],
        cuda_ok=False,
        answers=[False],
    )
    state_path = tmp_path / "machine_setup_v1.json"

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert not state_path.exists()
    assert services.install_calls == 0


def test_nvidia_is_detected_from_pnp_vendor_id_without_driver_name():
    adapters = [r"Microsoft Basic Display Adapter|PCI\VEN_10DE&DEV_2684"]

    assert machine_setup.has_nvidia_adapter(adapters)


def test_amd_or_intel_only_records_cpu_mode_and_warns(tmp_path):
    services = FakeServices(adapters=["AMD Radeon Test", "Intel(R) Graphics"], cuda_ok=False)
    state_path = tmp_path / "machine_setup_v1.json"

    assert machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert read_state(state_path)["status"] == "complete_cpu_only"
    assert "DeepCAD-RT" in services.infos[0][1]
    assert services.install_calls == 0


def test_unknown_adapter_detection_does_not_permanently_select_cpu_mode(tmp_path):
    services = FakeServices(adapters=[], cuda_ok=False)
    state_path = tmp_path / "machine_setup_v1.json"

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert not state_path.exists()
    assert "显卡" in services.errors[0][1]


def test_successful_driver_install_records_pending_and_restarts_only_after_confirmation(tmp_path):
    services = FakeServices(cuda_ok=False, answers=[True, True])
    state_path = tmp_path / "machine_setup_v1.json"

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert read_state(state_path)["status"] == "pending_restart"
    assert services.install_calls == 1
    assert services.restart_calls == 1


def test_successful_driver_install_can_wait_for_manual_restart(tmp_path):
    services = FakeServices(cuda_ok=False, answers=[True, False])
    state_path = tmp_path / "machine_setup_v1.json"

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert read_state(state_path)["status"] == "pending_restart"
    assert services.restart_calls == 0


def test_driver_install_failure_remains_incomplete(tmp_path):
    services = FakeServices(cuda_ok=False, install_ok=False, answers=[True])
    state_path = tmp_path / "machine_setup_v1.json"

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert not state_path.exists()
    assert "driver diagnostic" in services.errors[0][1]


def test_pending_restart_does_not_reinstall_driver(tmp_path):
    state_path = tmp_path / "machine_setup_v1.json"
    machine_setup.write_setup_state(
        state_path,
        "pending_restart",
        ["NVIDIA GeForce RTX Test"],
        boot_marker="boot-a",
    )
    services = FakeServices(cuda_ok=False)

    assert not machine_setup.ensure_first_run_setup(tmp_path, state_path=state_path, services=services)
    assert services.install_calls == 0
    assert "重启" in services.infos[0][1]


def test_source_launches_do_not_require_machine_setup(monkeypatch, tmp_path):
    monkeypatch.delattr(machine_setup.sys, "frozen", raising=False)
    services = FakeServices(admin=False)

    assert machine_setup.ensure_application_setup(tmp_path, services=services)
    assert not services.errors
