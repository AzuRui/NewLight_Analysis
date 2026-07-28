import unittest
from unittest import mock

import numpy as np

import analysis_core as core


class RoiColorTests(unittest.TestCase):
    def test_roi_color_is_stable_and_distinct_by_index(self):
        first_pass = [core.roi_color_rgb(index) for index in range(12)]
        second_pass = [core.roi_color_rgb(index) for index in range(12)]

        self.assertEqual(first_pass, second_pass)
        self.assertEqual(len(set(first_pass)), 12)

    def test_roi_color_representations_match(self):
        for index in range(8):
            rgb = core.roi_color_rgb(index)
            rgb_uint8 = core.roi_color_uint8(index)
            expected_uint8 = tuple(int(round(channel * 255)) for channel in rgb)
            expected_hex = "#" + "".join(f"{channel:02x}" for channel in expected_uint8)

            self.assertEqual(rgb_uint8, expected_uint8)
            self.assertEqual(core.roi_color_hex(index), expected_hex)

    def test_roi_overlay_uses_the_shared_roi_color(self):
        image = np.zeros((32, 32), dtype=np.float32)
        mask = np.zeros_like(image, dtype=bool)
        mask[8:24, 8:24] = True

        with mock.patch.object(core.cv2, "polylines", wraps=core.cv2.polylines) as polylines:
            core.draw_roi_overlay(image, [mask], ["ROI1"])

        self.assertTrue(polylines.called)
        self.assertEqual(polylines.call_args.args[3], core.roi_color_uint8(0))

    def test_selected_roi_overlay_is_thicker_without_changing_its_color(self):
        image = np.zeros((32, 32), dtype=np.float32)
        mask = np.zeros((32, 32), dtype=bool)
        mask[8:24, 9:23] = True
        color = np.asarray(core.roi_color_uint8(0), dtype=np.uint8)

        regular = core.draw_roi_overlay(image, [mask], ["ROI1"])
        selected = core.draw_roi_overlay(image, [mask], ["ROI1"], highlighted_index=0)

        regular_pixels = np.count_nonzero(np.all(regular == color, axis=2))
        selected_pixels = np.count_nonzero(np.all(selected == color, axis=2))
        self.assertGreater(selected_pixels, regular_pixels)
        self.assertEqual(np.count_nonzero(np.all(selected == 255, axis=2)), 0)

    def test_trace_export_uses_the_shared_roi_colors(self):
        traces = np.arange(18, dtype=np.float32).reshape(6, 3)
        t = np.arange(6, dtype=np.float32)
        with mock.patch("matplotlib.axes.Axes.plot", autospec=True) as plot:
            with mock.patch("matplotlib.figure.Figure.tight_layout"), mock.patch(
                "matplotlib.figure.Figure.savefig"
            ):
                core.plot_traces("traces.png", t, traces, ["ROI1", "ROI2", "ROI3"])

        colors = [call.kwargs.get("color") for call in plot.call_args_list[:3]]
        self.assertEqual(colors, [core.roi_color_hex(index) for index in range(3)])

    def test_trial_average_export_uses_the_shared_roi_colors(self):
        mean_trial = np.arange(18, dtype=np.float32).reshape(6, 3)
        t = np.linspace(-1.0, 1.0, 6)
        with mock.patch("matplotlib.axes.Axes.plot", autospec=True) as plot:
            with mock.patch("matplotlib.figure.Figure.tight_layout"), mock.patch(
                "matplotlib.figure.Figure.savefig"
            ):
                core.plot_trial_average("trial_average.png", t, mean_trial, ["ROI1", "ROI2", "ROI3"])

        colors = [call.kwargs.get("color") for call in plot.call_args_list[:3]]
        self.assertEqual(colors, [core.roi_color_hex(index) for index in range(3)])


if __name__ == "__main__":
    unittest.main()
