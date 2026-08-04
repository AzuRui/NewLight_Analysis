from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import threading

import cv2
import numpy as np

import analysis_core as core
from NewLight_Analysis import NewLightApp, parse_neuroalign_cfg_values


def test_neuroalign_cfg_parser_preserves_float_list_and_parses_numeric_types():
    parsed = parse_neuroalign_cfg_values(
        {
            "tps_smooth_candidates": "12, 8, 5, 3, 1",
            "outer_resample_n": "160",
            "resolution": "0.42",
        }
    )

    assert parsed["tps_smooth_candidates"] == "12,8,5,3,1"
    assert parsed["outer_resample_n"] == 160
    assert parsed["resolution"] == 0.42


def test_neuroalign_panel_uses_current_stream_without_video_path_field(tmp_path):
    app = NewLightApp.__new__(NewLightApp)
    app._neuroalign_panel_state = {
        "stage": "outer",
        "result": None,
        "values": {
            "atlas_json": str(tmp_path / "atlas.json"),
            "outdir": str(tmp_path / "run"),
            "cfg": {},
        },
    }
    app.show_parameter_panel = mock.Mock()
    app._close_neuroalign_panel = mock.Mock()
    app._rebuild_neuroalign_from_panel = mock.Mock()
    app._neuroalign_next_stage = mock.Mock()
    app._neuroalign_previous_stage = mock.Mock()
    app._accept_neuroalign_result = mock.Mock()

    app._show_neuroalign_panel()

    fields = app.show_parameter_panel.call_args.args[1]
    assert not any(isinstance(field, dict) and field.get("key") == "video" for field in fields)
    notes = [field.get("text", "") for field in fields if isinstance(field, dict) and field.get("type") == "note"]
    assert any("当前视频流" in note for note in notes)


def test_collect_neuroalign_values_does_not_persist_external_video(tmp_path, monkeypatch):
    atlas_path = tmp_path / "atlas.json"
    atlas_path.write_text("{}", encoding="utf-8")
    app = NewLightApp.__new__(NewLightApp)
    app._capture_neuroalign_panel_values = mock.Mock()
    app._neuroalign_panel_state = {
        "values": {
            "atlas_json": str(atlas_path),
            "outdir": str(tmp_path / "run"),
            "cfg": {"tps_smooth_candidates": "12,8,5,3,1"},
        }
    }
    app.user_settings = {"neuroalign": {"video": "C:/stale/original.avi"}}
    monkeypatch.setattr("NewLight_Analysis.save_user_settings", mock.Mock())

    values = app._collect_neuroalign_panel_values()

    assert "video" not in values
    assert "video" not in app.user_settings["neuroalign"]
    assert values["cfg"]["tps_smooth_candidates"] == "12,8,5,3,1"


def test_neuroalign_snapshot_descriptor_uses_current_movie_and_session_temp(tmp_path):
    current_movie = np.arange(3 * 8 * 10, dtype=np.uint16).reshape(3, 8, 10)
    app = NewLightApp.__new__(NewLightApp)
    app.state = SimpleNamespace(movie=current_movie, fs=17.5, source_path="C:/original/import.avi")
    app.movie_generation = 4
    app.session_temp_dir = tmp_path
    app._neuroalign_panel_state = {}

    snapshot = app._neuroalign_current_movie_snapshot()

    assert snapshot["movie"] is current_movie
    assert snapshot["source_id"] == id(current_movie)
    assert snapshot["source_generation"] == 4
    assert snapshot["fps"] == 17.5
    assert Path(snapshot["path"]).parent == tmp_path / "neuroalign_inputs"
    assert Path(snapshot["path"]).suffix.lower() == ".avi"


def test_neuroalign_stage_worker_passes_current_stream_snapshot_to_backend(tmp_path, monkeypatch):
    current_movie = np.arange(3 * 8 * 10, dtype=np.uint16).reshape(3, 8, 10)
    app = NewLightApp.__new__(NewLightApp)
    app.state = SimpleNamespace(movie=current_movie, fs=17.5, source_path="C:/original/import.avi")
    app.movie_generation = 4
    app.session_temp_dir = tmp_path
    app._neuroalign_panel_state = {
        "stage": "outer",
        "result": None,
        "input_snapshot": None,
    }
    app._collect_neuroalign_panel_values = mock.Mock(
        return_value={
            "atlas_json": str(tmp_path / "atlas.json"),
            "outdir": str(tmp_path / "run"),
            "cfg": {},
        }
    )
    app.set_parameter_feedback = mock.Mock()
    app.enqueue_task = mock.Mock()
    app.log = mock.Mock()
    app._display_neuroalign_preview = mock.Mock()
    app.worker_error_summary = mock.Mock(side_effect=str)
    app.run_neuroalign_backend = mock.Mock(return_value={"outdir": str(tmp_path / "run"), "log": ""})

    def fake_save(movie, path, fs):
        assert movie is current_movie
        assert fs == 17.5
        Path(path).write_bytes(b"current stream")

    monkeypatch.setattr("NewLight_Analysis.core.save_neuroalign_input_avi", mock.Mock(side_effect=fake_save))

    app._rebuild_neuroalign_from_panel()
    worker = app.enqueue_task.call_args.args[1]
    payload = worker(threading.Event())

    backend_values = app.run_neuroalign_backend.call_args.args[0]
    assert Path(backend_values["video"]).parent == tmp_path / "neuroalign_inputs"
    assert backend_values["video"] != app.state.source_path
    assert payload["source_id"] == id(current_movie)
    assert payload["source_generation"] == 4


def test_neuroalign_rejects_mixing_movie_generations_between_stages(tmp_path):
    app = NewLightApp.__new__(NewLightApp)
    app.state = SimpleNamespace(movie=np.zeros((3, 8, 10)), fs=10.0)
    app.movie_generation = 1
    app.session_temp_dir = tmp_path
    app._neuroalign_panel_state = {"input_snapshot": None}
    app._neuroalign_current_movie_snapshot()

    app.state.movie = np.ones((3, 8, 10))
    app.movie_generation = 2

    try:
        app._neuroalign_current_movie_snapshot()
    except ValueError as exc:
        assert "三个阶段混用不同视频" in str(exc)
    else:
        raise AssertionError("movie generation change should invalidate the staged NeuroAlign run")


def test_neuroalign_snapshot_avi_preserves_shape_frames_and_scaled_content(tmp_path):
    yy, xx = np.mgrid[:18, :22]
    movie = np.stack(
        [
            (xx * 17 + yy * 5 + frame * 31).astype(np.uint16)
            for frame in range(4)
        ]
    )
    output = tmp_path / "current_stream.avi"

    core.save_neuroalign_input_avi(movie, str(output), fs=13.0)

    cap = cv2.VideoCapture(str(output))
    decoded = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        decoded.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    cap.release()
    decoded = np.asarray(decoded)
    expected = core.render_grayscale_display(movie, core.movie_display_limits(movie))

    assert decoded.shape == expected.shape == movie.shape
    assert np.mean(np.abs(decoded.astype(np.int16) - expected.astype(np.int16))) < 3.0
