import tempfile
import unittest
from pathlib import Path

from PIL import Image

import ui_background


class BackgroundImageTests(unittest.TestCase):
    def test_cover_crop_image_keeps_center_columns_without_stretching(self):
        src = Image.new("RGB", (4, 2))
        palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        for x, color in enumerate(palette):
            for y in range(2):
                src.putpixel((x, y), color)

        fitted = ui_background.cover_crop_image(src, (2, 2))

        self.assertEqual(fitted.size, (2, 2))
        self.assertEqual(fitted.getpixel((0, 0)), (0, 255, 0))
        self.assertEqual(fitted.getpixel((1, 0)), (0, 0, 255))
        self.assertEqual(fitted.getpixel((0, 1)), (0, 255, 0))
        self.assertEqual(fitted.getpixel((1, 1)), (0, 0, 255))

    def test_find_existing_path_prefers_first_existing_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.png"
            found = root / "background.png"
            found.write_bytes(b"ok")

            result = ui_background.first_existing_path((missing, found))

            self.assertEqual(result, found)


if __name__ == "__main__":
    unittest.main()
