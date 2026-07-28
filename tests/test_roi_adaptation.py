import numpy as np

from roi_adaptation import (
    QUALITY_PRESETS,
    build_feature_table,
    display_roi_name,
    normalized_roi_metadata,
    refine_protected_mask,
    suggest_area_range,
)


def square(side, shape=(40, 40), top=2, left=3):
    mask = np.zeros(shape, dtype=bool)
    mask[top : top + side, left : left + side] = True
    return mask


def test_two_examples_fill_smallest_and_largest_with_margins():
    assert suggest_area_range([square(10), square(4)], 20, 4000) == (14, 110)


def test_multiple_examples_use_global_area_extremes_not_list_order():
    assert suggest_area_range([square(7), square(3), square(9)], 20, 4000) == (8, 89)


def test_one_example_only_replaces_maximum():
    assert suggest_area_range([square(10)], 20, 4000) == (20, 110)


def test_no_example_keeps_current_area_range():
    assert suggest_area_range([], 20, 4000) == (20, 4000)


def test_empty_masks_are_ignored_when_estimating_area():
    empty = np.zeros((40, 40), dtype=bool)
    assert suggest_area_range([empty, square(5)], 20, 4000) == (20, 28)


def test_low_quality_name_has_one_trailing_asterisk():
    metadata = normalized_roi_metadata(
        {"base_name": "ROI3*", "low_quality": True},
        "manual",
        "ROI3",
    )
    assert display_roi_name(metadata) == "ROI3*"


def test_normalized_metadata_uses_requested_source_and_safe_defaults():
    metadata = normalized_roi_metadata(None, "fast", "Fast_ROI1")
    assert metadata == {
        "source": "fast",
        "protected": False,
        "low_quality": False,
        "quality_reasons": [],
        "base_name": "Fast_ROI1",
    }


def test_balanced_preset_is_explicit_and_bounded():
    preset = QUALITY_PRESETS["balanced"]
    assert preset.fast_confidence == 0.25
    assert preset.caiman_min_snr == 2.0
    assert preset.caiman_rval == 0.80
    assert preset.caiman_cnn == 0.90
    assert QUALITY_PRESETS["recall"].similarity_limit > preset.similarity_limit
    assert QUALITY_PRESETS["precision"].similarity_limit < preset.similarity_limit


def synthetic_activity_movie():
    movie = np.zeros((30, 32, 32), dtype=np.float32)
    target = np.zeros((32, 32), dtype=bool)
    target[10:20, 10:13] = True
    target[17:20, 10:21] = True
    signal = np.sin(np.linspace(0, 4 * np.pi, movie.shape[0])).astype(np.float32)
    movie[:, target] = 10.0 + signal[:, None] * 4.0
    movie += np.random.default_rng(7).normal(0, 0.15, movie.shape).astype(np.float32)
    coarse = np.zeros((32, 32), dtype=bool)
    coarse[9:21, 9:21] = True
    return movie, target, coarse


def mask_iou(first, second):
    union = np.count_nonzero(first | second)
    return np.count_nonzero(first & second) / union if union else 0.0


def test_refinement_moves_coarse_mask_toward_irregular_activity():
    movie, target, coarse = synthetic_activity_movie()
    refined = refine_protected_mask(movie, movie.mean(axis=0), coarse)
    assert mask_iou(refined.mask, target) > mask_iou(coarse, target)
    assert refined.mask.any()
    assert refined.mask.dtype == np.bool_


def test_refinement_failure_keeps_original_and_marks_low_quality():
    movie = np.zeros((20, 24, 24), dtype=np.float32)
    mask = square(5, shape=(24, 24))
    refined = refine_protected_mask(movie, movie.mean(axis=0), mask)
    np.testing.assert_array_equal(refined.mask, mask)
    assert refined.low_quality
    assert refined.reasons


def test_refinement_does_not_merge_a_neighbor_outside_the_original_identity():
    movie, target, coarse = synthetic_activity_movie()
    neighbor = np.zeros_like(target)
    neighbor[9:21, 23:27] = True
    signal = np.sin(np.linspace(0, 4 * np.pi, movie.shape[0])).astype(np.float32)
    movie[:, neighbor] = 10.0 + signal[:, None] * 4.0
    refined = refine_protected_mask(movie, movie.mean(axis=0), coarse)
    assert not np.any(refined.mask & neighbor)
    assert mask_iou(refined.mask, target) > mask_iou(coarse, target)


def test_convolution_and_shape_features_are_finite():
    movie, _target, coarse = synthetic_activity_movie()
    table = build_feature_table(movie, movie.mean(axis=0), [coarse])
    assert table.values.shape[0] == 1
    assert np.isfinite(table.values).all()
    assert {
        "log_area",
        "solidity",
        "sobel_mean",
        "log_mean",
        "temporal_snr",
    }.issubset(table.columns)
