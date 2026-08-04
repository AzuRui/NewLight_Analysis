from unittest import mock
import time
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import numpy as np

import workflow_core
from NewLight_Analysis import NewLightApp
from task_queue import TaskController, TaskState
from ui_text_zh import PREPROCESS_PANEL_SPECS


ACTION_VALUES = {
    "caiman_motion": {"mode": "piecewise", "max_shift": "12"},
    "builtin_rigid_motion": {"reference_mode": "auto", "flexible_strength": "0.4"},
    "image_shift": {"range": "8", "row_parity": "odd"},
    "gaussian_smooth": {"sigma": "1.2"},
    "median_filter": {"size": "3"},
    "background_subtract": {"sigma": "20"},
    "bleach_correction": {},
    "enhance_contrast": {"clip_limit": "0.02"},
    "remove_vessel_artifact": {"threshold": "90"},
    "load_roi": {"path": "C:/data/rois.npz", "format": "npz"},
}


def make_capture_app():
    app = NewLightApp.__new__(NewLightApp)
    app.require_movie = mock.Mock(return_value=True)
    app.acceleration = mock.Mock(return_value="cpu")
    app.apply_movie_operation = mock.Mock(return_value="generic-task")
    app.run_caiman_motion_from_values = mock.Mock(return_value="caiman-task")
    app.run_image_shift_from_values = mock.Mock(return_value="shift-task")
    app.run_remove_vessels_from_values = mock.Mock(return_value="vessel-task")
    app.run_load_roi_from_values = mock.Mock(return_value="load-roi-task")
    return app


def test_caiman_panel_run_reaches_queue_with_saved_range_defaults(monkeypatch, tmp_path):
    app = NewLightApp.__new__(NewLightApp)
    movie = np.zeros((20, 12, 14), dtype=np.float32)
    app.state = SimpleNamespace(
        movie=movie,
        fs=40.0,
        invalid_start_frames=0,
        roi_masks=[],
    )
    app.user_settings = {
        "caiman_roi": {
            "cell_diameter": 12.0,
            "cell_diameter_min": 8.0,
            "cell_diameter_max": 18.0,
        }
    }
    app.session_temp_dir = tmp_path
    app.parameter_vars = {}
    app.apply_protocol = mock.Mock()
    app.enqueue_task = mock.Mock()
    app.set_parameter_feedback = mock.Mock()
    monkeypatch.setattr("NewLight_Analysis.save_user_settings", mock.Mock())

    app._run_caiman_roi_from_panel(
        {
            "quality_preset": "balanced",
            "mode": "two_photon",
            "size_mode": "range_adaptive",
            "cell_diameter_min": "12",
            "cell_diameter_max": "24",
            "cell_diameter": "12",
            "components_per_patch": "4",
            "background_components": "2",
            "spatial_subsample": "2",
            "temporal_subsample": "2",
            "ar_order": "1",
            "merge_threshold": "0.85",
            "min_snr": "2.0",
            "rval_threshold": "0.8",
            "use_cnn": True,
            "min_cnn_threshold": "0.9",
            "cnn_lowest": "0.1",
            "footprint_threshold": "0.2",
            "similarity_limit": "2.3",
        }
    )

    app.enqueue_task.assert_called_once()


def test_parameter_action_surfaces_unexpected_callback_errors():
    app = NewLightApp.__new__(NewLightApp)
    app.parameter_apply_command = mock.Mock(side_effect=NameError("missing value"))
    app.panel_parameter_values = mock.Mock(return_value={"value": "1"})
    app.set_parameter_feedback = mock.Mock()
    app.log = mock.Mock()

    app.run_parameter_action()

    app.set_parameter_feedback.assert_called_once_with(
        "参数任务提交失败：missing value",
        error=True,
    )
    assert app.log.call_args_list[0] == mock.call("参数任务提交失败：missing value")
    assert "NameError" in app.log.call_args_list[1].args[0]


def test_caiman_adaptive_cache_miss_builds_candidate_bank_before_fitting(monkeypatch, tmp_path):
    app = NewLightApp.__new__(NewLightApp)
    movie = np.zeros((20, 12, 14), dtype=np.float32)
    app.state = SimpleNamespace(
        movie=movie,
        fs=40.0,
        invalid_start_frames=0,
        baseline_start_frame=0,
        baseline_duration_frames=0,
        roi_masks=[],
        roi_metadata=[],
        roi_revision=0,
    )
    app.movie_generation = 1
    app.roi_candidate_banks = {"fast": None, "caiman": None}
    app.session_temp_dir = tmp_path
    app.acceleration = mock.Mock(return_value="cpu")
    app._roi_model_identity = mock.Mock(return_value="caiman-test")
    app.enqueue_task = mock.Mock()
    app.set_parameter_feedback = mock.Mock()

    mask = np.zeros((1, 12, 14), dtype=bool)
    mask[0, 3:7, 4:8] = True
    backend_result = SimpleNamespace(
        masks=mask,
        names=["candidate"],
        arrays={
            "traces": np.ones((1, 20), dtype=np.float32),
            "snr": np.asarray([3.0], dtype=np.float32),
            "r_values": np.asarray([0.9], dtype=np.float32),
            "cnn_scores": np.asarray([0.95], dtype=np.float32),
            "component_indices": np.asarray([0], dtype=np.int32),
            "preset_accepted": np.asarray([True], dtype=bool),
        },
    )
    monkeypatch.setattr("NewLight_Analysis.core.compute_projection", lambda *_args, **_kwargs: movie.mean(axis=0))
    run_backend = mock.Mock(return_value=backend_result)
    monkeypatch.setattr("NewLight_Analysis.core.run_caiman_roi_segmentation", run_backend)

    app._enqueue_adaptive_roi(
        "caiman",
        {
            "quality_preset": "balanced",
            "mode": "two_photon",
            "size_mode": "single",
            "cell_diameter_min": 12.0,
            "cell_diameter_max": 24.0,
            "cell_diameter": 12.0,
            "components_per_patch": 4,
            "background_components": 2,
            "spatial_subsample": 2,
            "temporal_subsample": 2,
            "ar_order": 1,
            "merge_threshold": 0.85,
            "min_snr": 2.0,
            "rval_threshold": 0.8,
            "use_cnn": True,
            "min_cnn_threshold": 0.9,
            "cnn_lowest": 0.1,
            "footprint_threshold": 0.2,
            "similarity_limit": 2.3,
        },
    )

    worker = app.enqueue_task.call_args.args[1]
    payload = worker(threading.Event())

    run_backend.assert_called_once()
    assert payload["bank"].masks.shape == (1, 12, 14)
    assert payload["fitted"].selected_count == 1


def test_main_window_requests_zoomed_state_after_layout():
    app = NewLightApp.__new__(NewLightApp)
    app.root = mock.Mock()
    app.root.state.return_value = "normal"

    app._maximize_main_window()

    app.root.state.assert_any_call("zoomed")


def test_hidden_test_window_is_not_forced_visible_by_maximize():
    app = NewLightApp.__new__(NewLightApp)
    app.root = mock.Mock()
    app.root.state.return_value = "withdrawn"

    app._maximize_main_window()

    assert app.root.state.call_args_list == [mock.call()]


def drain_until_idle(app, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.task_controller.drain_results()
        if app.task_controller.current_task is None and not app.task_controller.pending_tasks:
            return
        time.sleep(0.005)
    raise AssertionError("task queue did not become idle")


@pytest.mark.parametrize("action_id", sorted(workflow_core.SUPPORTED_FUNCTIONS))
def test_supported_preprocess_actions_capture_workflow_descriptor(action_id):
    app = make_capture_app()
    values = ACTION_VALUES[action_id]

    task = app.run_preprocess_action(
        action_id,
        values,
        workflow_run_id="run-1",
        workflow_is_last=True,
    )

    if action_id == "caiman_motion":
        target = app.run_caiman_motion_from_values
    elif action_id == "image_shift":
        target = app.run_image_shift_from_values
    elif action_id == "remove_vessel_artifact":
        target = app.run_remove_vessels_from_values
    elif action_id == "load_roi":
        target = app.run_load_roi_from_values
    else:
        target = app.apply_movie_operation
    kwargs = target.call_args.kwargs
    assert task == target.return_value
    assert kwargs["workflow_step"] == {
        "function": action_id,
        "name": PREPROCESS_PANEL_SPECS.get(action_id, {}).get("label", {"load_roi": "载入 ROI"}.get(action_id, action_id)),
        "parameters": values,
    }
    assert kwargs["workflow_run_id"] == "run-1"
    assert kwargs["workflow_is_last"] is True


def test_failed_workflow_skips_remaining_steps_but_not_manual_tasks():
    app = NewLightApp.__new__(NewLightApp)
    app.task_controller = TaskController()
    app.workflow_runs = {"run-1": "running"}
    app.log = mock.Mock()
    app.render_task_flow = mock.Mock()
    touched = []

    def fail(_cancel_event):
        raise RuntimeError("first step failed")

    first = app.enqueue_task(
        "第一步",
        fail,
        mock.Mock(),
        on_error=mock.Mock(),
        workflow_run_id="run-1",
    )
    second = app.enqueue_task(
        "第二步",
        lambda _cancel_event: touched.append("second"),
        mock.Mock(),
        workflow_run_id="run-1",
    )
    third = app.enqueue_task(
        "第三步",
        lambda _cancel_event: touched.append("third"),
        mock.Mock(),
        workflow_run_id="run-1",
        workflow_is_last=True,
    )
    manual = app.enqueue_task(
        "手动任务",
        lambda _cancel_event: touched.append("manual"),
        mock.Mock(),
    )

    drain_until_idle(app)

    assert first.state == TaskState.FAILED
    assert second.state == TaskState.CANCELLED
    assert third.state == TaskState.CANCELLED
    assert manual.state == TaskState.COMPLETED
    assert touched == ["manual"]
    assert app.workflow_runs["run-1"] == "failed"


def test_cancelling_workflow_marks_run_cancelled_and_skips_following_steps():
    app = NewLightApp.__new__(NewLightApp)
    app.task_controller = TaskController()
    app.workflow_runs = {"run-1": "running"}
    app.log = mock.Mock()
    app.render_task_flow = mock.Mock()
    started = threading.Event()
    release = threading.Event()
    touched = []

    def blocker(cancel_event):
        started.set()
        release.wait(1.0)

    first = app.enqueue_task(
        "第一步",
        blocker,
        mock.Mock(),
        workflow_run_id="run-1",
    )
    second = app.enqueue_task(
        "第二步",
        lambda _cancel_event: touched.append("second"),
        mock.Mock(),
        workflow_run_id="run-1",
        workflow_is_last=True,
    )

    assert started.wait(1.0)
    assert app.task_controller.cancel_current_task()
    release.set()
    drain_until_idle(app)

    assert first.state == TaskState.CANCELLED
    assert second.state == TaskState.CANCELLED
    assert touched == []
    assert app.workflow_runs["run-1"] == "cancelled"


def test_current_workflow_steps_keep_supported_order_and_skip_ineligible_history():
    descriptor = {
        "function": "gaussian_smooth",
        "name": "高斯平滑",
        "parameters": {"sigma": "1.5"},
    }
    app = NewLightApp.__new__(NewLightApp)
    app.task_controller = SimpleNamespace(
        history=[
            SimpleNamespace(state=TaskState.COMPLETED, workflow_step=descriptor),
            SimpleNamespace(
                state=TaskState.RUNNING,
                workflow_step={"function": "gaussian_smooth", "name": "高斯平滑", "parameters": {"sigma": "2"}},
            ),
            SimpleNamespace(
                state=TaskState.QUEUED,
                workflow_step={"function": "median_filter", "name": "中值滤波", "parameters": {"size": "3"}},
            ),
            SimpleNamespace(state=TaskState.FAILED, workflow_step=descriptor),
            SimpleNamespace(state=TaskState.COMPLETED, workflow_step=None),
            SimpleNamespace(
                state=TaskState.COMPLETED,
                workflow_step={"function": "unknown", "name": "未知", "parameters": {}},
            ),
        ]
    )

    steps, skipped = app.current_reusable_workflow_steps()

    assert [step["function"] for step in steps] == [
        "gaussian_smooth",
        "gaussian_smooth",
        "median_filter",
    ]
    assert steps[0] == descriptor
    assert skipped == 3


def test_save_current_workflow_writes_json_and_reports_saved_count(tmp_path, monkeypatch):
    app = NewLightApp.__new__(NewLightApp)
    app.task_controller = SimpleNamespace(
        history=[
            SimpleNamespace(
                state=TaskState.COMPLETED,
                workflow_step={"function": "gaussian_smooth", "name": "高斯平滑", "parameters": {"sigma": "1.5"}},
            )
        ]
    )
    app.state = SimpleNamespace(source_path=str(tmp_path / "input.avi"))
    app.log = mock.Mock()
    app.set_parameter_feedback = mock.Mock()
    path = tmp_path / "saved.nlworkflow.json"
    monkeypatch.setattr("NewLight_Analysis.filedialog.asksaveasfilename", lambda **_kwargs: str(path))

    app.save_current_workflow()

    document = workflow_core.load_workflow(path)
    assert document["steps"][0]["function"] == "gaussian_smooth"
    assert any("1" in str(call) and "工作流" in str(call) for call in app.log.call_args_list)


def test_execute_workflow_submits_validated_steps_in_order_with_shared_run_id(tmp_path, monkeypatch):
    path = tmp_path / "replay.nlworkflow.json"
    workflow_core.save_workflow(
        path,
        [
            {"function": "gaussian_smooth", "name": "高斯平滑", "parameters": {"sigma": "1.5"}},
            {"function": "median_filter", "name": "中值滤波", "parameters": {"size": "3"}},
        ],
    )
    app = NewLightApp.__new__(NewLightApp)
    app.state = SimpleNamespace(movie=object())
    app.workflow_runs = {}
    app.run_preprocess_action = mock.Mock(return_value=object())
    app.log = mock.Mock()
    app.set_parameter_feedback = mock.Mock()
    app.render_task_flow = mock.Mock()
    monkeypatch.setattr("NewLight_Analysis.filedialog.askopenfilename", lambda **_kwargs: str(path))

    app.execute_workflow()

    assert app.run_preprocess_action.call_count == 2
    first = app.run_preprocess_action.call_args_list[0]
    second = app.run_preprocess_action.call_args_list[1]
    assert first.args[:2] == ("gaussian_smooth", {"sigma": "1.5"})
    assert second.args[:2] == ("median_filter", {"size": "3"})
    assert first.kwargs["workflow_run_id"] == second.kwargs["workflow_run_id"]
    assert first.kwargs["workflow_is_last"] is False
    assert second.kwargs["workflow_is_last"] is True
    assert list(app.workflow_runs.values()) == ["running"]


def test_invalid_workflow_is_rejected_before_any_task_is_submitted(tmp_path, monkeypatch):
    path = tmp_path / "invalid.nlworkflow.json"
    path.write_text('{"format": "wrong", "version": 1, "steps": []}', encoding="utf-8")
    app = NewLightApp.__new__(NewLightApp)
    app.state = SimpleNamespace(movie=object())
    app.workflow_runs = {}
    app.run_preprocess_action = mock.Mock()
    app.log = mock.Mock()
    app.set_parameter_feedback = mock.Mock()
    app.render_task_flow = mock.Mock()
    monkeypatch.setattr("NewLight_Analysis.filedialog.askopenfilename", lambda **_kwargs: str(path))

    result = app.execute_workflow()

    assert result is None
    app.run_preprocess_action.assert_not_called()
    assert app.workflow_runs == {}
    assert app.set_parameter_feedback.call_args.kwargs["error"] is True


def test_last_successful_workflow_task_marks_run_completed():
    app = NewLightApp.__new__(NewLightApp)
    app.task_controller = TaskController()
    app.workflow_runs = {"run-1": "running"}
    app.log = mock.Mock()
    app.render_task_flow = mock.Mock()

    task = app.enqueue_task(
        "最后一步",
        lambda _cancel_event: "done",
        mock.Mock(),
        workflow_run_id="run-1",
        workflow_is_last=True,
    )
    drain_until_idle(app)

    assert task.state == TaskState.COMPLETED
    assert app.workflow_runs["run-1"] == "completed"
    assert any("工作流执行完成" in str(call) for call in app.log.call_args_list)


def test_manual_roi_file_load_creates_replayable_path_descriptor(tmp_path):
    roi_path = tmp_path / "cells.npz"
    app = NewLightApp.__new__(NewLightApp)
    app.state = SimpleNamespace(movie=object())
    app.run_worker = mock.Mock(return_value="roi-task")

    result = app.run_load_roi_from_values({"path": str(roi_path), "format": "npz"})

    assert result == "roi-task"
    kwargs = app.run_worker.call_args.kwargs
    assert kwargs["workflow_step"] == {
        "function": "load_roi",
        "name": "载入 ROI",
        "parameters": {
            "path": str(roi_path.resolve()),
            "format": "npz",
        },
    }


def test_npz_roi_replay_worker_loads_masks_for_current_movie_shape(tmp_path):
    roi_path = tmp_path / "cells.npz"
    masks = np.zeros((1, 4, 5), dtype=bool)
    masks[0, 1:3, 2:4] = True
    np.savez(roi_path, masks=masks, names=np.asarray(["Cell A"]))
    app = NewLightApp.__new__(NewLightApp)
    app.state = SimpleNamespace(movie=np.zeros((3, 4, 5), dtype=np.float32))
    app.run_worker = mock.Mock(return_value="roi-task")

    app.run_load_roi_from_values({"path": str(roi_path), "format": "npz"})
    worker = app.run_worker.call_args.args[1]
    result = worker()

    assert len(result[0]) == 1
    assert result[0][0].shape == (4, 5)
    assert result[1] == ["Cell A"]
