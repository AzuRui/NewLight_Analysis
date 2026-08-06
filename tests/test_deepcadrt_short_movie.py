import unittest
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import tifffile

import analysis_core as core
from workers import run_deepcadrt


class DeepCadRtShortMovieTests(unittest.TestCase):
    def test_headless_worker_stubs_optional_opencv_viewer(self):
        original = sys.modules.pop("cv2", None)
        try:
            run_deepcadrt.install_headless_cv2_compat()
            module = sys.modules["cv2"]
            self.assertTrue(callable(module.imshow))
            with self.assertRaisesRegex(RuntimeError, "display is disabled"):
                module.imshow("unused")
        finally:
            sys.modules.pop("cv2", None)
            if original is not None:
                sys.modules["cv2"] = original

    def test_short_movie_is_padded_to_two_temporal_stitch_windows(self):
        movie = np.arange(19 * 3 * 4, dtype=np.float32).reshape(19, 3, 4)

        padded, original_frames = run_deepcadrt.pad_short_movie_for_temporal_stitching(
            movie,
            patch_t=150,
            overlap=0.6,
        )

        self.assertEqual(original_frames, 19)
        self.assertEqual(padded.shape, (210, 3, 4))
        np.testing.assert_array_equal(padded[:19], movie)
        np.testing.assert_array_equal(padded[19:], np.repeat(movie[-1:], 191, axis=0))

    def test_longer_movie_is_not_padded(self):
        movie = np.ones((151, 3, 4), dtype=np.float32)

        padded, original_frames = run_deepcadrt.pad_short_movie_for_temporal_stitching(
            movie,
            patch_t=150,
            overlap=0.6,
        )

        self.assertEqual(original_frames, 151)
        self.assertIs(padded, movie)

    def test_nonempty_input_with_zero_model_output_falls_back_to_source(self):
        source = np.full((4, 3, 3), 10.0, dtype=np.float32)
        processed = source * 0.5
        processed[2] = 0.0

        restored, invalid = core.preserve_invalid_denoised_frames(source, processed)

        np.testing.assert_array_equal(invalid, np.array([2]))
        np.testing.assert_array_equal(restored[2], source[2])
        np.testing.assert_array_equal(restored[0], processed[0])

    def test_invalid_start_frames_bypass_model_and_are_restored(self):
        movie = np.arange(6 * 3 * 4, dtype=np.float32).reshape(6, 3, 4)

        def fake_worker(_env, _script, args, **_kwargs):
            input_path = Path(args[args.index("--input") + 1])
            output_path = Path(args[args.index("--output") + 1])
            model_input = tifffile.imread(input_path).astype(np.float32)
            self.assertEqual(model_input.shape[0], 4)
            np.testing.assert_array_equal(model_input, movie[2:])
            tifffile.imwrite(output_path, model_input + 100, photometric="minisblack")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with TemporaryDirectory() as tmp, \
                patch.object(core, "DEEPCADRT_DIR", Path(tmp)), \
                patch.object(core, "WORKER_DIR", Path(tmp)), \
                patch.object(core, "ensure_deepcadrt_model_available", return_value=""), \
                patch.object(core, "run_conda_worker", side_effect=fake_worker):
            denoised, _log = core.run_deepcadrt_denoise(
                movie,
                tmp,
                invalid_start_frames=2,
            )

        np.testing.assert_array_equal(denoised[:2], movie[:2])
        np.testing.assert_array_equal(denoised[2:], movie[2:] + 100)


if __name__ == "__main__":
    unittest.main()
