from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol


SETUP_VERSION = 1
COMPLETE_STATUSES = {"complete_cuda", "complete_cpu_only"}
STATE_FILE_NAME = "machine_setup_v1.json"
CREATE_NO_WINDOW = 0x08000000
ProgressCallback = Callable[[str], None]
VisibilityCallback = Callable[[bool], None]


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    diagnostic: str = ""


class SetupServices(Protocol):
    def is_admin(self) -> bool: ...

    def detect_display_adapters(self) -> list[str]: ...

    def system_boot_marker(self) -> str: ...

    def verify_backends(self) -> CommandResult: ...

    def cuda_available(self) -> CommandResult: ...

    def install_nvidia_driver(self) -> CommandResult: ...

    def ask_yes_no(self, title: str, message: str) -> bool: ...

    def show_info(self, title: str, message: str) -> None: ...

    def show_error(self, title: str, message: str) -> None: ...

    def restart_windows(self) -> None: ...


def machine_data_dir() -> Path:
    base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return base / "NewLight_Analysis"


def default_state_path() -> Path:
    return machine_data_dir() / STATE_FILE_NAME


def read_setup_state(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def setup_is_complete(path: Path) -> bool:
    state = read_setup_state(path)
    return state.get("setup_version") == SETUP_VERSION and state.get("status") in COMPLETE_STATUSES


def write_setup_state(path: Path, status: str, adapters: list[str], boot_marker: str = "") -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    value = {
        "setup_version": SETUP_VERSION,
        "status": str(status),
        "display_adapters": [str(item) for item in adapters],
        "boot_marker": str(boot_marker),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(destination)


def has_nvidia_adapter(adapters: list[str]) -> bool:
    return any(
        "nvidia" in str(name).lower() or "ven_10de" in str(name).lower()
        for name in adapters
    )


def _command_text(proc: subprocess.CompletedProcess) -> str:
    parts = [str(proc.stdout or "").strip(), str(proc.stderr or "").strip()]
    return "\n".join(part for part in parts if part).strip()


def _run_hidden(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    kwargs = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(command, **kwargs)


def _emit(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _show_dialog(dialog_visibility: VisibilityCallback | None, callback):
    if dialog_visibility is not None:
        dialog_visibility(False)
    try:
        return callback()
    finally:
        if dialog_visibility is not None:
            dialog_visibility(True)


class WindowsSetupServices:
    def __init__(self, application_dir: Path):
        self.application_dir = Path(application_dir).resolve()
        self.resource_dir = self.application_dir / "_internal"
        if not self.resource_dir.is_dir():
            self.resource_dir = self.application_dir

    def is_admin(self) -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    def detect_display_adapters(self) -> list[str]:
        command = (
            "Get-CimInstance Win32_VideoController | "
            "ForEach-Object { ([string]$_.Name) + '|' + ([string]$_.PNPDeviceID) } | ConvertTo-Json -Compress"
        )
        try:
            proc = _run_hidden(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                timeout=30,
            )
            if proc.returncode != 0:
                return []
            value = json.loads((proc.stdout or "null").strip() or "null")
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return [str(item) for item in value if item]
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            pass
        return []

    def system_boot_marker(self) -> str:
        command = (
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime()."
            "ToString('o')"
        )
        try:
            proc = _run_hidden(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                timeout=30,
            )
            if proc.returncode == 0:
                return str(proc.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return ""

    def verify_backends(self) -> CommandResult:
        script = self.application_dir / "check_backends.bat"
        if not script.is_file():
            return CommandResult(False, f"后端检查脚本不存在：\n{script}")
        try:
            proc = _run_hidden(["cmd.exe", "/d", "/c", str(script), "/verify-only"], timeout=180)
            return CommandResult(proc.returncode == 0, _command_text(proc))
        except (OSError, subprocess.SubprocessError) as exc:
            return CommandResult(False, str(exc))

    def cuda_available(self) -> CommandResult:
        worker = self.resource_dir / "NewLight_Worker.exe"
        if not worker.is_file():
            return CommandResult(False, f"冻结后台执行器不存在：\n{worker}")
        code = (
            "import torch; ok=bool(torch.cuda.is_available()); "
            "print('CUDA_AVAILABLE=' + str(ok)); "
            "print(torch.cuda.get_device_name(0) if ok else ''); "
            "raise SystemExit(0 if ok else 2)"
        )
        try:
            proc = _run_hidden([str(worker), "-c", code], timeout=90)
            return CommandResult(proc.returncode == 0, _command_text(proc))
        except (OSError, subprocess.SubprocessError) as exc:
            return CommandResult(False, str(exc))

    def install_nvidia_driver(self) -> CommandResult:
        script = self.application_dir / "check_backends.bat"
        try:
            proc = _run_hidden(
                ["cmd.exe", "/d", "/c", str(script), "/install-gpu-driver"],
                timeout=7200,
            )
            return CommandResult(proc.returncode == 0, _command_text(proc))
        except (OSError, subprocess.SubprocessError) as exc:
            return CommandResult(False, str(exc))

    @staticmethod
    def _message_box(title: str, message: str, flags: int) -> int:
        return int(ctypes.windll.user32.MessageBoxW(None, str(message), str(title), flags))

    def ask_yes_no(self, title: str, message: str) -> bool:
        return self._message_box(title, message, 0x00000004 | 0x00000020 | 0x00040000) == 6

    def show_info(self, title: str, message: str) -> None:
        self._message_box(title, message, 0x00000040 | 0x00040000)

    def show_error(self, title: str, message: str) -> None:
        self._message_box(title, message, 0x00000010 | 0x00040000)

    def restart_windows(self) -> None:
        subprocess.Popen(
            ["shutdown.exe", "/r", "/t", "0"],
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )


def ensure_first_run_setup(
    application_dir: Path,
    *,
    state_path: Path | None = None,
    services: SetupServices | None = None,
    progress: ProgressCallback | None = None,
    dialog_visibility: VisibilityCallback | None = None,
) -> bool:
    state_path = Path(state_path) if state_path is not None else default_state_path()
    if setup_is_complete(state_path):
        return True

    services = services or WindowsSetupServices(application_dir)
    if not services.is_admin():
        _show_dialog(
            dialog_visibility,
            lambda: services.show_error(
                "NewLight_Analysis 首次初始化",
                "本机尚未完成 NewLight_Analysis 首次初始化。\n\n"
                "请关闭本提示，右键 NewLight_Analysis.exe，选择“以管理员身份运行”。\n"
                "管理员权限仅用于首次后端检查和显卡驱动安装；初始化完成后可普通启动。",
            ),
        )
        return False

    _emit(progress, "正在验证分析后端...")
    backend = services.verify_backends()
    if not backend.ok:
        _show_dialog(
            dialog_visibility,
            lambda: services.show_error(
                "首次初始化失败",
                "软件内置后端或模型检查未通过，无法继续初始化。\n\n" + backend.diagnostic,
            ),
        )
        return False

    _emit(progress, "正在读取系统启动状态...")
    state = read_setup_state(state_path)
    current_boot_marker = services.system_boot_marker()
    if state.get("status") == "pending_restart" and state.get("boot_marker") == current_boot_marker:
        _show_dialog(
            dialog_visibility,
            lambda: services.show_info(
                "等待重启",
                "NVIDIA 显卡驱动已在本次 Windows 启动期间安装。请先重启系统，再次以管理员身份启动 NewLight_Analysis 完成 CUDA 验证。",
            ),
        )
        return False

    _emit(progress, "正在检测图形设备...")
    adapters = services.detect_display_adapters()
    if not adapters:
        _show_dialog(
            dialog_visibility,
            lambda: services.show_error(
                "显卡检测失败",
                "Windows 未返回任何显示适配器信息，无法可靠判断 NVIDIA、AMD 或 Intel 显卡类型。\n\n"
                "请确认 Windows Management Instrumentation (WMI) 服务正常，然后再次以管理员身份启动。",
            ),
        )
        return False
    if not has_nvidia_adapter(adapters):
        write_setup_state(state_path, "complete_cpu_only", adapters, current_boot_marker)
        detected = "\n".join(adapters) if adapters else "未检测到 NVIDIA 显卡"
        _emit(progress, "运行环境检测完成")
        _show_dialog(
            dialog_visibility,
            lambda: services.show_info(
                "CPU 模式初始化完成",
                "当前电脑未检测到 NVIDIA 显卡，已跳过 GPU/CUDA 驱动安装。\n\n"
                f"检测结果：\n{detected}\n\n"
                "DeepCAD-RT 降噪等 CUDA 专用功能不可用；支持 CPU 的预处理、分析和快速 ROI 功能仍可使用。",
            ),
        )
        return True

    _emit(progress, "正在检查 CUDA 状态...")
    cuda = services.cuda_available()
    if cuda.ok:
        write_setup_state(state_path, "complete_cuda", adapters, current_boot_marker)
        _emit(progress, "运行环境检测完成")
        return True

    install = _show_dialog(
        dialog_visibility,
        lambda: services.ask_yes_no(
            "补全 NVIDIA GPU/CUDA 环境",
            "检测到 NVIDIA 显卡，但当前驱动不能让软件使用 CUDA。\n\n"
            "是否立即通过 Windows Update 自动匹配并安装适用于本机的已签名 NVIDIA 显卡驱动？\n"
            "软件不会安装完整 CUDA Toolkit。安装可能需要较长时间，完成后通常需要重启。",
        ),
    )
    if not install:
        _show_dialog(
            dialog_visibility,
            lambda: services.show_info(
                "初始化未完成",
                "已取消 NVIDIA 驱动安装。NewLight_Analysis 将退出；下次请再次以管理员身份启动以完成初始化。",
            ),
        )
        return False

    _emit(progress, "正在安装 NVIDIA 显卡驱动...")
    driver = services.install_nvidia_driver()
    if not driver.ok:
        _show_dialog(
            dialog_visibility,
            lambda: services.show_error(
                "NVIDIA 驱动安装失败",
                "Windows Update 未能完成匹配驱动的安装，本机仍未完成初始化。\n\n" + driver.diagnostic,
            ),
        )
        return False

    write_setup_state(state_path, "pending_restart", adapters, current_boot_marker)
    restart_now = _show_dialog(
        dialog_visibility,
        lambda: services.ask_yes_no(
            "NVIDIA 驱动安装完成",
            "匹配的 NVIDIA 显卡驱动已安装。必须重启 Windows 后才能重新检测 CUDA。\n\n是否立即重启？",
        ),
    )
    if restart_now:
        services.restart_windows()
    else:
        _show_dialog(
            dialog_visibility,
            lambda: services.show_info(
                "等待重启",
                "请在方便时手动重启 Windows。重启后再次以管理员身份启动 NewLight_Analysis 完成 CUDA 验证。",
            ),
        )
    return False


def ensure_application_setup(
    application_dir: Path,
    *,
    state_path: Path | None = None,
    services: SetupServices | None = None,
    progress: ProgressCallback | None = None,
    dialog_visibility: VisibilityCallback | None = None,
) -> bool:
    if not getattr(sys, "frozen", False):
        return True
    return ensure_first_run_setup(
        application_dir,
        state_path=state_path,
        services=services,
        progress=progress,
        dialog_visibility=dialog_visibility,
    )
