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

    def test_main_surfaces_render_background_image_themselves(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("side = ui_background.BackgroundPane", source)
        self.assertIn("main = ui_background.BackgroundPane", source)

    def test_empty_preview_draws_window_background(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("def draw_empty_preview_background", source)
        self.assertIn("self.draw_empty_preview_background()", source)
        self.assertIn("self.redraw(preserve_view=False)", source)

    def test_logo_starfield_uses_small_quiet_points(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("for _ in range(24):", source)
        self.assertIn('"r": rng.choice([0.45, 0.55, 0.65])', source)
        self.assertNotIn('r = s["r"] + (1 if pulse > 0.96 else 0)', source)


if __name__ == "__main__":
    unittest.main()
