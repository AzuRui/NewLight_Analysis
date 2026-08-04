import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import tifffile

import analysis_core as core


class MovieFrameRateTests(unittest.TestCase):
    def test_imagej_tiff_uses_fps_metadata(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "movie.tif"
            tifffile.imwrite(path, np.zeros((3, 4, 5), dtype=np.uint16), imagej=True, metadata={"fps": 23.5})

            _movie, fps = core.load_movie(str(path))

        self.assertAlmostEqual(fps, 23.5)

    def test_imagej_tiff_converts_frame_interval_to_fps(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "movie.tif"
            tifffile.imwrite(path, np.zeros((3, 4, 5), dtype=np.uint16), imagej=True, metadata={"finterval": 0.04})

            _movie, fps = core.load_movie(str(path))

        self.assertAlmostEqual(fps, 25.0)

    def test_tiff_uses_nearby_two_photon_protocol_when_metadata_has_no_rate(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "movie.tif"
            tifffile.imwrite(path, np.zeros((3, 4, 5), dtype=np.uint16), photometric="minisblack")
            (folder / "protocol_real-time imaging.txt").write_text(
                "Image frame size (x): 5\n"
                "Image frame size (y): 4\n"
                "Image frame rate: 31.25\n",
                encoding="utf-8",
            )

            _movie, fps = core.load_movie(str(path))

        self.assertAlmostEqual(fps, 31.25)

    def test_tiff_without_rate_metadata_falls_back_to_ten_hz(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "movie.tif"
            tifffile.imwrite(path, np.zeros((3, 4, 5), dtype=np.uint16), photometric="minisblack")

            _movie, fps = core.load_movie(str(path))

        self.assertEqual(fps, 10.0)


if __name__ == "__main__":
    unittest.main()
