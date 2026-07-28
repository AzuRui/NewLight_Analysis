import numpy as np

from roi_adaptation import (
    QUALITY_PRESETS,
    display_roi_name,
    normalized_roi_metadata,
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
