import json

import numpy as np
import pytest

from roi_engines import (
    ROI_ARTIFACT_VERSION,
    ROIArtifactError,
    load_roi_artifact,
    normalize_instance_masks,
    save_roi_artifact,
)


def test_normalize_preserves_independent_irregular_and_overlapping_instances():
    masks = np.zeros((2, 7, 9), dtype=np.uint8)
    masks[0, 1:5, 2] = 1
    masks[0, 4, 2:6] = 1
    masks[1, 3:6, 4:8] = 1

    result = normalize_instance_masks(masks, image_shape=(7, 9), names=["cell-a", "cell-b"])

    assert result.masks.dtype == np.bool_
    assert result.masks.shape == (2, 7, 9)
    assert result.names == ["cell-a", "cell-b"]
    assert result.source_indices == [0, 1]
    assert result.masks[0, 4, 4]
    assert result.masks[1, 4, 4]
    np.testing.assert_array_equal(result.masks[0], masks[0].astype(bool))


def test_normalize_accepts_single_2d_float_mask_and_assigns_default_name():
    mask = np.array([[0.1, 0.7], [0.5, 0.49]], dtype=np.float32)

    result = normalize_instance_masks(mask, image_shape=(2, 2), threshold=0.5)

    assert result.masks.shape == (1, 2, 2)
    assert result.names == ["ROI1"]
    np.testing.assert_array_equal(
        result.masks[0],
        np.array([[False, True], [True, False]]),
    )


def test_normalize_drops_empty_instances_and_keeps_matching_names():
    masks = np.zeros((3, 4, 5), dtype=bool)
    masks[0, 1, 1] = True
    masks[2, 2, 3] = True

    result = normalize_instance_masks(masks, image_shape=(4, 5), names=["first", "empty", "third"])

    assert result.masks.shape == (2, 4, 5)
    assert result.names == ["first", "third"]
    assert result.source_indices == [0, 2]


def test_normalize_allows_zero_instances_without_inventing_an_roi():
    result = normalize_instance_masks(np.zeros((0, 3, 4), dtype=bool), image_shape=(3, 4))

    assert result.masks.shape == (0, 3, 4)
    assert result.names == []
    assert result.source_indices == []


@pytest.mark.parametrize(
    "masks,image_shape,message",
    [
        (np.zeros((2, 3, 4, 1)), (3, 4), "2D or 3D"),
        (np.zeros((2, 3, 4)), (4, 3), "spatial shape"),
        (np.zeros((2, 3, 4)), (3,), "image_shape"),
    ],
)
def test_normalize_rejects_invalid_dimensions(masks, image_shape, message):
    with pytest.raises(ROIArtifactError, match=message):
        normalize_instance_masks(masks, image_shape=image_shape)


def test_normalize_rejects_name_count_mismatch():
    with pytest.raises(ROIArtifactError, match="name count"):
        normalize_instance_masks(
            np.ones((2, 3, 4), dtype=bool),
            image_shape=(3, 4),
            names=["only-one"],
        )


def test_artifact_round_trip_preserves_masks_names_and_json_metadata(tmp_path):
    masks = np.zeros((2, 5, 6), dtype=bool)
    masks[0, 1:4, 2] = True
    masks[1, 2:5, 3:5] = True
    path = tmp_path / "roi_result.npz"
    metadata = {
        "engine": "fast",
        "scores": [0.91, 0.83],
        "parameters": {"conf": 0.25},
    }

    saved = save_roi_artifact(path, masks, image_shape=(5, 6), names=["a", "b"], metadata=metadata)
    loaded = load_roi_artifact(path, expected_shape=(5, 6))

    assert saved == path
    assert loaded.version == ROI_ARTIFACT_VERSION
    assert loaded.names == ["a", "b"]
    assert loaded.metadata == metadata
    np.testing.assert_array_equal(loaded.masks, masks)


def test_artifact_round_trip_preserves_numeric_backend_arrays(tmp_path):
    path = tmp_path / "caiman_result.npz"
    traces = np.arange(12, dtype=np.float32).reshape(2, 6)
    snr = np.array([2.5, 3.1], dtype=np.float32)

    save_roi_artifact(
        path,
        np.ones((2, 3, 4), dtype=bool),
        image_shape=(3, 4),
        extra_arrays={"traces": traces, "snr": snr},
    )
    loaded = load_roi_artifact(path)

    np.testing.assert_array_equal(loaded.arrays["traces"], traces)
    np.testing.assert_array_equal(loaded.arrays["snr"], snr)


def test_artifact_rejects_extra_array_that_overwrites_a_core_field(tmp_path):
    with pytest.raises(ROIArtifactError, match="reserved"):
        save_roi_artifact(
            tmp_path / "bad.npz",
            np.ones((1, 2, 2), dtype=bool),
            image_shape=(2, 2),
            extra_arrays={"masks": np.zeros((1, 2, 2), dtype=bool)},
        )


def test_load_rejects_wrong_expected_shape_without_returning_partial_data(tmp_path):
    path = tmp_path / "roi_result.npz"
    save_roi_artifact(path, np.ones((1, 3, 4), dtype=bool), image_shape=(3, 4))

    with pytest.raises(ROIArtifactError, match="spatial shape"):
        load_roi_artifact(path, expected_shape=(4, 3))


def test_load_rejects_unsupported_version_and_invalid_metadata(tmp_path):
    path = tmp_path / "bad.npz"
    np.savez_compressed(
        path,
        version=np.array(ROI_ARTIFACT_VERSION + 1),
        masks=np.ones((1, 2, 2), dtype=bool),
        names=np.array(["ROI1"]),
        image_shape=np.array([2, 2]),
        metadata_json=np.array(json.dumps({"engine": "test"})),
    )
    with pytest.raises(ROIArtifactError, match="version"):
        load_roi_artifact(path)

    np.savez_compressed(
        path,
        version=np.array(ROI_ARTIFACT_VERSION),
        masks=np.ones((1, 2, 2), dtype=bool),
        names=np.array(["ROI1"]),
        image_shape=np.array([2, 2]),
        metadata_json=np.array("not-json"),
    )
    with pytest.raises(ROIArtifactError, match="metadata"):
        load_roi_artifact(path)
