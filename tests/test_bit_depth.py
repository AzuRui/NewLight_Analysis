import tempfile
import unittest
from pathlib import Path

import numpy as np
import tifffile

import analysis_core as core


class MovieBitDepthTests(unittest.TestCase):
    def write_tiff(self, stack: np.ndarray) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "movie.tif"
        tifffile.imwrite(path, stack)
        return path

    def test_tiff_auto_import_preserves_uint16_range(self):
        stack = np.array(
            [
                [[0, 512, 4096], [8192, 16384, 65535]],
                [[1200, 2400, 4800], [9600, 19200, 38400]],
            ],
            dtype=np.uint16,
        )
        path = self.write_tiff(stack)

        movie, fs = core.load_movie(str(path), bit_depth="auto")

        self.assertEqual(movie.dtype, np.float32)
        self.assertEqual(fs, 10.0)
        self.assertGreater(float(movie.max()), 255.0)
        np.testing.assert_array_equal(movie, stack.astype(np.float32))

    def test_tiff_16bit_import_preserves_uint16_range(self):
        stack = np.array([[[0, 1024, 32768, 65535]]], dtype=np.uint16)
        path = self.write_tiff(stack)

        movie, _ = core.load_movie(str(path), bit_depth="16-bit")

        self.assertEqual(movie.dtype, np.float32)
        self.assertGreater(float(movie.max()), 255.0)
        np.testing.assert_array_equal(movie, stack.astype(np.float32))

    def test_tiff_8bit_import_quantizes_to_uint8_range(self):
        stack = np.array([[[0, 16384, 32768, 65535]]], dtype=np.uint16)
        path = self.write_tiff(stack)

        movie, _ = core.load_movie(str(path), bit_depth="8-bit")

        self.assertEqual(movie.dtype, np.float32)
        self.assertEqual(float(movie.min()), 0.0)
        self.assertEqual(float(movie.max()), 255.0)
        np.testing.assert_array_equal(movie, np.array([[[0, 64, 128, 255]]], dtype=np.float32))

    def test_tiff_save_can_emit_uint16_stack(self):
        movie = np.array([[[0.0, 128.0, 65535.0], [-5.0, 12345.0, 70000.0]]], dtype=np.float32)
        path = self.write_tiff(np.zeros((1, 1, 1), dtype=np.uint16)).with_name("saved.tif")

        core.save_movie_tiff(movie, str(path), bit_depth="16-bit")

        saved = tifffile.imread(path)
        self.assertEqual(saved.dtype, np.uint16)
        np.testing.assert_array_equal(saved, np.array([[[0, 128, 65535], [0, 12345, 65535]]], dtype=np.uint16))


if __name__ == "__main__":
    unittest.main()
