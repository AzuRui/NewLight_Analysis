from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol


SETUP_VERSION = 1
COMPLETE_STATUSES = {"complete_cuda", "complete_cpu_only", "pending_restart"}
STATE_FILE_NAME = "machine_setup_v1.json"
GPU_ADDON_DIR_NAME = "GPU_Addon"
GPU_ADDON_MANIFEST = "gpu_addon_manifest.json"
LEGACY_GPU_ADDON_MANIFEST = "deepcad_addon_manifest.json"
# Kept as aliases for callers from builds made before the unified GPU addon.
DEEPCAD_ADDON_DIR_NAME = GPU_ADDON_DIR_NAME
DEEPCAD_ADDON_MANIFEST = GPU_ADDON_MANIFEST
CREATE_NO_WINDOW = 0x08000000
ProgressCallback = Callable[[str], None]
VisibilityCallback = Callable[[bool], None]
# A long download/install reports one progress line per window, and a rate is only
# printed once at least this many seconds have been measured.
PROGRESS_WINDOW_SECONDS = 2.0
MEASURABLE_RATE_WINDOW_SECONDS = 0.05


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


def setup_log_path() -> Path:
    """Log file that records setup stages when nobody is listening to progress."""
    return machine_data_dir() / "setup_progress.log"


def _file_logging_progress(log_path: Path) -> ProgressCallback:
    def _record(message: str) -> None:
        try:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with Path(log_path).open("a", encoding="utf-8") as handle:
                handle.write(f"{stamp} {message}\n")
        except OSError:
            # Diagnostics must never be the reason initialization fails.
            pass

    return _record


def _human_size(num_bytes: float) -> str:
    """Format a byte count for console output (base 1024, one decimal)."""
    value = max(float(num_bytes), 0.0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def _rate_text(bytes_done: float, seconds: float) -> str:
    """Format throughput for a progress line.

    A window shorter than ``MEASURABLE_RATE_WINDOW_SECONDS`` cannot produce an honest
    number, so the line says so instead of inventing a rate (an instant cache-hot read
    once displayed "976.6 GB/s", which reads exactly like a broken meter).
    """
    if seconds < MEASURABLE_RATE_WINDOW_SECONDS:
        return "速率测量中"
    return f"{_human_size(bytes_done / seconds)}/s"


def _describe_setup_error(exc: BaseException) -> str:
    """Turn a download/extract/copy failure into text the user can act on."""
    if isinstance(exc, urllib.error.HTTPError):
        return (
            f"HTTP {exc.code} {exc.reason}（{exc.url}）；"
            "下载地址被拒绝，通常是网络代理或未登录导致的"
        )
    if isinstance(exc, urllib.error.URLError):
        return f"网络错误：{exc.reason}；请确认这台机器能访问 GitHub 下载域名（必要时配置代理）"
    if isinstance(exc, zipfile.BadZipFile):
        return "缓存的安装包不是有效 ZIP 或已损坏；删除缓存后重新下载"
    if isinstance(exc, OSError):
        code = getattr(exc, "errno", None)
        detail = getattr(exc, "strerror", None) or str(exc)
        where = getattr(exc, "filename", None)
        hint = ""
        if code == 28:
            hint = "；磁盘空间不足，请清理目标盘或改用空间充足的安装目录"
        elif code in (36, 206):
            hint = "；Windows 路径过长，建议把软件安装在靠近盘根的目录"
        elif code in (13, 5):
            hint = "；权限不足，请以管理员身份运行"
        location = f"（{where}）" if where else ""
        return f"文件操作失败 errno={code}：{detail}{location}{hint}"
    return f"{type(exc).__name__}：{exc}"


def _hash_file(
    path: Path,
    *,
    label: str,
    progress: ProgressCallback | None,
    chunk: int = 1024 * 1024,
) -> str:
    """SHA-256 a file, reporting throughput every couple of seconds."""
    digest = hashlib.sha256()
    total = path.stat().st_size
    done = 0
    started = time.monotonic()
    last_emit = started
    with path.open("rb") as source:
        for block in iter(lambda: source.read(chunk), b""):
            digest.update(block)
            done += len(block)
            now = time.monotonic()
            if progress is not None and (now - last_emit >= PROGRESS_WINDOW_SECONDS or done == total):
                _emit(
                    progress,
                    f"校验 {label}：{_human_size(done)}/{_human_size(total)}"
                    f"（{_rate_text(done, now - started)}）",
                )
                last_emit = now
    return digest.hexdigest().lower()


def _stream_to_file(
    source,
    output,
    *,
    label: str,
    progress: ProgressCallback | None,
    total: int | None = None,
    chunk: int = 1024 * 1024,
) -> int:
    """Copy a stream to an open file while reporting throughput and ETA."""
    done = 0
    started = time.monotonic()
    last_emit = started
    while True:
        block = source.read(chunk)
        if not block:
            break
        output.write(block)
        done += len(block)
        now = time.monotonic()
        if progress is not None and now - last_emit >= PROGRESS_WINDOW_SECONDS:
            window = now - started
            rate = done / window if window >= MEASURABLE_RATE_WINDOW_SECONDS else 0.0
            percent = f"（{done * 100 // total}%）" if total else ""
            eta = f"，剩余约 {max(total - done, 0) / rate:.0f}s" if total and rate > 0 else ""
            _emit(
                progress,
                f"下载 {label}：{_human_size(done)}{percent}，"
                f"{_rate_text(done, window)}{eta}",
            )
            last_emit = now
    return done


def _response_length(response) -> int | None:
    value = response.headers.get("Content-Length") if response is not None else None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _download_to(
    destination: Path,
    url: str,
    *,
    label: str,
    progress: ProgressCallback | None,
    cache_dir: Path,
) -> int:
    """Download one URL to disk with byte progress and a pre-flight space check."""
    request = urllib.request.Request(url, headers={"User-Agent": "NewLight_Analysis/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response:
        total = _response_length(response)
        free = shutil.disk_usage(cache_dir).free
        if total and free < total + 512 * 1024 * 1024:
            raise RuntimeError(
                f"下载前磁盘空间不足：{label} 约 {_human_size(total)}，"
                f"缓存目录所在盘剩余 {_human_size(free)}，请清理空间后重试"
            )
        size_text = f"约 {_human_size(total)}" if total else "大小未知"
        _emit(progress, f"开始下载 {label}：{size_text}，缓存盘剩余 {_human_size(free)}")
        with destination.open("wb") as output:
            return _stream_to_file(response, output, label=label, progress=progress, total=total)


def _show_dialog(dialog_visibility: VisibilityCallback | None, callback):
    if dialog_visibility is not None:
        dialog_visibility(False)
    try:
        return callback()
    finally:
        if dialog_visibility is not None:
            dialog_visibility(True)


def _resource_dir(application_dir: Path) -> Path:
    candidate = Path(application_dir) / "_internal"
    return candidate if candidate.is_dir() else Path(application_dir)


def _gpu_addon_ready(addon_dir: Path) -> bool:
    source = addon_dir / "DeepCAD-RT" / "DeepCAD_RT_pytorch" / "deepcad"
    model = addon_dir / "DeepCADRT_Model"
    neusuite_model = addon_dir / "NeuSuite2p" / "segment_model.pt"
    neusuite_runtime = addon_dir / "NeuSuite_RuntimeDeps"
    worker = addon_dir / "NewLight_GPU_Worker.exe"
    return (
        source.is_dir()
        and model.is_dir()
        and any(model.glob("*.pth"))
        and neusuite_model.is_file()
        and neusuite_runtime.is_dir()
        and worker.is_file()
    )


def _sync_gpu_shared_modules(root: Path, addon_dir: Path) -> None:
    """Make core Python helpers available to the isolated GPU worker."""
    source = root / "roi_engines.py"
    if not source.is_file():
        return
    target = addon_dir / source.name
    if not target.is_file() or source.stat().st_size != target.stat().st_size:
        addon_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


# Compatibility for source integrations that imported the old private helper.
_deepcad_addon_ready = _gpu_addon_ready


def inspect_gpu_addon(
    application_dir: Path,
    services: SetupServices,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    """Inspect the optional GPU package without making it a startup gate."""
    root = _resource_dir(Path(application_dir))
    addon_dir = root / GPU_ADDON_DIR_NAME
    _sync_gpu_shared_modules(root, addon_dir)
    if not _gpu_addon_ready(addon_dir):
        message = "GPU 扩展未配置，当前使用 CPU 模式。"
        _emit(progress, message)
        return False, message

    _emit(progress, "正在验证 GPU 扩展...")
    cuda = services.cuda_available()
    if cuda.ok:
        message = "GPU 扩展已配置且 CUDA 可用。"
        _emit(progress, message)
        return True, message
    message = "GPU 扩展已安装，但 CUDA 当前不可用；已切换为 CPU 模式。"
    _emit(progress, message)
    return False, message + (f"\n{cuda.diagnostic}" if cuda.diagnostic else "")


def startup_will_install_gpu_addon(
    application_dir: Path,
    *,
    state_path: Path | None = None,
) -> bool:
    """Whether launching the frozen app is about to download the multi-gigabyte GPU addon.

    ``ensure_first_run_setup`` only installs the extension on the "already complete with
    CUDA" branch, and that branch used to run without a progress display because
    ``launch.py`` only shows the initialization splash for an *incomplete* first run.  The
    launch screen checks this before deciding whether to keep the splash up.
    """
    state_path = Path(state_path) if state_path is not None else default_state_path()
    if not setup_is_complete(state_path):
        return False
    if read_setup_state(state_path).get("status") != "complete_cuda":
        return False
    root = _resource_dir(Path(application_dir))
    if _gpu_addon_ready(root / GPU_ADDON_DIR_NAME):
        return False
    return (root / GPU_ADDON_MANIFEST).is_file() or (root / LEGACY_GPU_ADDON_MANIFEST).is_file()


def ensure_gpu_addon(
    application_dir: Path,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[bool, str]:
    """Download and safely install the unified optional GPU extension."""
    root = _resource_dir(Path(application_dir))
    addon_dir = root / GPU_ADDON_DIR_NAME
    _sync_gpu_shared_modules(root, addon_dir)
    if _gpu_addon_ready(addon_dir):
        _emit(progress, f"统一 GPU 扩展已安装：{addon_dir}")
        return True, "统一 GPU 扩展已安装。"

    _emit(progress, f"统一 GPU 扩展未安装，目标目录：{addon_dir}")
    manifest_path = root / GPU_ADDON_MANIFEST
    if not manifest_path.is_file():
        legacy_manifest = root / LEGACY_GPU_ADDON_MANIFEST
        if legacy_manifest.is_file():
            manifest_path = legacy_manifest
    if not manifest_path.is_file():
        return False, f"未找到统一 GPU 扩展清单：{manifest_path}"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"GPU 扩展清单无法读取：{exc}"
    url = str(manifest.get("url", "")).strip()
    expected_hash = str(manifest.get("sha256", "")).strip().lower()
    parts = manifest.get("parts")
    if parts and not isinstance(parts, list):
        return False, "GPU 扩展清单的 parts 必须是列表。"
    if not parts and (not url or not expected_hash or len(expected_hash) != 64):
        return False, "GPU 扩展清单缺少有效下载地址或 SHA-256。"
    if parts:
        for part in parts:
            if (
                not isinstance(part, dict)
                or not str(part.get("url", "")).strip()
                or len(str(part.get("sha256", "")).strip()) != 64
            ):
                return False, "GPU 扩展清单包含无效的分段下载信息。"
    archive_hash = str(manifest.get("archive_sha256", expected_hash) or "").strip().lower()
    if len(archive_hash) != 64:
        return False, "GPU 扩展清单缺少有效的安装包 SHA-256。"

    cache_dir = Path(os.environ.get("PROGRAMDATA", tempfile.gettempdir())) / "NewLight_Analysis"
    archive_path = cache_dir / "GPU_Addon_CUDA.zip"
    temporary_archive = archive_path.with_suffix(".zip.part")
    part_paths: list[Path] = []
    install_started = time.monotonic()
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _emit(progress, f"下载缓存目录：{cache_dir}")
        _emit(progress, f"清单要求的安装包 SHA-256：{archive_hash}")

        archive_ready = False
        if archive_path.is_file():
            _emit(
                progress,
                f"发现缓存安装包（{_human_size(archive_path.stat().st_size)}），先校验 SHA-256…",
            )
            archive_ready = _hash_file(archive_path, label="缓存安装包", progress=progress) == archive_hash
            _emit(
                progress,
                "缓存校验通过，跳过下载。" if archive_ready else "缓存与清单不一致，将重新下载并覆盖。",
            )

        if not archive_ready:
            if parts:
                for index, part in enumerate(parts, start=1):
                    part_path = cache_dir / f"GPU_Addon_CUDA.zip.part{index:02d}"
                    part_hash = str(part["sha256"]).strip().lower()
                    part_paths.append(part_path)
                    if part_path.is_file() and (
                        _hash_file(part_path, label=f"分段 {index}", progress=progress) == part_hash
                    ):
                        _emit(progress, f"分段 {index} 已有校验通过的缓存，跳过下载。")
                        continue
                    _download_to(
                        part_path,
                        str(part["url"]).strip(),
                        label=f"分段 {index}/{len(parts)}",
                        progress=progress,
                        cache_dir=cache_dir,
                    )
                    if _hash_file(part_path, label=f"分段 {index}", progress=progress) != part_hash:
                        return False, f"GPU 扩展分段 {index} SHA-256 校验失败，已拒绝安装。"
                needed = sum(path.stat().st_size for path in part_paths if path.is_file())
                free = shutil.disk_usage(cache_dir).free
                if free < needed + 512 * 1024 * 1024:
                    raise RuntimeError(
                        f"合并分段需要约 {_human_size(needed)}，缓存盘剩余 {_human_size(free)}，"
                        "请清理空间后重试"
                    )
                _emit(progress, f"正在合并 {len(part_paths)} 个分段为完整安装包（{_human_size(needed)}）…")
                with temporary_archive.open("wb") as output:
                    for part_path in part_paths:
                        _emit(progress, f"合并 {part_path.name}")
                        with part_path.open("rb") as source:
                            _stream_to_file(
                                source,
                                output,
                                label=part_path.name,
                                progress=progress,
                                total=part_path.stat().st_size,
                            )
            else:
                _download_to(
                    temporary_archive,
                    url,
                    label="安装包",
                    progress=progress,
                    cache_dir=cache_dir,
                )
            if _hash_file(temporary_archive, label="新下载安装包", progress=progress) != archive_hash:
                return False, "GPU 扩展 SHA-256 校验失败，已拒绝安装。"
            temporary_archive.replace(archive_path)

        staging = Path(tempfile.mkdtemp(prefix="newlight_gpu_addon_"))
        try:
            with zipfile.ZipFile(archive_path) as archive:
                members = archive.infolist()
                payload_bytes = sum(int(member.file_size) for member in members)
                staging_root = staging.resolve()
                for member in members:
                    destination = (staging / member.filename).resolve()
                    if destination != staging_root and staging_root not in destination.parents:
                        raise RuntimeError("GPU 扩展包含非法压缩路径。")
                free_staging = shutil.disk_usage(staging).free
                free_target = shutil.disk_usage(addon_dir.parent).free
                _emit(
                    progress,
                    f"正在安装统一 GPU 扩展：{len(members)} 个条目，解压后约 {_human_size(payload_bytes)}；"
                    f"临时目录剩余 {_human_size(free_staging)}，安装目录剩余 {_human_size(free_target)}",
                )
                if payload_bytes and min(free_staging, free_target) < payload_bytes + 512 * 1024 * 1024:
                    raise RuntimeError(
                        f"磁盘空间不足：解压和安装各需约 {_human_size(payload_bytes)}，"
                        f"临时目录剩余 {_human_size(free_staging)}，"
                        f"安装目录剩余 {_human_size(free_target)}；请清理空间，"
                        "或把软件安装到剩余空间充足的磁盘"
                    )
                extract_started = time.monotonic()
                last_emit = extract_started
                for index, member in enumerate(members, start=1):
                    archive.extract(member, staging)
                    now = time.monotonic()
                    if progress is not None and now - last_emit >= PROGRESS_WINDOW_SECONDS:
                        _emit(progress, f"解压：{index}/{len(members)} 项，已用 {now - extract_started:.0f}s")
                        last_emit = now
                _emit(progress, f"解压完成，耗时 {time.monotonic() - extract_started:.1f}s")

            extracted = staging / GPU_ADDON_DIR_NAME
            if not extracted.is_dir():
                extracted = staging
            if not _gpu_addon_ready(extracted):
                return False, "GPU 扩展解压后缺少 Worker、DeepCAD 或 NeuSuite 组件。"
            addon_dir.mkdir(parents=True, exist_ok=True)
            items = sorted(extracted.iterdir(), key=lambda item: item.name)
            copy_state = {
                "files": 0,
                "bytes": 0,
                "started": time.monotonic(),
                "last": time.monotonic(),
                "index": 0,
                "name": "",
            }
            _emit(
                progress,
                f"正在复制 {len(items)} 个顶层条目到 {addon_dir}"
                f"（约 {_human_size(payload_bytes)}）",
            )

            def _copy_and_report(source_file, destination_file) -> None:
                shutil.copy2(source_file, destination_file)
                try:
                    copy_state["bytes"] += Path(source_file).stat().st_size
                except OSError:
                    pass
                copy_state["files"] += 1
                now = time.monotonic()
                if progress is not None and now - copy_state["last"] >= PROGRESS_WINDOW_SECONDS:
                    _emit(
                        progress,
                        f"复制：第 {copy_state['index']}/{len(items)} 项"
                        f"（{copy_state['name']}），{copy_state['files']} 个文件 / "
                        f"{_human_size(copy_state['bytes'])}"
                        f"（{_rate_text(copy_state['bytes'], now - copy_state['started'])}）",
                    )
                    copy_state["last"] = now

            for position, item in enumerate(items, start=1):
                target = addon_dir / item.name
                copy_state["index"] = position
                copy_state["name"] = item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True, copy_function=_copy_and_report)
                else:
                    _copy_and_report(item, target)
            _sync_gpu_shared_modules(root, addon_dir)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        if not _gpu_addon_ready(addon_dir):
            return False, f"扩展文件已复制，但完整性检查仍未通过：{addon_dir}"
        message = "统一 GPU 扩展安装完成。"
        _emit(progress, f"{message} 总耗时 {time.monotonic() - install_started:.1f}s")
        return True, message
    except (OSError, urllib.error.URLError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        reason = f"GPU 扩展下载或安装失败：{_describe_setup_error(exc)}"
        _emit(progress, reason)
        if isinstance(exc, zipfile.BadZipFile):
            try:
                archive_path.unlink(missing_ok=True)
                _emit(progress, f"已删除损坏的缓存安装包：{archive_path}")
            except OSError:
                pass
        return False, reason
    finally:
        temporary_archive.unlink(missing_ok=True)
        for part_path in part_paths:
            part_path.unlink(missing_ok=True)


# Public compatibility alias for older integrations and saved scripts.
ensure_deepcad_addon = ensure_gpu_addon


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
        gpu_worker = self.resource_dir / GPU_ADDON_DIR_NAME / "NewLight_GPU_Worker.exe"
        if gpu_worker.is_file():
            worker = gpu_worker
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

        # The CPU core cannot import CUDA Torch. NVIDIA's driver utility is a
        # sufficient preflight signal to allow the first-run GPU addon download.
        try:
            proc = _run_hidden(["nvidia-smi.exe", "-L"], timeout=30)
            if proc.returncode == 0 and _command_text(proc):
                return CommandResult(True, "NVIDIA driver detected; GPU addon is not installed yet.")
        except (OSError, subprocess.SubprocessError):
            pass
        return CommandResult(False, "NVIDIA driver/CUDA runtime is not available.")

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
    services = services or WindowsSetupServices(application_dir)
    if setup_is_complete(state_path):
        state = read_setup_state(state_path)
        addon_ready, _ = inspect_gpu_addon(application_dir, services, progress=progress)
        if addon_ready and state.get("status") != "complete_cuda":
            write_setup_state(
                state_path,
                "complete_cuda",
                state.get("display_adapters", []),
                state.get("boot_marker", ""),
            )
        elif not addon_ready and state.get("status") == "complete_cuda":
            addon_ok, addon_message = ensure_gpu_addon(application_dir, progress=progress)
            if not addon_ok:
                _emit(progress, f"统一 GPU 扩展未安装，已跳过。原因：{addon_message}")
        if state.get("status") == "pending_restart":
            _show_dialog(
                dialog_visibility,
                lambda: services.show_info(
                    "等待重启",
                    "NVIDIA 显卡驱动已安装但尚未完成重启验证。当前将以 CPU 模式进入软件；您可以稍后重启 Windows。",
                ),
            )
        return True
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
                "NVIDIA 显卡驱动已在本次 Windows 启动期间安装。当前将以 CPU 模式进入软件；请稍后重启系统以重新检测 CUDA。",
            ),
        )
        return True

    _emit(progress, "正在检测图形设备...")
    adapters = services.detect_display_adapters()
    if not adapters:
        write_setup_state(state_path, "complete_cpu_only", [], current_boot_marker)
        _emit(progress, "运行环境检测完成：CPU 模式")
        _show_dialog(
            dialog_visibility,
            lambda: services.show_info(
                "显卡检测未完成",
                "Windows 未返回显示适配器信息，软件将以 CPU 模式继续启动。\n\n"
                "GPU 专用功能暂不可用，您可以稍后检查 Windows Management Instrumentation (WMI) 服务和显卡驱动。",
            ),
        )
        return True
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
        addon_ok, addon_message = ensure_gpu_addon(application_dir, progress=progress)
        write_setup_state(state_path, "complete_cuda", adapters, current_boot_marker)
        _emit(progress, "运行环境检测完成")
        if not addon_ok:
            _show_dialog(
                dialog_visibility,
                lambda: services.show_info(
                    "统一 GPU 扩展未安装",
                    addon_message + "\n\n普通分析和不依赖 DeepCAD-RT 的功能仍可使用。",
                ),
            )
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
        write_setup_state(state_path, "complete_cpu_only", adapters, current_boot_marker)
        _show_dialog(
            dialog_visibility,
            lambda: services.show_info(
                "以 CPU 模式继续",
                "已取消 NVIDIA 驱动安装。NewLight_Analysis 将继续启动；DeepCAD-RT 和快速 GPU ROI 等 CUDA 功能暂不可用。",
            ),
        )
        return True

    _emit(progress, "正在安装 NVIDIA 显卡驱动...")
    driver = services.install_nvidia_driver()
    if not driver.ok:
        write_setup_state(state_path, "complete_cpu_only", adapters, current_boot_marker)
        _show_dialog(
            dialog_visibility,
            lambda: services.show_error(
                "NVIDIA 驱动安装失败",
                "Windows Update 未能完成匹配驱动的安装。软件将以 CPU 模式继续启动，GPU 专用功能暂不可用。\n\n"
                + driver.diagnostic,
            ),
        )
        return True

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
                "请在方便时手动重启 Windows。软件现在会以 CPU 模式继续运行，并在后续每次启动时重新检查 GPU 扩展状态。",
            ),
        )
    return True


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
    if progress is None:
        # A frozen launch that passes no callback would otherwise download and install
        # the GPU addon in complete silence; keep the stages in the machine log instead.
        progress = _file_logging_progress(setup_log_path())
    return ensure_first_run_setup(
        application_dir,
        state_path=state_path,
        services=services,
        progress=progress,
        dialog_visibility=dialog_visibility,
    )
