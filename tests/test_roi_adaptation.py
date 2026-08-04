import numpy as np

import analysis_core as core
from roi_adaptation import (
    CandidateBank,
    QualityPreset,
    QUALITY_PRESETS,
    adaptive_result_is_current,
    adapt_candidate_bank,
    build_feature_table,
    display_roi_name,
    deserialize_roi_metadata,
    normalize_roi_collection,
    normalized_roi_metadata,
    refine_protected_mask,
    serialize_roi_metadata,
    candidate_source_signature,
    caiman_multiscale_diameters,
    merge_caiman_multiscale_candidates,
    suggest_cell_diameter,
    suggest_cell_diameter_range,
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


def test_caiman_cell_diameter_uses_median_equivalent_diameter():
    diameter = suggest_cell_diameter([square(4), square(10), square(6)], current_value=12.0)
    expected = float(np.median([2 * np.sqrt(area / np.pi) for area in (16, 100, 36)]))
    assert np.isclose(diameter, expected)


def test_caiman_cell_diameter_keeps_current_value_without_valid_rois():
    assert suggest_cell_diameter([], current_value=15.0) == 15.0


def test_caiman_cell_diameter_range_preserves_small_and_large_hand_drawn_examples():
    minimum, maximum = suggest_cell_diameter_range(
        [square(4), square(10)],
        current_min=8.0,
        current_max=18.0,
    )
    assert minimum < 2.0 * np.sqrt(16 / np.pi)
    assert maximum > 2.0 * np.sqrt(100 / np.pi)
    assert minimum < maximum


def test_caiman_cell_diameter_range_with_one_example_only_updates_maximum():
    assert suggest_cell_diameter_range([square(10)], 4.0, 18.0) == (4.0, 12.0)


def test_caiman_multiscale_diameters_use_minimum_middle_maximum_and_skip_equal_gsig():
    assert caiman_multiscale_diameters(8.0, 18.0) == (8.0, 12.0, 18.0)
    assert caiman_multiscale_diameters(8.0, 9.0) == (8.0,)


def _caiman_candidate(mask, *, name, trace, snr, rval, cnn, accepted=True):
    return {
        "masks": np.asarray([mask], dtype=bool),
        "names": [name],
        "arrays": {
            "traces": np.asarray([trace], dtype=np.float32),
            "snr": np.asarray([snr], dtype=np.float32),
            "r_values": np.asarray([rval], dtype=np.float32),
            "cnn_scores": np.asarray([cnn], dtype=np.float32),
            "component_indices": np.asarray([0], dtype=np.int32),
            "preset_accepted": np.asarray([accepted], dtype=bool),
        },
    }


def test_caiman_multiscale_merge_keeps_higher_quality_duplicate_and_provenance():
    mask = square(5)
    lower_quality = _caiman_candidate(
        mask, name="small", trace=[0, 1, 2, 1], snr=2.0, rval=0.8, cnn=0.9
    )
    higher_quality = _caiman_candidate(
        mask, name="large", trace=[0, 1, 2, 1], snr=3.0, rval=0.9, cnn=0.95
    )
    merged = merge_caiman_multiscale_candidates(
        [(8.0, 2, lower_quality), (18.0, 4, higher_quality)]
    )
    assert merged.masks.shape == (1, 40, 40)
    assert merged.names == ("large",)
    assert merged.arrays["scale_diameter"].tolist() == [18.0]
    assert merged.arrays["scale_gsig"].tolist() == [4]
    assert merged.metadata["multiscale_duplicate_count"] == 1
    assert float(merged.arrays["snr"][0]) == 3.0


def test_caiman_multiscale_merge_does_not_merge_adjacent_cells_only_for_trace_similarity():
    first = square(5, top=2, left=2)
    second = square(5, top=2, left=8)
    trace = [0, 1, 2, 1]
    merged = merge_caiman_multiscale_candidates(
        [
            (8.0, 2, _caiman_candidate(first, name="first", trace=trace, snr=2.0, rval=0.8, cnn=0.9)),
            (18.0, 4, _caiman_candidate(second, name="second", trace=trace, snr=2.0, rval=0.8, cnn=0.9)),
        ]
    )
    assert merged.masks.shape[0] == 2
    assert merged.metadata["multiscale_duplicate_count"] == 0


def test_caiman_multiscale_quality_gate_rejects_unique_cnn_only_candidate():
    candidate = _caiman_candidate(
        square(5), name="cnn-only", trace=[0, 1, 2, 1], snr=0.8, rval=0.1, cnn=0.99
    )
    merged = merge_caiman_multiscale_candidates(
        [(8.0, 2, candidate)],
        min_snr=2.0,
        rval_threshold=0.8,
        require_non_cnn_evidence=True,
    )
    assert merged.masks.shape == (0, 40, 40)
    assert merged.metadata["multiscale_quality_rejected_count"] == 1


def test_caiman_multiscale_quality_gate_keeps_cross_scale_supported_candidate():
    mask = square(5)
    merged = merge_caiman_multiscale_candidates(
        [
            (8.0, 2, _caiman_candidate(mask, name="small", trace=[0, 1, 2, 1], snr=0.8, rval=0.1, cnn=0.99)),
            (12.0, 3, _caiman_candidate(mask, name="middle", trace=[0, 1, 2, 1], snr=0.9, rval=0.2, cnn=0.98)),
        ],
        min_snr=2.0,
        rval_threshold=0.8,
        require_non_cnn_evidence=True,
    )
    assert merged.masks.shape[0] == 1
    assert merged.metadata["multiscale_quality_rejected_count"] == 0


def test_caiman_multiscale_quality_gate_keeps_unique_temporally_strong_candidate():
    candidate = _caiman_candidate(
        square(5), name="temporal", trace=[0, 1, 2, 1], snr=2.5, rval=0.1, cnn=0.2
    )
    merged = merge_caiman_multiscale_candidates(
        [(12.0, 3, candidate)],
        min_snr=2.0,
        rval_threshold=0.8,
        require_non_cnn_evidence=True,
    )
    assert merged.names == ("temporal",)


def test_same_source_signature_reuses_candidate_bank():
    first = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    second = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    assert first == second


def test_projection_or_movie_generation_change_invalidates_fast_bank():
    base = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    changed_movie = candidate_source_signature(
        "fast", 8, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    changed_projection = candidate_source_signature(
        "fast", 7, (128, 128), 5, "max", (10, 50), "weights-v1", {"image_size": 960}
    )
    assert base != changed_movie
    assert base != changed_projection


def test_signature_normalizes_parameter_order_and_nested_values():
    first = candidate_source_signature(
        "caiman", 3, (20, 30), 0, "movie", (0, 0), "caiman", {"mode": "two_photon", "gSig": [3, 3]}
    )
    second = candidate_source_signature(
        "caiman", 3, (20, 30), 0, "movie", (0, 0), "caiman", {"gSig": [3, 3], "mode": "two_photon"}
    )
    assert first == second


def test_reference_revision_does_not_change_bank_signature_but_blocks_stale_apply():
    before = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    after = candidate_source_signature(
        "fast", 7, (128, 128), 5, "mean", (10, 50), "weights-v1", {"image_size": 960}
    )
    assert before == after
    assert adaptive_result_is_current(7, 12, current_generation=7, current_roi_revision=12)
    assert not adaptive_result_is_current(7, 12, current_generation=7, current_roi_revision=13)


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


def test_adaptation_retains_low_quality_reference_with_star_metadata():
    movie = np.zeros((20, 20, 20), dtype=np.float32)
    reference = square(4, shape=(20, 20))
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        CandidateBank.empty("fast", (20, 20)),
        "balanced",
    )
    assert len(result.masks) == 1
    assert result.metadata[0]["protected"]
    assert result.metadata[0]["low_quality"]
    assert display_roi_name(result.metadata[0]) == "ROI1*"


def test_adaptation_adds_similar_candidate_and_rejects_distant_shape():
    movie = np.zeros((20, 20, 20), dtype=np.float32)
    reference = np.zeros((20, 20), dtype=bool)
    reference[2:6, 2:6] = True
    similar = np.zeros((20, 20), dtype=bool)
    similar[10:14, 10:14] = True
    too_large = np.zeros((20, 20), dtype=bool)
    too_large[8:18, 8:18] = True
    signal = np.sin(np.linspace(0, 6, 20)).astype(np.float32)
    movie[:, reference | similar] = signal[:, None] + 2.0
    bank = CandidateBank(
        "fast",
        np.stack([similar, too_large]),
        ("candidate-1", "candidate-2"),
        {"scores": np.array([0.9, 0.95], dtype=np.float32)},
        ("fast", 1),
        {"confidence": 0.05},
    )
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "balanced",
    )
    assert result.protected_count == 1
    assert result.selected_count == 1
    assert len(result.masks) == 2
    assert np.count_nonzero(result.masks[1]) == 16


def test_matching_candidate_is_not_duplicated_after_reference_refinement():
    movie = np.ones((20, 20, 20), dtype=np.float32)
    reference = np.zeros((20, 20), dtype=bool)
    reference[4:9, 4:9] = True
    bank = CandidateBank(
        "fast",
        reference[None, ...],
        ("candidate-1",),
        {"scores": np.array([0.95], dtype=np.float32)},
        ("fast", 1),
        {"confidence": 0.05},
    )
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "balanced",
    )
    assert result.protected_count == 1
    assert result.selected_count == 0
    assert len(result.masks) == 1


def test_shifted_same_cell_candidate_is_matched_by_centroid_and_not_duplicated():
    movie = np.zeros((30, 24, 24), dtype=np.float32)
    reference = square(5, shape=(24, 24), top=7, left=7)
    shifted = square(5, shape=(24, 24), top=9, left=9)
    signal = np.sin(np.linspace(0, 4 * np.pi, movie.shape[0])).astype(np.float32)
    movie[:, reference | shifted] = signal[:, None] + 2.0
    bank = CandidateBank(
        "fast",
        shifted[None, ...],
        ("same-cell",),
        {"scores": np.array([0.95], dtype=np.float32)},
        ("fast", 1),
        {},
    )

    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "balanced",
    )

    assert result.protected_count == 1
    assert result.selected_count == 0
    assert len(result.masks) == 1


def test_successful_refit_recomputes_instead_of_preserving_stale_low_quality_flag():
    movie, _target, coarse = synthetic_activity_movie()
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [coarse],
        [{"source": "manual", "base_name": "ROI1", "low_quality": True, "quality_reasons": ["旧警告"]}],
        CandidateBank.empty("fast", coarse.shape),
        "recall",
    )

    assert not result.metadata[0]["low_quality"]
    assert result.metadata[0]["quality_reasons"] == []
    assert display_roi_name(result.metadata[0]) == "ROI1"


def test_matched_protected_roi_is_marked_when_candidate_fails_active_preset():
    movie = np.zeros((30, 24, 24), dtype=np.float32)
    reference = square(5, shape=(24, 24), top=7, left=7)
    signal = np.sin(np.linspace(0, 4 * np.pi, movie.shape[0])).astype(np.float32)
    movie[:, reference] = signal[:, None] + 2.0
    bank = CandidateBank(
        "fast",
        reference[None, ...],
        ("matched",),
        {"scores": np.array([0.15], dtype=np.float32)},
        ("fast", 1),
        {},
    )

    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "precision",
    )

    assert result.metadata[0]["low_quality"]
    assert "未达到当前模型质量预设" in result.metadata[0]["quality_reasons"]


def test_unmatched_model_generated_roi_is_retained_and_marked_not_reproduced():
    movie, _target, coarse = synthetic_activity_movie()
    for engine in ("fast", "caiman"):
        result = adapt_candidate_bank(
            movie,
            movie.mean(axis=0),
            [coarse],
            [{"source": engine, "base_name": f"{engine}-roi"}],
            CandidateBank.empty(engine, coarse.shape),
            "recall",
        )

        assert len(result.masks) == 1
        assert result.metadata[0]["low_quality"]
        assert "当前模型候选中未复现" in result.metadata[0]["quality_reasons"]
        assert display_roi_name(result.metadata[0]).endswith("*")


def test_nonempty_candidate_bank_requires_selection_quality_arrays():
    candidate = square(4, shape=(16, 16))[None, ...]
    with np.testing.assert_raises_regex(ValueError, "scores"):
        CandidateBank("fast", candidate, ("candidate",), {}, (), {})
    with np.testing.assert_raises_regex(ValueError, "snr"):
        CandidateBank("caiman", candidate, ("candidate",), {}, (), {})


def test_single_reference_uses_preset_scales_instead_of_zero_mad():
    movie = np.ones((20, 20, 20), dtype=np.float32)
    reference = np.zeros((20, 20), dtype=bool)
    reference[4:9, 4:9] = True
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        CandidateBank.empty("fast", (20, 20)),
        "balanced",
    )
    scales = np.asarray(result.fitted_parameters["feature_scales"], dtype=np.float32)
    assert np.isfinite(scales).all()
    assert np.all(scales > 0)


def test_caiman_candidate_requires_snr_and_either_spatial_or_cnn_quality():
    movie = np.zeros((30, 32, 32), dtype=np.float32)
    reference = np.zeros((32, 32), dtype=bool)
    reference[2:10, 2:10] = True
    candidate_good = np.zeros((32, 32), dtype=bool)
    candidate_good[2:10, 20:28] = True
    candidate_bad = np.zeros((32, 32), dtype=bool)
    candidate_bad[20:28, 2:10] = True
    signal = np.sin(np.linspace(0, 4 * np.pi, movie.shape[0])).astype(np.float32)
    movie[:, reference | candidate_good | candidate_bad] = signal[:, None] + 2.0
    bank = CandidateBank(
        "caiman",
        np.stack([candidate_good, candidate_bad]),
        ("good", "bad"),
        {
            "snr": np.array([3.0, 3.0], dtype=np.float32),
            "r_values": np.array([0.85, 0.2], dtype=np.float32),
            "cnn_scores": np.array([0.4, 0.4], dtype=np.float32),
        },
        ("caiman", 1),
        {},
    )
    result = adapt_candidate_bank(
        movie,
        movie.mean(axis=0),
        [reference],
        [{"source": "manual", "base_name": "ROI1"}],
        bank,
        "balanced",
    )
    assert result.selected_count == 1
    assert result.metadata[-1]["base_name"] == "good"


def test_custom_quality_preset_uses_current_thresholds():
    movie = np.ones((10, 12, 12), dtype=np.float32)
    candidate = np.zeros((12, 12), dtype=bool)
    candidate[3:7, 4:8] = True
    bank = CandidateBank(
        "fast",
        candidate[None, ...],
        ("candidate",),
        {"scores": np.array([0.15], dtype=np.float32)},
        ("fast", 1),
        {},
    )
    custom = QualityPreset(0.10, 2.0, 0.8, 0.9, 2.3)

    result = adapt_candidate_bank(movie, movie.mean(axis=0), [], [], bank, custom)

    assert result.selected_count == 1
    assert result.fitted_parameters["quality_preset"] == "custom"
    assert result.fitted_parameters["fast_confidence"] == 0.10


def test_analysis_state_starts_with_aligned_empty_roi_metadata_and_revision():
    state = core.AnalysisState()
    assert state.roi_masks == []
    assert state.roi_names == []
    assert state.roi_metadata == []
    assert state.roi_revision == 0


def test_normalize_roi_collection_keeps_masks_metadata_and_display_names_aligned():
    masks, names, metadata = normalize_roi_collection(
        [square(3), square(4)],
        names=["first", "second"],
        metadata=[
            {"source": "manual", "base_name": "first", "low_quality": True},
            {"source": "fast", "base_name": "second"},
        ],
        source="loaded",
    )
    assert len(masks) == len(names) == len(metadata) == 2
    assert names == ("first*", "second")
    assert masks[0].dtype == np.bool_
    assert not np.shares_memory(masks[0], masks[1])


def test_roi_metadata_json_round_trip_preserves_quality_and_rejects_extra_star():
    source = [
        normalized_roi_metadata(
            {"source": "manual", "base_name": "ROI1*", "low_quality": True, "quality_reasons": ["弱信号"]},
            "manual",
            "ROI1",
        )
    ]
    restored = deserialize_roi_metadata(
        serialize_roi_metadata(source),
        count=1,
        names=["ROI1*"],
        source="loaded",
    )
    assert restored[0]["base_name"] == "ROI1"
    assert restored[0]["low_quality"]
    assert restored[0]["quality_reasons"] == ["弱信号"]
    assert display_roi_name(restored[0]) == "ROI1*"


def test_missing_roi_metadata_uses_loaded_compatibility_defaults():
    restored = deserialize_roi_metadata(None, count=2, names=["old1", "old2"], source="loaded")
    assert [item["source"] for item in restored] == ["loaded", "loaded"]
    assert [display_roi_name(item) for item in restored] == ["old1", "old2"]
