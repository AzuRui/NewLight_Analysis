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


@dataclass(frozen=True)
class CandidateBank:
    engine: str
    masks: np.ndarray
    names: tuple[str, ...]
    model_quality: dict[str, np.ndarray]
    source_signature: tuple
    generation_parameters: dict

    def __post_init__(self):
        masks = np.asarray(self.masks, dtype=bool)
        if masks.ndim != 3:
            raise ValueError("Candidate masks must have shape (count, height, width)")
        if masks.shape[0] != len(self.names):
            raise ValueError("Candidate mask and name counts do not match")
        for key, values in self.model_quality.items():
            if np.asarray(values).reshape(-1).size != masks.shape[0]:
                raise ValueError(f"Candidate quality array '{key}' is not aligned with masks")

    @classmethod
    def empty(cls, engine, image_shape):
        shape = tuple(int(value) for value in image_shape)
        return cls(
            str(engine),
            np.zeros((0,) + shape, dtype=bool),
            (),
            {},
            (),
            {},
        )


@dataclass(frozen=True)
class AdaptiveROIResult:
    masks: tuple[np.ndarray, ...]
    metadata: tuple[dict, ...]
    fitted_parameters: dict
    protected_count: int
    selected_count: int
    low_quality_count: int


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


_FEATURE_SCALE_FLOORS = np.asarray(
    [0.35, 3.0, 0.20, 0.15, 0.20, 0.12, 0.15, 0.15, 0.15, 0.15, 0.15, 0.25, 0.15, 1.5, 0.20],
    dtype=np.float32,
)
_FEATURE_DISTANCE_WEIGHTS = np.asarray(
    [2.0, 2.0, 1.5, 1.5, 1.5, 1.5, 1.0, 1.0, 1.25, 1.0, 1.0, 1.0, 1.0, 1.25, 1.25],
    dtype=np.float32,
)


def _weighted_median(values, weights):
    order = np.argsort(values)
    sorted_values = np.asarray(values, dtype=np.float32)[order]
    sorted_weights = np.asarray(weights, dtype=np.float32)[order]
    cumulative = np.cumsum(sorted_weights)
    cutoff = float(cumulative[-1]) * 0.5
    return float(sorted_values[min(int(np.searchsorted(cumulative, cutoff, side="left")), len(sorted_values) - 1)])


def _fit_reference_distribution(features, metadata):
    values = np.asarray(features, dtype=np.float32)
    if values.shape[0] == 0:
        return np.zeros(len(FEATURE_COLUMNS), dtype=np.float32), np.ones(len(FEATURE_COLUMNS), dtype=np.float32)
    weights = np.asarray(
        [SOURCE_WEIGHTS.get(str(item.get("source", "loaded")), 0.7) for item in metadata],
        dtype=np.float32,
    )
    centers = np.asarray(
        [_weighted_median(values[:, column], weights) for column in range(values.shape[1])],
        dtype=np.float32,
    )
    deviations = np.abs(values - centers[None, :])
    scales = np.asarray(
        [_weighted_median(deviations[:, column], weights) * 1.4826 for column in range(values.shape[1])],
        dtype=np.float32,
    )
    return centers, np.maximum(scales, _FEATURE_SCALE_FLOORS)


def _mask_iou(first, second):
    first_mask = np.asarray(first, dtype=bool)
    second_mask = np.asarray(second, dtype=bool)
    union = int(np.count_nonzero(first_mask | second_mask))
    return float(np.count_nonzero(first_mask & second_mask) / union) if union else 0.0


def _candidate_quality_passes(bank, index, preset):
    quality = bank.model_quality
    if bank.engine == "fast":
        scores = np.asarray(quality.get("scores", np.ones(len(bank.names))), dtype=np.float32)
        return float(scores[index]) >= preset.fast_confidence
    if bank.engine == "caiman":
        snr = np.asarray(quality.get("snr", np.full(len(bank.names), np.inf)), dtype=np.float32)
        r_values = np.asarray(quality.get("r_values", np.full(len(bank.names), np.inf)), dtype=np.float32)
        cnn = np.asarray(quality.get("cnn_scores", np.full(len(bank.names), np.inf)), dtype=np.float32)
        return float(snr[index]) >= preset.caiman_min_snr and (
            float(r_values[index]) >= preset.caiman_rval or float(cnn[index]) >= preset.caiman_cnn
        )
    return True


def _candidate_distance(feature, centers, scales):
    standardized = np.abs((np.asarray(feature, dtype=np.float32) - centers) / scales)
    weighted = standardized * _FEATURE_DISTANCE_WEIGHTS
    return float(np.sqrt(np.mean(weighted * weighted)))


def _overlaps_existing(mask, existing, threshold=0.5):
    return any(_mask_iou(mask, other) >= float(threshold) for other in existing)


def adapt_candidate_bank(movie, projection, reference_masks, reference_metadata, bank, quality_preset="balanced"):
    data = np.asarray(movie, dtype=np.float32)
    image = np.asarray(projection, dtype=np.float32)
    if data.ndim != 3 or data.shape[1:] != image.shape:
        raise ValueError("Adaptive ROI fitting requires a movie and matching 2D projection")
    if bank.masks.shape[1:] != image.shape:
        raise ValueError("Candidate bank spatial shape does not match the projection")
    if len(reference_masks) != len(reference_metadata):
        raise ValueError("Reference mask and metadata counts do not match")
    preset = QUALITY_PRESETS.get(str(quality_preset), QUALITY_PRESETS["balanced"])

    protected_masks = []
    protected_metadata = []
    for index, (mask, metadata) in enumerate(zip(reference_masks, reference_metadata)):
        item = normalized_roi_metadata(metadata, str(metadata.get("source", "loaded")), f"ROI{index + 1}")
        item["protected"] = True
        refined = refine_protected_mask(data, image, mask)
        reasons = list(item.get("quality_reasons", []))
        reasons.extend(reason for reason in refined.reasons if reason not in reasons)
        item["low_quality"] = bool(item.get("low_quality", False) or refined.low_quality)
        item["quality_reasons"] = reasons
        protected_masks.append(np.asarray(refined.mask, dtype=bool).copy())
        protected_metadata.append(item)

    reference_features = build_feature_table(data, image, protected_masks).values
    centers, scales = _fit_reference_distribution(reference_features, protected_metadata)
    candidate_features = build_feature_table(data, image, bank.masks).values

    output_masks = list(protected_masks)
    output_metadata = list(protected_metadata)
    ranked = []
    for index, mask in enumerate(np.asarray(bank.masks, dtype=bool)):
        if _overlaps_existing(mask, protected_masks, threshold=0.35):
            continue
        if not _candidate_quality_passes(bank, index, preset):
            continue
        distance = 0.0 if not protected_masks else _candidate_distance(candidate_features[index], centers, scales)
        if protected_masks and distance > preset.similarity_limit:
            continue
        ranked.append((distance, index))

    for distance, index in sorted(ranked, key=lambda value: (value[0], value[1])):
        mask = np.asarray(bank.masks[index], dtype=bool)
        if _overlaps_existing(mask, output_masks, threshold=0.5):
            continue
        metadata = normalized_roi_metadata(
            {"base_name": bank.names[index], "source": bank.engine},
            bank.engine,
            f"ROI{len(output_masks) + 1}",
        )
        metadata["adaptive_distance"] = float(distance)
        output_masks.append(mask.copy())
        output_metadata.append(metadata)

    selected_count = len(output_masks) - len(protected_masks)
    low_quality_count = sum(bool(item.get("low_quality")) for item in protected_metadata)
    fitted_parameters = {
        "quality_preset": str(quality_preset),
        "feature_columns": list(FEATURE_COLUMNS),
        "feature_centers": centers.astype(float).tolist(),
        "feature_scales": scales.astype(float).tolist(),
        "similarity_limit": float(preset.similarity_limit),
        "fast_confidence": float(preset.fast_confidence),
        "caiman_min_snr": float(preset.caiman_min_snr),
        "caiman_rval": float(preset.caiman_rval),
        "caiman_cnn": float(preset.caiman_cnn),
    }
    return AdaptiveROIResult(
        masks=tuple(np.asarray(mask, dtype=bool).copy() for mask in output_masks),
        metadata=tuple(dict(item) for item in output_metadata),
        fitted_parameters=fitted_parameters,
        protected_count=len(protected_masks),
        selected_count=selected_count,
        low_quality_count=low_quality_count,
    )


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
