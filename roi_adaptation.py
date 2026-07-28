from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage
from skimage import filters, measure, morphology


@dataclass(frozen=True)
class QualityPreset:
    fast_confidence: float
    caiman_min_snr: float
    caiman_rval: float
    caiman_cnn: float
    similarity_limit: float


QUALITY_PRESETS = {
    "recall": QualityPreset(0.10, 1.5, 0.70, 0.70, 3.0),
    "balanced": QualityPreset(0.25, 2.0, 0.80, 0.90, 2.3),
    "precision": QualityPreset(0.40, 2.5, 0.90, 0.99, 1.7),
}

SOURCE_WEIGHTS = {
    "manual": 1.0,
    "loaded": 0.8,
    "atlas": 0.8,
    "fast": 0.6,
    "caiman": 0.6,
}

FEATURE_COLUMNS = (
    "log_area",
    "equivalent_diameter",
    "eccentricity",
    "solidity",
    "compactness",
    "perimeter_area",
    "projection_mean",
    "ring_mean",
    "local_contrast",
    "gaussian_1_mean",
    "gaussian_2_mean",
    "sobel_mean",
    "log_mean",
    "temporal_snr",
    "trace_consistency",
)


@dataclass(frozen=True)
class RefinedROI:
    mask: np.ndarray
    low_quality: bool
    reasons: tuple[str, ...]
    confidence: float


@dataclass(frozen=True)
class FeatureTable:
    values: np.ndarray
    columns: tuple[str, ...] = FEATURE_COLUMNS


def normalized_finite_image(image):
    array = np.asarray(image, dtype=np.float32)
    finite = np.isfinite(array)
    if not np.any(finite):
        return np.zeros(array.shape, dtype=np.float32)
    low, high = np.percentile(array[finite], (1.0, 99.0))
    if high <= low:
        return np.zeros(array.shape, dtype=np.float32)
    clean = np.where(finite, array, low)
    return np.clip((clean - low) / (high - low), 0.0, 1.0).astype(np.float32)


def fixed_convolution_maps(projection):
    image = normalized_finite_image(projection)
    return {
        "gaussian_1": ndimage.gaussian_filter(image, 1.0),
        "gaussian_2": ndimage.gaussian_filter(image, 2.0),
        "sobel": np.hypot(ndimage.sobel(image, axis=0), ndimage.sobel(image, axis=1)),
        "log": np.abs(ndimage.gaussian_laplace(image, 1.2)),
    }


def _trace_snr(trace):
    values = np.asarray(trace, dtype=np.float32)
    if values.size < 3 or not np.isfinite(values).any():
        return 0.0
    values = np.where(np.isfinite(values), values, np.nanmedian(values))
    noise = np.diff(values)
    noise_mad = float(np.median(np.abs(noise - np.median(noise))))
    noise_scale = max(1e-6, 1.4826 * noise_mad / np.sqrt(2.0))
    signal_scale = float(np.percentile(values, 95) - np.percentile(values, 20))
    return max(0.0, signal_scale / noise_scale)


def _pixel_trace_correlations(movie, mask, reference_trace):
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return np.zeros(mask.shape, dtype=np.float32)
    data = np.asarray(movie, dtype=np.float32).reshape(movie.shape[0], -1)[:, indices]
    reference = np.asarray(reference_trace, dtype=np.float32)
    reference = reference - np.mean(reference)
    reference_norm = float(np.linalg.norm(reference))
    if reference_norm <= 1e-8:
        return np.zeros(mask.shape, dtype=np.float32)
    data = data - np.mean(data, axis=0, keepdims=True)
    norms = np.linalg.norm(data, axis=0) * reference_norm
    correlations = np.divide(
        reference @ data,
        norms,
        out=np.zeros(indices.size, dtype=np.float32),
        where=norms > 1e-8,
    )
    result = np.zeros(mask.size, dtype=np.float32)
    result[indices] = np.clip(correlations, -1.0, 1.0)
    return result.reshape(mask.shape)


def _component_with_greatest_overlap(candidate, reference):
    labels = measure.label(np.asarray(candidate, dtype=bool), connectivity=2)
    if labels.max() == 0:
        return None
    best_label = max(
        range(1, int(labels.max()) + 1),
        key=lambda label: int(np.count_nonzero((labels == label) & reference)),
    )
    selected = labels == best_label
    if not np.any(selected & reference):
        return None
    return selected


def refine_protected_mask(movie, projection, mask):
    data = np.asarray(movie, dtype=np.float32)
    original = np.asarray(mask, dtype=bool)
    if data.ndim != 3 or data.shape[1:] != original.shape or not np.any(original):
        return RefinedROI(original.copy(), True, ("ROI 或视频尺寸无效",), 0.0)

    trace = np.mean(data[:, original], axis=1)
    if float(np.nanstd(trace)) <= 1e-6:
        return RefinedROI(original.copy(), True, ("ROI 内没有可辨识的时间活动",), 0.0)

    area = int(np.count_nonzero(original))
    equivalent_diameter = 2.0 * np.sqrt(area / np.pi)
    search_radius = int(np.clip(round(equivalent_diameter * 0.25), 2, 12))
    search = morphology.dilation(original, morphology.disk(search_radius))
    correlations = _pixel_trace_correlations(data, search, trace)
    projection_norm = normalized_finite_image(projection)
    gaussian_support = fixed_convolution_maps(projection)["gaussian_1"]
    correlation_support = np.clip((correlations + 1.0) * 0.5, 0.0, 1.0)
    support = 0.68 * correlation_support + 0.27 * projection_norm + 0.05 * gaussian_support
    values = support[search]
    try:
        threshold = float(filters.threshold_otsu(values))
    except ValueError:
        threshold = float(np.percentile(values, 65))
    threshold = max(threshold, float(np.percentile(values, 55)))
    selected = _component_with_greatest_overlap((support >= threshold) & search, original)
    if selected is None:
        return RefinedROI(original.copy(), True, ("未找到与原 ROI 相交的活动轮廓",), 0.0)

    minimum_area = max(1, int(np.ceil(area * 0.5)))
    maximum_area = max(minimum_area, int(np.floor(area * 1.8)))
    while np.count_nonzero(selected) < minimum_area:
        expanded = morphology.dilation(selected, morphology.disk(1)) & search
        if np.array_equal(expanded, selected):
            break
        selected = expanded
    selected = morphology.closing(selected, morphology.disk(1))
    selected = ndimage.binary_fill_holes(selected)
    selected = _component_with_greatest_overlap(selected, original)
    refined_area = 0 if selected is None else int(np.count_nonzero(selected))
    if selected is None or refined_area < minimum_area or refined_area > maximum_area:
        return RefinedROI(original.copy(), True, ("优化轮廓超出允许面积范围",), 0.0)

    confidence = float(np.mean(support[selected]))
    low_quality = confidence < 0.55
    reasons = ("活动轮廓支持较弱",) if low_quality else ()
    return RefinedROI(np.asarray(selected, dtype=bool).copy(), low_quality, reasons, confidence)


def build_feature_table(movie, projection, masks):
    data = np.asarray(movie, dtype=np.float32)
    image = normalized_finite_image(projection)
    convolution = fixed_convolution_maps(image)
    rows = []
    for value in masks:
        mask = np.asarray(value, dtype=bool)
        area = int(np.count_nonzero(mask))
        if area == 0:
            rows.append(np.zeros(len(FEATURE_COLUMNS), dtype=np.float32))
            continue
        props = measure.regionprops(mask.astype(np.uint8))[0]
        perimeter = float(measure.perimeter(mask))
        compactness = float(4.0 * np.pi * area / max(perimeter * perimeter, 1e-6))
        ring = morphology.dilation(mask, morphology.disk(3)) & ~mask
        projection_mean = float(np.mean(image[mask]))
        ring_mean = float(np.mean(image[ring])) if np.any(ring) else projection_mean
        trace = np.mean(data[:, mask], axis=1) if data.ndim == 3 and data.shape[1:] == mask.shape else np.zeros(1)
        correlations = _pixel_trace_correlations(data, mask, trace) if data.ndim == 3 and data.shape[1:] == mask.shape else np.zeros(mask.shape)
        rows.append(
            np.asarray(
                [
                    np.log1p(area),
                    2.0 * np.sqrt(area / np.pi),
                    float(props.eccentricity),
                    float(props.solidity),
                    compactness,
                    perimeter / area,
                    projection_mean,
                    ring_mean,
                    projection_mean - ring_mean,
                    float(np.mean(convolution["gaussian_1"][mask])),
                    float(np.mean(convolution["gaussian_2"][mask])),
                    float(np.mean(convolution["sobel"][mask])),
                    float(np.mean(convolution["log"][mask])),
                    _trace_snr(trace),
                    float(np.mean(correlations[mask])),
                ],
                dtype=np.float32,
            )
        )
    values = np.stack(rows) if rows else np.zeros((0, len(FEATURE_COLUMNS)), dtype=np.float32)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return FeatureTable(values=values, columns=FEATURE_COLUMNS)


def suggest_area_range(masks, current_min, current_max):
    areas = sorted(int(np.count_nonzero(mask)) for mask in masks if np.any(mask))
    if not areas:
        return int(current_min), int(current_max)
    suggested_max = max(1, int(round(areas[-1] * 1.1)))
    if len(areas) == 1:
        return int(current_min), max(int(current_min), suggested_max)
    suggested_min = max(1, int(round(areas[0] * 0.9)))
    return suggested_min, max(suggested_min, suggested_max)


def normalized_roi_metadata(value, source, fallback_name):
    item = dict(value or {})
    base_name = str(item.get("base_name", fallback_name)).rstrip("*") or str(fallback_name)
    return {
        "source": str(item.get("source", source)),
        "protected": bool(item.get("protected", False)),
        "low_quality": bool(item.get("low_quality", False)),
        "quality_reasons": [str(reason) for reason in item.get("quality_reasons", [])],
        "base_name": base_name,
    }


def display_roi_name(metadata):
    base_name = str(metadata["base_name"]).rstrip("*")
    return base_name + ("*" if metadata.get("low_quality") else "")
