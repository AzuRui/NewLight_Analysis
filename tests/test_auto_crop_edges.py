import unittest

import numpy as np

import analysis_core as core


class AutoCropEdgeTests(unittest.TestCase):
    @staticmethod
    def textured_movie(frames=12, height=64, width=72, seed=17):
        rng = np.random.default_rng(seed)
        return rng.normal(1000.0, 120.0, size=(frames, height, width)).astype(np.float32)

    def test_estimator_trims_stable_duplicated_motion_borders(self):
        movie = self.textured_movie()
        movie[:, :3, :] = movie[:, 3:4, :]
        movie[:, -2:, :] = movie[:, -3:-2, :]
        movie[:, :, :4] = movie[:, :, 4:5]
        movie[:, :, -5:] = movie[:, :, -6:-5]

        bounds = core.estimate_stable_crop_bounds(movie)

        self.assertEqual(bounds, (4, 3, 67, 62))

    def test_estimator_trims_constant_outer_lines(self):
        movie = self.textured_movie(seed=23)
        movie[:, :2, :] = 0
        movie[:, -3:, :] = 0
        movie[:, :, :1] = 0
        movie[:, :, -4:] = 0

        bounds = core.estimate_stable_crop_bounds(movie)

        self.assertEqual(bounds, (1, 2, 68, 61))

    def test_estimator_keeps_clean_movie_and_low_information_movie(self):
        clean = self.textured_movie(seed=31)
        constant = np.ones((8, 40, 48), dtype=np.float32)

        self.assertEqual(core.estimate_stable_crop_bounds(clean), (0, 0, 72, 64))
        self.assertEqual(core.estimate_stable_crop_bounds(constant), (0, 0, 48, 40))

    def test_estimator_ignores_a_single_transient_large_border(self):
        movie = self.textured_movie(seed=37)
        movie[0, :, :20] = movie[0, :, 20:21]

        self.assertEqual(core.estimate_stable_crop_bounds(movie), (0, 0, 72, 64))

    def test_estimator_requires_requested_frame_consensus(self):
        movie = self.textured_movie(frames=96, seed=39)
        movie[:6, :, :20] = movie[:6, :, 20:21]

        self.assertEqual(core.estimate_stable_crop_bounds(movie), (0, 0, 72, 64))

    def test_estimator_honors_minimum_size_guard(self):
        movie = self.textured_movie(height=20, width=22, seed=41)
        movie[:, :6, :] = movie[:, 6:7, :]
        movie[:, -6:, :] = movie[:, -7:-6, :]
        movie[:, :, :7] = movie[:, :, 7:8]
        movie[:, :, -7:] = movie[:, :, -8:-7]

        bounds = core.estimate_stable_crop_bounds(movie, minimum_size=16)
        x0, y0, x1, y1 = bounds

        self.assertGreaterEqual(x1 - x0, 16)
        self.assertGreaterEqual(y1 - y0, 16)

    def test_crop_preserves_frame_count_dtype_and_is_independent(self):
        movie = np.arange(3 * 10 * 12, dtype=np.uint16).reshape(3, 10, 12)

        cropped = core.crop_movie_bounds(movie, (2, 1, 10, 9))

        self.assertEqual(cropped.shape, (3, 8, 8))
        self.assertEqual(cropped.dtype, np.uint16)
        np.testing.assert_array_equal(cropped, movie[:, 1:9, 2:10])
        cropped[0, 0, 0] = 0
        self.assertNotEqual(movie[0, 1, 2], 0)

    def test_crop_applies_same_bounds_to_channels_and_masks(self):
        movie = np.zeros((4, 20, 24), dtype=np.float32)
        channels = (movie + 1, movie + 2)
        mask = np.zeros((20, 24), dtype=bool)
        mask[5:12, 7:15] = True
        bounds = (4, 3, 20, 17)

        cropped_channels = tuple(core.crop_movie_bounds(channel, bounds) for channel in channels)
        cropped_mask = core.crop_spatial_mask(mask, bounds)

        self.assertEqual([channel.shape for channel in cropped_channels], [(4, 14, 16), (4, 14, 16)])
        self.assertEqual(cropped_mask.shape, (14, 16))
        self.assertTrue(cropped_mask[2:9, 3:11].all())

    def test_crop_rejects_invalid_bounds(self):
        movie = np.zeros((3, 10, 12), dtype=np.float32)

        for bounds in ((-1, 0, 5, 5), (4, 2, 4, 8), (0, 0, 13, 10), (0, 0, 12, 11)):
            with self.subTest(bounds=bounds):
                with self.assertRaises(ValueError):
                    core.crop_movie_bounds(movie, bounds)


if __name__ == "__main__":
    unittest.main()
