from __future__ import annotations

import json
import os
import re
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
    traces: np.ndarray | None = None
    stimulus: np.ndarray | None = None
    trigger_frames: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    fs: float = 10.0
    stimulus_fs: float = 2000.0
    baseline_start_frame: int = 0
    baseline_duration_frames: int = 0
    pre_trigger_s: float = 0.0
    post_trigger_s: float = 0.0
    source_path: str = ""
    converted_color_avi_path: str = ""
    converted_source_folder: str = ""
    converted_channel_avi_paths: tuple[str, ...] = field(default_factory=tuple)
    converted_channel_movies: tuple[np.ndarray, ...] = field(default_factory=tuple)
    history: list[tuple] = field(default_factory=list)
    last_message: str = ""


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
    color_avi_path: Path
    channel_avi_paths: tuple[Path, ...]
    source_folder: Path
    protocol: TwoPhotonProtocol
    frames: int
    channel_count: int


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
        return "GPU requested, CuPy unavailable; using CPU"
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


def to_uint8(image: np.ndarray) -> np.ndarray:
    return (normalize_image(image) * 255).astype(np.uint8)


def load_movie(path: str, max_preview_frames: int | None = None) -> tuple[np.ndarray, float]:
    ext = Path(path).suffix.lower()
    if ext in {".tif", ".tiff"}:
        arr = tifffile.imread(path)
        arr = np.asarray(arr)
        if arr.ndim == 2:
            arr = arr[None, :, :]
        if arr.ndim == 3:
            pass
        elif arr.ndim == 4:
            arr = arr[..., 0]
        else:
            raise ValueError(f"Unsupported TIFF shape: {arr.shape}")
        if max_preview_frames and arr.shape[0] > max_preview_frames:
            arr = arr[:max_preview_frames]
        return arr.astype(np.float32), 10.0
    if ext in {".avi", ".mp4", ".mov", ".mkv"}:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
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
            raise IOError(f"No frames read from: {path}")
        return np.stack(frames, axis=0), float(fps)
    raise ValueError(f"Unsupported file type: {ext}")


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
        raise FileNotFoundError(f"No protocol*.txt file found in {folder}")
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
        raise ValueError(f"Protocol does not contain a valid image size: {protocol_path}")
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
                raise ValueError(f"Invalid TDMS segment at offset {pos}: {path}")
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
        raise ValueError(f"No raw TDMS image segments found: {path}")
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
        raise FileNotFoundError(f"No .tdms file found in {folder}")
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
    ch1_arr = np.asarray(ch1, dtype=np.float32)
    if ch1_limits is None:
        ch1_limits = (float(np.nanmin(ch1_arr)), float(np.nanmax(ch1_arr)))
    green = _scale_channel_to_uint8(ch1_arr, ch1_limits)
    if ch2 is None:
        red = np.zeros_like(green)
    else:
        ch2_arr = np.asarray(ch2, dtype=np.float32)
        if ch2_limits is None:
            ch2_limits = (float(np.nanmin(ch2_arr)), float(np.nanmax(ch2_arr)))
        red = _scale_channel_to_uint8(ch2_arr, ch2_limits)
    rgb = np.zeros(ch1_arr.shape + (3,), dtype=np.uint8)
    rgb[:, :, 0] = red
    rgb[:, :, 1] = green
    return rgb


def two_photon_analysis_movie(channel_movies: tuple[np.ndarray, ...]) -> np.ndarray:
    if not channel_movies:
        raise ValueError("No channel movies were provided")
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
) -> ConvertedTwoPhotonMovie:
    folder = Path(folder)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    protocol = read_two_photon_protocol(folder)
    tdms_path = _two_photon_tdms_path(folder)
    raw_slots = tdms_image_slot_count(tdms_path, protocol.width, protocol.height)
    frame_count, channel_count = _channel_frame_count(protocol, raw_slots)
    if frame_count <= 0:
        raise ValueError(f"No complete image frames found in {tdms_path}")

    ch1_limits, ch2_limits = _sample_channel_limits(tdms_path, protocol, frame_count, channel_count)
    movie_path = output_dir / "converted_movie.npy"
    movie = np.lib.format.open_memmap(
        movie_path,
        mode="w+",
        dtype=np.float32,
        shape=(frame_count, protocol.height, protocol.width),
    )
    channel_movies: list[np.ndarray] = []
    channel_avi_paths: list[Path] = []
    channel_writers = []
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
        ch_avi_path = output_dir / f"converted_ch{channel_idx + 1}.avi"
        ch_writer = cv2.VideoWriter(
            str(ch_avi_path),
            cv2.VideoWriter_fourcc(*"MJPG"),
            float(protocol.frame_rate),
            (protocol.width, protocol.height),
            isColor=True,
        )
        if not ch_writer.isOpened():
            raise IOError(f"Cannot create AVI video: {ch_avi_path}")
        channel_avi_paths.append(ch_avi_path)
        channel_writers.append(ch_writer)
    color_avi_path = output_dir / "converted_pseudocolor.avi"
    writer = cv2.VideoWriter(
        str(color_avi_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        float(protocol.frame_rate),
        (protocol.width, protocol.height),
        isColor=True,
    )
    if not writer.isOpened():
        raise IOError(f"Cannot create AVI video: {color_avi_path}")
    slots = iter_tdms_image_slots(tdms_path, protocol.width, protocol.height)
    try:
        for frame_idx in range(frame_count):
            ch1 = next(slots).astype(np.float32) + 32768.0
            ch2 = next(slots).astype(np.float32) + 32768.0 if channel_count == 2 else None
            channel_movies[0][frame_idx] = ch1
            channel_writers[0].write(cv2.cvtColor(_scale_channel_to_uint8(ch1, ch1_limits), cv2.COLOR_GRAY2BGR))
            if ch2 is not None and len(channel_movies) > 1:
                channel_movies[1][frame_idx] = ch2
                channel_writers[1].write(cv2.cvtColor(_scale_channel_to_uint8(ch2, ch2_limits), cv2.COLOR_GRAY2BGR))
            movie[frame_idx] = np.maximum(ch1, ch2) if ch2 is not None else ch1
            writer.write(pseudocolor_bgr(ch1, ch2, ch1_limits, ch2_limits))
            if progress is not None:
                progress(frame_idx + 1, frame_count)
    finally:
        writer.release()
        for ch_writer in channel_writers:
            ch_writer.release()
        movie.flush()
        for ch_movie in channel_movies:
            ch_movie.flush()

    return ConvertedTwoPhotonMovie(
        movie=movie,
        channel_movies=tuple(channel_movies),
        fs=float(protocol.frame_rate),
        color_avi_path=color_avi_path,
        channel_avi_paths=tuple(channel_avi_paths),
        source_folder=folder,
        protocol=protocol,
        frames=frame_count,
        channel_count=channel_count,
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
            raise ValueError("Stimulus CSV does not contain numeric columns")
        data = numeric.iloc[:, 0].to_numpy(dtype=np.float32)
    elif ext in {".txt", ".dat"}:
        data = np.loadtxt(path, dtype=np.float32)
    else:
        raise ValueError(f"Unsupported stimulus file: {ext}")
    data = np.asarray(data, dtype=np.float32).reshape(-1)
    return data[np.isfinite(data)]


def save_movie_tiff(movie: np.ndarray, path: str) -> None:
    tifffile.imwrite(path, np.asarray(movie, dtype=np.float32), photometric="minisblack")


def _movie_to_uint8(movie: np.ndarray) -> np.ndarray:
    arr = np.asarray(movie)
    if arr.ndim == 2:
        arr = arr[None, :, :]
    if arr.ndim != 3:
        raise ValueError(f"Expected a 3D movie stack, got shape {arr.shape}")
    if arr.dtype == np.uint8:
        return arr.copy()
    arr = arr.astype(np.float32, copy=False)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return np.zeros(arr.shape, dtype=np.uint8)
    lo, hi = np.percentile(finite, [1, 99])
    if hi <= lo:
        lo, hi = float(np.nanmin(finite)), float(np.nanmax(finite))
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    return np.clip((arr - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


def save_movie_avi(movie: np.ndarray, path: str, fs: float = 10.0) -> None:
    frames = _movie_to_uint8(movie)
    fps = float(fs) if fs and fs > 0 else 10.0
    h, w = frames.shape[1:3]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"MJPG"), fps, (w, h), isColor=True)
    if not writer.isOpened():
        raise IOError(f"Cannot create AVI video: {path}")
    try:
        for frame in frames:
            writer.write(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
    finally:
        writer.release()


def save_movie(movie: np.ndarray, path: str, fs: float = 10.0) -> None:
    ext = Path(path).suffix.lower()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if ext in {".tif", ".tiff"}:
        save_movie_tiff(movie, path)
        return
    if ext == ".avi":
        save_movie_avi(movie, path, fs=fs)
        return
    raise ValueError(f"Unsupported movie output type: {ext}. Use .tif, .tiff, or .avi")


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
        raise ValueError(f"Cannot blend movies with different shapes: {raw.shape} vs {denoised.shape}")
    return ((1.0 - weight) * raw + weight * denoised).astype(np.float32, copy=False)


def blend_images(raw_image: np.ndarray, denoised_image: np.ndarray, weight: float) -> np.ndarray:
    weight = float(np.clip(weight, 0.0, 1.0))
    raw = np.asarray(raw_image, dtype=np.float32)
    denoised = np.asarray(denoised_image, dtype=np.float32)
    if raw.shape != denoised.shape:
        raise ValueError(f"Cannot blend images with different shapes: {raw.shape} vs {denoised.shape}")
    return ((1.0 - weight) * raw + weight * denoised).astype(np.float32, copy=False)


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


def baseline_from_frames(movie: np.ndarray, start_frame: int | float = 0, duration_frames: int | float = 0) -> np.ndarray:
    start = max(0, int(round(float(start_frame))))
    duration = max(0, int(round(float(duration_frames))))
    if duration <= 0:
        return compute_baseline(movie, mode="percentile")
    if start >= movie.shape[0]:
        raise ValueError(f"Baseline start frame {start} is outside movie length {movie.shape[0]}")
    end = min(movie.shape[0], start + duration)
    if end <= start:
        raise ValueError("Baseline duration selects no frames")
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


def compute_projection(movie: np.ndarray, mode: str, acceleration: str = "auto") -> np.ndarray:
    cp = get_cupy() if acceleration in {"auto", "gpu"} else None
    if cp is not None and mode in {"mean", "max", "std"}:
        arr = cp.asarray(movie, dtype=cp.float32)
        if mode == "max":
            return cp.asnumpy(cp.max(arr, axis=0)).astype(np.float32)
        if mode == "std":
            return cp.asnumpy(cp.std(arr, axis=0)).astype(np.float32)
        return cp.asnumpy(cp.mean(arr, axis=0)).astype(np.float32)
    if mode == "max":
        return np.max(movie, axis=0)
    if mode == "std":
        return np.std(movie, axis=0)
    if mode == "corr":
        return local_correlation_image(movie)
    return np.mean(movie, axis=0)


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


def enhance_contrast(movie: np.ndarray) -> np.ndarray:
    out = np.empty_like(movie, dtype=np.float32)
    for i, frame in enumerate(movie):
        out[i] = exposure.equalize_adapthist(normalize_image(frame), clip_limit=0.02)
    return out.astype(np.float32)


def rigid_motion_correction(movie: np.ndarray, template_frames: int = 100) -> tuple[np.ndarray, list[tuple[float, float]]]:
    n = min(movie.shape[0], max(1, int(template_frames)))
    template = np.mean(movie[:n], axis=0)
    corrected = np.empty_like(movie, dtype=np.float32)
    shifts = []
    try:
        from skimage.registration import phase_cross_correlation
    except Exception as exc:
        raise RuntimeError("skimage.registration.phase_cross_correlation is unavailable") from exc
    for i, frame in enumerate(movie):
        shift, _, _ = phase_cross_correlation(template, frame, upsample_factor=10)
        corrected[i] = ndimage.shift(frame, shift=shift, order=1, mode="nearest")
        shifts.append((float(shift[0]), float(shift[1])))
    return corrected, shifts


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
        raise ValueError("x_data and y_data must have the same length")
    if x.size == 0:
        return np.array([], dtype=np.float32)
    view = int(view)
    if view <= 1:
        raise ValueError("Parameter <view> too small")
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
        raise ValueError("Atlas image contains no valid pixels")

    p2, p98 = np.percentile(finite, (2, 98))
    if p98 <= p2:
        p2 = float(np.min(finite))
        p98 = float(np.max(finite))
    if p98 <= p2:
        raise ValueError("Atlas image has no contrast")

    atlas_norm = np.clip((atlas - p2) / (p98 - p2), 0, 1)
    binary = atlas_norm > 0.9
    if not np.any(binary):
        binary = atlas_norm > float(filters.threshold_otsu(atlas_norm))

    binary = morphology.remove_small_objects(binary.astype(bool), min_size=max(1, int(min_area)))
    labels = measure.label(binary)
    if labels.max() == 0:
        raise ValueError("No valid ROIs found in atlas image")

    resized = cv2.resize(labels.astype(np.int32), (frame_shape[1], frame_shape[0]), interpolation=cv2.INTER_NEAREST)
    regions = [region for region in measure.regionprops(resized) if region.area >= min_area]
    if not regions:
        raise ValueError("No valid ROIs found in atlas image")

    regions = sorted(regions, key=lambda region: (region.centroid[0], region.centroid[1]))
    rois = [resized == region.label for region in regions]
    names = [f"AtlasROI{i + 1}" for i in range(len(rois))]
    return rois, names


def process_atlas_json(path: str, frame_shape: tuple[int, int], min_area: int = 50) -> tuple[list[np.ndarray], list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        atlas = json.load(f)
    regions = atlas.get("regions", [])
    if not isinstance(regions, list) or not regions:
        raise ValueError("Atlas JSON has no regions")

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
        raise ValueError("No valid ROIs found in atlas JSON")

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


def draw_roi_overlay(image: np.ndarray, roi_masks: list[np.ndarray], roi_names: list[str]) -> np.ndarray:
    base = (normalize_image(image) * 255).astype(np.uint8)
    rgb = cv2.cvtColor(base, cv2.COLOR_GRAY2RGB)
    if not roi_masks:
        return rgb
    colors = (plt.cm.hsv(np.linspace(0, 1, max(len(roi_masks), 1)))[:, :3] * 255).astype(np.uint8)
    for i, mask in enumerate(roi_masks):
        contours = measure.find_contours(mask.astype(np.uint8), 0.5)
        color = tuple(int(c) for c in colors[i % len(colors)])
        for contour in contours:
            pts = np.round(contour[:, ::-1]).astype(np.int32)
            cv2.polylines(rgb, [pts], True, color, 1, cv2.LINE_AA)
        props = measure.regionprops(mask.astype(np.uint8))
        if props:
            y, x = props[0].centroid
            cv2.putText(rgb, str(i + 1), (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)
    return rgb


def plot_traces(path: str, t: np.ndarray, traces: np.ndarray, roi_names: list[str], trigger_frames: np.ndarray | None = None, fs: float = 10.0) -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    if traces is not None and traces.size:
        offsets = np.arange(traces.shape[1]) * (np.nanstd(traces) * 4 + 0.1)
        for i in range(traces.shape[1]):
            ax.plot(t, traces[:, i] + offsets[i], lw=0.9, label=roi_names[i] if i < len(roi_names) else f"ROI{i+1}")
        ax.set_yticks(offsets)
        ax.set_yticklabels(roi_names)
    if trigger_frames is not None:
        for frame in trigger_frames:
            if 0 <= frame < len(t):
                ax.axvline(frame / fs, color="red", linestyle="--", linewidth=0.8, alpha=0.55)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("ROI dF/F")
    ax.set_title("ROI Calcium Traces")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_trial_average(path: str, t: np.ndarray, mean_trial: np.ndarray, roi_names: list[str]) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    if mean_trial.size:
        offsets = np.arange(mean_trial.shape[1]) * (np.nanstd(mean_trial) * 4 + 0.1)
        for i in range(mean_trial.shape[1]):
            ax.plot(t, mean_trial[:, i] + offsets[i], lw=1.0)
        ax.set_yticks(offsets)
        ax.set_yticklabels(roi_names)
    ax.axvline(0, color="red", linestyle="--", linewidth=1.0)
    ax.set_xlabel("Time from trigger (s)")
    ax.set_ylabel("Mean ROI dF/F")
    ax.set_title("Trial Average")
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
        ax.plot(trial_t, mean_trial, color="black", linewidth=2.0, label="Mean")
    ax.axvline(0, color="red", linestyle="--", linewidth=1.2, label="Stimulus")
    ax.set_xlabel("Time from stimulus (s)")
    ax.set_ylabel("dF/F")
    ax.set_title(f"{roi_name} stimulus-aligned response, n={trigger_count}")
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
    ax.set_title("ROI Correlation")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def save_heatmap(path: str, heat: np.ndarray, mask: np.ndarray) -> None:
    data = gaussian_filter(heat.astype(np.float32), sigma=2)
    data = data.copy()
    data[~mask] = np.nan
    fig, ax = plt.subplots(figsize=(7, 6))
    im = ax.imshow(data, cmap="jet")
    ax.set_title("Mean dF/F Heatmap")
    ax.axis("off")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)


def save_event_heatmap(path: str, heat: np.ndarray, title: str = "Stimulus-aligned mean dF/F", top_percent: float | None = None) -> None:
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
        raise ValueError("Need at least two ROI traces for correlation export")
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
        raise ValueError("Stimulus event average needs extracted ROI traces")
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_name = safe_filename(name, "NewLight")
    paths: dict[str, str] = {}

    trials, trial_t, kept_triggers = event_aligned_blocks(traces, trigger_frames, fs, pre_s, post_s)
    if trials.size == 0 or kept_triggers.size == 0:
        raise ValueError("No complete stimulus events fit inside the selected pre/post window")

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
        raise ValueError("No complete movie events fit inside the selected pre/post window")
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
        title=f"Stimulus-aligned mean dF/F ({h_start:g} to {h_end:g} s)",
    )

    if top_percent is not None and float(top_percent) > 0:
        pct = float(np.clip(float(top_percent), 0.0, 100.0))
        paths["event_heatmap_top_png"] = str(out_dir / f"{safe_name}_stimulus_event_heatmap_top_{pct:g}pct.png")
        save_event_heatmap(
            paths["event_heatmap_top_png"],
            event_heat,
            title=f"Stimulus-aligned mean dF/F, top {pct:g}%",
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
        raise IOError(f"Cannot create heatmap video: {path}")
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
        cmd = ["conda", "run", "-n", env_name, "python", script] + args
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("NEWLIGHT_RESOURCE_DIR", str(APP_RESOURCE_DIR))
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
        raise RuntimeError(log.strip() or "NeuroSeg3 failed")
    if not mask_path.exists():
        raise RuntimeError("NeuroSeg3 finished but did not create masks")
    with np.load(mask_path, allow_pickle=True) as data:
        masks = [m.astype(bool) for m in data["masks"]]
    return masks, log


def run_caiman_motion(input_movie: np.ndarray, output_dir: str, mode: str = "rigid") -> tuple[np.ndarray, str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = out_dir / "caiman_input.tif"
    output_path = out_dir / f"caiman_corrected_{uuid.uuid4().hex[:8]}.tif"
    save_movie_tiff(input_movie, str(input_path))
    script = WORKER_DIR / "run_caiman.py"
    proc = run_conda_worker(
        "caiman_latest",
        str(script),
        ["motion", "--input", str(input_path), "--output", str(output_path), "--mode", mode],
        timeout=1800,
    )
    log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        raise RuntimeError(log.strip() or "CaImAn motion correction failed")
    return tifffile.imread(output_path).astype(np.float32), log


def run_deepcadrt_denoise(
    input_movie: np.ndarray,
    output_dir: str,
    model: str | None = None,
    overlap: float = 0.6,
) -> tuple[np.ndarray, str]:
    if not DEEPCADRT_DIR.exists():
        raise FileNotFoundError(f"DeepCAD-RT pytorch folder not found: {DEEPCADRT_DIR}")
    model_arg = ensure_deepcadrt_model_available(model)
    overlap = float(np.clip(float(overlap), 0.0, 0.95))
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = out_dir / f"deepcadrt_input_{uuid.uuid4().hex[:8]}.tif"
    output_path = out_dir / f"deepcadrt_denoised_{uuid.uuid4().hex[:8]}.tif"
    save_movie_tiff(input_movie, str(input_path))
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
        raise RuntimeError(log.strip() or "DeepCAD-RT denoising failed")
    if not output_path.exists():
        raise RuntimeError("DeepCAD-RT finished but did not create an output TIFF.")
    denoised = tifffile.imread(output_path).astype(np.float32)
    if denoised.ndim == 2:
        denoised = denoised[None, :, :]
    if denoised.shape != np.asarray(input_movie).shape:
        raise RuntimeError(f"DeepCAD-RT output shape {denoised.shape} does not match input {np.asarray(input_movie).shape}.")
    return denoised, log
