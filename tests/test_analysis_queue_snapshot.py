import threading
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

import analysis_core as core
from NewLight_Analysis import NewLightApp


class ValueVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class AnalysisQueueSnapshotTests(unittest.TestCase):
    def make_app(self):
        app = object.__new__(NewLightApp)
        old_movie = np.ones((6, 4, 5), dtype=np.float32)
        app.state = SimpleNamespace(
            movie=old_movie,
            roi_masks=[np.ones((4, 5), dtype=bool)],
            roi_names=["OldROI"],
            roi_revision=1,
            baseline_start_frame=0,
            baseline_duration_frames=0,
            invalid_start_frames=0,
            trigger_frames=np.array([], dtype=int),
            fs=10.0,
            pre_trigger_s=1.0,
            post_trigger_s=2.0,
            baseline_image=None,
            dff_movie=None,
            traces=None,
        )
        app.trace_baseline_correct_var = ValueVar(False)
        app.trace_baseline_window_var = ValueVar("30")
        app.trace_smooth_window_var = ValueVar("1")
        app.user_settings = {"peak_detection": {"min_percentile": 25.0}}
        app.require_movie = lambda: True
        app.apply_protocol = lambda update_baseline=False: None
        app.ensure_global_roi = mock.Mock()
        app.sync_roi_names = mock.Mock()
        app.acceleration_value = "cpu"
        app.acceleration = lambda: app.acceleration_value
        app.log = mock.Mock()
        captured = {}

        def capture_enqueue(label, worker, finish, **kwargs):
            captured.update(label=label, worker=worker, finish=finish, **kwargs)

        app.enqueue_task = capture_enqueue
        return app, captured

    def test_worker_snapshots_movie_and_rois_when_it_reaches_front_of_fifo(self):
        app, captured = self.make_app()
        outputs = []

        def operation(movie, _baseline, traces, masks, names, _fs, _frames, _context, _cancel_event):
            return movie.shape, traces.shape, masks[0].shape, names

        app.queue_analysis_operation("analysis", operation, outputs.append, need_traces=True)
        new_movie = np.full((8, 6, 7), 2.0, dtype=np.float32)
        app.state.movie = new_movie
        app.state.roi_masks = [np.ones((6, 7), dtype=bool)]
        app.state.roi_names = ["NewROI"]
        app.state.roi_revision = 2

        captured["on_start"]()
        result = captured["worker"](threading.Event())

        self.assertEqual(result["source_id"], id(new_movie))
        self.assertEqual(result["roi_revision"], 2)
        self.assertEqual(result["output"], ((8, 6, 7), (8, 1), (6, 7), ["NewROI"]))

    def test_finish_rejects_result_after_roi_revision_changes(self):
        app, captured = self.make_app()
        completed = mock.Mock()
        app.queue_analysis_operation(
            "analysis",
            lambda _movie, _baseline, _traces, _masks, names, _fs, _frames, _context, _cancel: names,
            completed,
            need_traces=True,
        )
        captured["on_start"]()
        result = captured["worker"](threading.Event())
        app.state.roi_revision += 1

        captured["finish"](result)

        completed.assert_not_called()
        self.assertIsNone(app.state.traces)
        self.assertTrue(any("ROI" in str(call) and "过期" in str(call) for call in app.log.call_args_list))

    def test_finish_rejects_result_after_protocol_or_trace_settings_change(self):
        app, captured = self.make_app()
        completed = mock.Mock()
        app.queue_analysis_operation(
            "analysis",
            lambda _movie, _baseline, _traces, _masks, names, _fs, _frames, _context, _cancel: names,
            completed,
            need_traces=True,
        )
        captured["on_start"]()
        result = captured["worker"](threading.Event())
        app.state.fs = 20.0
        app.trace_smooth_window_var.set("5")

        captured["finish"](result)

        completed.assert_not_called()
        self.assertIsNone(app.state.traces)
        self.assertTrue(any("协议" in str(call) and "过期" in str(call) for call in app.log.call_args_list))

    def test_start_hook_snapshots_latest_protocol_and_trace_settings_together(self):
        app, captured = self.make_app()
        app.queue_analysis_operation(
            "analysis",
            lambda _movie, baseline, traces, _masks, _names, fs, frames, _context, _cancel: (
                baseline.copy(),
                traces.copy(),
                fs,
                frames.copy(),
            ),
            mock.Mock(),
            need_traces=True,
        )

        app.state.movie = np.arange(8, dtype=np.float32)[:, None, None] * np.ones((1, 4, 5), dtype=np.float32)
        app.state.roi_masks = [np.ones((4, 5), dtype=bool)]
        app.state.roi_names = ["LatestROI"]
        app.state.roi_revision = 7
        app.state.baseline_start_frame = 2
        app.state.baseline_duration_frames = 2
        app.state.invalid_start_frames = 1
        app.state.fs = 25.0
        app.state.trigger_frames = np.array([3, 6], dtype=int)
        app.trace_baseline_correct_var.set(False)
        app.trace_baseline_window_var.set("7")
        app.trace_smooth_window_var.set("3")

        captured["on_start"]()
        result = captured["worker"](threading.Event())
        baseline, traces, fs, frames = result["output"]
        expected_baseline = core.baseline_from_frames(app.state.movie, 2, 2, invalid_start_frames=1)
        expected_traces = core.extract_traces(app.state.movie, app.state.roi_masks, "dff", expected_baseline)
        expected_traces = core.process_traces(
            expected_traces,
            baseline_correct=False,
            baseline_window=7,
            smooth_window=3,
        )

        np.testing.assert_allclose(baseline, expected_baseline)
        np.testing.assert_allclose(traces, expected_traces)
        self.assertEqual(fs, 25.0)
        np.testing.assert_array_equal(frames, [3, 6])

    def test_operation_context_uses_start_time_acceleration_and_event_window(self):
        app, captured = self.make_app()
        app.queue_analysis_operation(
            "analysis",
            lambda _movie, _baseline, _traces, _masks, _names, _fs, _frames, context, _cancel: context,
            mock.Mock(),
            need_baseline=False,
        )
        app.acceleration_value = "gpu"
        app.state.pre_trigger_s = 3.5
        app.state.post_trigger_s = 7.25

        captured["on_start"]()
        result = captured["worker"](threading.Event())

        self.assertEqual(result["output"]["acceleration"], "gpu")
        self.assertEqual(result["output"]["pre_trigger_s"], 3.5)
        self.assertEqual(result["output"]["post_trigger_s"], 7.25)

    def test_peak_dependent_operation_uses_start_time_percentile(self):
        app, captured = self.make_app()
        app.queue_analysis_operation(
            "ROI statistics",
            lambda _movie, _baseline, _traces, _masks, _names, _fs, _frames, context, _cancel: context,
            mock.Mock(),
            need_baseline=False,
            depends_on_peak_settings=True,
        )
        app.user_settings["peak_detection"]["min_percentile"] = 75.0

        captured["on_start"]()
        result = captured["worker"](threading.Event())

        self.assertEqual(result["output"]["peak_min_percentile"], 75.0)

    def test_peak_dependent_completion_rejects_changed_percentile(self):
        app, captured = self.make_app()
        completed = mock.Mock()
        app.queue_analysis_operation(
            "ROI statistics",
            lambda _movie, _baseline, _traces, _masks, _names, _fs, _frames, context, _cancel: context,
            completed,
            need_baseline=False,
            depends_on_peak_settings=True,
        )
        captured["on_start"]()
        result = captured["worker"](threading.Event())
        app.user_settings["peak_detection"]["min_percentile"] = 75.0

        captured["finish"](result)

        completed.assert_not_called()
        self.assertTrue(any("峰值" in str(call) and "过期" in str(call) for call in app.log.call_args_list))

    def test_roi_dependent_operation_without_traces_rejects_stale_completion(self):
        app, captured = self.make_app()
        completed = mock.Mock()
        app.queue_analysis_operation(
            "ROI export",
            lambda _movie, _baseline, _traces, _masks, names, _fs, _frames, _context, _cancel: names,
            completed,
            need_traces=False,
            depends_on_rois=True,
        )
        captured["on_start"]()
        result = captured["worker"](threading.Event())
        app.state.roi_revision += 1

        captured["finish"](result)

        completed.assert_not_called()
        self.assertTrue(any("ROI" in str(call) and "过期" in str(call) for call in app.log.call_args_list))

    def test_start_hook_creates_global_roi_for_new_movie_before_trace_snapshot(self):
        app, captured = self.make_app()

        def ensure_global_roi():
            if not app.state.roi_masks:
                app.state.roi_masks = [np.ones(app.state.movie.shape[1:], dtype=bool)]
                app.state.roi_names = ["Global_ROI"]
                app.state.roi_revision += 1

        app.ensure_global_roi = ensure_global_roi
        completed = mock.Mock()
        app.queue_analysis_operation(
            "analysis",
            lambda _movie, _baseline, traces, _masks, names, _fs, _frames, _context, _cancel: (traces.shape, names),
            completed,
            need_traces=True,
        )
        app.state.movie = np.full((5, 6, 7), 2.0, dtype=np.float32)
        app.state.roi_masks = []
        app.state.roi_names = []
        app.state.roi_revision = 10

        captured["on_start"]()
        result = captured["worker"](threading.Event())
        captured["finish"](result)

        self.assertEqual(len(app.state.roi_masks), 1)
        self.assertEqual(app.state.roi_masks[0].shape, (6, 7))
        self.assertEqual(app.state.roi_names, ["Global_ROI"])
        self.assertEqual(app.state.traces.shape, (5, 1))
        completed.assert_called_once_with(((5, 1), ["Global_ROI"]))


if __name__ == "__main__":
    unittest.main()
