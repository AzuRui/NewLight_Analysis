from __future__ import annotations

import math
import queue
import threading
import tkinter as tk
from pathlib import Path
from typing import Callable

from PIL import Image, ImageSequence, ImageTk


WINDOW_SIZE = (720, 480)
BACKGROUND_NAME = "neural_starlight_startup.gif"
LOGO_NAME = "xhr.ico"


class SplashUnavailableError(RuntimeError):
    pass


def resolve_resource_dir(application_dir: Path) -> Path:
    application_dir = Path(application_dir)
    internal = application_dir / "_internal"
    return internal if internal.is_dir() else application_dir


class SplashWindow:
    def __init__(self, application_dir: Path):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.configure(background="#071421")
        self.root.attributes("-topmost", True)
        self.canvas = tk.Canvas(
            self.root,
            width=WINDOW_SIZE[0],
            height=WINDOW_SIZE[1],
            highlightthickness=0,
            background="#071421",
        )
        self.canvas.pack()
        self._events: queue.Queue = queue.Queue()
        self._closed = False
        self._visible = False
        self._gif_index = 0
        self._bubble_index = 0
        self._gif_frames = []
        self._gif_delays = []
        self._logo = None
        self._background_item = None
        self._status_item = None
        self._bubble_items = []
        self._result = None
        self._error = None

        self._load_resources(resolve_resource_dir(application_dir))
        self._draw_layout()
        self._center_window()

    def _load_resources(self, resource_dir: Path) -> None:
        try:
            with Image.open(resource_dir / BACKGROUND_NAME) as image:
                for frame in ImageSequence.Iterator(image):
                    converted = frame.convert("RGB").resize(WINDOW_SIZE, Image.Resampling.LANCZOS)
                    self._gif_frames.append(ImageTk.PhotoImage(converted))
                    self._gif_delays.append(max(40, int(frame.info.get("duration", 200))))
        except (OSError, ValueError, tk.TclError):
            self._gif_frames = []
            self._gif_delays = []

        try:
            with Image.open(resource_dir / LOGO_NAME) as image:
                logo = image.convert("RGBA").resize((76, 76), Image.Resampling.LANCZOS)
                self._logo = ImageTk.PhotoImage(logo)
        except (OSError, ValueError, tk.TclError):
            self._logo = None

    def _draw_layout(self) -> None:
        if self._gif_frames:
            self._background_item = self.canvas.create_image(0, 0, anchor="nw", image=self._gif_frames[0])

        if self._logo is not None:
            self.canvas.create_image(360, 184, image=self._logo)
        self.canvas.create_text(
            360,
            254,
            text="NewLight Analysis",
            fill="#f5fbff",
            font=("Microsoft YaHei UI", 22, "normal"),
        )
        self.canvas.create_text(
            360,
            291,
            text="神经影像分析平台",
            fill="#dceff7",
            font=("Microsoft YaHei UI", 10, "normal"),
        )
        self.canvas.create_text(
            22,
            449,
            anchor="w",
            text="Version 1.0",
            fill="#c9dce5",
            font=("Microsoft YaHei UI", 8, "normal"),
        )
        self._status_item = self.canvas.create_text(
            360,
            449,
            text="正在检测运行环境...",
            fill="#eaf6fb",
            font=("Microsoft YaHei UI", 10, "normal"),
        )
        for _ in range(8):
            self._bubble_items.append(self.canvas.create_oval(0, 0, 0, 0, outline="", fill="#d9e5e9"))
        self._draw_bubbles()

    def _center_window(self) -> None:
        self.root.update_idletasks()
        x = max(0, (self.root.winfo_screenwidth() - WINDOW_SIZE[0]) // 2)
        y = max(0, (self.root.winfo_screenheight() - WINDOW_SIZE[1]) // 2)
        self.root.geometry(f"{WINDOW_SIZE[0]}x{WINDOW_SIZE[1]}+{x}+{y}")

    def _draw_bubbles(self) -> None:
        center_x, center_y, radius = 676, 449, 19
        for index, item in enumerate(self._bubble_items):
            phase = (index - self._bubble_index) % 8
            dot_radius = 4.5 if phase == 0 else 3.4 if phase == 1 else 2.5
            angle = math.radians(index * 45 - 90)
            x = center_x + math.cos(angle) * radius
            y = center_y + math.sin(angle) * radius
            self.canvas.coords(item, x - dot_radius, y - dot_radius, x + dot_radius, y + dot_radius)
            self.canvas.itemconfigure(item, fill="#f4fafc" if phase == 0 else "#c6d3d8" if phase == 1 else "#7f9097")

    def _animate_gif(self) -> None:
        if self._closed or not self._gif_frames:
            return
        self._gif_index = (self._gif_index + 1) % len(self._gif_frames)
        self.canvas.itemconfigure(self._background_item, image=self._gif_frames[self._gif_index])
        self.canvas.tag_lower(self._background_item)
        self.root.after(self._gif_delays[self._gif_index], self._animate_gif)

    def _animate_bubbles(self) -> None:
        if self._closed:
            return
        self._bubble_index = (self._bubble_index + 1) % 8
        self._draw_bubbles()
        self.root.after(130, self._animate_bubbles)

    def set_status(self, message: str) -> None:
        self._events.put(("status", str(message), None))

    def set_visible(self, visible: bool) -> None:
        acknowledgement = threading.Event()
        self._events.put(("visible", bool(visible), acknowledgement))
        acknowledgement.wait(timeout=2)

    def _apply_visibility(self, visible: bool) -> None:
        self._visible = bool(visible)
        if self._visible:
            self.root.deiconify()
            self.root.lift()
        else:
            self.root.withdraw()

    def _poll_events(self) -> None:
        while True:
            try:
                kind, value, acknowledgement = self._events.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                self.canvas.itemconfigure(self._status_item, text=value)
            elif kind == "visible":
                self._apply_visibility(value)
            elif kind == "complete":
                self._result = value
                self.root.quit()
            elif kind == "error":
                self._error = value
                self.root.quit()
            if acknowledgement is not None:
                acknowledgement.set()
        if not self._closed and self._result is None and self._error is None:
            self.root.after(25, self._poll_events)

    def run_until_complete(self, operation: Callable) -> bool:
        def worker() -> None:
            try:
                result = operation(self.set_status, self.set_visible)
            except BaseException as exc:
                self._events.put(("error", exc, None))
            else:
                self._events.put(("complete", result, None))

        self._apply_visibility(True)
        threading.Thread(target=worker, name="NewLight initialization", daemon=True).start()
        self.root.after(25, self._poll_events)
        self.root.after(self._gif_delays[0] if self._gif_delays else 200, self._animate_gif)
        self.root.after(130, self._animate_bubbles)
        self.root.mainloop()
        if self._error is not None:
            raise self._error
        return bool(self._result)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def run_with_initialization_splash(
    application_dir: Path,
    operation: Callable,
    *,
    splash_factory: Callable[[Path], SplashWindow] = SplashWindow,
) -> bool:
    try:
        splash = splash_factory(Path(application_dir))
    except (OSError, RuntimeError, tk.TclError) as exc:
        raise SplashUnavailableError(str(exc)) from exc
    try:
        return bool(splash.run_until_complete(operation))
    finally:
        splash.close()
