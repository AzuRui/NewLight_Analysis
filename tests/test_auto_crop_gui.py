import threading
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from NewLight_Analysis import NewLightApp


class AutoCropGuiBehaviorTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        self.root.withdraw()
        self.app = NewLightApp(self.root)

    def tearDown(self):
        if hasattr(self, "app") and self.app.root.winfo_exists():
            self.app.on_close()

    def pump_tasks(self, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.root.update()
            if self.app.task_controller.current_task is None and not self.app.task_controller.pending_tasks:
                self.root.update()
                return
            time.sleep(0.01)
        self.fail("task queue did not become idle")

    @staticmethod
    def movie_with_borders(height=64, width=72, seed=91):
        rng = np.random.default_rng(seed)
        movie = rng.normal(1000.0, 100.0, size=(8, height, width)).astype(np.float32)
        movie[:, :3] = movie[:, 3:4]
        movie[:, :, :4] = movie[:, :, 4:5]
        return movie

    def set_movie(self, movie):
        self.app.state.movie = movie
        self.app.state.display_image = movie.mean(axis=0)
        self.app.state.baseline_image = self.app.state.display_image.copy()

    def test_refit_uses_movie_active_when_queued_worker_starts(self):
        old_movie = np.ones((4, 40, 44), dtype=np.float32)
        new_movie = self.movie_with_borders(height=50, width=60)
        self.set_movie(old_movie)

        def replace_worker(_cancel_event):
            return new_movie

        def replace_finish(movie):
            self.set_movie(movie)

        self.app.enqueue_task("replace movie", replace_worker, replace_finish)
        self.app.show_auto_crop_edges_panel()
        self.pump_tasks()

        self.assertEqual(self.app.auto_crop_bounds, (4, 3, 60, 50))

    def test_drag_confirm_and_undo_keep_channels_rois_and_source_aligned(self):
        movie = self.movie_with_borders()
        original = movie.copy()
        self.set_movie(movie)
        self.app.state.converted_channel_movies = (movie + 10, movie + 20)
        self.app.state.channel_colors = ("green", "red")
        inside = np.zeros((64, 72), dtype=bool)
        inside[12:20, 14:22] = True
        outside = np.zeros((64, 72), dtype=bool)
        outside[:2, :2] = True
        self.app.state.roi_masks = [inside, outside]
        self.app.state.roi_names = ["ROI1", "ROI2"]
        self.app.state.roi_metadata = [{"base_name": "ROI1"}, {"base_name": "ROI2"}]
        self.app.show_auto_crop_edges_panel()
        self.pump_tasks()

        x0, y0, x1, y1 = self.app.auto_crop_bounds
        middle_y = (y0 + y1) / 2.0
        self.app._start_auto_crop_drag(
            SimpleNamespace(button=1, xdata=x0 - 0.5, ydata=middle_y - 0.5)
        )
        self.app._update_auto_crop_drag(
            SimpleNamespace(inaxes=self.app.ax, xdata=x0 + 1.5, ydata=middle_y - 0.5)
        )
        self.app.on_release(SimpleNamespace())
        self.assertEqual(self.app.auto_crop_bounds, (6, 3, 72, 64))

        self.app.confirm_auto_crop_edges()
        self.pump_tasks()
        self.assertEqual(self.app.state.movie.shape, (8, 61, 66))
        self.assertEqual([item.shape for item in self.app.state.converted_channel_movies], [(8, 61, 66)] * 2)
        self.assertEqual(len(self.app.state.roi_masks), 1)
        self.assertEqual(self.app.state.roi_masks[0].shape, (61, 66))
        np.testing.assert_array_equal(movie, original)

        self.app.undo()
        self.assertEqual(self.app.state.movie.shape, (8, 64, 72))
        self.assertEqual(len(self.app.state.roi_masks), 2)
        self.assertEqual(self.app.state.roi_masks[0].shape, (64, 72))
        self.pump_tasks()

    def test_pending_confirmation_survives_panel_replacement_and_does_not_close_it(self):
        movie = self.movie_with_borders()
        self.set_movie(movie)
        self.app.show_auto_crop_edges_panel()
        self.pump_tasks()
        gate = threading.Event()

        def blocker(_cancel_event):
            gate.wait(5.0)

        self.app.enqueue_task("blocker", blocker, lambda _result: None)
        self.app.auto_crop_bounds = (4, 3, 70, 62)
        self.app.confirm_auto_crop_edges()
        self.app.show_parameter_panel("其他参数", [], panel_id="other")
        self.app.show_auto_crop_edges_panel()

        self.assertTrue(self.app.auto_crop_confirmation_pending)
        self.assertEqual(self.app.active_parameter_panel_id, "other")
        gate.set()
        self.pump_tasks()
        self.assertEqual(self.app.active_parameter_panel_id, "other")
        self.assertEqual(self.app.state.movie.shape, (8, 59, 66))

    def test_opening_without_movie_uses_embedded_feedback_not_messagebox(self):
        self.app.state.movie = None

        with mock.patch("NewLight_Analysis.messagebox.showwarning") as warning:
            self.app.show_auto_crop_edges_panel()

        warning.assert_not_called()
        self.assertEqual(self.app.active_parameter_panel_id, "auto_crop_edges")
        self.assertIn("请先", self.app.parameter_feedback_var.get())


if __name__ == "__main__":
    unittest.main()
