import unittest

import numpy as np
from scipy import ndimage

import analysis_core as core


def _reference_image(height=64, width=80, seed=23):
    rng = np.random.default_rng(seed)
    image = ndimage.gaussian_filter(rng.normal(size=(height, width)), sigma=1.2)
    image -= float(image.min())
    image /= float(image.max() - image.min())
    return image.astype(np.float32)


def _shifted_movie(image, shifts):
    return np.stack(
        [ndimage.shift(image, shift=shift, order=1, mode="nearest") for shift in shifts],
        axis=0,
    ).astype(np.float32)


def _cropped_mae(frame, reference, margin=8):
    return float(np.mean(np.abs(frame[margin:-margin, margin:-margin] - reference[margin:-margin, margin:-margin])))


def _locally_warped_image(image, dy_field, dx_field):
    yy, xx = np.indices(image.shape, dtype=np.float32)
    return ndimage.map_coordinates(
        image,
        [yy - np.asarray(dy_field, dtype=np.float32), xx - np.asarray(dx_field, dtype=np.float32)],
        order=1,
        mode="nearest",
    ).astype(np.float32)


class RigidMotionTests(unittest.TestCase):
    def test_manual_reference_interval_is_refined_and_all_its_frames_are_corrected(self):
        reference = _reference_image()
        source_shifts = [(-4, 0), (-2, 0), (0, 0), (2, 0), (4, 0), (1, -2), (-1, 2)]
        movie = _shifted_movie(reference, source_shifts)

        corrected, shifts, info = core.rigid_motion_correction(
            movie,
            reference_mode="manual",
            reference_start=0,
            reference_frames=5,
            max_shift=8,
        )

        before = np.mean([_cropped_mae(movie[i], reference) for i in (0, 1, 3, 4)])
        after = np.mean([_cropped_mae(corrected[i], reference) for i in (0, 1, 3, 4)])
        self.assertLess(after, before * 0.35)
        self.assertFalse(np.allclose(corrected[0], movie[0]))
        self.assertFalse(np.allclose(corrected[4], movie[4]))
        self.assertEqual(info["reference_start"], 0)
        self.assertEqual(info["reference_end"], 5)
        self.assertEqual(info["anchor_frame"], 2)
        self.assertEqual(len(shifts), movie.shape[0])
        self.assertEqual(corrected.shape, movie.shape)
        self.assertEqual(corrected.dtype, np.float32)

    def test_auto_reference_uses_stable_window_after_unstable_opening(self):
        reference = _reference_image(seed=31)
        opening_shifts = [(0, 0), (4, -2), (-3, 3), (5, 1), (-4, -3), (3, 4)]
        movie = _shifted_movie(reference, opening_shifts + [(0, 0)] * 8)

        corrected, _shifts, info = core.rigid_motion_correction(
            movie,
            reference_mode="auto",
            reference_frames=4,
            max_shift=8,
        )

        self.assertGreaterEqual(info["reference_start"], len(opening_shifts))
        before = np.mean([_cropped_mae(movie[i], reference) for i in range(len(opening_shifts))])
        after = np.mean([_cropped_mae(corrected[i], reference) for i in range(len(opening_shifts))])
        self.assertLess(after, before * 0.4)

    def test_auto_reference_prefers_the_dominant_position_over_a_short_offset_opening(self):
        reference = _reference_image(seed=47)
        movie = _shifted_movie(reference, [(4, 0)] * 4 + [(0, 0)] * 8)

        corrected, _shifts, info = core.rigid_motion_correction(
            movie,
            reference_mode="auto",
            reference_frames=4,
            max_shift=8,
        )

        self.assertGreaterEqual(info["reference_start"], 4)
        self.assertLess(_cropped_mae(corrected[0], reference), _cropped_mae(movie[0], reference) * 0.35)

    def test_fast_motion_strength_zero_exactly_matches_rigid_correction(self):
        reference = _reference_image(seed=53)
        movie = _shifted_movie(reference, [(0, 0), (3, -2), (-2, 1), (1, 2)])
        kwargs = {
            "reference_mode": "manual",
            "reference_start": 0,
            "reference_frames": 1,
            "max_shift": 8,
        }

        rigid, rigid_shifts, rigid_info = core.rigid_motion_correction(movie, **kwargs)
        fast, fast_shifts, fast_info = core.fast_motion_correction(
            movie,
            **kwargs,
            flexible_strength=0.0,
            local_block_size=32,
            max_local_deformation=3.0,
        )

        np.testing.assert_array_equal(fast, rigid)
        self.assertEqual(fast_shifts, rigid_shifts)
        self.assertEqual(fast_info["reference_start"], rigid_info["reference_start"])
        self.assertEqual(fast_info["reference_end"], rigid_info["reference_end"])
        self.assertEqual(fast_info["anchor_frame"], rigid_info["anchor_frame"])
        self.assertFalse(fast_info["local_applied"])
        self.assertEqual(fast_info["local_skip_reason"], "flexible_strength_zero")

    def test_fast_motion_reduces_smooth_local_deformation_after_rigid_stage(self):
        reference = _reference_image(height=96, width=112, seed=61)
        yy, xx = np.indices(reference.shape, dtype=np.float32)
        dx = 2.5 * np.tanh((xx - reference.shape[1] / 2.0) / 14.0)
        dy = 1.5 * np.sin(2.0 * np.pi * xx / reference.shape[1])
        warped_a = _locally_warped_image(reference, dy, dx)
        warped_b = _locally_warped_image(reference, -0.8 * dy, -0.8 * dx)
        movie = np.stack([reference, reference, reference, warped_a, warped_b]).astype(np.float32)

        rigid, _rigid_shifts, _rigid_info = core.rigid_motion_correction(
            movie,
            reference_mode="manual",
            reference_start=0,
            reference_frames=3,
            max_shift=6,
        )
        corrected, _shifts, info = core.fast_motion_correction(
            movie,
            reference_mode="manual",
            reference_start=0,
            reference_frames=3,
            max_shift=6,
            flexible_strength=1.0,
            local_block_size=32,
            max_local_deformation=4.0,
        )

        before = np.mean([_cropped_mae(rigid[i], reference, margin=12) for i in (3, 4)])
        after = np.mean([_cropped_mae(corrected[i], reference, margin=12) for i in (3, 4)])
        self.assertLess(after, before * 0.9)
        self.assertTrue(info["local_applied"])
        self.assertGreaterEqual(info["local_grid_shape"][0], 2)
        self.assertGreaterEqual(info["local_grid_shape"][1], 2)
        self.assertLessEqual(info["local_max_abs_shift"], 4.0 + 1e-6)
        self.assertEqual(corrected.shape, movie.shape)
        self.assertEqual(corrected.dtype, np.float32)
        self.assertTrue(np.all(np.isfinite(corrected)))

    def test_fast_motion_small_image_falls_back_and_rejects_invalid_limits(self):
        reference = _reference_image(height=20, width=20, seed=71)
        movie = _shifted_movie(reference, [(0, 0), (1, -1)])

        rigid, _rigid_shifts, _rigid_info = core.rigid_motion_correction(
            movie,
            reference_mode="manual",
            reference_start=0,
            reference_frames=1,
            max_shift=4,
        )
        corrected, _shifts, info = core.fast_motion_correction(
            movie,
            reference_mode="manual",
            reference_start=0,
            reference_frames=1,
            max_shift=4,
            flexible_strength=0.5,
            local_block_size=32,
            max_local_deformation=2.0,
        )

        np.testing.assert_array_equal(corrected, rigid)
        self.assertFalse(info["local_applied"])
        self.assertEqual(info["local_skip_reason"], "image_too_small")
        with self.assertRaisesRegex(ValueError, "柔性强度"):
            core.fast_motion_correction(movie, flexible_strength=float("nan"))
        with self.assertRaisesRegex(ValueError, "最大局部形变"):
            core.fast_motion_correction(movie, flexible_strength=0.5, max_local_deformation=-1)


if __name__ == "__main__":
    unittest.main()
