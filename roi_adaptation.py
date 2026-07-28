from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
