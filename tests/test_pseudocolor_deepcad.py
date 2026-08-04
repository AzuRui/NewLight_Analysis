import numpy as np
import tifffile
from unittest import mock

import analysis_core as core
from NewLight_Analysis import NewLightApp


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_blend_channel_movies_preserves_channel_identity_and_weight():
    raw_green = np.array([[[0, 10], [20, 30]]], dtype=np.float32)
    raw_red = np.array([[[30, 20], [10, 0]]], dtype=np.float32)
    denoised_green = np.full_like(raw_green, 100)
    denoised_red = np.full_like(raw_red, 200)

    blended = core.blend_channel_movies(
        (raw_green, raw_red),
        (denoised_green, denoised_red),
        0.7,
    )

    np.testing.assert_allclose(blended[0], raw_green * 0.3 + denoised_green * 0.7)
    np.testing.assert_allclose(blended[1], raw_red * 0.3 + denoised_red * 0.7)


def test_pseudocolor_changes_after_per_channel_deepcad_blend():
    raw = np.array([[[0, 10], [20, 30]]], dtype=np.float32)
    denoised = np.array([[[0, 2], [25, 100]]], dtype=np.float32)

    raw_rgb = core.compose_channel_pseudocolor_rgb([raw[0]], ("green",), limits=((0, 100),))
    blended_movie = core.blend_channel_movies((raw,), (denoised,), 0.7)[0]
    blended_rgb = core.compose_channel_pseudocolor_rgb([blended_movie[0]], ("green",), limits=((0, 100),))

    assert not np.array_equal(raw_rgb, blended_rgb)
    assert np.all(blended_rgb[:, :, 0] == 0)
    assert np.all(blended_rgb[:, :, 2] == 0)


def test_channel_blend_weight_endpoints_are_exact():
    raw = (np.arange(8, dtype=np.float32).reshape(2, 2, 2),)
    denoised = (np.full((2, 2, 2), 42, dtype=np.float32),)

    np.testing.assert_array_equal(core.blend_channel_movies(raw, denoised, 0)[0], raw[0])
    np.testing.assert_array_equal(core.blend_channel_movies(raw, denoised, 1)[0], denoised[0])


def test_channel_blend_rejects_mismatched_channel_counts():
    movie = np.zeros((2, 3, 4), dtype=np.float32)

    try:
        core.blend_channel_movies((movie, movie), (movie,), 0.5)
    except ValueError as exc:
        assert "通道数量" in str(exc)
    else:
        raise AssertionError("mismatched channel counts must fail")


def test_gui_pseudocolor_frame_uses_deepcad_channel_before_coloring():
    raw = np.array([[[0, 10], [20, 30]]], dtype=np.float32)
    denoised = np.array([[[0, 2], [25, 100]]], dtype=np.float32)
    app = NewLightApp.__new__(NewLightApp)
    app.state = core.AnalysisState(
        movie=raw,
        converted_channel_movies=(raw,),
        channel_colors=("green",),
    )
    app.deepcad_enabled_var = Value(True)
    app.deepcad_denoised_movie = denoised
    app.deepcad_denoised_channels = (denoised,)
    app.deepcad_cache_movie_id = id(app.state.movie)
    app.deepcad_cache_invalid_start_frames = 0
    app.deepcad_weight = lambda: 0.7
    app._converted_frame_cache = (None, None, None)
    app._converted_projection_cache = {}

    actual = app.converted_color_image(("frame", 0))
    blended = core.blend_images(raw[0], denoised[0], 0.7)
    expected = core.compose_channel_pseudocolor_rgb([blended], ("green",))
    raw_rgb = core.compose_channel_pseudocolor_rgb([raw[0]], ("green",))

    np.testing.assert_array_equal(actual, expected)
    assert not np.array_equal(actual, raw_rgb)


def test_deepcad_source_runner_processes_each_color_channel_independently(tmp_path):
    channel_1 = np.zeros((2, 2, 2), dtype=np.float32)
    channel_2 = np.ones((2, 2, 2), dtype=np.float32) * 10
    app = NewLightApp.__new__(NewLightApp)
    cancel_event = mock.Mock()
    cancel_event.is_set.return_value = False

    with mock.patch(
        "NewLight_Analysis.core.run_deepcadrt_denoise",
        side_effect=[(channel_1 + 1, "green log"), (channel_2 + 2, "red log")],
    ) as run:
        movie, channels, log = app.run_deepcad_sources(
            (channel_1, channel_2),
            np.maximum(channel_1, channel_2),
            tmp_path,
            0,
            cancel_event,
        )

    assert run.call_count == 2
    np.testing.assert_array_equal(channels[0], channel_1 + 1)
    np.testing.assert_array_equal(channels[1], channel_2 + 2)
    np.testing.assert_array_equal(movie, np.maximum(channel_1 + 1, channel_2 + 2))
    assert "Ch1" in log and "Ch2" in log


def test_pseudocolor_tiff_applies_deepcad_overlay_before_coloring(tmp_path):
    raw = np.array([[[0, 10], [20, 30]]], dtype=np.float32)
    denoised = np.array([[[0, 2], [25, 100]]], dtype=np.float32)
    raw_path = tmp_path / "raw.tif"
    deepcad_path = tmp_path / "deepcad.tif"

    core.save_channel_pseudocolor_tiff(
        (raw,),
        ("green",),
        str(raw_path),
        limits=((0, 100),),
        shadows=0,
        highlights=100,
    )
    core.save_channel_pseudocolor_tiff(
        (raw,),
        ("green",),
        str(deepcad_path),
        limits=((0, 100),),
        shadows=0,
        highlights=100,
        overlay_movies=(denoised,),
        overlay_weight=0.7,
    )

    raw_rgb = tifffile.imread(raw_path)
    deepcad_rgb = tifffile.imread(deepcad_path)
    assert not np.array_equal(raw_rgb, deepcad_rgb)
    assert np.all(deepcad_rgb[..., 0] == 0)
    assert np.all(deepcad_rgb[..., 2] == 0)
