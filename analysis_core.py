from __future__ import annotations

import colorsys
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile
from scipy import ndimage, signal
from scipy.ndimage import gaussian_filter
from skimage import exposure, filters, measure, morphology, restoration
from PIL import Image

from roi_engines import ROIArtifactError, load_roi_artifact


IS_FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE = PROJECT_DIR.parents[0]
APP_RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
APP_EXEC_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else PROJECT_DIR
WORKER_DIR = APP_RESOURCE_DIR / "workers" if (APP_RESOURCE_DIR / "workers").exists() else PROJECT_DIR / "workers"


def resource_dir(relative: str | Path, fallback: Path) -> Path:
    bundled = APP_RESOURCE_DIR / Path(relative)
    return bundled if bundled.exists() else fallback


NEUROSEG3_DIR = resource_dir("NeuroSeg3", WORKSPACE / "NeuroSeg3")
NEUROALIGN_DIR = resource_dir("NeuroAlign", WORKSPACE / "2cafe_analysis" / "NeuroAlign")
DEEPCADRT_DIR = resource_dir(Path("DeepCAD-RT") / "DeepCAD_RT_pytorch", WORKSPACE / "DeepCAD-RT" / "DeepCAD_RT_pytorch")
DEEPCADRT_MODEL_DIR = APP_RESOURCE_DIR / "DeepCADRT_Model"
DEEPCADRT_DEFAULT_MODEL_FILE = DEEPCADRT_MODEL_DIR / "E_02_Iter_6416.pth"
NEUSUITE_DIR = resource_dir("NeuSuite2p", WORKSPACE / "NeuSuite2p")
NEUSUITE_DEFAULT_WEIGHTS = NEUSUITE_DIR / "segment_model.pt"
NEUSUITE_RUNTIME_ROOT = NEUSUITE_DIR / "method"
CAIMAN_RESOURCE_DIR = resource_dir("CaImAn_Resources", PROJECT_DIR / "CaImAn_Resources")
NEWLIGHT_CAIMAN_PREFIX = PROJECT_DIR / ".conda_envs" / "newlight_caiman"
_CUPY_CACHE = None


def hidden_subprocess_kwargs() -> dict[str, object]:
    if os.name != "nt":
        return {}
    kwargs: dict[str, object] = {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags
    startupinfo_cls = getattr(subprocess, "STARTUPINFO", None)
    if startupinfo_cls is not None:
        startupinfo = startupinfo_cls()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 1)
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    return kwargs


@dataclass
class AnalysisState:
    movie: np.ndarray | None = None
    display_image: np.ndarray | None = None
    baseline_image: np.ndarray | None = None
    dff_movie: np.ndarray | None = None
    roi_masks: list[np.ndarray] = field(default_factory=list)
    roi_names: list[str] = field(default_factory=list)
    roi_metadata: list[dict] = field(default_factory=list)
    roi_revision: int = 0
    traces: np.ndarray | None = None
    stimulus: np.ndarray | None = None
    trigger_frames: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    fs: float = 10.0
    stimulus_fs: float = 2000.0
    invalid_start_frames: int = 0
    baseline_start_frame: int = 0
    baseline_duration_frames: int = 0
    pre_trigger_s: float = 0.0
    post_trigger_s: float = 0.0
    source_path: str = ""
    import_bit_depth: str = "auto"
    converted_color_avi_path: str = ""
    converted_source_folder: str = ""
    converted_channel_avi_paths: tuple[str, ...] = field(default_factory=tuple)
    converted_channel_movies: tuple[np.ndarray, ...] = field(default_factory=tuple)
    channel_colors: tuple[str, ...] = field(default_factory=tuple)
    history: list[tuple] = field(default_factory=list)
    last_message: str = ""


@dataclass(frozen=True)
class ROIBackendResult:
    masks: np.ndarray
    names: list[str]
    metadata: dict
    arrays: dict[str, np.ndarray]
    log: str
    artifact_path: Path
    summary_path: Path


@dataclass(frozen=True)
class TwoPhotonProtocol:
    folder: Path
    width: int
    height: int
    frame_rate: float
    recording_time_s: float
    expected_frames: int
    channels: tuple[str, ...]
    values: dict[str, str] = field(default_factory=dict)


@dataclass
class ConvertedTwoPhotonMovie:
    movie: np.ndarray
    channel_movies: tuple[np.ndarray, ...]
    fs: float
    color_avi_path: Path | None
    channel_avi_paths: tuple[Path, ...]
    source_folder: Path
    protocol: TwoPhotonProtocol
    frames: int
    channel_count: int
    interlacing_shift_px: int = 0
    interlacing_search_range: int = 0


@dataclass(frozen=True)
class StimulusFileData:
    signal: np.ndarray
    fs: float | None = None
    column_name: str = ""
    columns: tuple[str, ...] = field(default_factory=tuple)
    sample_count: int = 0


def get_cupy():
    global _CUPY_CACHE
    if _CUPY_CACHE is False:
        return None
    if _CUPY_CACHE is not None:
        return _CUPY_CACHE
    try:
        import cupy as cp

        _ = cp.cuda.runtime.getDeviceCount()
        _CUPY_CACHE = cp
        return cp
    except Exception:
        _CUPY_CACHE = False
        return None


def cuda_status(check_neuroseg3: bool = False) -> dict[str, object]:
    status: dict[str, object] = {
        "cupy_available": False,
        "cupy_device": "",
        "torch_cuda_available": False,
        "torch_device": "",
        "opencv_cuda_devices": 0,
        "neuroseg3_cuda_available": None,
        "neuroseg3_device": "",
    }
    cp = get_cupy()
    if cp is not None:
        try:
            status["cupy_available"] = cp.cuda.runtime.getDeviceCount() > 0
            if status["cupy_available"]:
                props = cp.cuda.runtime.getDeviceProperties(0)
                name = props.get("name", b"")
                status["cupy_device"] = name.decode("utf-8", "ignore") if isinstance(name, bytes) else str(name)
        except Exception:
            pass
    try:
        import torch

        status["torch_cuda_available"] = bool(torch.cuda.is_available())
        if status["torch_cuda_available"]:
            status["torch_device"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    try:
        status["opencv_cuda_devices"] = int(cv2.cuda.getCudaEnabledDeviceCount())
    except Exception:
        pass
    if check_neuroseg3:
        try:
            proc = subprocess.run(
                ["conda", "run", "-n", "neuroseg3", "python", "-c", "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"],
                capture_output=True,
                text=True,
                timeout=30,
                **hidden_subprocess_kwargs(),
            )
            lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
            status["neuroseg3_cuda_available"] = bool(lines and lines[0].lower() == "true")
            if len(lines) > 1:
                status["neuroseg3_device"] = lines[1]
        except Exception:
            status["neuroseg3_cuda_available"] = False
    return status


def acceleration_label(acceleration: str = "auto") -> str:
    cp = get_cupy()
    if acceleration == "gpu" and cp is None:
        return "已请求 GPU，但 CuPy 不可用；当前使用 CPU"
    if acceleration in {"auto", "gpu"} and cp is not None:
        try:
            props = cp.cuda.runtime.getDeviceProperties(0)
            name = props.get("name", b"GPU")
            name = name.decode("utf-8", "ignore") if isinstance(name, bytes) else str(name)
            return f"GPU/CuPy: {name}"
        except Exception:
            return "GPU/CuPy"
    return "CPU/NumPy"


def normalize_image(image: np.ndarray, p_low: float = 1, p_high: float = 99) -> np.ndarray:
    arr = np.asarray(image, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros_like(arr, dtype=np.float32)
    lo, hi = np.percentile(finite, [p_low, p_high])
    if hi <= lo:
        lo, hi = float(np.min(finite)), float(np.max(finite))
    if hi <= lo:
        return np.zeros_like(arr, dtype=np.float32)
    return np.clip((arr - lo) / (hi - lo), 0, 1).astype(np.float32)


def normalized_display_controls(
    shadows: float = 1.0,
    highlights: float = 99.0,
    brightness: float = 0.0,
    contrast: float = 100.0,
) -> tuple[float, float, float, float]:
    """Clamp display controls to stable, user-facing ranges."""
    low = float(np.clip(float(shadows), 0.0, 99.9))
    high = float(np.clip(float(highlights), 0.1, 100.0))
    if high <= low:
        high = min(100.0, low + 0.1)
    return low, high, float(np.clip(float(brightness), -100.0, 100.0)), float(np.clip(float(contrast), 0.0, 300.0))


def movie_display_limits(
    movie: np.ndarray,
    shadows: float = 1.0,
    highlights: float = 99.0,
    overlay_movie: np.ndarray | None = None,
    overlay_weight: float = 0.0,
    max_sample_frames: int = 64,
) -> tuple[float, float]:
    """Return stable intensity limits for preview and 8-bit AVI rendering.

    Sampling evenly through the time axis avoids materializing a second full
    movie when a DeepCAD-RT blend is being displayed.
    """
    arr = np.asarray(movie, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[None, :, :]
    if arr.ndim != 3 or arr.shape[0] == 0:
        return 0.0, 1.0
    indices = np.unique(np.linspace(0, arr.shape[0] - 1, min(arr.shape[0], max(1, int(max_sample_frames))), dtype=int))
    sample = arr[indices]
    if overlay_movie is not None:
        other = np.asarray(overlay_movie, dtype=np.float32)
        if other.shape != arr.shape:
            raise ValueError(f"显示融合 shape 不一致：{arr.shape} 与 {other.shape}")
        weight = float(np.clip(float(overlay_weight), 0.0, 1.0))
        sample = (1.0 - weight) * sample + weight * other[indices]
    finite = sample[np.isfinite(sample)]
    if finite.size == 0:
        return 0.0, 1.0
    low_pct, high_pct, _brightness, _contrast = normalized_display_controls(shadows, highlights)
    lo, hi = np.percentile(finite, [low_pct, high_pct])
    if hi <= lo:
        lo, hi = float(np.min(finite)), float(np.max(finite))
    if hi <= lo:
        hi = lo + 1.0
    return float(lo), float(hi)


def render_grayscale_display(
    image: np.ndarray,
    limits: tuple[float, float],
    brightness: float = 0.0,
    contrast: float = 100.0,
) -> np.ndarray:
    """Map a grayscale image to the exact 8-bit view used by AVI export."""
    lo, hi = float(limits[0]), float(limits[1])
    _shadows, _highlights, brightness, contrast = normalized_display_controls(1.0, 99.0, brightness, contrast)
    if hi <= lo:
        hi = lo + 1.0
    values = np.asarray(image, dtype=np.float32)
    normalized = np.clip((values - lo) / (hi - lo), 0.0, 1.0)
    normalized = (normalized - 0.5) * (contrast / 100.0) + 0.5 + brightness / 100.0
    return np.rint(np.clip(normalized, 0.0, 1.0) * 255.0).astype(np.uint8)


def render_rgb_display(
    image: np.ndarray,
    shadows: float = 1.0,
    highlights: float = 99.0,
    brightness: float = 0.0,
    contrast: float = 100.0,
) -> np.ndarray:
    """Apply the four display controls to an RGB display/export image."""
    low_pct, high_pct, brightness, contrast = normalized_display_controls(shadows, highlights, brightness, contrast)
    arr = np.asarray(image, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[-1] != 3:
        raise ValueError(f"需要 RGB 图像，实际 shape 为 {arr.shape}")
    if np.nanmax(arr) <= 1.0:
        arr = arr * 255.0
    low = low_pct / 100.0
    high = high_pct / 100.0
    normalized = np.clip((arr / 255.0 - low) / max(1e-6, high - low), 0.0, 1.0)
    normalized = (normalized - 0.5) * (contrast / 100.0) + 0.5 + brightness / 100.0
    return np.rint(np.clip(normalized, 0.0, 1.0) * 255.0).astype(np.uint8)


def to_uint8(image: np.ndarray) -> np.ndarray:
    return (normalize_image(image) * 255).astype(np.uint8)


def normalized_movie_bit_depth(bit_depth: str | None) -> str:
    raw = "auto" if bit_depth is None else str(bit_depth).strip().lower()
    raw = raw.replace(" ", "").replace("_", "-")
    aliases = {
        "auto": "auto",
        "preserve": "auto",
        "native": "auto",
        "original": "auto",
        "8": "8-bit",
        "8bit": "8-bit",
        "8-bit": "8-bit",
        "uint8": "8-bit",
        "16": "16-bit",
        "16bit": "16-bit",
        "16-bit": "16-bit",
        "uint16": "16-bit",
    }
    if raw in aliases:
        return aliases[raw]
    raise ValueError(f"不支持的位深模式：{bit_depth}")


def _movie_to_8bit_stack(movie: np.ndarray) -> np.ndarray:
    arr = np.asarray(movie)
    if arr.ndim == 2:
        arr = arr[None, :, :]
    if arr.ndim != 3:
        raise ValueError(f"需要三维视频堆栈，实际 shape 为 {arr.shape}")
    if arr.dtype == np.uint8:
        return arr.astype(np.float32, copy=False)
    arr32 = arr.astype(np.float32, copy=False)
    if np.issubdtype(arr.dtype, np.integer):
        info = np.iinfo(arr.dtype)
        scale = float(info.max - info.min)
        if scale <= 0:
            return np.zeros(arr.shape, dtype=np.float32)
        arr32 = np.clip(arr32 - float(info.min), 0.0, scale)
        return np.rint(arr32 * (255.0 / scale)).astype(np.float32)
    finite = arr32[np.isfinite(arr32)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype=np.float32)
    lo, hi = float(np.min(finite)), float(np.max(finite))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.float32)
    return np.rint(np.clip((arr32 - lo) / (hi - lo), 0.0, 1.0) * 255.0).astype(np.float32)


def _valid_frame_rate(value: object, default: float | None = None) -> float | None:
    try:
        fps = float(value)
    except (TypeError, ValueError):
        return default
    return fps if np.isfinite(fps) and fps > 0 else default


def _nearby_protocol_frame_rate(path: Path) -> float | None:
    for protocol_path in sorted(path.parent.glob("protocol*.txt")):
        text = None
        for encoding in ("gbk", "utf-8", "latin1"):
            try:
                text = protocol_path.read_text(encoding=encoding)
                break
            except (OSError, UnicodeError):
                continue
        if text is None:
            continue
        match = re.search(r"^\s*Image frame rate\s*:\s*([-+]?\d+(?:\.\d+)?)", text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            fps = _valid_frame_rate(match.group(1))
            if fps is not None:
                return fps
    return None


def _tiff_frame_rate(tif: tifffile.TiffFile, path: Path) -> float:
    metadata = tif.imagej_metadata or {}
    fps = _valid_frame_rate(metadata.get("fps"))
    if fps is not None:
        return fps
    frame_interval = _valid_frame_rate(metadata.get("finterval"))
    if frame_interval is not None:
        return 1.0 / frame_interval
    ome_metadata = tif.ome_metadata or ""
    match = re.search(r'\bTimeIncrement="([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"', ome_metadata)
    if match:
        frame_interval = _valid_frame_rate(match.group(1))
        if frame_interval is not None:
            return 1.0 / frame_interval
    return _nearby_protocol_frame_rate(path) or 10.0


def load_movie(path: str, max_preview_frames: int | None = None, bit_depth: str = "auto") -> tuple[np.ndarray, float]:
    mode = normalized_movie_bit_depth(bit_depth)
    movie_path = Path(path)
    ext = movie_path.suffix.lower()
    if ext in {".tif", ".tiff"}:
        with tifffile.TiffFile(path) as tif:
            arr = tif.asarray()
            fps = _tiff_frame_rate(tif, movie_path)
        arr = np.asarray(arr)
        if arr.ndim == 2:
            arr = arr[None, :, :]
        if arr.ndim == 3:
            pass
        elif arr.ndim == 4:
            arr = arr[..., 0]
        else:
            raise ValueError(f"不支持的 TIFF shape：{arr.shape}")
        if max_preview_frames and arr.shape[0] > max_preview_frames:
            arr = arr[:max_preview_frames]
        if mode == "8-bit":
            arr = _movie_to_8bit_stack(arr)
        return arr.astype(np.float32), fps
    if ext in {".avi", ".mp4", ".mov", ".mkv"}:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise IOError(f"无法打开视频：{path}")
        fps = _valid_frame_rate(cap.get(cv2.CAP_PROP_FPS), 10.0)
        frames = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
            frames.append(gray.astype(np.float32))
            if max_preview_frames and len(frames) >= max_preview_frames:
                break
        cap.release()
        if not frames:
            raise IOError(f"未能从文件中读取任何帧：{path}")
        movie = np.stack(frames, axis=0)
        if mode == "8-bit" and movie.dtype != np.uint8:
            movie = _movie_to_8bit_stack(movie)
        return movie.astype(np.float32), float(fps)
    raise ValueError(f"不支持的文件类型：{ext}")


def _read_text_with_fallback(path: Path, encodings: tuple[str, ...] = ("gbk", "utf-8", "latin1")) -> str:
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise UnicodeError(f"Cannot read text file {path}: {last_error}")


def _protocol_float(values: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = values.get(key, "")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    return float(match.group(0)) if match else float(default)


def _protocol_int(values: dict[str, str], key: str, default: int = 0) -> int:
    return int(round(_protocol_float(values, key, float(default))))


def _protocol_channels(values: dict[str, str]) -> tuple[str, ...]:
    raw = values.get("Recorded channels", "")
    channels = tuple(dict.fromkeys(f"Ch{ch[-1]}" for ch in re.findall(r"Ch[12]", raw, flags=re.IGNORECASE)))
    if channels:
        return channels
    inferred: list[str] = []
    if _protocol_float(values, "Ch1 PMT voltage", 0.0) > 0:
        inferred.append("Ch1")
    if _protocol_float(values, "Ch2 PMT voltage", 0.0) > 0:
        inferred.append("Ch2")
    return tuple(inferred or ["Ch1"])


def read_two_photon_protocol(folder: str | Path) -> TwoPhotonProtocol:
    folder = Path(folder)
    candidates = sorted(folder.glob("protocol*.txt"))
    if not candidates:
        raise FileNotFoundError(f"在 {folder} 中未找到 protocol*.txt 文件")
    protocol_path = candidates[0]
    values: dict[str, str] = {}
    for line in _read_text_with_fallback(protocol_path).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()
    width = _protocol_int(values, "Image frame size (x)")
    height = _protocol_int(values, "Image frame size (y)")
    frame_rate = _protocol_float(values, "Image frame rate", 10.0)
    recording_time_s = _protocol_float(values, "Recording time", 0.0)
    if width <= 0 or height <= 0:
        raise ValueError(f"协议文件中没有有效的图像尺寸：{protocol_path}")
    if frame_rate <= 0:
        frame_rate = 10.0
    expected_frames = int(round(recording_time_s * frame_rate)) if recording_time_s > 0 else 0
    return TwoPhotonProtocol(
        folder=folder,
        width=width,
        height=height,
        frame_rate=frame_rate,
        recording_time_s=recording_time_s,
        expected_frames=expected_frames,
        channels=_protocol_channels(values),
        values=values,
    )


def is_two_photon_folder(path: str | Path) -> bool:
    folder = Path(path)
    return folder.is_dir() and any(folder.glob("*.tdms")) and any(folder.glob("protocol*.txt"))


def _tdms_u32(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<I", buf, offset)[0]


def _tdms_u64(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", buf, offset)[0]


def _tdms_raw_segments(path: str | Path) -> list[tuple[int, int]]:
    path = Path(path)
    size = path.stat().st_size
    segments: list[tuple[int, int]] = []
    pos = 0
    with path.open("rb") as f:
        while pos + 28 <= size:
            f.seek(pos)
            leadin = f.read(28)
            if len(leadin) < 28:
                break
            if leadin[:4] != b"TDSm":
                raise ValueError(f"TDMS 数据段无效，偏移位置 {pos}：{path}")
            next_segment_offset = _tdms_u64(leadin, 12)
            raw_data_offset = _tdms_u64(leadin, 20)
            if next_segment_offset == 0xFFFFFFFFFFFFFFFF:
                segment_end = size
            else:
                segment_end = min(size, pos + 28 + int(next_segment_offset))
            raw_start = pos + 28 + int(raw_data_offset)
            if raw_start < segment_end:
                segments.append((raw_start, segment_end - raw_start))
            if segment_end <= pos:
                break
            pos = segment_end
    if not segments:
        raise ValueError(f"未找到原始 TDMS 图像数据段：{path}")
    return segments


def tdms_image_slot_count(path: str | Path, width: int, height: int) -> int:
    frame_bytes = int(width) * int(height) * 2
    if frame_bytes <= 0:
        return 0
    return sum(length // frame_bytes for _, length in _tdms_raw_segments(path))


def iter_tdms_image_slots(path: str | Path, width: int, height: int):
    frame_bytes = int(width) * int(height) * 2
    if frame_bytes <= 0:
        return
    with Path(path).open("rb") as f:
        for raw_start, raw_length in _tdms_raw_segments(path):
            frames = raw_length // frame_bytes
            f.seek(raw_start)
            for _ in range(frames):
                data = f.read(frame_bytes)
                if len(data) != frame_bytes:
                    return
                yield np.frombuffer(data, dtype="<i2").reshape((height, width))


def _two_photon_tdms_path(folder: Path) -> Path:
    tdms_files = sorted(p for p in folder.glob("*.tdms") if not p.name.endswith("_index"))
    if not tdms_files:
        raise FileNotFoundError(f"在 {folder} 中未找到 .tdms 文件")
    preferred = [p for p in tdms_files if "real-time imaging" in p.name.lower()]
    return preferred[0] if preferred else tdms_files[0]


def _channel_frame_count(protocol: TwoPhotonProtocol, raw_slots: int) -> tuple[int, int]:
    wants_two = "Ch2" in protocol.channels
    expected = protocol.expected_frames if protocol.expected_frames > 0 else raw_slots
    if wants_two and raw_slots >= expected * 2:
        return expected, 2
    if wants_two and raw_slots >= 2 and raw_slots % 2 == 0 and protocol.expected_frames == 0:
        return raw_slots // 2, 2
    return min(expected, raw_slots), 1


def _scale_channel_to_uint8(image: np.ndarray, limits: tuple[float, float]) -> np.ndarray:
    lo, hi = float(limits[0]), float(limits[1])
    if hi <= lo:
        return np.zeros(image.shape, dtype=np.uint8)
    return np.clip((np.asarray(image, dtype=np.float32) - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


CHANNEL_COLOR_VECTORS: dict[str, tuple[float, float, float]] = {
    "green": (0.0, 1.0, 0.0),
    "red": (1.0, 0.0, 0.0),
    "yellow": (1.0, 1.0, 0.0),
    "blue": (0.0, 0.35, 1.0),
    "purple": (0.75, 0.0, 1.0),
    "gray": (1.0, 1.0, 1.0),
}


def normalized_channel_color(name: str | None) -> str:
    key = str(name or "gray").strip().lower()
    return key if key in CHANNEL_COLOR_VECTORS else "gray"


def channel_colors_for_count(colors: tuple[str, ...] | list[str] | None, count: int) -> tuple[str, ...]:
    values = [normalized_channel_color(color) for color in (colors or ())]
    if len(values) < count:
        values.extend(["gray"] * (count - len(values)))
    return tuple(values[:count])


def has_pseudocolor(colors: tuple[str, ...] | list[str] | None) -> bool:
    return any(normalized_channel_color(color) != "gray" for color in (colors or ()))


def compose_channel_pseudocolor_rgb(
    channel_images: tuple[np.ndarray, ...] | list[np.ndarray],
    colors: tuple[str, ...] | list[str] | None,
    limits: tuple[tuple[float, float] | None, ...] | None = None,
) -> np.ndarray:
    if not channel_images:
        raise ValueError("未提供任何通道图像")
    images = [np.asarray(image, dtype=np.float32) for image in channel_images]
    shape = images[0].shape
    if any(image.shape != shape for image in images):
        shapes = ", ".join(str(image.shape) for image in images)
        raise ValueError(f"各通道图像必须具有相同 shape，实际为：{shapes}")
    color_names = channel_colors_for_count(colors, len(images))
    if limits is None:
        limits = tuple(None for _ in images)
    rgb = np.zeros(shape + (3,), dtype=np.float32)
    for image, color_name, limit in zip(images, color_names, limits):
        if limit is None:
            finite = image[np.isfinite(image)]
            if finite.size:
                lo, hi = np.percentile(finite, [1, 99])
            else:
                lo, hi = 0.0, 1.0
            if hi <= lo:
                lo, hi = float(np.nanmin(image)), float(np.nanmax(image))
            if hi <= lo:
                hi = lo + 1.0
            limit = (float(lo), float(hi))
        intensity = _scale_channel_to_uint8(image, limit).astype(np.float32) / 255.0
        rgb += intensity[:, :, None] * np.asarray(CHANNEL_COLOR_VECTORS[normalized_channel_color(color_name)], dtype=np.float32)
    return np.clip(rgb * 255.0, 0, 255).astype(np.uint8)


def pseudocolor_bgr(
    ch1: np.ndarray,
    ch2: np.ndarray | None = None,
    ch1_limits: tuple[float, float] | None = None,
    ch2_limits: tuple[float, float] | None = None,
) -> np.ndarray:
    return cv2.cvtColor(pseudocolor_rgb(ch1, ch2, ch1_limits, ch2_limits), cv2.COLOR_RGB2BGR)


def pseudocolor_rgb(
    ch1: np.ndarray,
    ch2: np.ndarray | None = None,
    ch1_limits: tuple[float, float] | None = None,
    ch2_limits: tuple[float, float] | None = None,
) -> np.ndarray:
    channels = [ch1]
    colors = ["green"]
    limits: list[tuple[float, float] | None] = [ch1_limits]
    if ch2 is not None:
        channels.append(ch2)
        colors.append("red")
        limits.append(ch2_limits)
    return compose_channel_pseudocolor_rgb(channels, colors, tuple(limits))


def two_photon_analysis_movie(channel_movies: tuple[np.ndarray, ...]) -> np.ndarray:
    if not channel_movies:
        raise ValueError("未提供任何通道视频")
    if len(channel_movies) == 1:
        return np.asarray(channel_movies[0], dtype=np.float32)
    return np.maximum.reduce([np.asarray(movie, dtype=np.float32) for movie in channel_movies])


def _sample_channel_limits(tdms_path: Path, protocol: TwoPhotonProtocol, frame_count: int, channel_count: int) -> tuple[tuple[float, float], tuple[float, float]]:
    ch1_samples: list[np.ndarray] = []
    ch2_samples: list[np.ndarray] = []
    if frame_count <= 0:
        return (0.0, 1.0), (0.0, 1.0)
    frame_step = max(1, frame_count // 200)
    pixel_step = max(1, (protocol.width * protocol.height) // 5000)
    slots = iter_tdms_image_slots(tdms_path, protocol.width, protocol.height)
    for frame_idx in range(frame_count):
        try:
            ch1_raw = next(slots)
            ch2_raw = next(slots) if channel_count == 2 else None
        except StopIteration:
            break
        if frame_idx % frame_step != 0:
            continue
        ch1_samples.append((ch1_raw.astype(np.float32).reshape(-1)[::pixel_step] + 32768.0))
        if ch2_raw is not None:
            ch2_samples.append((ch2_raw.astype(np.float32).reshape(-1)[::pixel_step] + 32768.0))

    def limits(samples: list[np.ndarray]) -> tuple[float, float]:
        if not samples:
            return (0.0, 1.0)
        arr = np.concatenate(samples)
        lo, hi = np.percentile(arr[np.isfinite(arr)], [1, 99]) if np.any(np.isfinite(arr)) else (0.0, 1.0)
        if hi <= lo:
            lo, hi = float(np.nanmin(arr)), float(np.nanmax(arr))
        if hi <= lo:
            hi = lo + 1.0
        return float(lo), float(hi)

    return limits(ch1_samples), limits(ch2_samples)


def convert_two_photon_folder_to_movie(
    folder: str | Path,
    output_dir: str | Path,
    progress=None,
    interlacing_search_range: int = 10,
) -> ConvertedTwoPhotonMovie:
    folder = Path(folder)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol = read_two_photon_protocol(folder)
    tdms_path = _two_photon_tdms_path(folder)
    raw_slots = tdms_image_slot_count(tdms_path, protocol.width, protocol.height)
    frame_count, channel_count = _channel_frame_count(protocol, raw_slots)
    if frame_count <= 0:
        raise ValueError(f"在 {tdms_path} 中未找到完整图像帧")

    movie_path = output_dir / "converted_movie.npy"
    movie = np.lib.format.open_memmap(
        movie_path,
        mode="w+",
        dtype=np.float32,
        shape=(frame_count, protocol.height, protocol.width),
    )
    channel_movies: list[np.ndarray] = []
    channel_avi_paths: list[Path] = []
    for channel_idx in range(channel_count):
        ch_movie_path = output_dir / f"converted_ch{channel_idx + 1}_movie.npy"
        channel_movies.append(
            np.lib.format.open_memmap(
                ch_movie_path,
                mode="w+",
                dtype=np.float32,
                shape=(frame_count, protocol.height, protocol.width),
            )
        )
    slots = iter_tdms_image_slots(tdms_path, protocol.width, protocol.height)
    try:
        for frame_idx in range(frame_count):
            ch1 = next(slots).astype(np.float32) + 32768.0
            ch2 = next(slots).astype(np.float32) + 32768.0 if channel_count == 2 else None
            channel_movies[0][frame_idx] = ch1
            if ch2 is not None and len(channel_movies) > 1:
                channel_movies[1][frame_idx] = ch2
            movie[frame_idx] = np.maximum(ch1, ch2) if ch2 is not None else ch1
            if progress is not None:
                progress(frame_idx + 1, frame_count)
    finally:
        movie.flush()
        for ch_movie in channel_movies:
            ch_movie.flush()

    interlacing_search = max(0, int(round(float(interlacing_search_range))))
    interlacing_shift = 0
    if interlacing_search > 0 and channel_movies:
        interlacing_shift = estimate_interlacing_shift_from_movie(
            channel_movies[0],
            search_range=interlacing_search,
            row_parity="odd",
        )
        if interlacing_shift != 0:
            for ch_movie in channel_movies:
                apply_interlacing_shift_movie_inplace(ch_movie, interlacing_shift, row_parity="odd")
            write_analysis_movie_from_channels(movie, channel_movies)

    return ConvertedTwoPhotonMovie(
        movie=movie,
        channel_movies=tuple(channel_movies),
        fs=float(protocol.frame_rate),
        color_avi_path=None,
        channel_avi_paths=tuple(channel_avi_paths),
        source_folder=folder,
        protocol=protocol,
        frames=frame_count,
        channel_count=channel_count,
        interlacing_shift_px=int(interlacing_shift),
        interlacing_search_range=int(interlacing_search),
    )


def read_video_frame_rgb(path: str | Path, frame_index: int) -> np.ndarray | None:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_index)))
        ok, frame = cap.read()
        if not ok:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()


def read_stimulus_file(path: str) -> np.ndarray:
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(path)
        numeric = df.select_dtypes(include=[np.number])
        if numeric.empty:
            raise ValueError("刺激 CSV 中没有数值列")
        data = numeric.iloc[:, 0].to_numpy(dtype=np.float32)
    elif ext in {".txt", ".dat"}:
        data = np.loadtxt(path, dtype=np.float32)
    else:
        raise ValueError(f"不支持的刺激文件类型：{ext}")
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    return data[np.isfinite(data)]


def _line_has_text_header(line: str) -> bool:
    parts = re.split(r"[\t,; ]+", line.strip())
    parts = [part for part in parts if part]
    if not parts:
        return False
    numeric = 0
    for part in parts:
        try:
            float(part)
            numeric += 1
        except Exception:
            pass
    return numeric < len(parts)


def _count_numeric_rows(path: Path) -> int:
    count = 0
    with path.open("rb") as f:
        first = f.readline()
        try:
            first_text = first.decode("utf-8", "ignore")
        except Exception:
            first_text = ""
        header = _line_has_text_header(first_text)
        if first and not header:
            count += 1
        for chunk in iter(lambda: f.read(1024 * 1024 * 8), b""):
            count += chunk.count(b"\n")
    return max(0, count)


def infer_stimulus_fs_from_folder(path: str | Path, sample_count: int) -> float | None:
    if sample_count <= 0:
        return None
    folder = Path(path).parent
    try:
        protocol = read_two_photon_protocol(folder)
    except Exception:
        return None
    if protocol.recording_time_s <= 0:
        return None
    fs = float(sample_count) / float(protocol.recording_time_s)
    return fs if fs > 0 else None


def _score_stimulus_column(values: np.ndarray) -> float:
    col = np.asarray(values, dtype=np.float32)
    finite = col[np.isfinite(col)]
    if finite.size < 3:
        return -np.inf
    p1, p5, p50, p95, p99, p999 = np.percentile(finite, [1, 5, 50, 95, 99, 99.9])
    pulse_strength = float(max(p999 - p50, p99 - p50, 0.0))
    tail_jump = float(max(p999 - p99, p99 - p95, p95 - p50, 0.0))
    noise = float(max(np.median(np.abs(finite - p50)) * 1.4826, (p95 - p5) / 3.29, np.finfo(np.float32).eps))
    if pulse_strength <= 0 or noise <= 0:
        return -np.inf
    auto_thr = max(float(p50 + 5.0 * noise), float(p99))
    above = col > auto_thr
    edge_count = int(np.count_nonzero(np.diff(np.concatenate(([False], above, [False])).astype(np.int8)) == 1))
    duty = float(np.mean(above))
    duty_penalty = 0.0 if 0.0001 <= duty <= 0.25 else 25.0
    return pulse_strength * 100.0 + tail_jump * 50.0 + np.log1p(pulse_strength / noise) * 5.0 + min(edge_count, 500) * 0.25 - duty_penalty


def _best_stimulus_column(data: np.ndarray, columns: tuple[str, ...]) -> int:
    if data.ndim == 1:
        return 0
    lower_names = [name.strip().lower() for name in columns]
    scores = [_score_stimulus_column(data[:, idx]) for idx in range(data.shape[1])]
    for idx, name in enumerate(lower_names):
        if any(keyword in name for keyword in ("stim", "trigger", "marker", "ttl")):
            scores[idx] += 1.0
    return int(np.nanargmax(scores))


def read_stimulus_file_info(path: str | Path) -> StimulusFileData:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(path)
        numeric = df.select_dtypes(include=[np.number])
        if numeric.empty:
            raise ValueError("刺激 CSV 中没有数值列")
        data2 = numeric.to_numpy(dtype=np.float32)
        columns = tuple(str(col) for col in numeric.columns)
        col_idx = _best_stimulus_column(data2, columns)
        signal_data = data2[:, col_idx]
        sample_count = int(data2.shape[0])
        fs = infer_stimulus_fs_from_folder(path, sample_count)
        return StimulusFileData(signal=signal_data[np.isfinite(signal_data)], fs=fs, column_name=columns[col_idx], columns=columns, sample_count=sample_count)
    if ext in {".txt", ".dat"}:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline()
        has_header = _line_has_text_header(first_line)
        delimiter = "\t" if "\t" in first_line else None
        data = np.loadtxt(path, dtype=np.float32, skiprows=1 if has_header else 0, delimiter=delimiter)
        arr = np.asarray(data, dtype=np.float32)
        if arr.ndim == 1:
            signal_data = arr
            columns = ()
            col_idx = 0
        else:
            columns = tuple(part.strip() for part in re.split(r"\t|,", first_line.strip()) if part.strip()) if has_header else tuple(f"Column {i + 1}" for i in range(arr.shape[1]))
            if len(columns) < arr.shape[1]:
                columns = tuple(list(columns) + [f"Column {i + 1}" for i in range(len(columns), arr.shape[1])])
            col_idx = _best_stimulus_column(arr, columns)
            signal_data = arr[:, col_idx]
        sample_count = int(arr.shape[0])
        fs = infer_stimulus_fs_from_folder(path, sample_count)
        column_name = columns[col_idx] if columns else ""
        finite_signal = signal_data[np.isfinite(signal_data)]
        return StimulusFileData(signal=finite_signal.astype(np.float32), fs=fs, column_name=column_name, columns=columns, sample_count=sample_count)
    signal_data = read_stimulus_file(str(path))
    fs = infer_stimulus_fs_from_folder(path, signal_data.size)
    return StimulusFileData(signal=signal_data, fs=fs, sample_count=int(signal_data.size))


def _movie_to_unsigned_integer_stack(movie: np.ndarray, dtype: np.dtype) -> np.ndarray:
    arr = np.asarray(movie, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[None, :, :]
    if arr.ndim != 3:
        raise ValueError(f"需要三维视频堆栈，实际 shape 为 {arr.shape}")
    info = np.iinfo(dtype)
    arr = np.nan_to_num(arr, nan=0.0, posinf=float(info.max), neginf=0.0)
    return np.clip(np.rint(arr), 0, info.max).astype(dtype)


def save_movie_tiff(movie: np.ndarray, path: str, bit_depth: str = "auto") -> None:
    mode = normalized_movie_bit_depth(bit_depth)
    if mode == "8-bit":
        arr = _movie_to_unsigned_integer_stack(movie, np.uint8)
    elif mode == "16-bit":
        arr = _movie_to_unsigned_integer_stack(movie, np.uint16)
    else:
        arr = np.asarray(movie, dtype=np.float32)
    tifffile.imwrite(path, arr, photometric="minisblack")


def _movie_to_uint8(
    movie: np.ndarray,
    display_limits: tuple[float, float] | None = None,
    brightness: float = 0.0,
    contrast: float = 100.0,
) -> np.ndarray:
    arr = np.asarray(movie)
    if arr.ndim == 2:
        arr = arr[None, :, :]
    if arr.ndim != 3:
        raise ValueError(f"需要三维视频堆栈，实际 shape 为 {arr.shape}")
    if display_limits is None:
        display_limits = movie_display_limits(arr)
    return render_grayscale_display(arr, display_limits, brightness=brightness, contrast=contrast)


def save_movie_avi(
    movie: np.ndarray,
    path: str,
    fs: float = 10.0,
    display_limits: tuple[float, float] | None = None,
    brightness: float = 0.0,
    contrast: float = 100.0,
) -> None:
    """Save the same fixed 8-bit mapping used by the grayscale preview."""
    frames = _movie_to_uint8(movie, display_limits=display_limits, brightness=brightness, contrast=contrast)
    fps = float(fs) if fs and fs > 0 else 10.0
    h, w = frames.shape[1:3]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h), isColor=True)
    if not writer.isOpened():
        raise IOError(f"无法创建 AVI 视频：{path}")
    try:
        for frame in frames:
            writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    finally:
        writer.release()


def save_channel_pseudocolor_avi(
    channel_movies: tuple[np.ndarray, ...] | list[np.ndarray],
    colors: tuple[str, ...] | list[str] | None,
    path: str,
    fs: float = 10.0,
    limits: tuple[tuple[float, float] | None, ...] | None = None,
    shadows: float = 1.0,
    highlights: float = 99.0,
    brightness: float = 0.0,
    contrast: float = 100.0,
    progress=None,
) -> None:
    movies = [np.asarray(movie) for movie in channel_movies if movie is not None]
    if not movies:
        raise ValueError("未提供任何通道视频")
    first_shape = movies[0].shape
    if len(first_shape) != 3:
        raise ValueError(f"需要三维通道视频，实际 shape 为 {first_shape}")
    if any(movie.shape != first_shape for movie in movies):
        shapes = ", ".join(str(movie.shape) for movie in movies)
        raise ValueError(f"各通道视频必须具有相同 shape，实际为：{shapes}")
    color_names = channel_colors_for_count(colors, len(movies))
    frame_count, h, w = first_shape
    fps = float(fs) if fs and fs > 0 else 10.0
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h), isColor=True)
    if not writer.isOpened():
        raise IOError(f"无法创建 AVI 视频：{path}")
    try:
        for frame_idx in range(frame_count):
            rgb = compose_channel_pseudocolor_rgb([movie[frame_idx] for movie in movies], color_names, limits=limits)
            rgb = render_rgb_display(rgb, shadows, highlights, brightness, contrast)
            writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            if progress is not None:
                progress(frame_idx + 1, frame_count)
    finally:
        writer.release()


def save_channel_pseudocolor_tiff(
    channel_movies: tuple[np.ndarray, ...] | list[np.ndarray],
    colors: tuple[str, ...] | list[str] | None,
    path: str,
    limits: tuple[tuple[float, float] | None, ...] | None = None,
    shadows: float = 1.0,
    highlights: float = 99.0,
    brightness: float = 0.0,
    contrast: float = 100.0,
    progress=None,
) -> None:
    """Write an RGB TIFF stack that matches the pseudo-colour preview."""
    movies = [np.asarray(movie) for movie in channel_movies if movie is not None]
    if not movies:
        raise ValueError("未提供任何通道视频")
    first_shape = movies[0].shape
    if len(first_shape) != 3 or any(movie.shape != first_shape for movie in movies):
        raise ValueError("各通道视频必须是 shape 相同的三维堆栈")
    color_names = channel_colors_for_count(colors, len(movies))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with tifffile.TiffWriter(path, bigtiff=True) as writer:
        for frame_idx in range(first_shape[0]):
            rgb = compose_channel_pseudocolor_rgb([movie[frame_idx] for movie in movies], color_names, limits=limits)
            rgb = render_rgb_display(rgb, shadows, highlights, brightness, contrast)
            writer.write(rgb, photometric="rgb", metadata=None)
            if progress is not None:
                progress(frame_idx + 1, first_shape[0])


def save_movie(
    movie: np.ndarray,
    path: str,
    fs: float = 10.0,
    bit_depth: str = "auto",
    display_limits: tuple[float, float] | None = None,
    brightness: float = 0.0,
    contrast: float = 100.0,
) -> None:
    ext = Path(path).suffix.lower()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if ext in {".tif", ".tiff"}:
        save_movie_tiff(movie, path, bit_depth=bit_depth)
        return
    if ext == ".avi":
        save_movie_avi(movie, path, fs=fs, display_limits=display_limits, brightness=brightness, contrast=contrast)
        return
    raise ValueError(f"不支持的视频输出类型：{ext}。请使用 .tif、.tiff 或 .avi")


def ensure_deepcadrt_model_available(model: str | None = None) -> str:
    model_path = Path(model) if model else DEEPCADRT_DEFAULT_MODEL_FILE
    if not model_path.is_absolute():
        model_path = APP_RESOURCE_DIR / model_path
    if model_path.is_file() and model_path.suffix.lower() == ".pth":
        return str(model_path)
    if model_path.is_dir() and list(model_path.glob("*.pth")):
        return str(model_path)
    raise FileNotFoundError(
        "No usable DeepCAD-RT .pth model file was found.\n"
        f"Default project model:\n{DEEPCADRT_DEFAULT_MODEL_FILE}\n\n"
        "Put the trained .pth model in NewLight_Analysis\\DeepCADRT_Model, "
        "or pass an explicit .pth file / model folder."
    )


def blend_movies(raw_movie: np.ndarray, denoised_movie: np.ndarray, weight: float) -> np.ndarray:
    weight = float(np.clip(weight, 0.0, 1.0))
    raw = np.asarray(raw_movie, dtype=np.float32)
    denoised = np.asarray(denoised_movie, dtype=np.float32)
    if raw.shape != denoised.shape:
        raise ValueError(f"无法混合 shape 不同的视频：{raw.shape} 与 {denoised.shape}")
    return ((1.0 - weight) * raw + weight * denoised).astype(np.float32, copy=False)


def blend_images(raw_image: np.ndarray, denoised_image: np.ndarray, weight: float) -> np.ndarray:
    weight = float(np.clip(weight, 0.0, 1.0))
    raw = np.asarray(raw_image, dtype=np.float32)
    denoised = np.asarray(denoised_image, dtype=np.float32)
    if raw.shape != denoised.shape:
        raise ValueError(f"无法混合 shape 不同的图像：{raw.shape} 与 {denoised.shape}")
    return ((1.0 - weight) * raw + weight * denoised).astype(np.float32, copy=False)


def preserve_empty_source_frames(source_movie: np.ndarray, processed_movie: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Restore strictly empty source frames after a temporal denoising model.

    DeepCAD-RT uses temporal patches and can emit nonzero model-bias values for
    an all-zero frame at the beginning or end of a recording. Those frames
    contain no acquisition data and must remain empty in preview and export.
    """
    source = np.asarray(source_movie, dtype=np.float32)
    processed = np.asarray(processed_movie, dtype=np.float32)
    if source.shape != processed.shape or source.ndim != 3:
        raise ValueError(f"空帧保护需要相同的三维堆栈，实际为 {source.shape} 与 {processed.shape}")
    safe_source = np.nan_to_num(source, nan=0.0, posinf=0.0, neginf=0.0)
    global_peak = float(np.max(np.abs(safe_source))) if safe_source.size else 0.0
    tolerance = max(1e-6, global_peak * 1e-8)
    empty_mask = np.max(np.abs(safe_source), axis=(1, 2)) <= tolerance
    if not np.any(empty_mask):
        return processed, np.empty(0, dtype=int)
    restored = processed.copy()
    restored[empty_mask] = source[empty_mask]
    return restored, np.flatnonzero(empty_mask).astype(int)


def preserve_invalid_denoised_frames(source_movie: np.ndarray, processed_movie: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Restore nonempty input frames when DeepCAD-RT emitted an empty frame.

    DeepCAD-RT's upstream temporal stitcher can leave trailing frames as zero
    for a short movie.  A zero output for a nonempty input is invalid; keeping
    the source frame is safer than blending an artificial black frame into a
    preview or a saved movie.
    """
    source = np.asarray(source_movie, dtype=np.float32)
    processed = np.asarray(processed_movie, dtype=np.float32)
    if source.shape != processed.shape or source.ndim != 3:
        raise ValueError(f"异常帧保护需要相同的三维堆栈，实际为 {source.shape} 与 {processed.shape}")
    safe_source = np.nan_to_num(source, nan=0.0, posinf=0.0, neginf=0.0)
    safe_processed = np.nan_to_num(processed, nan=0.0, posinf=0.0, neginf=0.0)
    source_peak = np.max(np.abs(safe_source), axis=(1, 2))
    output_peak = np.max(np.abs(safe_processed), axis=(1, 2))
    source_tolerance = max(1e-6, float(np.max(source_peak)) * 1e-8)
    invalid_mask = (source_peak > source_tolerance) & (output_peak <= source_tolerance)
    if not np.any(invalid_mask):
        return processed, np.empty(0, dtype=int)
    restored = processed.copy()
    restored[invalid_mask] = source[invalid_mask]
    return restored, np.flatnonzero(invalid_mask).astype(int)


def compute_baseline(movie: np.ndarray, mode: str = "percentile", start: int = 0, end: int | None = None) -> np.ndarray:
    if end is None or end <= start:
        end = movie.shape[0]
    block = movie[max(0, start): min(movie.shape[0], end)]
    if block.size == 0:
        block = movie
    if mode == "mean":
        baseline = np.mean(block, axis=0)
    elif mode == "max":
        baseline = np.max(block, axis=0)
    else:
        baseline = np.percentile(block, 25, axis=0)
    baseline = baseline.astype(np.float32)
    baseline[baseline <= 0] = np.finfo(np.float32).eps
    return baseline


def normalized_invalid_start_frames(movie: np.ndarray, invalid_start_frames: int | float = 0) -> int:
    frame_count = int(np.asarray(movie).shape[0])
    invalid = int(round(float(invalid_start_frames)))
    if invalid < 0:
        raise ValueError("无效起始帧数必须大于或等于 0")
    if frame_count <= 0 or invalid >= frame_count:
        raise ValueError(f"无效起始帧数 {invalid} 必须小于视频总帧数 {frame_count}")
    return invalid


def baseline_from_frames(
    movie: np.ndarray,
    start_frame: int | float = 0,
    duration_frames: int | float = 0,
    invalid_start_frames: int | float = 0,
) -> np.ndarray:
    invalid = normalized_invalid_start_frames(movie, invalid_start_frames)
    start = max(invalid, int(round(float(start_frame))))
    duration = max(0, int(round(float(duration_frames))))
    if duration <= 0:
        return compute_baseline(movie, mode="percentile", start=invalid)
    if start >= movie.shape[0]:
        raise ValueError(f"基线起始帧 {start} 超出视频总帧数 {movie.shape[0]}")
    end = min(movie.shape[0], start + duration)
    if end <= start:
        raise ValueError("基线持续帧数没有选中任何帧")
    return compute_baseline(movie, mode="mean", start=start, end=end)


def baseline_from_seconds(movie: np.ndarray, fs: float, start_s: float, duration_s: float, mode: str = "percentile") -> np.ndarray:
    start = max(0, int(round(start_s * fs)))
    if duration_s and duration_s > 0:
        end = start + int(round(duration_s * fs))
    else:
        end = None
    if mode == "percentile" and (duration_s is None or duration_s <= 0):
        return baseline_from_frames(movie, start_frame=start, duration_frames=0)
    if mode == "percentile":
        return baseline_from_frames(movie, start_frame=start, duration_frames=(end - start if end is not None else 0))
    return compute_baseline(movie, mode=mode, start=start, end=end)


def compute_projection(
    movie: np.ndarray,
    mode: str,
    acceleration: str = "auto",
    mean_start_frame: int = 0,
    mean_duration_frames: int = 0,
    invalid_start_frames: int = 0,
) -> np.ndarray:
    """Create a display projection without changing the analysis movie.

    A positive mean duration restricts only the mean projection to the protocol
    frame window. Max, standard deviation, and 25th-percentile views always
    describe the full movie.
    """
    arr_movie = np.asarray(movie)
    invalid = normalized_invalid_start_frames(arr_movie, invalid_start_frames)
    if mode == "mean" and int(mean_duration_frames) > 0:
        start = max(invalid, int(mean_start_frame))
        end = min(arr_movie.shape[0], start + int(mean_duration_frames))
        if end > start:
            arr_movie = arr_movie[start:end]
    else:
        arr_movie = arr_movie[invalid:]
    cp = get_cupy() if acceleration in {"auto", "gpu"} else None
    if cp is not None and mode in {"mean", "max", "std"}:
        arr = cp.asarray(arr_movie, dtype=cp.float32)
        if mode == "max":
            return cp.asnumpy(cp.max(arr, axis=0)).astype(np.float32)
        if mode == "std":
            return cp.asnumpy(cp.std(arr, axis=0)).astype(np.float32)
        return cp.asnumpy(cp.mean(arr, axis=0)).astype(np.float32)
    if mode == "max":
        return np.max(arr_movie, axis=0)
    if mode == "std":
        return np.std(arr_movie, axis=0)
    if mode == "p25":
        return np.percentile(arr_movie, 25, axis=0).astype(np.float32)
    if mode == "corr":
        return local_correlation_image(arr_movie)
    return np.mean(arr_movie, axis=0)


def local_correlation_image(movie: np.ndarray) -> np.ndarray:
    arr = movie.astype(np.float32)
    arr = arr - arr.mean(axis=0, keepdims=True)
    arr = arr / (arr.std(axis=0, keepdims=True) + 1e-6)
    corr = np.zeros(arr.shape[1:], dtype=np.float32)
    count = 0
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        shifted = np.roll(arr, shift=(dy, dx), axis=(1, 2))
        corr += np.mean(arr * shifted, axis=0)
        count += 1
    corr /= max(count, 1)
    return corr


def compute_dff(movie: np.ndarray, baseline: np.ndarray | None = None, acceleration: str = "auto") -> np.ndarray:
    if baseline is None:
        baseline = compute_baseline(movie)
    cp = get_cupy() if acceleration in {"auto", "gpu"} else None
    if cp is not None:
        movie_gpu = cp.asarray(movie, dtype=cp.float32)
        baseline_gpu = cp.asarray(baseline, dtype=cp.float32)
        return cp.asnumpy((movie_gpu - baseline_gpu[None, :, :]) / (baseline_gpu[None, :, :] + 1e-6)).astype(np.float32)
    return ((movie - baseline[None, :, :]) / (baseline[None, :, :] + 1e-6)).astype(np.float32)


def _interlacing_row_start(row_parity: str) -> int:
    key = str(row_parity or "odd").strip().lower()
    return 0 if key in {"even", "0"} else 1


def _shift_2d_rows(rows: np.ndarray, shift_px: int) -> np.ndarray:
    rows = np.asarray(rows)
    shift = int(round(float(shift_px)))
    out = np.empty_like(rows)
    if shift == 0:
        out[...] = rows
    elif shift > 0:
        if shift < rows.shape[1]:
            out[:, shift:] = rows[:, :-shift]
            out[:, :shift] = rows[:, :1]
        else:
            out[...] = rows[:, :1]
    else:
        shift = abs(shift)
        if shift < rows.shape[1]:
            out[:, :-shift] = rows[:, shift:]
            out[:, -shift:] = rows[:, -1:]
        else:
            out[...] = rows[:, -1:]
    return out


def apply_interlacing_shift_image(image: np.ndarray, shift_px: int, row_parity: str = "odd") -> np.ndarray:
    arr = np.asarray(image)
    if arr.ndim != 2:
        raise ValueError(f"需要二维图像，实际 shape 为 {arr.shape}")
    shift = int(round(float(shift_px)))
    out = arr.copy()
    if shift == 0:
        return out
    row_start = _interlacing_row_start(row_parity)
    out[row_start::2, :] = _shift_2d_rows(arr[row_start::2, :], shift)
    return out


def apply_interlacing_shift_movie(movie: np.ndarray, shift_px: int, row_parity: str = "odd") -> np.ndarray:
    arr = np.asarray(movie)
    if arr.ndim != 3:
        raise ValueError(f"需要三维视频堆栈，实际 shape 为 {arr.shape}")
    shift = int(round(float(shift_px)))
    out = np.empty_like(arr, dtype=np.float32)
    for frame_idx, frame in enumerate(arr):
        out[frame_idx] = apply_interlacing_shift_image(frame, shift, row_parity=row_parity)
    return out.astype(np.float32, copy=False)


def apply_interlacing_shift_movie_inplace(movie: np.ndarray, shift_px: int, row_parity: str = "odd", progress=None) -> None:
    arr = np.asarray(movie)
    if arr.ndim != 3:
        raise ValueError(f"需要三维视频堆栈，实际 shape 为 {arr.shape}")
    shift = int(round(float(shift_px)))
    if shift == 0:
        return
    for frame_idx in range(arr.shape[0]):
        arr[frame_idx] = apply_interlacing_shift_image(arr[frame_idx], shift, row_parity=row_parity)
        if progress is not None:
            progress(frame_idx + 1, arr.shape[0])
    flush = getattr(movie, "flush", None)
    if callable(flush):
        flush()


def estimate_interlacing_shift(image: np.ndarray, search_range: int = 10, row_parity: str = "odd") -> int:
    arr = np.asarray(image, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"需要二维图像，实际 shape 为 {arr.shape}")
    h, w = arr.shape
    if h < 4 or w < 8:
        return 0
    search = max(0, int(round(float(search_range))))
    search = min(search, max(0, w // 4))
    if search <= 0:
        return 0
    row_start = _interlacing_row_start(row_parity)
    rows = np.arange(row_start, h, 2, dtype=int)
    rows = rows[(rows > 0) & (rows < h - 1)]
    if rows.size == 0:
        return 0
    target = (arr[rows - 1, :] + arr[rows + 1, :]) * 0.5
    source = arr[rows, :]
    margin = min(max(search + 2, 2), max(0, (w - 4) // 2))
    col_slice = slice(margin, w - margin) if w - 2 * margin >= 4 else slice(0, w)
    target = target[:, col_slice]
    best_shift = 0
    best_score = -np.inf
    for shift in range(-search, search + 1):
        shifted = _shift_2d_rows(source, shift)[:, col_slice]
        valid = np.isfinite(shifted) & np.isfinite(target)
        if np.count_nonzero(valid) < 8:
            continue
        a = shifted[valid].astype(np.float64, copy=False)
        b = target[valid].astype(np.float64, copy=False)
        a -= float(a.mean())
        b -= float(b.mean())
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        score = float(np.dot(a, b) / denom) if denom > 0 else -np.inf
        if score > best_score + 1e-9 or (abs(score - best_score) <= 1e-9 and abs(shift) < abs(best_shift)):
            best_score = score
            best_shift = shift
    return int(best_shift)


def estimate_interlacing_shift_from_movie(
    movie: np.ndarray,
    search_range: int = 10,
    row_parity: str = "odd",
    max_frames: int = 200,
) -> int:
    arr = np.asarray(movie)
    if arr.ndim != 3:
        raise ValueError(f"需要三维视频堆栈，实际 shape 为 {arr.shape}")
    n_frames = arr.shape[0]
    if n_frames <= 0:
        return 0
    sample_count = min(max(1, int(max_frames)), n_frames)
    indices = np.linspace(0, n_frames - 1, sample_count, dtype=int)
    projection = np.zeros(arr.shape[1:], dtype=np.float64)
    for idx in indices:
        projection += np.asarray(arr[int(idx)], dtype=np.float32)
    projection /= float(sample_count)
    return estimate_interlacing_shift(projection.astype(np.float32), search_range=search_range, row_parity=row_parity)


def write_analysis_movie_from_channels(movie: np.ndarray, channel_movies: tuple[np.ndarray, ...] | list[np.ndarray]) -> None:
    channels = [np.asarray(channel) for channel in channel_movies if channel is not None]
    if not channels:
        raise ValueError("未提供任何通道视频")
    target = np.asarray(movie)
    if any(channel.shape != target.shape for channel in channels):
        shapes = ", ".join(str(channel.shape) for channel in channels)
        raise ValueError(f"各通道视频必须匹配分析视频 shape {target.shape}，实际为：{shapes}")
    for frame_idx in range(target.shape[0]):
        if len(channels) == 1:
            target[frame_idx] = channels[0][frame_idx]
        else:
            target[frame_idx] = np.maximum.reduce([channel[frame_idx] for channel in channels])
    flush = getattr(movie, "flush", None)
    if callable(flush):
        flush()


def available_neuroseg3_weights() -> list[str]:
    weights_dir = NEUROSEG3_DIR / "weights"
    if not weights_dir.exists():
        return []
    return [str(path) for path in sorted(weights_dir.rglob("*.pt"))]


def gaussian_smooth_movie(movie: np.ndarray, sigma: float, acceleration: str = "auto") -> np.ndarray:
    if sigma <= 0:
        return movie.copy()
    cp = get_cupy() if acceleration in {"auto", "gpu"} else None
    if cp is not None:
        try:
            from cupyx.scipy.ndimage import gaussian_filter as cupy_gaussian_filter

            arr = cp.asarray(movie, dtype=cp.float32)
            return cp.asnumpy(cupy_gaussian_filter(arr, sigma=(0, sigma, sigma))).astype(np.float32)
        except Exception:
            pass
    return gaussian_filter(movie, sigma=(0, sigma, sigma)).astype(np.float32)


def median_filter_movie(movie: np.ndarray, size: int) -> np.ndarray:
    size = max(1, int(size))
    if size <= 1:
        return movie.copy()
    out = np.empty_like(movie, dtype=np.float32)
    for i, frame in enumerate(movie):
        out[i] = ndimage.median_filter(frame, size=size)
    return out


def background_subtract(movie: np.ndarray, sigma: float) -> np.ndarray:
    sigma = max(1.0, float(sigma))
    out = np.empty_like(movie, dtype=np.float32)
    for i, frame in enumerate(movie):
        bg = gaussian_filter(frame, sigma=sigma)
        out[i] = frame - bg
    out -= out.min()
    return out.astype(np.float32)


def bleach_correct(movie: np.ndarray) -> np.ndarray:
    t = np.arange(movie.shape[0], dtype=np.float32)
    mean_trace = movie.mean(axis=(1, 2))
    if movie.shape[0] < 4:
        return movie.copy()
    coeff = np.polyfit(t, mean_trace, deg=2)
    trend = np.polyval(coeff, t)
    trend = trend - trend.mean()
    return (movie - trend[:, None, None]).astype(np.float32)


def enhance_contrast(movie: np.ndarray, clip_limit: float = 0.02) -> np.ndarray:
    clip_limit = max(0.001, float(clip_limit))
    out = np.empty_like(movie, dtype=np.float32)
    for i, frame in enumerate(movie):
        out[i] = exposure.equalize_adapthist(normalize_image(frame), clip_limit=clip_limit)
    return out.astype(np.float32)


def _phase_translation(reference: np.ndarray, moving: np.ndarray, upsample_factor: int, max_shift: float) -> np.ndarray:
    try:
        from skimage.registration import phase_cross_correlation
    except Exception as exc:
        raise RuntimeError("无法使用 skimage.registration.phase_cross_correlation") from exc

    shift, _, _ = phase_cross_correlation(reference, moving, upsample_factor=max(1, int(upsample_factor)))
    shift = np.asarray(shift, dtype=np.float32)
    if not np.all(np.isfinite(shift)):
        return np.zeros(2, dtype=np.float32)
    return np.clip(shift, -float(max_shift), float(max_shift))


def _rigid_reference_window(
    movie: np.ndarray,
    reference_mode: str,
    reference_start: int,
    reference_frames: int,
) -> tuple[int, int]:
    frame_count = int(movie.shape[0])
    window = min(frame_count, max(1, int(reference_frames)))
    mode = str(reference_mode).strip().lower()
    if mode == "manual":
        start = int(reference_start)
        if start < 0 or start >= frame_count:
            raise ValueError(f"参考起始帧必须位于 0 到 {frame_count - 1} 之间。")
        return start, min(frame_count, start + window)
    if mode != "auto":
        raise ValueError("参考帧模式必须为 auto 或 manual。")
    if window >= frame_count:
        return 0, frame_count
    if window == 1:
        sharpness = [float(np.var(ndimage.laplace(frame))) for frame in movie]
        start = int(np.argmax(sharpness))
        return start, start + 1

    sample_step = max(1, int(np.ceil(max(movie.shape[1:]) / 128.0)))
    sample = np.asarray(movie[:, ::sample_step, ::sample_step], dtype=np.float32)
    transition_scores = np.empty(frame_count - 1, dtype=np.float32)
    trajectory = np.zeros((frame_count, 2), dtype=np.float32)
    for i in range(1, frame_count):
        shift = _phase_translation(sample[i - 1], sample[i], upsample_factor=1, max_shift=max(sample.shape[1:]))
        transition_scores[i - 1] = float(np.linalg.norm(shift))
        trajectory[i] = trajectory[i - 1] - shift

    typical_position = np.median(trajectory, axis=0)
    candidate_scores = np.empty(frame_count - window + 1, dtype=np.float32)
    for start in range(candidate_scores.size):
        local = transition_scores[start : start + window - 1]
        position_distance = np.linalg.norm(trajectory[start : start + window] - typical_position, axis=1)
        candidate_scores[start] = float(
            np.median(local) + 0.25 * np.mean(local) + 0.1 * np.median(position_distance)
        )
    start = int(np.argmin(candidate_scores))
    return start, start + window


def rigid_motion_correction(
    movie: np.ndarray,
    template_frames: int = 100,
    *,
    reference_mode: str = "auto",
    reference_start: int = 0,
    reference_frames: int | None = None,
    max_shift: float = 15.0,
    upsample_factor: int = 10,
) -> tuple[np.ndarray, list[tuple[float, float]], dict]:
    source = np.asarray(movie, dtype=np.float32)
    if source.ndim != 3 or source.shape[0] < 1:
        raise ValueError(f"刚性运动矫正需要非空三维视频，实际 shape 为 {source.shape}。")
    max_shift = float(max_shift)
    if not np.isfinite(max_shift) or max_shift < 0:
        raise ValueError("最大刚性位移必须是大于或等于 0 的有限数值。")
    requested_frames = template_frames if reference_frames is None else reference_frames
    start, end = _rigid_reference_window(source, reference_mode, reference_start, requested_frames)
    anchor_frame = start + (end - start) // 2
    anchor = source[anchor_frame]

    aligned_reference = np.empty((end - start,) + source.shape[1:], dtype=np.float32)
    for output_index, frame_index in enumerate(range(start, end)):
        shift = _phase_translation(anchor, source[frame_index], upsample_factor, max_shift)
        aligned_reference[output_index] = ndimage.shift(source[frame_index], shift=shift, order=1, mode="nearest")
    template = np.median(aligned_reference, axis=0).astype(np.float32)

    corrected = np.empty_like(source, dtype=np.float32)
    shifts = []
    for i, frame in enumerate(source):
        shift = _phase_translation(template, frame, upsample_factor, max_shift)
        corrected[i] = ndimage.shift(frame, shift=shift, order=1, mode="nearest")
        shifts.append((float(shift[0]), float(shift[1])))
    info = {
        "reference_start": int(start),
        "reference_end": int(end),
        "anchor_frame": int(anchor_frame),
        "template": template,
    }
    return corrected, shifts, info


def _local_patch_starts(length: int, block_size: int) -> list[int]:
    last = max(0, int(length) - int(block_size))
    stride = max(8, int(block_size) // 2)
    starts = list(range(0, last + 1, stride))
    if not starts or starts[-1] != last:
        starts.append(last)
    return starts


def _interpolate_local_shift_grid(
    grid: np.ndarray,
    centers_y: np.ndarray,
    centers_x: np.ndarray,
    shape: tuple[int, int],
) -> np.ndarray:
    height, width = shape
    target_x = np.arange(width, dtype=np.float32)
    target_y = np.arange(height, dtype=np.float32)
    rows = np.empty((grid.shape[0], width), dtype=np.float32)
    for row_index, row in enumerate(grid):
        rows[row_index] = np.interp(target_x, centers_x, row, left=row[0], right=row[-1])
    dense = np.empty((height, width), dtype=np.float32)
    for column_index in range(width):
        column = rows[:, column_index]
        dense[:, column_index] = np.interp(
            target_y,
            centers_y,
            column,
            left=column[0],
            right=column[-1],
        )
    return dense


def _estimate_local_shift_grid(
    template: np.ndarray,
    frame: np.ndarray,
    starts_y: list[int],
    starts_x: list[int],
    block_size: int,
    max_local_deformation: float,
) -> tuple[np.ndarray, np.ndarray]:
    shift_grid = np.zeros((len(starts_y), len(starts_x), 2), dtype=np.float32)
    limit_hits = np.zeros((len(starts_y), len(starts_x)), dtype=bool)
    window_1d = np.hanning(block_size).astype(np.float32)
    window = np.outer(window_1d, window_1d)
    texture_floor = max(float(np.std(template)) * 1e-3, np.finfo(np.float32).eps)

    for row_index, start_y in enumerate(starts_y):
        for column_index, start_x in enumerate(starts_x):
            ref_patch = template[start_y : start_y + block_size, start_x : start_x + block_size]
            moving_patch = frame[start_y : start_y + block_size, start_x : start_x + block_size]
            if float(np.std(ref_patch)) <= texture_floor or float(np.std(moving_patch)) <= texture_floor:
                continue
            ref_windowed = (ref_patch - float(np.mean(ref_patch))) * window
            moving_windowed = (moving_patch - float(np.mean(moving_patch))) * window
            shift = _phase_translation(
                ref_windowed,
                moving_windowed,
                upsample_factor=4,
                max_shift=max_local_deformation,
            )
            if not np.all(np.isfinite(shift)):
                continue
            shift_grid[row_index, column_index] = shift
            if max_local_deformation > 0:
                limit_hits[row_index, column_index] = bool(
                    np.any(np.abs(shift) >= max_local_deformation - 1e-6)
                )

    # Keep residual whole-frame motion: the rigid estimate can be biased by local deformation.
    shift_grid = np.clip(shift_grid, -max_local_deformation, max_local_deformation)
    shift_grid[..., 0] = ndimage.median_filter(shift_grid[..., 0], size=3, mode="nearest")
    shift_grid[..., 1] = ndimage.median_filter(shift_grid[..., 1], size=3, mode="nearest")
    return shift_grid.astype(np.float32), limit_hits


def fast_motion_correction(
    movie: np.ndarray,
    *,
    reference_mode: str = "auto",
    reference_start: int = 0,
    reference_frames: int = 100,
    max_shift: float = 15.0,
    flexible_strength: float = 0.0,
    local_block_size: int = 96,
    max_local_deformation: float = 3.0,
    upsample_factor: int = 10,
) -> tuple[np.ndarray, list[tuple[float, float]], dict]:
    strength = float(flexible_strength)
    if not np.isfinite(strength):
        raise ValueError("柔性强度必须是有限数值。")
    strength = float(np.clip(strength, 0.0, 1.0))
    max_local = float(max_local_deformation)
    if not np.isfinite(max_local) or max_local < 0:
        raise ValueError("最大局部形变必须是大于或等于 0 的有限数值。")
    try:
        requested_block = int(round(float(local_block_size)))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("局部块尺寸必须是有限整数。") from exc
    if requested_block < 8:
        raise ValueError("局部块尺寸必须大于或等于 8 px。")

    corrected, shifts, rigid_info = rigid_motion_correction(
        movie,
        reference_mode=reference_mode,
        reference_start=reference_start,
        reference_frames=reference_frames,
        max_shift=max_shift,
        upsample_factor=upsample_factor,
    )
    info = dict(rigid_info)
    info.update(
        {
            "flexible_strength": strength,
            "local_applied": False,
            "local_skip_reason": "",
            "local_block_size": 0,
            "local_grid_shape": (0, 0),
            "local_median_abs_shift": (0.0, 0.0),
            "local_max_abs_shift_by_axis": (0.0, 0.0),
            "local_max_abs_shift": 0.0,
            "local_limit_hit_fraction": 0.0,
        }
    )
    if strength <= 0.0:
        info["local_skip_reason"] = "flexible_strength_zero"
        return corrected, shifts, info
    if max_local <= 0.0:
        info["local_skip_reason"] = "max_local_deformation_zero"
        return corrected, shifts, info

    height, width = corrected.shape[1:]
    if min(height, width) < 32:
        info["local_skip_reason"] = "image_too_small"
        return corrected, shifts, info
    largest_useful_block = max(16, (2 * min(height, width)) // 3)
    block_size = min(max(16, requested_block), largest_useful_block)
    starts_y = _local_patch_starts(height, block_size)
    starts_x = _local_patch_starts(width, block_size)
    if len(starts_y) < 2 or len(starts_x) < 2:
        info["local_skip_reason"] = "image_too_small"
        return corrected, shifts, info

    centers_y = np.asarray(starts_y, dtype=np.float32) + (block_size - 1) / 2.0
    centers_x = np.asarray(starts_x, dtype=np.float32) + (block_size - 1) / 2.0
    template = np.asarray(info["template"], dtype=np.float32)
    output = np.empty_like(corrected, dtype=np.float32)
    yy, xx = np.indices((height, width), dtype=np.float32)
    all_local_shifts = []
    all_limit_hits = []
    smooth_sigma = max(1.0, block_size / 8.0)

    for frame_index, frame in enumerate(corrected):
        shift_grid, limit_hits = _estimate_local_shift_grid(
            template,
            frame,
            starts_y,
            starts_x,
            block_size,
            max_local,
        )
        dense_y = _interpolate_local_shift_grid(shift_grid[..., 0], centers_y, centers_x, (height, width))
        dense_x = _interpolate_local_shift_grid(shift_grid[..., 1], centers_y, centers_x, (height, width))
        dense_y = gaussian_filter(dense_y, sigma=smooth_sigma, mode="nearest") * strength
        dense_x = gaussian_filter(dense_x, sigma=smooth_sigma, mode="nearest") * strength
        output[frame_index] = ndimage.map_coordinates(
            frame,
            [yy - dense_y, xx - dense_x],
            order=1,
            mode="nearest",
        )
        all_local_shifts.append(shift_grid)
        all_limit_hits.append(limit_hits)

    local_shifts = np.stack(all_local_shifts).astype(np.float32)
    absolute_shifts = np.abs(local_shifts)
    limit_hit_fraction = float(np.mean(np.stack(all_limit_hits))) if all_limit_hits else 0.0
    info.update(
        {
            "local_applied": True,
            "local_skip_reason": "",
            "local_block_size": int(block_size),
            "local_grid_shape": (len(starts_y), len(starts_x)),
            "local_median_abs_shift": tuple(float(v) for v in np.median(absolute_shifts, axis=(0, 1, 2))),
            "local_max_abs_shift_by_axis": tuple(float(v) for v in np.max(absolute_shifts, axis=(0, 1, 2))),
            "local_max_abs_shift": float(np.max(absolute_shifts)),
            "local_limit_hit_fraction": limit_hit_fraction,
        }
    )
    return output.astype(np.float32), shifts, info


def detect_vessels(movie: np.ndarray, fs: float = 10.0, threshold: float = 90.0) -> tuple[np.ndarray, np.ndarray]:
    mean_img = normalize_image(np.mean(movie, axis=0))
    try:
        vesselness = filters.frangi(mean_img, sigmas=range(1, 8, 2), black_ridges=False)
    except Exception:
        vesselness = filters.sobel(mean_img)
    vesselness = normalize_image(vesselness)
    thr = np.percentile(vesselness, threshold)
    mask = vesselness > thr
    mask = morphology.remove_small_objects(mask, min_size=64)
    mask = morphology.binary_closing(mask, morphology.disk(2))
    return mask.astype(bool), vesselness


def suppress_vessels(movie: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = movie.copy()
    if not np.any(mask):
        return out
    inv = ~mask
    replacement = np.median(movie[:, inv], axis=1) if np.any(inv) else np.median(movie, axis=(1, 2))
    out[:, mask] = replacement[:, None]
    return out.astype(np.float32)


def auto_roi_from_image(image: np.ndarray, min_area: int = 20, max_area: int = 4000, threshold: float | None = None) -> list[np.ndarray]:
    img = normalize_image(image)
    img = gaussian_filter(img, sigma=1.0)
    if threshold is None:
        threshold = float(filters.threshold_otsu(img))
    mask = img > threshold
    mask = morphology.remove_small_objects(mask, min_size=max(3, min_area))
    mask = morphology.binary_opening(mask, morphology.disk(1))
    labels = measure.label(mask)
    rois = []
    for region in measure.regionprops(labels):
        if min_area <= region.area <= max_area:
            rois.append(labels == region.label)
    return rois


def estimate_auto_roi_area_range(
    image: np.ndarray,
    seed_xy: tuple[float, float],
    threshold: float | None = None,
    min_scale: float = 0.5,
    max_scale: float = 2.5,
) -> tuple[int, int] | None:
    img = gaussian_filter(normalize_image(image), sigma=1.0)
    if img.ndim != 2:
        return None
    h, w = img.shape[:2]
    try:
        x, y = float(seed_xy[0]), float(seed_xy[1])
    except Exception:
        return None
    if not np.isfinite(x) or not np.isfinite(y):
        return None
    col = int(round(x))
    row = int(round(y))
    if row < 0 or row >= h or col < 0 or col >= w:
        return None

    if threshold is None:
        try:
            threshold = float(filters.threshold_otsu(img))
        except Exception:
            return None

    mask = img > threshold
    labels = measure.label(mask)
    area = None
    seed_label = labels[row, col]
    if seed_label > 0:
        for region in measure.regionprops(labels):
            if region.label == seed_label:
                area = float(region.area)
                break

    if area is None:
        radius = max(24, min(h, w) // 8)
        y0 = max(0, row - radius)
        y1 = min(h, row + radius + 1)
        x0 = max(0, col - radius)
        x1 = min(w, col + radius + 1)
        crop = img[y0:y1, x0:x1]
        if crop.size == 0:
            return None
        try:
            crop_threshold = float(filters.threshold_otsu(crop))
        except Exception:
            crop_threshold = float(threshold)
        crop_mask = crop > crop_threshold
        crop_labels = measure.label(crop_mask)
        crop_regions = measure.regionprops(crop_labels)
        if not crop_regions:
            return None
        local_row = row - y0
        local_col = col - x0
        crop_label = crop_labels[local_row, local_col]
        if crop_label > 0:
            for region in crop_regions:
                if region.label == crop_label:
                    area = float(region.area)
                    break
        if area is None:
            seed = np.array([local_row, local_col], dtype=np.float32)
            region = min(
                crop_regions,
                key=lambda r: float(np.sum((np.asarray(r.centroid, dtype=np.float32) - seed) ** 2)),
            )
            area = float(region.area)

    if area is None or area <= 0:
        return None

    min_area = max(3, int(round(area * min_scale)))
    max_area = max(min_area + 1, int(round(area * max_scale)))
    max_area = min(max_area, int(h * w))
    return min_area, max_area


def circle_mask(shape: tuple[int, int], center: tuple[float, float], radius: float) -> np.ndarray:
    y, x = np.ogrid[:shape[0], :shape[1]]
    cx, cy = center
    return ((x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2)


def polygon_mask(shape: tuple[int, int], points: list[tuple[float, float]]) -> np.ndarray:
    if len(points) < 3:
        return np.zeros(shape, dtype=bool)
    from matplotlib.path import Path as MplPath

    y, x = np.mgrid[:shape[0], :shape[1]]
    coords = np.vstack((x.ravel(), y.ravel())).T
    return MplPath(points).contains_points(coords).reshape(shape)


def extract_traces(movie: np.ndarray, roi_masks: list[np.ndarray], mode: str = "dff", baseline: np.ndarray | None = None, acceleration: str = "auto") -> np.ndarray:
    if not roi_masks:
        return np.empty((movie.shape[0], 0), dtype=np.float32)
    data = compute_dff(movie, baseline, acceleration=acceleration) if mode == "dff" else movie
    cp = get_cupy() if acceleration in {"auto", "gpu"} else None
    if cp is not None:
        arr = cp.asarray(data, dtype=cp.float32).reshape(data.shape[0], -1)
        masks = cp.asarray(np.stack([m.reshape(-1) for m in roi_masks]).astype(np.float32))
        areas = cp.maximum(cp.sum(masks, axis=1), 1.0)
        traces_gpu = arr @ masks.T / areas[None, :]
        return cp.asnumpy(traces_gpu).astype(np.float32)
    traces = np.zeros((data.shape[0], len(roi_masks)), dtype=np.float32)
    for i, mask in enumerate(roi_masks):
        if np.any(mask):
            traces[:, i] = data[:, mask].mean(axis=1)
    return traces


def env_secant(x_data: np.ndarray, y_data: np.ndarray, view: int, side: str = "bottom") -> np.ndarray:
    x = np.asarray(x_data, dtype=np.float64).reshape(-1)
    y = np.asarray(y_data, dtype=np.float64).reshape(-1)
    if x.size != y.size:
        raise ValueError("x_data 与 y_data 的长度必须相同")
    if x.size == 0:
        return np.array([], dtype=np.float32)
    view = int(view)
    if view <= 1:
        raise ValueError("参数 <view> 过小")
    side_factor = 1.0 if str(side).lower() == "top" else -1.0
    data_len = y.size
    x_new = [x[0]]
    y_new = [y[0]]
    i = 0
    while i < data_len - 1:
        end = min(i + view, data_len - 1)
        ii = np.arange(i + 1, end + 1)
        slopes = ((y[ii] - y[i]) / (ii - i)) * side_factor
        idx = int(np.argmax(slopes))
        i = int(ii[idx])
        x_new.append(x[i])
        y_new.append(y[i])
    if x_new[-1] != x[-1]:
        x_new.append(x[-1])
        y_new.append(y[-1])
    x_unique, idx = np.unique(np.asarray(x_new), return_index=True)
    y_unique = np.asarray(y_new)[idx]
    return np.interp(x, x_unique, y_unique).astype(np.float32)


def baseline_correct_traces(traces: np.ndarray, window: int = 30, method: str = "env_secant") -> np.ndarray:
    if traces.size == 0:
        return traces
    out = traces.copy()
    window = max(3, int(window))
    if method == "env_secant":
        x = np.arange(out.shape[0], dtype=np.float32)
        for i in range(out.shape[1]):
            baseline = env_secant(x, out[:, i], window, "bottom")
            out[:, i] -= baseline
        return out.astype(np.float32)
    for i in range(out.shape[1]):
        baseline = ndimage.percentile_filter(out[:, i], percentile=20, size=window, mode="nearest")
        out[:, i] -= baseline
    return out.astype(np.float32)


def moving_average_traces(traces: np.ndarray, window: int = 1) -> np.ndarray:
    if traces.size == 0:
        return traces
    window = int(window)
    if window <= 1:
        return traces.astype(np.float32, copy=True)
    kernel = np.ones(window, dtype=np.float32) / float(window)
    out = np.empty_like(traces, dtype=np.float32)
    for i in range(traces.shape[1]):
        out[:, i] = np.convolve(traces[:, i], kernel, mode="same")
    return out


def process_traces(traces: np.ndarray, baseline_correct: bool = True, baseline_window: int = 30, smooth_window: int = 1) -> np.ndarray:
    out = traces.astype(np.float32, copy=True)
    if baseline_correct:
        out = baseline_correct_traces(out, baseline_window, method="env_secant")
    out = moving_average_traces(out, smooth_window)
    return out.astype(np.float32)


def detect_trace_peaks(trace: np.ndarray, fs: float, prominence_scale: float = 1.0) -> np.ndarray:
    if trace.size < 3:
        return np.array([], dtype=int)
    prominence = max(np.std(trace) * prominence_scale, 1e-6)
    distance = max(1, int(fs * 0.5))
    peaks, _ = signal.find_peaks(trace, prominence=prominence, distance=distance)
    return peaks


def detect_stimulus_triggers(stimulus: np.ndarray, fs_stimulus: float, threshold: float = 0.0, threshold_factor: float = 2.0) -> np.ndarray:
    if stimulus.size == 0:
        return np.array([], dtype=int)
    data = np.asarray(stimulus, dtype=np.float32)
    auto_threshold = float(np.nanmean(data) + threshold_factor * np.nanstd(data))
    thr = max(float(threshold), auto_threshold)
    above = data > thr
    if not np.any(above):
        thr = float(np.nanmean(data) * 2)
        above = data > thr
    edges = np.diff(np.concatenate(([False], above, [False])).astype(np.int8))
    starts = np.where(edges == 1)[0]
    if starts.size <= 1:
        return starts.astype(int)
    min_interval = max(1, int(round(0.5 * fs_stimulus)))
    kept = [int(starts[0])]
    for idx in starts[1:]:
        if int(idx) - kept[-1] >= min_interval:
            kept.append(int(idx))
    return np.asarray(kept, dtype=int)


def map_stimulus_triggers_to_frames(trigger_samples: np.ndarray, fs_stimulus: float, movie_fs: float, n_frames: int, pre_s: float = 0.0, post_s: float = 0.0) -> np.ndarray:
    if trigger_samples.size == 0:
        return np.array([], dtype=int)
    trigger_times = trigger_samples / float(fs_stimulus)
    frames = np.rint(trigger_times * float(movie_fs)).astype(int)
    pre_frames = int(round(pre_s * movie_fs))
    post_frames = int(round(post_s * movie_fs))
    valid = [int(f) for f in frames if 0 <= f - pre_frames and f + post_frames < n_frames]
    return np.asarray(valid, dtype=int)


def generate_interval_triggers(start_s: float, interval_s: float, movie_fs: float, n_frames: int, pre_s: float = 0.0, post_s: float = 0.0) -> np.ndarray:
    if interval_s <= 0:
        return np.array([], dtype=int)
    start = int(round(start_s * movie_fs))
    step = max(1, int(round(interval_s * movie_fs)))
    pre_frames = int(round(pre_s * movie_fs))
    post_frames = int(round(post_s * movie_fs))
    frames = np.arange(start, n_frames, step, dtype=int)
    return frames[(frames - pre_frames >= 0) & (frames + post_frames < n_frames)]


def event_aligned_blocks(data: np.ndarray, trigger_frames: np.ndarray, fs: float, pre_s: float, post_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    arr = np.asarray(data)
    triggers = np.asarray(trigger_frames, dtype=int).reshape(-1)
    pre = max(0, int(round(float(pre_s) * float(fs))))
    post = max(0, int(round(float(post_s) * float(fs))))
    if pre == 0 and post == 0:
        post = max(1, int(round(float(fs))))
    window = pre + post + 1
    trial_t = (np.arange(window, dtype=np.float32) - pre) / float(fs)
    if arr.ndim == 0 or arr.shape[0] == 0 or triggers.size == 0:
        return np.empty((0, window) + tuple(arr.shape[1:]), dtype=np.float32), trial_t, np.array([], dtype=int)
    blocks = []
    kept = []
    for frame in triggers:
        start = int(frame) - pre
        end = int(frame) + post + 1
        if start >= 0 and end <= arr.shape[0]:
            blocks.append(arr[start:end])
            kept.append(int(frame))
    if not blocks:
        return np.empty((0, window) + tuple(arr.shape[1:]), dtype=np.float32), trial_t, np.array([], dtype=int)
    return np.stack(blocks).astype(np.float32), trial_t, np.asarray(kept, dtype=int)


def event_aligned_mean(data: np.ndarray, trigger_frames: np.ndarray, fs: float, pre_s: float, post_s: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    arr = np.asarray(data, dtype=np.float32)
    triggers = np.asarray(trigger_frames, dtype=int).reshape(-1)
    pre = max(0, int(round(float(pre_s) * float(fs))))
    post = max(0, int(round(float(post_s) * float(fs))))
    if pre == 0 and post == 0:
        post = max(1, int(round(float(fs))))
    window = pre + post + 1
    trial_t = (np.arange(window, dtype=np.float32) - pre) / float(fs)
    out_shape = (window,) + tuple(arr.shape[1:])
    acc = np.zeros(out_shape, dtype=np.float64)
    kept = []
    if arr.ndim == 0 or arr.shape[0] == 0 or triggers.size == 0:
        return np.zeros(out_shape, dtype=np.float32), trial_t, np.array([], dtype=int)
    for frame in triggers:
        start = int(frame) - pre
        end = int(frame) + post + 1
        if start >= 0 and end <= arr.shape[0]:
            acc += arr[start:end].astype(np.float64, copy=False)
            kept.append(int(frame))
    if not kept:
        return np.zeros(out_shape, dtype=np.float32), trial_t, np.array([], dtype=int)
    return (acc / float(len(kept))).astype(np.float32), trial_t, np.asarray(kept, dtype=int)


def trial_average(traces: np.ndarray, trigger_frames: np.ndarray, fs: float, pre_s: float, post_s: float) -> tuple[np.ndarray, np.ndarray]:
    if traces is None:
        return np.empty((0, 0, 0), dtype=np.float32), np.array([], dtype=np.float32)
    blocks, trial_t, _ = event_aligned_blocks(traces, trigger_frames, fs, pre_s, post_s)
    return blocks, trial_t


def roi_statistics(traces: np.ndarray, roi_names: list[str], fs: float, trigger_frames: np.ndarray | None = None) -> pd.DataFrame:
    rows = []
    for i, name in enumerate(roi_names):
        if traces is None or i >= traces.shape[1]:
            continue
        trace = traces[:, i]
        peaks = detect_trace_peaks(trace, fs)
        mean = float(np.nanmean(trace))
        std = float(np.nanstd(trace))
        rows.append({
            "ROI": name,
            "Mean": mean,
            "Std": std,
            "Max": float(np.nanmax(trace)),
            "Baseline_25pct": float(np.nanpercentile(trace, 25)),
            "CV": float(std / abs(mean)) if abs(mean) > 1e-12 else np.nan,
            "Peak_Count": int(len(peaks)),
            "Trigger_Count": int(0 if trigger_frames is None else len(trigger_frames)),
        })
    return pd.DataFrame(rows)


def process_atlas_image(path: str, frame_shape: tuple[int, int], min_area: int = 50) -> tuple[list[np.ndarray], list[str]]:
    atlas = np.asarray(Image.open(path).convert("L"), dtype=np.float32)
    finite = atlas[np.isfinite(atlas)]
    if finite.size == 0:
        raise ValueError("图谱图像中没有有效像素")

    p2, p98 = np.percentile(finite, (2, 98))
    if p98 <= p2:
        p2 = float(np.min(finite))
        p98 = float(np.max(finite))
    if p98 <= p2:
        raise ValueError("图谱图像没有可用对比度")

    atlas_norm = np.clip((atlas - p2) / (p98 - p2), 0, 1)
    binary = atlas_norm > 0.9
    if not np.any(binary):
        binary = atlas_norm > float(filters.threshold_otsu(atlas_norm))

    binary = morphology.remove_small_objects(binary.astype(bool), min_size=max(1, int(min_area)))
    labels = measure.label(binary)
    if labels.max() == 0:
        raise ValueError("图谱图像中未找到有效 ROI")

    resized = cv2.resize(labels.astype(np.int32), (frame_shape[1], frame_shape[0]), interpolation=cv2.INTER_NEAREST)
    regions = [region for region in measure.regionprops(resized) if region.area >= min_area]
    if not regions:
        raise ValueError("图谱图像中未找到有效 ROI")

    regions = sorted(regions, key=lambda region: (region.centroid[0], region.centroid[1]))
    rois = [resized == region.label for region in regions]
    names = [f"AtlasROI{i + 1}" for i in range(len(rois))]
    return rois, names


def process_atlas_json(path: str, frame_shape: tuple[int, int], min_area: int = 50) -> tuple[list[np.ndarray], list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        atlas = json.load(f)
    regions = atlas.get("regions", [])
    if not isinstance(regions, list) or not regions:
        raise ValueError("Atlas JSON 中没有区域")

    frame_h, frame_w = frame_shape[:2]
    src_w = int(atlas.get("image_width", frame_w) or frame_w)
    src_h = int(atlas.get("image_height", frame_h) or frame_h)
    scale_x = frame_w / max(src_w, 1)
    scale_y = frame_h / max(src_h, 1)

    region_items = []
    for idx, region in enumerate(regions, start=1):
        polygon = region.get("polygon")
        if not polygon:
            continue
        pts = np.asarray(polygon, dtype=np.float32)
        if pts.ndim != 2 or pts.shape[0] < 3:
            continue
        pts = np.column_stack([pts[:, 0] * scale_x, pts[:, 1] * scale_y])
        mask = np.zeros((frame_h, frame_w), dtype=np.uint8)
        cv2.fillPoly(mask, [np.round(pts).astype(np.int32)], 1)
        if int(mask.sum()) < int(min_area):
            continue
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            continue
        centroid_x = float(np.mean(xs))
        centroid_y = float(np.mean(ys))
        name = region.get("name")
        if name is None or str(name).strip() == "":
            name = f"AtlasROI{idx}"
        region_items.append((centroid_y, centroid_x, mask.astype(bool), str(name)))

    if not region_items:
        raise ValueError("Atlas JSON 中未找到有效 ROI")

    region_items.sort(key=lambda item: (item[0], item[1]))
    rois = [item[2] for item in region_items]
    names = [item[3] for item in region_items]
    return rois, names


def export_results(
    output_dir: str,
    name: str,
    movie: np.ndarray,
    baseline: np.ndarray,
    roi_masks: list[np.ndarray],
    roi_names: list[str],
    traces: np.ndarray,
    fs: float,
    trigger_frames: np.ndarray | None = None,
    pre_trigger_s: float = 0.0,
    post_trigger_s: float = 0.0,
) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    paths["baseline_png"] = str(out_dir / f"{name}_baseline.png")
    plt.imsave(paths["baseline_png"], normalize_image(baseline), cmap="gray")

    if roi_masks:
        masks = np.stack(roi_masks).astype(bool)
    else:
        masks = np.zeros((0,) + baseline.shape, dtype=bool)
    paths["roi_npz"] = str(out_dir / f"{name}_ROI_data.npz")
    np.savez_compressed(paths["roi_npz"], masks=masks, names=np.array(roi_names), baseline_shape=baseline.shape)

    overlay = draw_roi_overlay(baseline, roi_masks, roi_names)
    paths["roi_overlay_png"] = str(out_dir / f"{name}_ROI_overlay.png")
    cv2.imwrite(paths["roi_overlay_png"], cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    t = np.arange(traces.shape[0]) / fs if traces is not None else np.array([])
    df = pd.DataFrame({"Time_sec": t})
    for i, roi_name in enumerate(roi_names):
        if traces is not None and i < traces.shape[1]:
            df[roi_name] = traces[:, i]
    paths["traces_csv"] = str(out_dir / f"{name}_deltaF_F_multiROI.csv")
    df.to_csv(paths["traces_csv"], index=False)

    paths["trace_plot_png"] = str(out_dir / f"{name}_traces.png")
    plot_traces(paths["trace_plot_png"], t, traces, roi_names, trigger_frames, fs)

    stats = roi_statistics(traces, roi_names, fs, trigger_frames)
    paths["roi_statistics_csv"] = str(out_dir / f"{name}_ROI_statistics.csv")
    stats.to_csv(paths["roi_statistics_csv"], index=False)
    paths["roi_statistics_xlsx"] = str(out_dir / f"{name}_ROI_statistics.xlsx")
    with pd.ExcelWriter(paths["roi_statistics_xlsx"], engine="openpyxl") as writer:
        stats.to_excel(writer, sheet_name="ROI Statistics", index=False)
        info = pd.DataFrame({
            "Item": ["Frames", "Frame Rate Hz", "ROI Count", "Trigger Count", "Pre Trigger s", "Post Trigger s"],
            "Value": [
                int(movie.shape[0]),
                float(fs),
                int(len(roi_masks)),
                int(0 if trigger_frames is None else len(trigger_frames)),
                float(pre_trigger_s),
                float(post_trigger_s),
            ],
        })
        info.to_excel(writer, sheet_name="Experiment Info", index=False)

    if trigger_frames is not None and len(trigger_frames) and traces is not None and traces.size:
        trials, trial_t = trial_average(traces, trigger_frames, fs, pre_trigger_s, post_trigger_s)
        if trials.size:
            mean_trial = np.nanmean(trials, axis=0)
            paths["trial_average_csv"] = str(out_dir / f"{name}_trial_average.csv")
            trial_df = pd.DataFrame({"Time_from_trigger_sec": trial_t})
            for i, roi_name in enumerate(roi_names):
                trial_df[roi_name] = mean_trial[:, i]
            trial_df.to_csv(paths["trial_average_csv"], index=False)
            paths["trial_average_png"] = str(out_dir / f"{name}_trial_average.png")
            plot_trial_average(paths["trial_average_png"], trial_t, mean_trial, roi_names)

    if traces is not None and traces.shape[1] > 1:
        corr = np.corrcoef(traces.T)
        paths["correlation_csv"] = str(out_dir / f"{name}_roi_correlation_matrix.csv")
        pd.DataFrame(corr, index=roi_names, columns=roi_names).to_csv(paths["correlation_csv"])
        paths["correlation_png"] = str(out_dir / f"{name}_roi_correlation_matrix.png")
        plot_correlation(paths["correlation_png"], corr, roi_names)

    dff = compute_dff(movie, baseline)
    heat = np.mean(dff, axis=0)
    combined = np.any(masks, axis=0) if masks.size else np.ones_like(heat, dtype=bool)
    paths["heatmap_png"] = str(out_dir / f"{name}_diff_heatmap.png")
    save_heatmap(paths["heatmap_png"], heat, combined)

    summary = {
        "source": name,
        "frames": int(movie.shape[0]),
        "height": int(movie.shape[1]),
        "width": int(movie.shape[2]),
        "fs": float(fs),
        "roi_count": len(roi_masks),
        "trigger_count": int(0 if trigger_frames is None else len(trigger_frames)),
        "files": paths,
    }
    paths["summary_json"] = str(out_dir / f"{name}_summary.json")
    with open(paths["summary_json"], "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return paths


def roi_color_rgb(index: int) -> tuple[float, float, float]:
    """Return the stable display color assigned to a zero-based ROI index."""
    index = int(index)
    if index < 0:
        raise ValueError("ROI index must be non-negative")
    hue = (0.53 + index * 0.618033988749895) % 1.0
    return tuple(float(channel) for channel in colorsys.hsv_to_rgb(hue, 0.78, 0.82))


def roi_color_uint8(index: int) -> tuple[int, int, int]:
    return tuple(int(round(channel * 255)) for channel in roi_color_rgb(index))


def roi_color_hex(index: int) -> str:
    return "#" + "".join(f"{channel:02x}" for channel in roi_color_uint8(index))


def draw_roi_overlay(
    image: np.ndarray,
    roi_masks: list[np.ndarray],
    roi_names: list[str],
    highlighted_index: int | None = None,
) -> np.ndarray:
    base = (normalize_image(image) * 255).astype(np.uint8)
    rgb = cv2.cvtColor(base, cv2.COLOR_GRAY2RGB)
    if not roi_masks:
        return rgb
    for i, mask in enumerate(roi_masks):
        contours = measure.find_contours(mask.astype(np.uint8), 0.5)
        highlighted = highlighted_index is not None and i == int(highlighted_index)
        color = roi_color_uint8(i)
        thickness = 3 if highlighted else 1
        for contour in contours:
            pts = np.round(contour[:, ::-1]).astype(np.int32)
            cv2.polylines(rgb, [pts], True, color, thickness, cv2.LINE_AA)
        props = measure.regionprops(mask.astype(np.uint8))
        if props:
            y, x = props[0].centroid
            font_scale = 0.50 if highlighted else 0.35
            text_thickness = 2 if highlighted else 1
            cv2.putText(
                rgb,
                str(i + 1),
                (int(x), int(y)),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                color,
                text_thickness,
                cv2.LINE_AA,
            )
    return rgb


def plot_traces(path: str, t: np.ndarray, traces: np.ndarray, roi_names: list[str], trigger_frames: np.ndarray | None = None, fs: float = 10.0) -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    if traces is not None and traces.size:
        offsets = np.arange(traces.shape[1]) * (np.nanstd(traces) * 4 + 0.1)
        for i in range(traces.shape[1]):
            ax.plot(
                t,
                traces[:, i] + offsets[i],
                color=roi_color_hex(i),
                lw=0.9,
                label=roi_names[i] if i < len(roi_names) else f"ROI{i+1}",
            )
        ax.set_yticks(offsets)
        ax.set_yticklabels(roi_names)
    if trigger_frames is not None:
        for frame in trigger_frames:
            if 0 <= frame < len(t):
                ax.axvline(frame / fs, color="red", linestyle="--", linewidth=0.8, alpha=0.55)
    ax.set_xlabel("时间 (s)")
    ax.set_ylabel("ROI dF/F")
    ax.set_title("ROI 钙信号曲线")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_trial_average(path: str, t: np.ndarray, mean_trial: np.ndarray, roi_names: list[str]) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    if mean_trial.size:
        offsets = np.arange(mean_trial.shape[1]) * (np.nanstd(mean_trial) * 4 + 0.1)
        for i in range(mean_trial.shape[1]):
            ax.plot(t, mean_trial[:, i] + offsets[i], color=roi_color_hex(i), lw=1.0)
        ax.set_yticks(offsets)
        ax.set_yticklabels(roi_names)
    ax.axvline(0, color="red", linestyle="--", linewidth=1.0)
    ax.set_xlabel("相对触发时间 (s)")
    ax.set_ylabel("ROI 平均 dF/F")
    ax.set_title("试次平均")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def safe_filename(text: object, fallback: str = "item") -> str:
    name = re.sub(r"[^\w.-]+", "_", str(text).strip(), flags=re.UNICODE).strip("._")
    return name or fallback


def plot_event_aligned_roi(path: str, trial_t: np.ndarray, roi_trials: np.ndarray, roi_name: str, trigger_count: int) -> None:
    arr = np.asarray(roi_trials, dtype=np.float32)
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    if arr.size:
        for trial in arr:
            ax.plot(trial_t, trial, color="0.70", linewidth=0.8, alpha=0.55)
        mean_trial = np.nanmean(arr, axis=0)
        ax.plot(trial_t, mean_trial, color="black", linewidth=2.0, label="均值")
    ax.axvline(0, color="red", linestyle="--", linewidth=1.2, label="刺激")
    ax.set_xlabel("相对刺激时间 (s)")
    ax.set_ylabel("dF/F")
    ax.set_title(f"{roi_name} 刺激对齐响应，n={trigger_count}")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", frameon=False)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_correlation(path: str, corr: np.ndarray, roi_names: list[str]) -> None:
    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(corr, cmap="hot", vmin=-1, vmax=1)
    ax.set_xticks(np.arange(len(roi_names)))
    ax.set_yticks(np.arange(len(roi_names)))
    ax.set_xticklabels(roi_names, rotation=45, ha="right")
    ax.set_yticklabels(roi_names)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title("ROI 相关性")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def save_heatmap(path: str, heat: np.ndarray, mask: np.ndarray) -> None:
    data = gaussian_filter(heat.astype(np.float32), sigma=2)
    data = data.copy()
    data[~mask] = np.nan
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(data, cmap="jet")
    ax.set_title("均值 dF/F 热图")
    ax.axis("off")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def save_event_heatmap(path: str, heat: np.ndarray, title: str = "刺激对齐均值 dF/F", top_percent: float | None = None) -> None:
    data = gaussian_filter(np.asarray(heat, dtype=np.float32), sigma=2)
    data = data.copy()
    if top_percent is not None and top_percent > 0:
        top_percent = float(np.clip(top_percent, 0.0, 100.0))
        finite = data[np.isfinite(data)]
        if finite.size:
            threshold = float(np.percentile(finite, 100.0 - top_percent))
            data[data < threshold] = np.nan
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(data, cmap="jet")
    ax.set_title(title)
    ax.axis("off")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def traces_dataframe(traces: np.ndarray, roi_names: list[str], fs: float) -> pd.DataFrame:
    traces = np.asarray(traces, dtype=np.float32)
    t = np.arange(traces.shape[0], dtype=np.float32) / float(fs)
    df = pd.DataFrame({"Time_sec": t})
    for i, roi_name in enumerate(roi_names):
        if i < traces.shape[1]:
            df[str(roi_name)] = traces[:, i]
    return df


def save_traces_csv(path: str, traces: np.ndarray, roi_names: list[str], fs: float) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    traces_dataframe(traces, roi_names, fs).to_csv(path, index=False)


def save_roi_statistics_table(
    path: str,
    stats: pd.DataFrame,
    movie: np.ndarray | None = None,
    fs: float | None = None,
    roi_count: int | None = None,
    trigger_count: int | None = None,
    pre_trigger_s: float = 0.0,
    post_trigger_s: float = 0.0,
) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    ext = Path(path).suffix.lower()
    if ext == ".xlsx":
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            stats.to_excel(writer, sheet_name="ROI Statistics", index=False)
            if movie is not None:
                info = pd.DataFrame({
                    "Item": ["Frames", "Frame Rate Hz", "ROI Count", "Trigger Count", "Pre Trigger s", "Post Trigger s"],
                    "Value": [
                        int(movie.shape[0]),
                        float(fs or 0),
                        int(0 if roi_count is None else roi_count),
                        int(0 if trigger_count is None else trigger_count),
                        float(pre_trigger_s),
                        float(post_trigger_s),
                    ],
                })
                info.to_excel(writer, sheet_name="Experiment Info", index=False)
        return
    stats.to_csv(path, index=False)


def save_correlation_outputs(output_dir: str, name: str, traces: np.ndarray, roi_names: list[str]) -> dict[str, str]:
    if traces is None or traces.shape[1] < 2:
        raise ValueError("相关性导出至少需要两条 ROI 曲线")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    corr = np.corrcoef(traces.T)
    paths = {
        "correlation_csv": str(out_dir / f"{name}_roi_correlation_matrix.csv"),
        "correlation_png": str(out_dir / f"{name}_roi_correlation_matrix.png"),
    }
    pd.DataFrame(corr, index=roi_names, columns=roi_names).to_csv(paths["correlation_csv"])
    plot_correlation(paths["correlation_png"], corr, roi_names)
    return paths


def save_roi_snapshot_outputs(output_dir: str, name: str, baseline: np.ndarray, roi_masks: list[np.ndarray], roi_names: list[str]) -> dict[str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "baseline_png": str(out_dir / f"{name}_baseline.png"),
        "roi_npz": str(out_dir / f"{name}_ROI_data.npz"),
        "roi_overlay_png": str(out_dir / f"{name}_ROI_overlay.png"),
    }
    plt.imsave(paths["baseline_png"], normalize_image(baseline), cmap="gray")
    masks = np.stack(roi_masks).astype(bool) if roi_masks else np.zeros((0,) + baseline.shape, dtype=bool)
    np.savez_compressed(paths["roi_npz"], masks=masks, names=np.array(roi_names), baseline_shape=baseline.shape)
    overlay = draw_roi_overlay(baseline, roi_masks, roi_names)
    cv2.imwrite(paths["roi_overlay_png"], cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    return paths


def save_summary_json(
    path: str,
    name: str,
    movie: np.ndarray,
    fs: float,
    roi_masks: list[np.ndarray],
    trigger_frames: np.ndarray | None = None,
    files: dict[str, str] | None = None,
) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "source": name,
        "frames": int(movie.shape[0]),
        "height": int(movie.shape[1]),
        "width": int(movie.shape[2]),
        "fs": float(fs),
        "roi_count": int(len(roi_masks)),
        "trigger_count": int(0 if trigger_frames is None else len(trigger_frames)),
        "files": files or {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return path


def export_event_aligned_response(
    output_dir: str,
    name: str,
    movie: np.ndarray,
    baseline: np.ndarray,
    roi_masks: list[np.ndarray],
    roi_names: list[str],
    traces: np.ndarray,
    trigger_frames: np.ndarray,
    fs: float,
    pre_s: float,
    post_s: float,
    heatmap_start_s: float = 0.0,
    heatmap_end_s: float | None = None,
    top_percent: float | None = None,
    acceleration: str = "auto",
) -> dict[str, str]:
    if traces is None or traces.size == 0:
        raise ValueError("刺激事件对齐平均需要先提取 ROI 曲线")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_filename(name, "NewLight")
    paths: dict[str, str] = {}

    trials, trial_t, kept_triggers = event_aligned_blocks(traces, trigger_frames, fs, pre_s, post_s)
    if trials.size == 0 or kept_triggers.size == 0:
        raise ValueError("所选事件前后窗口内没有完整刺激事件")

    paths["event_trials_npz"] = str(out_dir / f"{safe_name}_stimulus_event_trials.npz")
    np.savez_compressed(
        paths["event_trials_npz"],
        trials=trials,
        trial_time_sec=trial_t,
        trigger_frames=kept_triggers,
        roi_names=np.array(roi_names),
        pre_s=float(pre_s),
        post_s=float(post_s),
    )

    mean_trial = np.nanmean(trials, axis=0)
    mean_df = pd.DataFrame({"Time_from_stimulus_sec": trial_t})
    for i, roi_name in enumerate(roi_names):
        if i < mean_trial.shape[1]:
            mean_df[str(roi_name)] = mean_trial[:, i]
    paths["event_mean_csv"] = str(out_dir / f"{safe_name}_stimulus_event_mean_traces.csv")
    mean_df.to_csv(paths["event_mean_csv"], index=False)

    for i, roi_name in enumerate(roi_names):
        if i >= trials.shape[2]:
            continue
        roi_path = out_dir / f"{safe_name}_stimulus_event_{i + 1:03d}_{safe_filename(roi_name, f'ROI{i + 1}')}.png"
        plot_event_aligned_roi(str(roi_path), trial_t, trials[:, :, i], str(roi_name), int(kept_triggers.size))
        paths[f"event_roi_{i + 1:03d}_png"] = str(roi_path)

    dff = compute_dff(movie, baseline, acceleration=acceleration)
    mean_movie, movie_t, kept_movie_triggers = event_aligned_mean(dff, kept_triggers, fs, pre_s, post_s)
    if kept_movie_triggers.size == 0:
        raise ValueError("所选事件前后窗口内没有完整视频事件")
    if heatmap_end_s is None:
        heatmap_end_s = float(post_s)
    h_start = float(heatmap_start_s)
    h_end = float(heatmap_end_s)
    if h_end < h_start:
        h_start, h_end = h_end, h_start
    frame_mask = (movie_t >= h_start) & (movie_t <= h_end)
    if not np.any(frame_mask):
        frame_mask = movie_t >= 0
    if not np.any(frame_mask):
        frame_mask = np.ones_like(movie_t, dtype=bool)
    event_heat = np.nanmean(mean_movie[frame_mask], axis=0)
    paths["event_heatmap_png"] = str(out_dir / f"{safe_name}_stimulus_event_heatmap.png")
    save_event_heatmap(
        paths["event_heatmap_png"],
        event_heat,
        title=f"刺激对齐均值 dF/F（{h_start:g} 至 {h_end:g} s）",
    )

    if top_percent is not None and float(top_percent) > 0:
        pct = float(np.clip(float(top_percent), 0.0, 100.0))
        paths["event_heatmap_top_png"] = str(out_dir / f"{safe_name}_stimulus_event_heatmap_top_{pct:g}pct.png")
        save_event_heatmap(
            paths["event_heatmap_top_png"],
            event_heat,
            title=f"刺激对齐均值 dF/F，最高 {pct:g}%",
            top_percent=pct,
        )

    paths["event_summary_json"] = str(out_dir / f"{safe_name}_stimulus_event_summary.json")
    summary = {
        "source": name,
        "fs": float(fs),
        "pre_s": float(pre_s),
        "post_s": float(post_s),
        "heatmap_start_s": float(h_start),
        "heatmap_end_s": float(h_end),
        "top_percent": None if top_percent is None else float(top_percent),
        "trigger_count_input": int(len(trigger_frames)),
        "trigger_count_used": int(kept_triggers.size),
        "roi_count": int(len(roi_names)),
        "movie_shape": [int(x) for x in movie.shape],
        "files": paths,
    }
    with open(paths["event_summary_json"], "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return paths


def heatmap_limits(
    data: np.ndarray,
    low_percentile: float = 1.0,
    high_percentile: float = 99.0,
    max_display: float | None = None,
) -> tuple[float, float]:
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return -0.1, 1.0
    vmin = float(np.percentile(finite, low_percentile))
    if max_display is None:
        vmax = float(np.percentile(finite, high_percentile))
    else:
        vmax = float(max_display)
    if vmax <= vmin:
        vmax = vmin + 1.0
    return vmin, vmax


def add_heatmap_colorbar(
    frame_rgb: np.ndarray,
    vmin: float,
    vmax: float,
    colormap: str = "jet",
    label: str = "dF/F",
) -> np.ndarray:
    frame = np.asarray(frame_rgb, dtype=np.uint8).copy()
    if frame.ndim != 3 or frame.shape[2] != 3:
        return frame
    h, w = frame.shape[:2]
    if h < 40 or w < 80:
        return frame

    panel_w = min(max(72, w // 6), max(72, w // 4))
    out = np.zeros((h, w + panel_w, 3), dtype=np.uint8)
    out[:, :w] = frame
    frame = out
    x_panel = w

    margin = max(8, panel_w // 10)
    top = max(18, h // 18)
    bottom = h - max(18, h // 18)
    bar_h = max(1, bottom - top)
    bar_w = max(12, min(20, panel_w // 4))
    bar_x = x_panel + margin
    bar_y = top
    cmap = plt.get_cmap(colormap)
    gradient = np.linspace(1.0, 0.0, bar_h, dtype=np.float32).reshape(bar_h, 1)
    bar = (cmap(gradient)[:, :, :3] * 255).astype(np.uint8)
    bar = np.repeat(bar, bar_w, axis=1)
    frame[bar_y:bar_y + bar_h, bar_x:bar_x + bar_w] = bar

    cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (255, 255, 255), 1, cv2.LINE_AA)

    def fmt(value: float) -> str:
        value = float(value)
        if abs(value) >= 100 or (0 < abs(value) < 0.01):
            return f"{value:.2g}"
        return f"{value:.3g}"

    text_x = min(frame.shape[1] - 4, bar_x + bar_w + 6)
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, label, (bar_x, max(11, top - 6)), font, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, fmt(vmax), (text_x, min(h - 4, top + 5)), font, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, fmt((vmin + vmax) / 2.0), (text_x, min(h - 4, top + bar_h // 2 + 4)), font, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, fmt(vmin), (text_x, max(10, bottom - 2)), font, 0.35, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def render_heatmap_frame_rgb(
    dff_frame: np.ndarray,
    raw_frame: np.ndarray,
    mask: np.ndarray,
    vmin: float,
    vmax: float,
    alpha: float = 0.55,
    sigma: float = 1.2,
    show_colorbar: bool = False,
    heatmap_only: bool = False,
    colormap: str = "jet",
) -> np.ndarray:
    bg = cv2.cvtColor(to_uint8(raw_frame), cv2.COLOR_GRAY2RGB).astype(np.float32)
    smooth = gaussian_filter(dff_frame.astype(np.float32), sigma=max(0.0, float(sigma)))
    span = max(float(vmax) - float(vmin), 1e-6)
    norm = np.clip((smooth - vmin) / span, 0, 1)
    heat_rgb = (plt.get_cmap(colormap)(norm)[..., :3] * 255).astype(np.float32)
    mask3 = mask[..., None].astype(np.float32)
    alpha = float(np.clip(alpha, 0, 1))
    if heatmap_only:
        frame = np.full_like(heat_rgb, 255, dtype=np.float32)
        mask_bool = mask.astype(bool)
        frame[mask_bool] = heat_rgb[mask_bool]
    else:
        frame = ((1 - alpha * mask3) * bg + (alpha * mask3) * heat_rgb)
    frame = np.clip(frame, 0, 255).astype(np.uint8)
    if show_colorbar:
        frame = add_heatmap_colorbar(frame, vmin, vmax, colormap=colormap)
    return frame


def parse_optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"auto", "none", "nan"}:
        return None
    return float(text)


def save_heatmap_video(
    path: str,
    dff_movie: np.ndarray,
    raw_movie: np.ndarray,
    mask: np.ndarray,
    fs: float,
    alpha: float = 0.55,
    sigma: float = 1.2,
    low_percentile: float = 1.0,
    high_percentile: float = 99.0,
    max_display: float | None = None,
    show_colorbar: bool = True,
    heatmap_only: bool = False,
    cancel_event=None,
    progress_callback=None,
) -> bool:
    if dff_movie.ndim != 3 or dff_movie.shape[0] == 0:
        return False
    fps = float(fs) if fs and fs > 0 else 10.0
    vmin, vmax = heatmap_limits(dff_movie, low_percentile, high_percentile, max_display=max_display)
    if cancel_event is not None and cancel_event.is_set():
        return False
    first_rgb = render_heatmap_frame_rgb(
        dff_movie[0],
        raw_movie[0],
        mask,
        vmin,
        vmax,
        alpha,
        sigma,
        show_colorbar=show_colorbar,
        heatmap_only=heatmap_only,
    )
    out_h, out_w = first_rgb.shape[:2]
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (out_w, out_h), isColor=True)
    if not writer.isOpened():
        raise IOError(f"无法创建热图视频：{path}")
    completed = False
    try:
        writer.write(cv2.cvtColor(first_rgb, cv2.COLOR_RGB2BGR))
        if progress_callback is not None:
            progress_callback(1, dff_movie.shape[0])
        for i in range(1, dff_movie.shape[0]):
            if cancel_event is not None and cancel_event.is_set():
                break
            frame_rgb = render_heatmap_frame_rgb(
                dff_movie[i],
                raw_movie[i],
                mask,
                vmin,
                vmax,
                alpha,
                sigma,
                show_colorbar=show_colorbar,
                heatmap_only=heatmap_only,
            )
            writer.write(cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR))
            if progress_callback is not None:
                progress_callback(i + 1, dff_movie.shape[0])
        completed = cancel_event is None or not cancel_event.is_set()
    finally:
        writer.release()
    return completed


def run_conda_worker(env_name: str, script: str, args: list[str], cwd: str | None = None, timeout: int | None = None) -> subprocess.CompletedProcess:
    if IS_FROZEN:
        worker_candidates = [
            APP_RESOURCE_DIR / "NewLight_Worker.exe",
            APP_EXEC_DIR / "NewLight_Worker.exe",
            APP_RESOURCE_DIR.parent / "NewLight_Worker.exe",
            PROJECT_DIR / "NewLight_Worker.exe",
        ]
        worker_exe = next((candidate for candidate in worker_candidates if candidate.exists()), None)
        if worker_exe is not None:
            cmd = [str(worker_exe), script] + args
        else:
            cmd = [str(Path(sys.executable)), "--worker", script] + args
    else:
        environment_path = Path(env_name)
        selector = ["-p", str(environment_path)] if environment_path.is_dir() else ["-n", env_name]
        cmd = ["conda", "run"] + selector + ["--no-capture-output", "python", script] + args
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("NEWLIGHT_RESOURCE_DIR", str(APP_RESOURCE_DIR))
    env.setdefault("MKL_THREADING_LAYER", "SEQUENTIAL")
    env.setdefault("KERAS_BACKEND", "torch")
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        **hidden_subprocess_kwargs(),
    )


def caiman_worker_environment() -> str:
    if (NEWLIGHT_CAIMAN_PREFIX / "python.exe").is_file():
        return str(NEWLIGHT_CAIMAN_PREFIX)
    return "caiman_latest"


def resolve_conda_environment_prefix(environment: str) -> Path | None:
    selector = Path(str(environment)).expanduser()
    if selector.is_dir():
        return selector.resolve()

    name = str(environment)
    candidates = []
    for value in (os.environ.get("CONDA_PREFIX"), sys.prefix):
        if value:
            candidate = Path(value).expanduser()
            if candidate.name.lower() == name.lower():
                candidates.append(candidate)

    conda_executable = shutil.which("conda")
    if conda_executable:
        executable = Path(conda_executable).resolve()
        roots = (executable.parent, executable.parent.parent)
        candidates.extend(root / "envs" / name for root in roots)
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / ".conda" / "envs" / name)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return None


def run_neuroseg3(input_image: np.ndarray, output_dir: str, weights: str | None = None, conf: float = 0.25, mask_threshold: float = 0.5) -> tuple[list[np.ndarray], str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = out_dir / "neuroseg3_input.png"
    mask_path = out_dir / "neuroseg3_masks.npz"
    plt.imsave(input_path, normalize_image(input_image), cmap="gray")
    script = WORKER_DIR / "run_neuroseg3.py"
    weights = weights or str(NEUROSEG3_DIR / "weights" / "segmentation" / "yolov8s-seg.pt")
    proc = run_conda_worker(
        "neuroseg3",
        str(script),
        [
            "--input", str(input_path),
            "--output", str(mask_path),
            "--weights", weights,
            "--conf", str(conf),
            "--mask-threshold", str(mask_threshold),
        ],
        cwd=str(NEUROSEG3_DIR),
        timeout=600,
    )
    log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        raise RuntimeError(log.strip() or "NeuroSeg3 运行失败")
    if not mask_path.exists():
        raise RuntimeError("NeuroSeg3 已结束，但未生成蒙版")
    with np.load(mask_path, allow_pickle=True) as data:
        masks = [m.astype(bool) for m in data["masks"]]
    return masks, log


def _roi_worker_log(proc: subprocess.CompletedProcess) -> str:
    raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        if "OpenCL" in line and "vendors" in line and "temp.txt" in line:
            continue
        if stripped in {"Access is denied.", "The system cannot find the file specified."}:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _load_roi_worker_result(
    artifact_path: Path,
    summary_path: Path,
    expected_shape: tuple[int, int],
    log: str,
    metadata_updates: dict | None = None,
    aligned_arrays: tuple[str, ...] = (),
    required_arrays: tuple[str, ...] = (),
) -> ROIBackendResult:
    if not artifact_path.is_file():
        raise RuntimeError("ROI worker finished without creating an ROI artifact")
    if not summary_path.is_file():
        raise RuntimeError("ROI worker finished without creating a summary")
    artifact = load_roi_artifact(artifact_path, expected_shape=expected_shape)
    mask_count = int(artifact.masks.shape[0])
    for name in aligned_arrays:
        if name not in artifact.arrays:
            continue
        array = np.asarray(artifact.arrays[name])
        if array.ndim == 0 or int(array.shape[0]) != mask_count:
            raise ROIArtifactError(
                f"ROI quality array {name!r} count does not match mask count {mask_count}"
            )
    missing = [name for name in required_arrays if name not in artifact.arrays]
    if missing:
        raise ROIArtifactError(f"ROI artifact is missing required quality array {missing[0]!r}")
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read ROI worker summary: {exc}") from exc
    if not isinstance(summary, dict):
        raise RuntimeError("ROI worker summary must be a JSON object")
    metadata = dict(artifact.metadata)
    metadata.update(summary)
    metadata.update(metadata_updates or {})
    return ROIBackendResult(
        masks=artifact.masks,
        names=artifact.names,
        metadata=metadata,
        arrays=artifact.arrays,
        log=log,
        artifact_path=artifact_path,
        summary_path=summary_path,
    )


def run_caiman_roi_segmentation(
    input_movie: np.ndarray,
    session_dir: str,
    frame_rate: float = 10.0,
    invalid_start_frames: int = 0,
    mode: str = "two_photon",
    cell_diameter: float = 12.0,
    components_per_patch: int = 4,
    background_components: int = 2,
    spatial_subsample: int = 2,
    temporal_subsample: int = 2,
    ar_order: int = 1,
    merge_threshold: float = 0.85,
    min_snr: float = 2.0,
    rval_threshold: float = 0.85,
    use_cnn: bool = True,
    min_cnn_threshold: float = 0.99,
    cnn_lowest: float = 0.1,
    footprint_threshold: float = 0.20,
    candidate_mode: bool = False,
) -> ROIBackendResult:
    movie = np.asarray(input_movie)
    if movie.ndim != 3 or movie.shape[0] == 0:
        raise ValueError("CaImAn ROI extraction requires a non-empty (frames, height, width) movie")
    root = Path(session_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    job_dir = root / f"caiman_roi_{uuid.uuid4().hex[:10]}"
    job_dir.mkdir(parents=True, exist_ok=False)
    input_path = job_dir / "input_movie.tif"
    artifact_path = job_dir / "caiman_rois.npz"
    summary_path = job_dir / "caiman_summary.json"
    tifffile.imwrite(input_path, movie, photometric="minisblack")
    script = WORKER_DIR / "run_caiman_roi.py"
    environment = caiman_worker_environment()
    args = [
        "--input", str(input_path),
        "--output", str(artifact_path),
        "--summary", str(summary_path),
        "--session-dir", str(job_dir),
        "--caiman-data", str(CAIMAN_RESOURCE_DIR),
        "--mode", str(mode),
        "--frame-rate", str(float(frame_rate)),
        "--invalid-start-frames", str(max(0, int(invalid_start_frames))),
        "--cell-diameter", str(float(cell_diameter)),
        "--components-per-patch", str(int(components_per_patch)),
        "--background-components", str(int(background_components)),
        "--spatial-subsample", str(int(spatial_subsample)),
        "--temporal-subsample", str(int(temporal_subsample)),
        "--ar-order", str(int(ar_order)),
        "--merge-threshold", str(float(merge_threshold)),
        "--min-snr", str(float(min_snr)),
        "--rval-threshold", str(float(rval_threshold)),
        "--use-cnn" if use_cnn else "--no-cnn",
        "--min-cnn-threshold", str(float(min_cnn_threshold)),
        "--cnn-lowest", str(float(cnn_lowest)),
        "--footprint-threshold", str(float(footprint_threshold)),
    ]
    if candidate_mode:
        args.append("--candidate-mode")
    succeeded = False
    try:
        proc = run_conda_worker(environment, str(script), args, cwd=str(PROJECT_DIR), timeout=7200)
        log = _roi_worker_log(proc)
        if proc.returncode != 0:
            raise RuntimeError(log or "CaImAn ROI extraction failed")
        result = _load_roi_worker_result(
            artifact_path,
            summary_path,
            expected_shape=tuple(movie.shape[1:]),
            log=log,
            aligned_arrays=(
                "traces",
                "snr",
                "r_values",
                "cnn_scores",
                "component_indices",
                "preset_accepted",
            ),
            required_arrays=(
                "traces",
                "snr",
                "r_values",
                "cnn_scores",
                "component_indices",
                "preset_accepted",
            ) if candidate_mode else (),
        )
        succeeded = True
        return result
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except OSError:
            pass
        if not succeeded:
            shutil.rmtree(job_dir, ignore_errors=True)


def run_fast_roi_segmentation(
    input_image: np.ndarray,
    session_dir: str,
    projection_mode: str = "mean",
    weights: str | None = None,
    runtime_root: str | None = None,
    image_size: int = 960,
    confidence: float = 0.25,
    iou: float = 0.70,
    min_area: int = 20,
    max_area: int = 4000,
    device: str = "auto",
    candidate_mode: bool = False,
    candidate_confidence: float = 0.05,
) -> ROIBackendResult:
    image = np.asarray(input_image)
    if image.ndim != 2 or image.size == 0:
        raise ValueError("Fast ROI extraction requires a non-empty 2D projection")
    root = Path(session_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    job_dir = root / f"fast_roi_{uuid.uuid4().hex[:10]}"
    job_dir.mkdir(parents=True, exist_ok=False)
    input_path = job_dir / "projection.tif"
    artifact_path = job_dir / "fast_rois.npz"
    summary_path = job_dir / "fast_summary.json"
    tifffile.imwrite(input_path, image, photometric="minisblack")
    script = WORKER_DIR / "run_neusuite_roi.py"
    weights_path = Path(weights).resolve() if weights else NEUSUITE_DEFAULT_WEIGHTS.resolve()
    runtime_path = Path(runtime_root).resolve() if runtime_root else NEUSUITE_RUNTIME_ROOT.resolve()
    args = [
        "--input", str(input_path),
        "--output", str(artifact_path),
        "--summary", str(summary_path),
        "--weights", str(weights_path),
        "--runtime-root", str(runtime_path),
        "--image-size", str(int(image_size)),
        "--confidence", str(float(confidence)),
        "--candidate-confidence", str(float(candidate_confidence)),
        "--iou", str(float(iou)),
        "--min-area", str(int(min_area)),
        "--max-area", str(int(max_area)),
        "--device", str(device),
    ]
    if candidate_mode:
        args.append("--candidate-mode")
    succeeded = False
    try:
        proc = run_conda_worker("neuroseg3", str(script), args, cwd=str(PROJECT_DIR), timeout=1800)
        log = _roi_worker_log(proc)
        if proc.returncode != 0:
            raise RuntimeError(log or "Fast ROI extraction failed")
        result = _load_roi_worker_result(
            artifact_path,
            summary_path,
            expected_shape=tuple(image.shape),
            log=log,
            metadata_updates={"projection_mode": str(projection_mode)},
            aligned_arrays=("scores", "source_indices"),
            required_arrays=("scores", "source_indices") if candidate_mode else (),
        )
        succeeded = True
        return result
    finally:
        try:
            input_path.unlink(missing_ok=True)
        except OSError:
            pass
        if not succeeded:
            shutil.rmtree(job_dir, ignore_errors=True)


def run_caiman_motion(
    input_movie: np.ndarray,
    output_dir: str,
    mode: str = "rigid",
    max_shift: int = 12,
    stride: int = 48,
    overlap: int = 24,
    max_deviation: int = 5,
) -> tuple[np.ndarray, str, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = out_dir / "caiman_input.tif"
    output_path = out_dir / "caiman_preview.tif"
    output_path.unlink(missing_ok=True)
    max_shift = max(1, int(max_shift))
    stride = max(1, int(stride))
    overlap = max(0, int(overlap))
    max_deviation = max(0, int(max_deviation))
    save_movie_tiff(input_movie, str(input_path))
    script = WORKER_DIR / "run_caiman.py"
    proc = run_conda_worker(
        "caiman_latest",
        str(script),
        [
            "motion",
            "--input", str(input_path),
            "--output", str(output_path),
            "--mode", mode,
            "--max-shift", str(max_shift),
            "--stride", str(stride),
            "--overlap", str(overlap),
            "--max-deviation", str(max_deviation),
        ],
        timeout=1800,
    )
    raw_log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    log_lines = []
    for line in raw_log.splitlines():
        stripped = line.strip()
        if stripped.startswith("CaImAn motion correction saved "):
            continue
        if "OpenCL" in line and "vendors" in line and "temp.txt" in line:
            continue
        if stripped in {"Access is denied.", "The system cannot find the file specified."}:
            continue
        log_lines.append(line)
    log = "\n".join(log_lines).strip()
    keep_preview = False
    try:
        if proc.returncode != 0:
            raise RuntimeError(log or raw_log.strip() or "CaImAn 运动矫正失败")
        result = tifffile.imread(output_path).astype(np.float32)
        keep_preview = True
        return result, log, str(output_path)
    finally:
        cleanup_paths = (input_path,) if keep_preview else (input_path, output_path)
        for temporary_path in cleanup_paths:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def run_deepcadrt_denoise(
    input_movie: np.ndarray,
    output_dir: str,
    model: str | None = None,
    overlap: float = 0.6,
    invalid_start_frames: int = 0,
) -> tuple[np.ndarray, str]:
    if not DEEPCADRT_DIR.exists():
        raise FileNotFoundError(f"未找到 DeepCAD-RT PyTorch 文件夹：{DEEPCADRT_DIR}")
    model_arg = ensure_deepcadrt_model_available(model)
    overlap = float(np.clip(float(overlap), 0.0, 0.95))
    source_movie = np.asarray(input_movie)
    invalid_start_frames = normalized_invalid_start_frames(source_movie, invalid_start_frames)
    model_input = source_movie[invalid_start_frames:]
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = out_dir / f"deepcadrt_input_{uuid.uuid4().hex[:8]}.tif"
    output_path = out_dir / f"deepcadrt_denoised_{uuid.uuid4().hex[:8]}.tif"
    save_movie_tiff(model_input, str(input_path))
    script = WORKER_DIR / "run_deepcadrt.py"
    args = [
        "--input", str(input_path),
        "--output", str(output_path),
        "--deepcad-dir", str(DEEPCADRT_DIR),
        "--overlap", f"{overlap:.6g}",
    ]
    if model_arg:
        args.extend(["--model", model_arg])
    proc = run_conda_worker(
        "deepcadrt",
        str(script),
        args,
        cwd=str(DEEPCADRT_DIR),
        timeout=None,
    )
    log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    try:
        input_path.unlink(missing_ok=True)
    except OSError:
        pass
    if proc.returncode != 0:
        raise RuntimeError(log.strip() or "DeepCAD-RT 降噪失败")
    if not output_path.exists():
        raise RuntimeError("DeepCAD-RT 已结束，但未生成输出 TIFF。")
    denoised = tifffile.imread(output_path).astype(np.float32)
    if denoised.ndim == 2:
        denoised = denoised[None, :, :]
    if denoised.shape != model_input.shape:
        raise RuntimeError(f"DeepCAD-RT 输出 shape {denoised.shape} 与有效输入 {model_input.shape} 不一致。")
    denoised, empty_frames = preserve_empty_source_frames(model_input, denoised)
    if empty_frames.size:
        log = log.rstrip() + f"\n已保留 {empty_frames.size} 个输入空白帧：" + ", ".join(str(int(frame)) for frame in empty_frames)
    denoised, invalid_frames = preserve_invalid_denoised_frames(model_input, denoised)
    if invalid_frames.size:
        log = log.rstrip() + f"\n已回退 {invalid_frames.size} 个异常 DeepCAD-RT 输出帧：" + ", ".join(str(int(frame)) for frame in invalid_frames)
    if invalid_start_frames:
        denoised = np.concatenate((source_movie[:invalid_start_frames].astype(np.float32), denoised), axis=0)
        log = log.rstrip() + f"\n已跳过并原样保留前 {invalid_start_frames} 个无效起始帧。"
    return denoised, log
