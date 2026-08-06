import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import tifffile

import analysis_core as core
from workers import run_caiman


class CaimanMotionTests(unittest.TestCase):
    def test_worker_uses_writable_user_temp_instead_of_bundled_resources(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict("os.environ", {}, clear=False), mock.patch.object(
            run_caiman.tempfile, "gettempdir", return_value=tmp
        ):
            with mock.patch.dict("os.environ", {"CAIMAN_TEMP": ""}, clear=False):
                del os.environ["CAIMAN_TEMP"]
                path = run_caiman.prepare_caiman_temp_dir()

                self.assertEqual(path, Path(tmp) / "NewLight_Analysis" / "caiman")
                self.assertTrue(path.is_dir())
                self.assertEqual(os.environ["CAIMAN_TEMP"], str(path))

    def test_result_is_loaded_and_session_preview_tiff_is_retained(self):
        movie = np.arange(3 * 12 * 16, dtype=np.float32).reshape(3, 12, 16)

        def fake_worker(_env_name, _script, args, cwd=None, timeout=None):
            output_path = Path(args[args.index("--output") + 1])
            tifffile.imwrite(output_path, movie + 10.0, photometric="minisblack")
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=f"CaImAn motion correction saved {output_path}\n",
                stderr="",
            )

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            core, "run_conda_worker", side_effect=fake_worker
        ):
            result, log, preview_path = core.run_caiman_motion(movie, tmp, mode="piecewise")

            np.testing.assert_allclose(result, movie + 10.0)
            self.assertEqual(Path(preview_path), Path(tmp) / "caiman_preview.tif")
            self.assertTrue(Path(preview_path).is_file())
            self.assertFalse((Path(tmp) / "caiman_input.tif").exists())
            self.assertNotIn("saved", log.lower())

    def test_motion_parameters_are_forwarded_to_worker(self):
        movie = np.ones((3, 12, 16), dtype=np.float32)
        captured_args = []

        def fake_worker(_env_name, _script, args, cwd=None, timeout=None):
            captured_args.extend(args)
            output_path = Path(args[args.index("--output") + 1])
            tifffile.imwrite(output_path, movie, photometric="minisblack")
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            core, "run_conda_worker", side_effect=fake_worker
        ):
            core.run_caiman_motion(
                movie,
                tmp,
                mode="piecewise",
                max_shift=12,
                stride=48,
                overlap=24,
                max_deviation=5,
            )

        self.assertIn("--max-shift", captured_args)
        self.assertEqual(captured_args[captured_args.index("--max-shift") + 1], "12")
        self.assertEqual(captured_args[captured_args.index("--stride") + 1], "48")
        self.assertEqual(captured_args[captured_args.index("--overlap") + 1], "24")
        self.assertEqual(captured_args[captured_args.index("--max-deviation") + 1], "5")

    def test_worker_reports_parameters_and_shift_statistics(self):
        source = Path("workers/run_caiman.py").read_text(encoding="utf-8")

        self.assertIn("CaImAn parameters:", source)
        self.assertIn("CaImAn rigid shift statistics:", source)
        self.assertIn("CaImAn local shift statistics:", source)


if __name__ == "__main__":
    unittest.main()
