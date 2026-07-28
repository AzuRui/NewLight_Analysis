from __future__ import annotations

import json
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
        required = {
            "fast": ("scores",),
            "caiman": ("snr", "r_values", "cnn_scores"),
        }.get(str(self.engine), ())
        if masks.shape[0]:
            missing = [name for name in required if name not in self.model_quality]
            if missing:
                raise ValueError(f"Candidate bank is missing required quality array '{missing[0]}'")

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


def refine_protected_mask(movie, projection, mask, proposal=None):
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
    if proposal is not None:
        proposal_mask = np.asarray(proposal, dtype=bool)
        if proposal_mask.shape == original.shape:
            proposal_mask = _component_with_greatest_overlap(proposal_mask & search, original)
            if proposal_mask is not None:
                support = support + 0.12 * proposal_mask.astype(np.float32)
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


def _normalized_centroid_distance(first, second):
    first_mask = np.asarray(first, dtype=bool)
    second_mask = np.asarray(second, dtype=bool)
    first_points = np.argwhere(first_mask)
    second_points = np.argwhere(second_mask)
    if first_points.size == 0 or second_points.size == 0:
        return np.inf
    distance = float(np.linalg.norm(np.mean(first_points, axis=0) - np.mean(second_points, axis=0)))
    first_diameter = 2.0 * np.sqrt(first_points.shape[0] / np.pi)
    second_diameter = 2.0 * np.sqrt(second_points.shape[0] / np.pi)
    return distance / max(1.0, 0.5 * (first_diameter + second_diameter))


def _protected_candidate_match(first, second):
    iou = _mask_iou(first, second)
    centroid_distance = _normalized_centroid_distance(first, second)
    first_area = int(np.count_nonzero(first))
    second_area = int(np.count_nonzero(second))
    area_ratio = second_area / max(1, first_area)
    matched = iou >= 0.35 or (
        0.5 <= area_ratio <= 2.0
        and centroid_distance <= 0.55
        and np.any(morphology.dilation(np.asarray(first, dtype=bool), morphology.disk(2)) & second)
    )
    score = iou + max(0.0, 1.0 - centroid_distance) * 0.25
    return matched, score


def _candidate_quality_passes(bank, index, preset):
    quality = bank.model_quality
    if bank.engine == "fast":
        scores = np.asarray(quality["scores"], dtype=np.float32)
        return float(scores[index]) >= preset.fast_confidence
    if bank.engine == "caiman":
        snr = np.asarray(quality["snr"], dtype=np.float32)
        r_values = np.asarray(quality["r_values"], dtype=np.float32)
        cnn = np.asarray(quality["cnn_scores"], dtype=np.float32)
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
    if isinstance(quality_preset, QualityPreset):
        preset = quality_preset
        preset_name = "custom"
    else:
        preset_name = str(quality_preset)
        preset = QUALITY_PRESETS.get(preset_name, QUALITY_PRESETS["balanced"])

    match_pairs = []
    for reference_index, reference_mask in enumerate(reference_masks):
        for candidate_index, candidate_mask in enumerate(np.asarray(bank.masks, dtype=bool)):
            matched, score = _protected_candidate_match(reference_mask, candidate_mask)
            if matched:
                match_pairs.append((score, reference_index, candidate_index))
    matched_by_reference = {}
    matched_candidate_indices = set()
    for _score, reference_index, candidate_index in sorted(match_pairs, reverse=True):
        if reference_index in matched_by_reference or candidate_index in matched_candidate_indices:
            continue
        matched_by_reference[reference_index] = candidate_index
        matched_candidate_indices.add(candidate_index)

    refinement_threshold = {
        "recall": 0.45,
        "balanced": 0.55,
        "precision": 0.65,
    }.get(preset_name, 0.55)
    protected_masks = []
    protected_metadata = []
    for index, (mask, metadata) in enumerate(zip(reference_masks, reference_metadata)):
        item = normalized_roi_metadata(metadata, str(metadata.get("source", "loaded")), f"ROI{index + 1}")
        item["protected"] = True
        matched_index = matched_by_reference.get(index)
        proposal = None if matched_index is None else bank.masks[matched_index]
        refined = refine_protected_mask(data, image, mask, proposal=proposal)
        reasons = [reason for reason in refined.reasons if reason != "活动轮廓支持较弱"]
        if refined.confidence < refinement_threshold and "活动轮廓支持较弱" not in reasons:
            reasons.append("活动轮廓支持较弱")
        if matched_index is not None and not _candidate_quality_passes(bank, matched_index, preset):
            reasons.append("未达到当前模型质量预设")
        elif matched_index is None and item["source"] in {"fast", "caiman"}:
            reasons.append("当前模型候选中未复现")
        item["low_quality"] = bool(reasons)
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
        if index in matched_candidate_indices:
            continue
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
        "quality_preset": preset_name,
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


def suggest_cell_diameter(masks, current_value):
    diameters = [
        2.0 * np.sqrt(int(np.count_nonzero(mask)) / np.pi)
        for mask in masks
        if np.any(mask)
    ]
    if not diameters:
        return float(current_value)
    return float(np.median(np.asarray(diameters, dtype=np.float32)))


def candidate_source_signature(
    engine,
    movie_generation,
    image_shape,
    invalid_start_frames,
    projection_mode,
    baseline_window,
    model_identity,
    generation_parameters,
):
    parameters = tuple(
        sorted((str(key), repr(value)) for key, value in dict(generation_parameters).items())
    )
    return (
        str(engine),
        int(movie_generation),
        tuple(int(value) for value in image_shape),
        int(invalid_start_frames),
        str(projection_mode),
        tuple(int(value) for value in baseline_window),
        str(model_identity),
        parameters,
    )


def adaptive_result_is_current(
    source_generation,
    source_roi_revision,
    *,
    current_generation,
    current_roi_revision,
):
    return (
        int(source_generation) == int(current_generation)
        and int(source_roi_revision) == int(current_roi_revision)
    )


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


def normalize_roi_collection(masks, names=None, metadata=None, source="loaded"):
    mask_values = tuple(np.asarray(mask, dtype=bool).copy() for mask in masks)
    count = len(mask_values)
    if names is not None and len(names) != count:
        raise ValueError("ROI name count does not match mask count")
    if metadata is not None and len(metadata) != count:
        raise ValueError("ROI metadata count does not match mask count")
    base_names = tuple(str(names[index]) if names is not None else f"ROI{index + 1}" for index in range(count))
    metadata_values = tuple(
        normalized_roi_metadata(
            metadata[index] if metadata is not None else None,
            source,
            base_names[index],
        )
        for index in range(count)
    )
    display_names = tuple(display_roi_name(item) for item in metadata_values)
    return mask_values, display_names, metadata_values


def serialize_roi_metadata(metadata):
    return json.dumps([dict(item) for item in metadata], ensure_ascii=False, separators=(",", ":"))


def deserialize_roi_metadata(value, count, names=None, source="loaded"):
    count = int(count)
    names = list(names) if names is not None else [f"ROI{index + 1}" for index in range(count)]
    if len(names) != count:
        names = [f"ROI{index + 1}" for index in range(count)]
    decoded = None
    if value is not None:
        raw = value
        if isinstance(raw, np.ndarray):
            raw = raw.item() if raw.size == 1 else None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if isinstance(raw, str):
            try:
                candidate = json.loads(raw)
                if isinstance(candidate, list) and len(candidate) == count:
                    decoded = candidate
            except (TypeError, ValueError, json.JSONDecodeError):
                decoded = None
    return [
        normalized_roi_metadata(
            decoded[index] if decoded is not None else None,
            source,
            names[index],
        )
        for index in range(count)
    ]
