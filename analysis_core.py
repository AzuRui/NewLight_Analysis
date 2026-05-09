from __future__ import annotations

import json
import os
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


WORKSPACE = Path(__file__).resolve().parents[1]
NEUROSEG3_DIR = WORKSPACE / "NeuroSeg3"
_CUPY_CACHE = None


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
    baseline_start_s: float = 0.0
    baseline_duration_s: float = 0.0
    pre_trigger_s: float = 0.0
    post_trigger_s: float = 0.0
    source_path: str = ""
    history: list[tuple[str, np.ndarray]] = field(default_factory=list)
    last_message: str = ""


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
        baseline = np.percentile(movie, 25, axis=0)
    baseline = baseline.astype(np.float32)
    baseline[baseline <= 0] = np.finfo(np.float32).eps
    return baseline


def baseline_from_seconds(movie: np.ndarray, fs: float, start_s: float, duration_s: float, mode: str = "percentile") -> np.ndarray:
    start = max(0, int(round(start_s * fs)))
    if duration_s and duration_s > 0:
        end = start + int(round(duration_s * fs))
    else:
        end = None
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


def trial_average(traces: np.ndarray, trigger_frames: np.ndarray, fs: float, pre_s: float, post_s: float) -> tuple[np.ndarray, np.ndarray]:
    if traces is None or traces.size == 0 or trigger_frames.size == 0:
        return np.empty((0, 0, 0), dtype=np.float32), np.array([], dtype=np.float32)
    pre = int(round(pre_s * fs))
    post = int(round(post_s * fs))
    if pre == 0 and post == 0:
        post = int(round(fs))
    window = pre + post + 1
    blocks = []
    for frame in trigger_frames:
        start = int(frame) - pre
        end = int(frame) + post + 1
        if start >= 0 and end <= traces.shape[0]:
            blocks.append(traces[start:end])
    if not blocks:
        return np.empty((0, 0, 0), dtype=np.float32), np.array([], dtype=np.float32)
    stack = np.stack(blocks).astype(np.float32)
    t = (np.arange(window) - pre) / float(fs)
    return stack, t.astype(np.float32)


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
        frame = heat_rgb * mask3
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
    cmd = ["conda", "run", "-n", env_name, "python", script] + args
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def run_neuroseg3(input_image: np.ndarray, output_dir: str, weights: str | None = None, conf: float = 0.25, mask_threshold: float = 0.5) -> tuple[list[np.ndarray], str]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = out_dir / "neuroseg3_input.png"
    mask_path = out_dir / "neuroseg3_masks.npz"
    plt.imsave(input_path, normalize_image(input_image), cmap="gray")
    script = Path(__file__).resolve().parent / "workers" / "run_neuroseg3.py"
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
    script = Path(__file__).resolve().parent / "workers" / "run_caiman.py"
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
