from __future__ import annotations

from pathlib import Path
import tkinter as tk
from typing import Iterable

from PIL import Image, ImageColor, ImageOps


MODULE_DIR = Path(__file__).resolve().parent


def first_existing_path(candidates: Iterable[str | Path | None]) -> Path | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def cover_crop_image(image: Image.Image, target_size: tuple[int, int]) -> Image.Image:
    width = max(1, int(target_size[0]))
    height = max(1, int(target_size[1]))
    if image.mode != "RGB":
        image = image.convert("RGB")
    return ImageOps.fit(
        image,
        (width, height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )


def tint_image(image: Image.Image, color: str, alpha: float) -> Image.Image:
    alpha = max(0.0, min(1.0, float(alpha)))
    if alpha <= 0:
        return image
    rgb = ImageColor.getrgb(color)
    overlay = Image.new("RGB", image.size, rgb)
    return Image.blend(image, overlay, alpha)


def default_background_path() -> Path | None:
    return first_existing_path(
        (
            MODULE_DIR / "background.png",
            Path.cwd() / "background.png",
        )
    )


class WindowBackground:
    def __init__(self, root, image_path: str | Path | None = None):
        self.root = root
        self.image_path = Path(image_path) if image_path else default_background_path()
        self._image = None
        self._photo = None
        self._widget = None
        self._after_id = None
        self._load_image()
        self._install()

    def _load_image(self) -> None:
        if self.image_path is None:
            self._image = None
            return
        try:
            with Image.open(self.image_path) as img:
                self._image = img.convert("RGB")
        except Exception:
            self._image = None

    def _install(self) -> None:
        import tkinter as tk

        self._widget = tk.Label(self.root, bd=0, highlightthickness=0, borderwidth=0)
        self._widget.place(x=0, y=0, relwidth=1, relheight=1)
        self._widget.lower()
        self.root.bind("<Configure>", self._schedule_render, add="+")
        self.render()

    def _schedule_render(self, event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not self.root:
            return
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.root.after(25, self.render)

    def render(self) -> None:
        self._after_id = None
        if self._widget is None or self._image is None:
            return
        width = max(1, int(self.root.winfo_width()))
        height = max(1, int(self.root.winfo_height()))
        if width <= 1 or height <= 1:
            return
        fitted = cover_crop_image(self._image, (width, height))
        from PIL import ImageTk

        self._photo = ImageTk.PhotoImage(fitted)
        self._widget.configure(image=self._photo)
        self._widget.lower()


class BackgroundPane(tk.Frame):
    def __init__(
        self,
        master,
        image_path: str | Path | None = None,
        fallback_bg: str = "#07111f",
        overlay_color: str | None = None,
        overlay_alpha: float = 0.0,
        **kwargs,
    ):
        super().__init__(master, bg=fallback_bg, bd=0, highlightthickness=0, **kwargs)
        self.image_path = Path(image_path) if image_path else default_background_path()
        self.fallback_bg = fallback_bg
        self.overlay_color = overlay_color
        self.overlay_alpha = overlay_alpha
        self._image = None
        self._photo = None
        self._after_id = None
        self._background_label = tk.Label(self, bd=0, highlightthickness=0, borderwidth=0, bg=fallback_bg)
        self._background_label.place(x=0, y=0, relwidth=1, relheight=1)
        self._load_image()
        self.bind("<Configure>", self._schedule_render, add="+")
        self.render()

    def _load_image(self) -> None:
        if self.image_path is None:
            self._image = None
            return
        try:
            with Image.open(self.image_path) as img:
                self._image = img.convert("RGB")
        except Exception:
            self._image = None

    def _schedule_render(self, event=None) -> None:
        if event is not None and getattr(event, "widget", None) is not self:
            return
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.after(25, self.render)

    def render(self) -> None:
        self._after_id = None
        if self._image is None:
            self._background_label.configure(image="", bg=self.fallback_bg)
            self._background_label.lower()
            return
        width = max(1, int(self.winfo_width()))
        height = max(1, int(self.winfo_height()))
        if width <= 1 or height <= 1:
            self._background_label.lower()
            return
        fitted = cover_crop_image(self._image, (width, height))
        if self.overlay_color:
            fitted = tint_image(fitted, self.overlay_color, self.overlay_alpha)
        from PIL import ImageTk

        self._photo = ImageTk.PhotoImage(fitted)
        self._background_label.configure(image=self._photo)
        self._background_label.lower()
