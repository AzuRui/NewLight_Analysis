import threading
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import ttk
from unittest import mock

import numpy as np
from matplotlib.backend_bases import MouseEvent
from matplotlib.figure import Figure

import analysis_core as core
import NewLight_Analysis as newlight

NewLightApp = newlight.NewLightApp


class PeakDetectionPlotTests(unittest.TestCase):
    def test_peak_button_opens_embedded_parameter_panel_before_queueing(self):
        app = object.__new__(NewLightApp)
        app.user_settings = {}
        app.show_parameter_panel = mock.Mock()
        app.queue_analysis_operation = mock.Mock()

        app.peak_detection()

        app.queue_analysis_operation.assert_not_called()
        app.show_parameter_panel.assert_called_once()
        args, kwargs = app.show_parameter_panel.call_args
        self.assertIn("峰值", args[0])
        percentile_fields = [
            field
            for field in args[1]
            if isinstance(field, dict) and field.get("key") == "min_percentile"
        ]
        self.assertEqual(len(percentile_fields), 1)
        self.assertEqual(float(percentile_fields[0]["default"]), 25.0)
        self.assertEqual(kwargs["apply_command"], app.run_peak_detection)

        app.user_settings = {"peak_detection": {"min_percentile": 72.5}}
        app.peak_detection()
        saved_fields = app.show_parameter_panel.call_args.args[1]
        saved_percentile = next(field for field in saved_fields if field.get("key") == "min_percentile")
        self.assertEqual(float(saved_percentile["default"]), 72.5)

    def test_peak_analysis_returns_the_exact_indices_used_by_the_plot(self):
        app = object.__new__(NewLightApp)
        captured = {}
        app.log = mock.Mock()
        app.set_parameter_feedback = mock.Mock()
        app.show_peak_detection_window = mock.Mock()
        app.user_settings = {}

        def capture_queue(label, operation, on_complete, **kwargs):
            captured.update(label=label, operation=operation, on_complete=on_complete, kwargs=kwargs)

        app.queue_analysis_operation = capture_queue
        with mock.patch("NewLight_Analysis.save_user_settings") as save_settings:
            app.run_peak_detection({"min_percentile": "75"})
        save_settings.assert_called_once_with(app.user_settings)
        self.assertEqual(app.user_settings["peak_detection"]["min_percentile"], 75.0)
        fs = 10.0
        traces = np.zeros((60, 2), dtype=np.float32)
        traces[[10, 35], 0] = [4.0, 5.0]
        traces[[20, 45], 1] = [6.0, 4.5]
        names = ["ROI1", "ROI2"]

        result = captured["operation"](
            None,
            None,
            traces,
            None,
            names,
            fs,
            np.array([], dtype=int),
            {},
            threading.Event(),
        )

        np.testing.assert_array_equal(result["traces"], traces)
        self.assertEqual(result["names"], names)
        self.assertEqual(result["fs"], fs)
        self.assertEqual(result["min_percentile"], 75.0)
        self.assertEqual(len(result["peaks"]), 2)
        for index in range(2):
            np.testing.assert_array_equal(
                result["peaks"][index],
                core.detect_trace_peaks(traces[:, index], fs, min_percentile=75.0),
            )
        for invalid_fs in (0.0, -1.0, np.nan, np.inf):
            with self.subTest(fs=invalid_fs), self.assertRaisesRegex(ValueError, "帧率"):
                captured["operation"](
                    None,
                    None,
                    traces,
                    None,
                    names,
                    invalid_fs,
                    np.array([], dtype=int),
                    {},
                    threading.Event(),
                )

        with mock.patch("NewLight_Analysis.messagebox.showinfo") as info:
            captured["on_complete"](result)

        info.assert_not_called()
        app.show_peak_detection_window.assert_called_once_with(
            result["traces"],
            result["names"],
            result["peaks"],
            result["fs"],
            result["min_percentile"],
        )
        self.assertTrue(app.log.called)
        self.assertTrue(captured["kwargs"]["need_traces"])

    def test_peak_percentile_filters_low_peaks_and_validates_range(self):
        trace = np.array([0, 1, 0, 4, 0, 10, 0, 8, 0, 2, 0], dtype=np.float32)

        all_peaks = core.detect_trace_peaks(trace, 1.0, prominence_scale=0.0, min_percentile=0.0)
        high_peaks = core.detect_trace_peaks(trace, 1.0, prominence_scale=0.0, min_percentile=75.0)

        np.testing.assert_array_equal(all_peaks, [1, 3, 5, 7, 9])
        np.testing.assert_array_equal(high_peaks, [3, 5, 7])
        for value in (-1.0, 101.0, np.nan):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "分位"):
                core.detect_trace_peaks(trace, 1.0, min_percentile=value)

    def test_core_default_preserves_legacy_detection_and_statistics_can_use_saved_percentile(self):
        trace = np.array([0, 1, 0, 100, 90, 100, 90, 100, 90], dtype=np.float32)
        traces = trace[:, None]

        legacy_peaks = core.detect_trace_peaks(trace, 1.0, prominence_scale=0.0)
        q50_peaks = core.detect_trace_peaks(trace, 1.0, prominence_scale=0.0, min_percentile=50.0)
        stats = core.roi_statistics(
            traces,
            ["ROI1"],
            1.0,
            min_peak_percentile=50.0,
            peak_prominence_scale=0.0,
        )

        self.assertIn(1, legacy_peaks)
        self.assertNotIn(1, q50_peaks)
        self.assertEqual(int(stats.loc[0, "Peak_Count"]), len(q50_peaks))

    def test_invalid_peak_percentile_does_not_save_or_queue(self):
        app = object.__new__(NewLightApp)
        app.user_settings = {}
        app.set_parameter_feedback = mock.Mock()
        app.queue_analysis_operation = mock.Mock()

        for value in ("bad", "-1", "101", "nan"):
            with self.subTest(value=value), mock.patch("NewLight_Analysis.save_user_settings") as save_settings:
                app.run_peak_detection({"min_percentile": value})
                save_settings.assert_not_called()

        app.queue_analysis_operation.assert_not_called()
        self.assertNotIn("peak_detection", app.user_settings)
        self.assertTrue(app.set_parameter_feedback.called)

    def test_peak_plot_marks_peak_coordinates_and_keeps_roi_colors(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def draw_peak_trace_axis(")
        end = source.index("    def show_peak_detection_window(", start)
        method = source[start:end]

        self.assertIn("t[peaks]", method)
        self.assertIn("trace[peaks]", method)
        self.assertIn("ax.scatter", method)
        self.assertIn("color=core.roi_color_hex(roi_index)", method)

    def test_peak_axis_draws_exact_scatter_coordinates_and_rejects_invalid_fs(self):
        trace = np.array([0.0, 2.0, 0.5, 4.0, 0.0], dtype=np.float32)
        peaks = np.array([1, 3], dtype=int)
        fig = Figure(figsize=(5, 3), dpi=100)
        ax = fig.add_subplot(111)

        valid_peaks = NewLightApp.draw_peak_trace_axis(ax, trace, peaks, 2.0, 1, "ROI2")

        np.testing.assert_array_equal(valid_peaks, peaks)
        np.testing.assert_allclose(ax.lines[0].get_xdata(), np.arange(5) / 2.0)
        np.testing.assert_allclose(ax.lines[0].get_ydata(), trace)
        np.testing.assert_allclose(ax.collections[0].get_offsets(), np.array([[0.5, 2.0], [1.5, 4.0]]))
        self.assertEqual(ax.lines[0].get_color(), core.roi_color_hex(1))
        self.assertIn("n=2", ax.get_title())
        with self.assertRaisesRegex(ValueError, "帧率"):
            NewLightApp.draw_peak_trace_axis(ax, trace, peaks, 0.0, 0, "ROI1")

    def test_peak_window_uses_synchronized_selector_toolbar_and_mouse_wheel(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def show_peak_detection_window(")
        end = source.index("    def peak_detection(self):", start)
        method = source[start:end]

        self.assertIn("ttk.Combobox", method)
        self.assertIn("render_selected_roi", method)
        self.assertIn("PeakPlotToolbar", method)
        self.assertIn("step_selected_roi", method)
        self.assertIn("toolbar.set_view_step_callback(step_selected_roi)", method)
        self.assertIn('canvas.mpl_connect("scroll_event", on_peak_scroll)', method)

    def test_peak_toolbar_maps_back_and_forward_to_roi_navigation(self):
        self.assertTrue(hasattr(newlight, "PeakPlotToolbar"))
        callbacks = {item[3] for item in newlight.PeakPlotToolbar.toolitems if item is not None and item[3]}
        main_callbacks = {item[3] for item in newlight.ImageToolbar.toolitems if item is not None and item[3]}

        self.assertEqual(callbacks, {"home", "back", "forward", "pan", "zoom", "save_figure"})
        self.assertIn("back", main_callbacks)
        self.assertIn("forward", main_callbacks)

        callback = mock.Mock()
        toolbar = object.__new__(newlight.PeakPlotToolbar)
        toolbar._view_step_callback = callback
        toolbar.back()
        toolbar.forward()

        callback.assert_has_calls([mock.call(-1), mock.call(1)])

    def test_peak_roi_navigation_wraps_and_mouse_wheel_uses_expected_direction(self):
        self.assertEqual(newlight.wrapped_view_index(0, 3, -1), 2)
        self.assertEqual(newlight.wrapped_view_index(2, 3, 1), 0)
        self.assertEqual(newlight.wrapped_view_index(-1, 3, 1), 1)
        with self.assertRaisesRegex(ValueError, "ROI"):
            newlight.wrapped_view_index(0, 0, 1)

        self.assertEqual(newlight.peak_scroll_delta(mock.Mock(button="up", step=0)), -1)
        self.assertEqual(newlight.peak_scroll_delta(mock.Mock(button="down", step=0)), 1)
        self.assertEqual(newlight.peak_scroll_delta(mock.Mock(button=None, step=1)), -1)
        self.assertEqual(newlight.peak_scroll_delta(mock.Mock(button=None, step=-1)), 1)
        self.assertEqual(newlight.peak_scroll_delta(mock.Mock(button=None, step=0)), 0)

    def test_peak_window_keeps_initial_selection_and_synchronizes_real_tk_controls(self):
        root = tk.Tk()
        root.withdraw()
        app = object.__new__(NewLightApp)
        app.root = root
        traces = np.zeros((20, 3), dtype=np.float32)
        traces[[3, 7, 11], [0, 1, 2]] = 5.0
        win = None
        try:
            win = app.show_peak_detection_window(
                traces,
                ["ROI-A", "ROI-B", "ROI-C"],
                [np.array([3]), np.array([7]), np.array([11])],
                10.0,
                25.0,
            )
            root.update()

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            widgets = list(descendants(win))
            selector = next(widget for widget in widgets if isinstance(widget, ttk.Combobox))
            toolbar = next(widget for widget in widgets if isinstance(widget, newlight.PeakPlotToolbar))

            self.assertEqual(selector.current(), 0)
            toolbar.forward()
            root.update()
            self.assertEqual(selector.current(), 1)
            self.assertIn("ROI-B", toolbar.canvas.figure.axes[0].get_title())

            toolbar.back()
            toolbar.back()
            root.update()
            self.assertEqual(selector.current(), 2)

            down = MouseEvent("scroll_event", toolbar.canvas, 100, 100, button="down", step=-1)
            toolbar.canvas.callbacks.process("scroll_event", down)
            root.update()
            self.assertEqual(selector.current(), 0)

            up = MouseEvent("scroll_event", toolbar.canvas, 100, 100, button="up", step=1)
            toolbar.canvas.callbacks.process("scroll_event", up)
            root.update()
            self.assertEqual(selector.current(), 2)
            self.assertIn("ROI-C", toolbar.canvas.figure.axes[0].get_title())
        finally:
            if win is not None and win.winfo_exists():
                win.destroy()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
