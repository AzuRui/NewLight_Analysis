import unittest

import numpy as np

import analysis_core as core


class BaselineFrameSelectionTests(unittest.TestCase):
    def test_zero_duration_uses_full_movie_25th_percentile(self):
        movie = np.arange(1, 6, dtype=np.float32).reshape(5, 1, 1)

        baseline = core.baseline_from_frames(movie, start_frame=2, duration_frames=0)

        np.testing.assert_allclose(baseline, np.percentile(movie, 25, axis=0))

    def test_positive_duration_uses_mean_of_selected_frames(self):
        movie = np.arange(1, 6, dtype=np.float32).reshape(5, 1, 1)

        baseline = core.baseline_from_frames(movie, start_frame=1, duration_frames=3)

        np.testing.assert_allclose(baseline, np.mean(movie[1:4], axis=0))


if __name__ == "__main__":
    unittest.main()
