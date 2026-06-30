import unittest
from pathlib import Path


class GuiStaticTests(unittest.TestCase):
    def test_preprocess_tab_exposes_image_shift_button(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn('("Image Shift", self.image_shift)', source)
        self.assertIn('("Rigid Motion (Built-in)", self.builtin_motion)', source)
        self.assertLess(
            source.index('("Rigid Motion (Built-in)", self.builtin_motion)'),
            source.index('("Image Shift", self.image_shift)'),
        )


if __name__ == "__main__":
    unittest.main()
