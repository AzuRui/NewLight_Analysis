"""Shared, backend-independent ROI artifact validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


ROI_ARTIFACT_VERSION = 1


class ROIArtifactError(ValueError):
    """Raised when a worker ROI artifact is incomplete or inconsistent."""


@dataclass(frozen=True)
class NormalizedROIs:
    masks: np.ndarray
    names: list[str]
    source_indices: list[int]


@dataclass(frozen=True)
class ROIArtifact:
    version: int
    masks: np.ndarray
    names: list[str]
    metadata: dict[str, Any]
    image_shape: tuple[int, int]
    arrays: dict[str, np.ndarray]


def _validated_image_shape(image_shape: Sequence[int]) -> tuple[int, int]:
    try:
        values = tuple(int(value) for value in image_shape)
    except (TypeError, ValueError) as exc:
        raise ROIArtifactError("image_shape must contain two positive integers") from exc
    if len(values) != 2 or values[0] <= 0 or values[1] <= 0:
        raise ROIArtifactError("image_shape must contain two positive integers")
    return values


def normalize_instance_masks(
    masks: np.ndarray | Iterable[np.ndarray],
    image_shape: Sequence[int],
    names: Sequence[str] | None = None,
    threshold: float = 0.5,
) -> NormalizedROIs:
    """Validate masks while preserving each backend instance independently."""

    shape = _validated_image_shape(image_shape)
    try:
        array = np.asarray(masks)
    except (TypeError, ValueError) as exc:
        raise ROIArtifactError("ROI masks must form a regular 2D or 3D array") from exc
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    elif array.ndim != 3:
        raise ROIArtifactError("ROI masks must be a 2D or 3D array")
    if tuple(array.shape[1:]) != shape:
        raise ROIArtifactError(
            f"ROI spatial shape {tuple(array.shape[1:])} does not match image shape {shape}"
        )

    if names is None:
        source_names = [f"ROI{index + 1}" for index in range(array.shape[0])]
    else:
        if len(names) != array.shape[0]:
            raise ROIArtifactError(
                f"ROI name count {len(names)} does not match mask count {array.shape[0]}"
            )
        source_names = [str(name) for name in names]

    if array.dtype == np.bool_:
        boolean_masks = np.array(array, dtype=bool, copy=True)
    else:
        boolean_masks = np.asarray(array >= float(threshold), dtype=bool)

    source_indices = [index for index, mask in enumerate(boolean_masks) if np.any(mask)]
    if source_indices:
        normalized = np.stack([boolean_masks[index] for index in source_indices]).astype(bool, copy=False)
    else:
        normalized = np.zeros((0,) + shape, dtype=bool)
    normalized_names = [source_names[index] for index in source_indices]
    return NormalizedROIs(normalized, normalized_names, source_indices)


def save_roi_artifact(
    path: str | Path,
    masks: np.ndarray | Iterable[np.ndarray],
    image_shape: Sequence[int],
    names: Sequence[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    extra_arrays: Mapping[str, np.ndarray] | None = None,
) -> Path:
    """Atomically save a validated worker result without object arrays."""

    target = Path(path)
    shape = _validated_image_shape(image_shape)
    normalized = normalize_instance_masks(masks, shape, names=names)
    metadata_value = dict(metadata or {})
    try:
        metadata_json = json.dumps(metadata_value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ROIArtifactError(f"ROI metadata is not valid JSON: {exc}") from exc

    reserved = {"version", "masks", "names", "image_shape", "metadata_json"}
    arrays: dict[str, np.ndarray] = {}
    for key, value in dict(extra_arrays or {}).items():
        name = str(key)
        if name in reserved:
            raise ROIArtifactError(f"Extra ROI array name {name!r} is reserved")
        array = np.asarray(value)
        if array.dtype.hasobject:
            raise ROIArtifactError(f"Extra ROI array {name!r} cannot use object dtype")
        arrays[name] = array

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            np.savez_compressed(
                handle,
                version=np.array(ROI_ARTIFACT_VERSION, dtype=np.int64),
                masks=normalized.masks,
                names=np.asarray(normalized.names, dtype=np.str_),
                image_shape=np.asarray(shape, dtype=np.int64),
                metadata_json=np.array(metadata_json, dtype=np.str_),
                **arrays,
            )
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def load_roi_artifact(
    path: str | Path,
    expected_shape: Sequence[int] | None = None,
) -> ROIArtifact:
    """Load a complete artifact and reject incompatible worker output."""

    source = Path(path)
    try:
        with np.load(source, allow_pickle=False) as data:
            required = {"version", "masks", "names", "image_shape", "metadata_json"}
            missing = required.difference(data.files)
            if missing:
                raise ROIArtifactError(f"ROI artifact is missing fields: {', '.join(sorted(missing))}")
            version = int(np.asarray(data["version"]).reshape(()))
            if version != ROI_ARTIFACT_VERSION:
                raise ROIArtifactError(
                    f"Unsupported ROI artifact version {version}; expected {ROI_ARTIFACT_VERSION}"
                )
            shape = _validated_image_shape(np.asarray(data["image_shape"]).tolist())
            names = [str(value) for value in np.asarray(data["names"]).tolist()]
            masks = np.array(data["masks"], copy=True)
            metadata_text = str(np.asarray(data["metadata_json"]).reshape(()))
            arrays = {
                name: np.array(data[name], copy=True)
                for name in data.files
                if name not in required
            }
    except ROIArtifactError:
        raise
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ROIArtifactError(f"Cannot read ROI artifact {source}: {exc}") from exc

    if expected_shape is not None:
        expected = _validated_image_shape(expected_shape)
        if shape != expected:
            raise ROIArtifactError(f"ROI spatial shape {shape} does not match image shape {expected}")
    normalized = normalize_instance_masks(masks, shape, names=names)
    if len(normalized.source_indices) != masks.shape[0]:
        raise ROIArtifactError("ROI artifact contains empty instances")
    try:
        metadata = json.loads(metadata_text)
    except json.JSONDecodeError as exc:
        raise ROIArtifactError(f"ROI metadata is invalid JSON: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ROIArtifactError("ROI metadata must be a JSON object")
    return ROIArtifact(version, normalized.masks, normalized.names, metadata, shape, arrays)
