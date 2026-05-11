from __future__ import annotations

import os
import queue
import random
import threading
import time
import traceback
import tempfile
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np

import analysis_core as core


THEME = {
    "bg": "#07111f",
    "panel": "#0d1b2e",
    "panel_2": "#12233a",
    "panel_3": "#172b46",
    "text": "#dbeafe",
    "muted": "#8ea7c7",
    "accent": "#38bdf8",
    "accent_2": "#a78bfa",
    "success": "#5eead4",
    "warning": "#fbbf24",
    "border": "#25405f",
    "entry": "#081525",
}


class ImageToolbar(NavigationToolbar2Tk):
    toolitems = tuple(item for item in NavigationToolbar2Tk.toolitems if item[0] != "Subplots")


def apply_dark_theme(root):
    root.configure(bg=THEME["bg"])
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure(".", background=THEME["bg"], foreground=THEME["text"], fieldbackground=THEME["entry"], bordercolor=THEME["border"], lightcolor=THEME["panel_2"], darkcolor=THEME["bg"], font=("Segoe UI", 10))
    style.configure("TFrame", background=THEME["bg"])
    style.configure("Sidebar.TFrame", background=THEME["panel"])
    style.configure("Work.TFrame", background=THEME["bg"])
    style.configure("Toolbar.TFrame", background=THEME["panel"])
    style.configure("TLabel", background=THEME["bg"], foreground=THEME["text"])
    style.configure("Muted.TLabel", background=THEME["panel"], foreground=THEME["muted"])
    style.configure("Status.TLabel", background=THEME["panel"], foreground=THEME["success"])
    style.configure("TLabelframe", background=THEME["panel"], foreground=THEME["text"], bordercolor=THEME["border"], relief="solid")
    style.configure("TLabelframe.Label", background=THEME["panel"], foreground=THEME["accent"], font=("Segoe UI Semibold", 10))
    style.configure("TButton", background=THEME["panel_2"], foreground=THEME["text"], bordercolor=THEME["border"], focusthickness=1, focuscolor=THEME["accent"], padding=(10, 5))
    style.map("TButton", background=[("active", THEME["panel_3"]), ("pressed", "#0f2742")], foreground=[("active", "#ffffff")])
    style.configure("Accent.TButton", background="#0e7490", foreground="#ecfeff", bordercolor=THEME["accent"], padding=(10, 5))
    style.map("Accent.TButton", background=[("active", "#0891b2"), ("pressed", "#155e75")])
    style.configure("TRadiobutton", background=THEME["panel"], foreground=THEME["text"], indicatorcolor=THEME["entry"], padding=2)
    style.map("TRadiobutton", background=[("active", THEME["panel_2"])], foreground=[("active", "#ffffff")])
    style.configure("TCheckbutton", background=THEME["panel"], foreground=THEME["text"], indicatorcolor=THEME["entry"], padding=2)
    style.map("TCheckbutton", background=[("active", THEME["panel_2"])])
    style.configure("TEntry", fieldbackground=THEME["entry"], foreground=THEME["text"], insertcolor=THEME["accent"], bordercolor=THEME["border"])
    style.configure("TNotebook", background=THEME["panel"], borderwidth=0)
    style.configure("TNotebook.Tab", background=THEME["panel_2"], foreground=THEME["muted"], padding=(10, 6))
    style.map("TNotebook.Tab", background=[("selected", "#102a44"), ("active", THEME["panel_3"])], foreground=[("selected", THEME["accent"]), ("active", THEME["text"])])
    style.configure("Horizontal.TScale", background=THEME["panel"], troughcolor=THEME["entry"], bordercolor=THEME["border"], lightcolor=THEME["accent"], darkcolor=THEME["accent_2"])
    style.configure("Horizontal.TProgressbar", background=THEME["accent"], troughcolor=THEME["entry"], bordercolor=THEME["border"], lightcolor=THEME["accent"], darkcolor=THEME["accent"])
    style.configure("Treeview", background=THEME["entry"], foreground=THEME["text"], fieldbackground=THEME["entry"], bordercolor=THEME["border"], rowheight=24)
    style.configure("Treeview.Heading", background=THEME["panel_2"], foreground=THEME["accent"], font=("Segoe UI Semibold", 10))
    return style


class StarfieldCanvas(tk.Canvas):
    def __init__(self, master, width=270, height=104):
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0, bg=THEME["panel"])
        rng = random.Random(202505)
        self.stars = []
        for _ in range(34):
            self.stars.append({
                "x": rng.randint(4, width - 4),
                "y": rng.randint(4, height - 4),
                "r": rng.choice([1, 1, 1, 2]),
                "phase": rng.random() * 6.28,
                "speed": rng.uniform(0.018, 0.055),
                "tone": rng.choice([THEME["accent"], THEME["accent_2"], "#93c5fd", "#67e8f9"]),
            })
        self.t = 0.0
        self.bind("<Configure>", self._resize)
        self.after(120, self.animate)

    def _resize(self, event):
        self.render()

    def render(self):
        self.delete("all")
        w = max(1, self.winfo_width())
        h = max(1, self.winfo_height())
        bands = ["#07111f", "#0a1630", "#10133a", "#17113a"]
        band_h = max(1, h // len(bands))
        for i, color in enumerate(bands):
            self.create_rectangle(0, i * band_h, w, (i + 1) * band_h + 2, fill=color, outline="")
        for idx, s in enumerate(self.stars):
            x = int((s["x"] / 270) * w)
            y = int((s["y"] / 112) * h)
            pulse = 0.5 + 0.5 * np.sin(self.t * s["speed"] + s["phase"])
            color = s["tone"] if pulse > 0.58 else "#24415f"
            r = s["r"] + (1 if pulse > 0.96 else 0)
            self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")
            if pulse > 0.985 and idx % 11 == 0:
                self.create_line(x - 5, y, x + 5, y, fill=color)
                self.create_line(x, y - 5, x, y + 5, fill=color)
        self.create_text(16, 26, anchor="w", text="NewLight_Analysis", fill="#f8fafc", font=("Segoe UI Semibold", 17))
        self.create_text(16, 54, anchor="w", text="Neurosurgical Imaging Workstation", fill=THEME["accent"], font=("Segoe UI", 9))
        self.create_text(16, 80, anchor="w", text="ROI | Motion | dF/F | Heatmap", fill=THEME["muted"], font=("Segoe UI", 9))

    def animate(self):
        self.t += 1.0
        self.render()
        self.after(260, self.animate)


class ParameterDialog(tk.Toplevel):
    def __init__(self, parent, title, fields):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.values = None
        self.entries = {}
        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        for r, (key, label, default) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=4)
            entry = ttk.Entry(body, width=18)
            entry.insert(0, str(default))
            entry.grid(row=r, column=1, sticky="ew", pady=4, padx=(8, 0))
            self.entries[key] = entry
        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Apply", command=self._apply).grid(row=0, column=1)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _apply(self):
        self.values = {k: e.get() for k, e in self.entries.items()}
        self.destroy()


class NeuroSeg3Dialog(tk.Toplevel):
    def __init__(self, parent, title, weights, default_weight="", default_conf=0.05, mask_threshold=0.5, fallback_default=True):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.values = None
        self.conf_var = tk.DoubleVar(value=float(default_conf))
        self.conf_text = tk.StringVar(value=f"{float(default_conf):.2f}")
        self.weights_var = tk.StringVar(value=default_weight)
        self.fallback_var = tk.BooleanVar(value=bool(fallback_default))
        self._mask_threshold = float(mask_threshold)

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Detection conf").grid(row=0, column=0, sticky="w", pady=4)
        conf_row = ttk.Frame(body)
        conf_row.grid(row=0, column=1, sticky="ew", pady=4)
        conf_row.columnconfigure(0, weight=1)
        self.conf_scale = ttk.Scale(conf_row, from_=0.0, to=1.0, orient="horizontal", variable=self.conf_var, command=self._on_conf_change)
        self.conf_scale.grid(row=0, column=0, sticky="ew")
        ttk.Label(conf_row, textvariable=self.conf_text, width=6, anchor="e").grid(row=0, column=1, padx=(8, 0))

        preset_row = ttk.Frame(body)
        preset_row.grid(row=1, column=1, sticky="w", pady=(0, 6))
        for value in (0.02, 0.05, 0.10, 0.20, 0.35):
            label = f"{value:.2f}".rstrip("0").rstrip(".")
            ttk.Button(preset_row, text=label, width=5, command=lambda v=value: self.set_conf(v)).pack(side="left", padx=(0, 4))

        ttk.Label(body, text="Mask pixel cutoff").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(body, text=f"Fixed at {self._mask_threshold:.2f}", style="Muted.TLabel").grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(body, text="Weights .pt").grid(row=3, column=0, sticky="w", pady=4)
        weight_row = ttk.Frame(body)
        weight_row.grid(row=3, column=1, sticky="ew", pady=4)
        weight_row.columnconfigure(0, weight=1)
        if weights:
            combo = ttk.Combobox(weight_row, textvariable=self.weights_var, values=weights)
            combo.grid(row=0, column=0, sticky="ew")
            combo.bind("<<ComboboxSelected>>", self._sync_weight_var)
            self.weights_combo = combo
        else:
            entry = ttk.Entry(weight_row, textvariable=self.weights_var)
            entry.grid(row=0, column=0, sticky="ew")
            self.weights_entry = entry
        ttk.Button(weight_row, text="Browse", command=self.browse_weights).grid(row=0, column=1, padx=(8, 0))

        ttk.Checkbutton(
            body,
            text="Fallback on zero masks",
            variable=self.fallback_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 4))

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Apply", command=self._apply).grid(row=0, column=1)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._apply())
        self.set_conf(default_conf)
        self.after(0, self._focus_default)
        self.wait_window(self)

    def _focus_default(self):
        if hasattr(self, "weights_combo"):
            self.weights_combo.focus_set()
        elif hasattr(self, "weights_entry"):
            self.weights_entry.focus_set()

    def _on_conf_change(self, value):
        try:
            self.conf_text.set(f"{max(0.0, min(1.0, float(value))):.2f}")
        except Exception:
            self.conf_text.set("0.05")

    def set_conf(self, value):
        value = max(0.0, min(1.0, float(value)))
        self.conf_var.set(value)
        self.conf_text.set(f"{value:.2f}")

    def _sync_weight_var(self, _event=None):
        self.weights_var.set(self.weights_var.get().strip())

    def browse_weights(self):
        initialdir = None
        current = self.weights_var.get().strip()
        if current:
            current_path = Path(current).expanduser()
            if current_path.parent.exists():
                initialdir = str(current_path.parent)
        if initialdir is None:
            weights_dir = core.NEUROSEG3_DIR / "weights"
            if weights_dir.exists():
                initialdir = str(weights_dir)
        options = {
            "parent": self,
            "title": "Select NeuroSeg3 weights",
            "filetypes": [("PyTorch weights", "*.pt"), ("All files", "*.*")],
        }
        if initialdir:
            options["initialdir"] = initialdir
        path = filedialog.askopenfilename(**options)
        if path:
            self.weights_var.set(path)

    def _apply(self):
        self.values = {
            "conf": round(float(self.conf_var.get()), 4),
            "weights": self.weights_var.get(),
            "fallback": bool(self.fallback_var.get()),
            "mask_threshold": self._mask_threshold,
        }
        self.destroy()


class HeatmapVideoDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Generate Heatmap AVI")
        self.geometry("920x680")
        self.configure(bg=THEME["bg"])
        self.cancel_event = threading.Event()
        self.worker = None
        self.alpha = tk.StringVar(value="0.55")
        self.sigma = tk.StringVar(value="1.2")
        self.low = tk.StringVar(value="1")
        self.high = tk.StringVar(value="99")
        self.max_display = tk.StringVar(value="auto")
        self.roi_only = tk.BooleanVar(value=True)
        self.show_colorbar = tk.BooleanVar(value=True)
        self.heatmap_only = tk.BooleanVar(value=False)
        self.frame = tk.IntVar(value=app.current_frame.get())
        self.progress = tk.DoubleVar(value=0)
        self.status = tk.StringVar(value="Ready")
        self.dff = core.compute_dff(app.state.movie, app.state.baseline_image, acceleration=app.acceleration())
        self.mask = None
        self._after_id = None
        self._build_ui()
        self.update_preview()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        fig = Figure(figsize=(7, 5), dpi=100)
        fig.patch.set_facecolor(THEME["bg"])
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.fig = fig
        self.ax = fig.add_subplot(111)
        self.ax.set_facecolor("#020617")
        self.ax.set_axis_off()
        self.canvas = FigureCanvasTkAgg(fig, master=self)
        self.canvas.get_tk_widget().configure(bg=THEME["bg"], highlightthickness=1, highlightbackground=THEME["border"])
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        panel = ttk.Frame(self, padding=8)
        panel.grid(row=0, column=1, sticky="ns")
        panel.columnconfigure(1, weight=1)
        rows = [
            ("Overlay alpha", self.alpha),
            ("Smooth sigma", self.sigma),
            ("Low percentile", self.low),
            ("High percentile", self.high),
            ("Max display", self.max_display),
        ]
        for r, (label, var) in enumerate(rows):
            ttk.Label(panel, text=label).grid(row=r, column=0, sticky="w", pady=3)
            entry = ttk.Entry(panel, textvariable=var, width=12)
            entry.grid(row=r, column=1, sticky="ew", pady=3, padx=(6, 0))
            entry.bind("<KeyRelease>", self.schedule_preview)
        ttk.Checkbutton(panel, text="Show colorbar", variable=self.show_colorbar, command=self.update_preview).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Checkbutton(panel, text="Heatmap only", variable=self.heatmap_only, command=self.update_preview).grid(row=6, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Checkbutton(panel, text="ROI only", variable=self.roi_only, command=self.update_preview).grid(row=7, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(panel, text="Preview frame").grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 2))
        self.frame_scale = ttk.Scale(panel, from_=0, to=self.app.state.movie.shape[0] - 1, orient="horizontal", command=self.on_frame_change)
        self.frame_scale.set(self.frame.get())
        self.frame_scale.grid(row=9, column=0, columnspan=2, sticky="ew")
        self.frame_label = ttk.Label(panel, text="")
        self.frame_label.grid(row=10, column=0, columnspan=2, sticky="w")
        ttk.Button(panel, text="Refresh Preview", command=self.update_preview).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(12, 3))
        ttk.Button(panel, text="Save AVI", command=self.start_save).grid(row=12, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(panel, text="Cancel Generation", command=self.cancel_generation).grid(row=13, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Progressbar(panel, variable=self.progress, maximum=100).grid(row=14, column=0, columnspan=2, sticky="ew", pady=(12, 3))
        ttk.Label(panel, textvariable=self.status, wraplength=210).grid(row=15, column=0, columnspan=2, sticky="ew")

    def schedule_preview(self, event=None):
        if self._after_id is not None:
            self.after_cancel(self._after_id)
        self._after_id = self.after(250, self.update_preview)

    def params(self):
        low = float(self.low.get())
        high = float(self.high.get())
        if high <= low:
            high = low + 1
        max_display = core.parse_optional_float(self.max_display.get())
        return float(self.alpha.get()), float(self.sigma.get()), low, high, max_display

    def current_mask(self):
        return self.app.heatmap_mask(use_roi=self.roi_only.get())

    def on_frame_change(self, value):
        frame = int(round(float(value)))
        self.frame.set(frame)
        self.app.current_frame.set(frame)
        self.app.show_frame(frame)
        self.update_preview()

    def update_preview(self):
        self._after_id = None
        try:
            frame = min(max(0, self.frame.get()), self.app.state.movie.shape[0] - 1)
            self.frame_label.configure(text=f"Frame {frame + 1}/{self.app.state.movie.shape[0]}")
            alpha, sigma, low, high, max_display = self.params()
            mask = self.current_mask()
            vmin, vmax = core.heatmap_limits(self.dff, low, high, max_display=max_display)
            preview = core.render_heatmap_frame_rgb(
                self.dff[frame],
                self.app.state.movie[frame],
                mask,
                vmin,
                vmax,
                alpha,
                sigma,
                show_colorbar=self.show_colorbar.get(),
                heatmap_only=self.heatmap_only.get(),
            )
            self.ax.clear()
            self.ax.set_axis_off()
            self.ax.set_facecolor("#020617")
            self.ax.imshow(preview, interpolation="nearest", origin="upper")
            self.ax.set_aspect("equal", adjustable="box")
            self.canvas.draw_idle()
            self.status.set("Preview updated")
        except Exception as exc:
            self.status.set(f"Preview failed: {exc}")

    def start_save(self):
        if self.worker and self.worker.is_alive():
            return
        path = filedialog.asksaveasfilename(defaultextension=".avi", filetypes=[("AVI video", "*.avi")])
        if not path:
            return
        self.cancel_event.clear()
        try:
            alpha, sigma, low, high, max_display = self.params()
        except Exception as exc:
            messagebox.showerror("Heatmap AVI", f"Invalid heatmap parameters: {exc}")
            return
        mask = self.current_mask()
        self.progress.set(0)
        self.status.set("Generating AVI...")

        def progress(done, total):
            self.app.worker_queue.put((lambda result: self.on_progress(*result), (done, total), None))

        def target():
            try:
                completed = core.save_heatmap_video(
                    path,
                    self.dff,
                    self.app.state.movie,
                    mask,
                    self.app.state.fs,
                    alpha=alpha,
                    sigma=sigma,
                    low_percentile=low,
                    high_percentile=high,
                    max_display=max_display,
                    show_colorbar=self.show_colorbar.get(),
                    heatmap_only=self.heatmap_only.get(),
                    cancel_event=self.cancel_event,
                    progress_callback=progress,
                )
                self.app.worker_queue.put((lambda result: self.on_done(*result), (path, completed), None))
            except Exception as exc:
                self.app.worker_queue.put((None, None, exc))

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def on_progress(self, done, total):
        self.progress.set(100 * done / max(1, total))
        self.status.set(f"Generating {done}/{total}")

    def on_done(self, path, completed):
        if completed:
            self.progress.set(100)
            self.status.set(f"Saved: {path}")
            self.app.log(f"Heatmap AVI saved: {path}")
        else:
            self.status.set("Generation cancelled")
            self.app.log("Heatmap AVI generation cancelled.")

    def cancel_generation(self):
        self.cancel_event.set()
        self.status.set("Cancelling...")


class NewLightApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NewLight_Analysis")
        icon_path = Path(__file__).resolve().parent / "xhr.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass
        self.root.geometry("1440x920")
        self.state = core.AnalysisState()
        self.mode = tk.StringVar(value="inspect")
        self.projection_mode = tk.StringVar(value="mean")
        self.status = tk.StringVar(value="Ready")
        self.worker_queue = queue.Queue()
        self.current_polygon = []
        self.freehand_drawing = False
        self.circle_start = None
        self.inspect_pan_start = None
        self.preview_overlay = None
        self.current_frame = tk.IntVar(value=0)
        self.frame_label_var = tk.StringVar(value="Frame 1/1")
        self.fs_var = tk.StringVar(value="10")
        self.stim_fs_var = tk.StringVar(value="2000")
        self.baseline_start_var = tk.StringVar(value="0")
        self.baseline_duration_var = tk.StringVar(value="0")
        self.trigger_threshold_var = tk.StringVar(value="0")
        self.trigger_start_var = tk.StringVar(value="0")
        self.trigger_interval_var = tk.StringVar(value="0")
        self.pre_trigger_var = tk.StringVar(value="0")
        self.post_trigger_var = tk.StringVar(value="0")
        self.trace_baseline_correct_var = tk.BooleanVar(value=True)
        self.trace_baseline_window_var = tk.StringVar(value="30")
        self.trace_smooth_window_var = tk.StringVar(value="1")
        self.acceleration_var = tk.StringVar(value="auto")
        self._view_limits = None
        self._view_is_fit = True
        self._view_lock = False
        self._setting_frame_scale = False
        self._build_ui()
        self._poll_worker()
        self.root.after(600, self.check_cuda_status_quick)

    def _build_ui(self):
        self.root.configure(bg=THEME["bg"])
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        side = ttk.Frame(self.root, padding=10, style="Sidebar.TFrame")
        side.grid(row=0, column=0, sticky="ns")
        side.columnconfigure(0, weight=1)

        StarfieldCanvas(side).grid(row=0, column=0, sticky="ew", pady=(0, 12))

        tabs = ttk.Notebook(side)
        tabs.grid(row=1, column=0, sticky="nsew")
        flow_tab = ttk.Frame(tabs, padding=4)
        pre_tab = ttk.Frame(tabs, padding=4)
        roi_tab = ttk.Frame(tabs, padding=4)
        analysis_tab = ttk.Frame(tabs, padding=4)
        tabs.add(flow_tab, text="Data")
        tabs.add(pre_tab, text="Preprocess")
        tabs.add(roi_tab, text="ROI")
        tabs.add(analysis_tab, text="Analysis")
        for tab in (flow_tab, pre_tab, roi_tab, analysis_tab):
            tab.columnconfigure(0, weight=1)

        file_box = ttk.LabelFrame(flow_tab, text="Data", padding=8)
        file_box.grid(row=0, column=0, sticky="ew", pady=6)
        ttk.Button(file_box, text="Open Movie", command=self.open_movie).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(file_box, text="Open Stimulus", command=self.open_stimulus).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(file_box, text="Save Current Movie", command=self.save_current_movie).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(file_box, text="Export Analysis", command=self.export_analysis).grid(row=3, column=0, sticky="ew", pady=2)

        view_box = ttk.LabelFrame(flow_tab, text="View", padding=8)
        view_box.grid(row=1, column=0, sticky="ew", pady=6)
        for i, (text, value) in enumerate([("Mean", "mean"), ("Max", "max"), ("Std", "std"), ("Corr", "corr")]):
            ttk.Radiobutton(view_box, text=text, variable=self.projection_mode, value=value, command=self.refresh_projection).grid(row=i // 2, column=i % 2, sticky="w")
        ttk.Button(view_box, text="Show dF/F Heatmap", command=self.show_dff_heatmap).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        protocol_box = ttk.LabelFrame(flow_tab, text="Protocol", padding=8)
        protocol_box.grid(row=2, column=0, sticky="ew", pady=6)
        protocol_box.columnconfigure(1, weight=1)
        protocol_rows = [
            ("Movie Hz", self.fs_var),
            ("Stim Hz", self.stim_fs_var),
            ("Base start s", self.baseline_start_var),
            ("Base dur s", self.baseline_duration_var),
            ("Trig threshold", self.trigger_threshold_var),
            ("Trig start s", self.trigger_start_var),
            ("Trig interval s", self.trigger_interval_var),
            ("Pre s", self.pre_trigger_var),
            ("Post s", self.post_trigger_var),
        ]
        for r, (label, var) in enumerate(protocol_rows):
            ttk.Label(protocol_box, text=label).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Entry(protocol_box, textvariable=var, width=10).grid(row=r, column=1, sticky="ew", pady=1, padx=(6, 0))
        ttk.Button(protocol_box, text="Apply Protocol", command=self.apply_protocol).grid(row=len(protocol_rows), column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Button(protocol_box, text="Detect Triggers", command=self.detect_triggers).grid(row=len(protocol_rows) + 1, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(protocol_box, text="Trial Average", command=self.show_trial_average).grid(row=len(protocol_rows) + 2, column=0, columnspan=2, sticky="ew", pady=2)

        pre_box = ttk.LabelFrame(pre_tab, text="Preprocessing", padding=8)
        pre_box.grid(row=0, column=0, sticky="ew", pady=6)
        accel_box = ttk.LabelFrame(pre_tab, text="Acceleration", padding=8)
        accel_box.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Radiobutton(accel_box, text="Auto", variable=self.acceleration_var, value="auto").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(accel_box, text="CPU", variable=self.acceleration_var, value="cpu").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(accel_box, text="GPU", variable=self.acceleration_var, value="gpu").grid(row=0, column=2, sticky="w")
        ttk.Button(accel_box, text="Check CUDA", command=self.check_cuda_status).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        buttons = [
            ("CaImAn Motion", self.caiman_motion),
            ("Rigid Motion (Built-in)", self.builtin_motion),
            ("Gaussian Smooth", self.gaussian_smooth),
            ("Median Filter", self.median_filter),
            ("Background Subtract", self.background_subtract),
            ("Bleach Correction", self.bleach_correct),
            ("Enhance Contrast", self.enhance_contrast),
            ("Detect Vessels", self.detect_vessels),
            ("Remove Vessel Artifact", self.remove_vessels),
        ]
        for i, (label, command) in enumerate(buttons):
            ttk.Button(pre_box, text=label, command=command).grid(row=i, column=0, sticky="ew", pady=2)

        roi_box = ttk.LabelFrame(roi_tab, text="ROI", padding=8)
        roi_box.grid(row=0, column=0, sticky="ew", pady=6)
        ttk.Button(roi_box, text="NeuroSeg3 Auto ROI", command=self.neuroseg3_roi).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Built-in Auto ROI", command=self.auto_roi).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Atlas Image ROI", command=self.atlas_roi).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Load ROI .npz", command=self.load_roi).grid(row=3, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Save ROI .npz", command=self.save_roi).grid(row=4, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Clear ROIs", command=self.clear_rois).grid(row=5, column=0, sticky="ew", pady=2)

        analysis_box = ttk.LabelFrame(analysis_tab, text="Analysis", padding=8)
        analysis_box.grid(row=0, column=0, sticky="ew", pady=6)
        ttk.Button(analysis_box, text="Extract dF/F Traces", command=self.extract_traces).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="Peak Detection", command=self.peak_detection).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="ROI Correlation", command=self.roi_correlation).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="ROI Statistics", command=self.show_roi_statistics).grid(row=3, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="Generate Heatmap AVI", command=self.generate_heatmap_avi).grid(row=4, column=0, sticky="ew", pady=2)
        trace_box = ttk.LabelFrame(analysis_tab, text="dF/F Options", padding=8)
        trace_box.grid(row=1, column=0, sticky="ew", pady=6)
        trace_box.columnconfigure(1, weight=1)
        ttk.Checkbutton(trace_box, text="Baseline correction", variable=self.trace_baseline_correct_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(trace_box, text="Baseline view").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(trace_box, textvariable=self.trace_baseline_window_var, width=10).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=2)
        ttk.Label(trace_box, text="Moving avg").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(trace_box, textvariable=self.trace_smooth_window_var, width=10).grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=2)

        main = ttk.Frame(self.root, padding=(0, 10, 10, 10), style="Work.TFrame")
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(0, weight=1)
        self.fig = Figure(figsize=(8, 6), dpi=100)
        self.fig.patch.set_facecolor("#020617")
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#020617")
        self.ax.set_position([0, 0, 1, 1])
        self.ax.set_anchor("C")
        self.ax.set_axis_off()
        self.ax.callbacks.connect("xlim_changed", self._on_axes_limits_changed)
        self.ax.callbacks.connect("ylim_changed", self._on_axes_limits_changed)
        self.canvas = FigureCanvasTkAgg(self.fig, master=main)
        self.canvas.get_tk_widget().configure(bg="#020617", highlightthickness=1, highlightbackground=THEME["border"])
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self.canvas.mpl_connect("resize_event", self.on_canvas_resize)
        self.nav_toolbar = ImageToolbar(self.canvas, main, pack_toolbar=False)
        self.nav_toolbar.configure(background=THEME["panel"])
        for child in self.nav_toolbar.winfo_children():
            try:
                child.configure(background=THEME["panel"])
            except tk.TclError:
                pass
        self.nav_toolbar.update()
        self.nav_toolbar.grid(row=1, column=0, sticky="ew")

        bottom = ttk.Frame(main, style="Toolbar.TFrame")
        bottom.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        bottom.columnconfigure(9, weight=1)
        ttk.Button(bottom, text="Undo", command=self.undo).grid(row=0, column=0, padx=3)
        ttk.Radiobutton(bottom, text="Inspect", variable=self.mode, value="inspect").grid(row=0, column=1, padx=3)
        ttk.Radiobutton(bottom, text="Circle ROI", variable=self.mode, value="circle").grid(row=0, column=2, padx=3)
        ttk.Radiobutton(bottom, text="Freehand ROI", variable=self.mode, value="freehand").grid(row=0, column=3, padx=3)
        ttk.Radiobutton(bottom, text="Delete ROI", variable=self.mode, value="delete_roi").grid(row=0, column=4, padx=3)
        ttk.Button(bottom, text="Cancel Freehand", command=self.cancel_freehand).grid(row=0, column=5, padx=3)
        ttk.Button(bottom, text="Delete Last ROI", command=self.delete_last_roi).grid(row=0, column=6, padx=3)
        ttk.Label(bottom, textvariable=self.status).grid(row=0, column=9, sticky="e")

        frame_bar = ttk.Frame(main, style="Toolbar.TFrame")
        frame_bar.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        frame_bar.columnconfigure(1, weight=1)
        ttk.Label(frame_bar, text="Frame").grid(row=0, column=0, padx=(0, 6))
        self.frame_scale = ttk.Scale(frame_bar, from_=0, to=0, orient="horizontal", command=self.on_frame_slider)
        self.frame_scale.grid(row=0, column=1, sticky="ew")
        ttk.Label(frame_bar, textvariable=self.frame_label_var, width=14).grid(row=0, column=2, padx=(6, 0))

        log_box = ttk.LabelFrame(main, text="Run Log", padding=4)
        log_box.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        self.log_text = tk.Text(log_box, height=7, wrap="word")
        self.log_text.configure(bg=THEME["entry"], fg=THEME["text"], insertbackground=THEME["accent"], relief="flat", highlightthickness=1, highlightbackground=THEME["border"])
        self.log_text.pack(fill="both", expand=True)

        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)

    def on_canvas_resize(self, event):
        if self.state.display_image is not None or self.state.baseline_image is not None:
            self.redraw(preserve_view=True)
        else:
            self.canvas.draw_idle()

    def update_frame_controls(self):
        if self.state.movie is None:
            self.frame_scale.configure(from_=0, to=0)
            self.current_frame.set(0)
            self.frame_label_var.set("Frame 1/1")
            return
        last = max(0, self.state.movie.shape[0] - 1)
        self.frame_scale.configure(from_=0, to=last)
        frame = min(max(0, int(self.current_frame.get())), last)
        self._setting_frame_scale = True
        try:
            self.current_frame.set(frame)
            self.frame_scale.set(frame)
            self.frame_label_var.set(f"Frame {frame + 1}/{last + 1}")
        finally:
            self._setting_frame_scale = False

    def on_frame_slider(self, value):
        if self._setting_frame_scale:
            return
        if self.state.movie is None:
            return
        frame = int(round(float(value)))
        frame = min(max(0, frame), self.state.movie.shape[0] - 1)
        if frame == self.current_frame.get():
            self.frame_label_var.set(f"Frame {frame + 1}/{self.state.movie.shape[0]}")
            return
        self.current_frame.set(frame)
        self.frame_label_var.set(f"Frame {frame + 1}/{self.state.movie.shape[0]}")
        self.show_frame(frame)

    def show_frame(self, frame=None):
        if not self.require_movie():
            return
        if frame is None:
            frame = self.current_frame.get()
        frame = min(max(0, int(frame)), self.state.movie.shape[0] - 1)
        self.current_frame.set(frame)
        self.frame_label_var.set(f"Frame {frame + 1}/{self.state.movie.shape[0]}")
        self.state.display_image = self.state.movie[frame]
        self.redraw()

    def fit_view(self):
        if self.state.display_image is None and self.state.baseline_image is None:
            return
        self._view_limits = None
        self._view_is_fit = True
        self.redraw(preserve_view=False)
        self.log("Image fitted to canvas.")

    def apply_view_limits(self, view_limits):
        img = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        view_limits = self._sanitize_view_limits(view_limits, img.shape if img is not None else None)
        if view_limits is None:
            return
        self._view_limits = view_limits
        self._view_is_fit = False
        self._view_lock = True
        try:
            self.ax.set_xlim(*view_limits[0])
            self.ax.set_ylim(*view_limits[1])
        finally:
            self._view_lock = False
        self.canvas.draw_idle()

    def zoom_view(self, scale):
        if self.state.display_image is None:
            return
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        x = (xlim[0] + xlim[1]) / 2.0
        y = (ylim[0] + ylim[1]) / 2.0
        new_xlim = (x - (x - xlim[0]) * scale, x + (xlim[1] - x) * scale)
        new_ylim = (y - (y - ylim[0]) * scale, y + (ylim[1] - y) * scale)
        self.apply_view_limits((new_xlim, new_ylim))

    def log(self, text):
        stamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{stamp}] {text}\n")
        self.log_text.see("end")
        self.status.set(text)
        self.root.update_idletasks()

    def acceleration(self):
        return self.acceleration_var.get()

    def check_cuda_status_quick(self):
        self.log(f"Acceleration backend: {core.acceleration_label(self.acceleration())}")

    def check_cuda_status(self):
        try:
            status = core.cuda_status(check_neuroseg3=True)
            lines = [
                f"Main dF/F GPU (CuPy): {'YES' if status['cupy_available'] else 'NO'} {status['cupy_device']}",
                f"Main Python torch CUDA: {'YES' if status['torch_cuda_available'] else 'NO'} {status['torch_device']}",
                f"OpenCV CUDA devices: {status['opencv_cuda_devices']}",
                f"NeuroSeg3 CUDA: {'YES' if status['neuroseg3_cuda_available'] else 'NO'} {status['neuroseg3_device']}",
            ]
            message = "\n".join(lines)
            self.log(message.replace("\n", " | "))
            messagebox.showinfo("CUDA Status", message)
        except Exception as exc:
            messagebox.showerror("CUDA Status", str(exc))

    def require_movie(self):
        if self.state.movie is None:
            messagebox.showwarning("No movie", "Please open a movie first.")
            return False
        return True

    def push_history(self, label):
        if self.state.movie is not None:
            self.state.history.append((label, self.state.movie.copy()))
            if len(self.state.history) > 12:
                self.state.history.pop(0)

    def sync_roi_names(self):
        self.state.roi_names = [f"ROI{i + 1}" for i in range(len(self.state.roi_masks))]

    def set_rois(self, masks, source="ROI", names=None):
        self.state.roi_masks = [m.astype(bool) for m in masks]
        if names is not None and len(names) == len(self.state.roi_masks):
            self.state.roi_names = [str(name) for name in names]
        else:
            self.sync_roi_names()
        self.state.traces = None
        self.redraw()
        if self.state.roi_masks:
            if names is not None and len(names) == len(self.state.roi_masks):
                self.log(f"{source}: {len(self.state.roi_masks)} ROIs loaded with names preserved.")
            else:
                self.log(f"{source}: {len(self.state.roi_masks)} ROIs, renumbered ROI1-ROI{len(self.state.roi_masks)}.")
        else:
            self.log(f"{source}: 0 ROIs.")

    def mark_rois_changed(self):
        self.sync_roi_names()
        self.state.traces = None

    def undo(self):
        if not self.state.history:
            self.log("Nothing to undo.")
            return
        label, movie = self.state.history.pop()
        self.state.movie = movie
        self.state.baseline_image = core.baseline_from_seconds(
            movie,
            self.state.fs,
            self.state.baseline_start_s,
            self.state.baseline_duration_s,
        )
        self.update_frame_controls()
        self.refresh_projection()
        self.log(f"Undone: {label}")

    def open_movie(self):
        path = filedialog.askopenfilename(filetypes=[("Movies", "*.tif *.tiff *.avi *.mp4 *.mov *.mkv"), ("All files", "*.*")])
        if not path:
            return
        try:
            movie, fs = core.load_movie(path)
            self.state = core.AnalysisState(movie=movie, fs=fs, source_path=path)
            self.fs_var.set(f"{fs:.6g}")
            self.apply_protocol(update_baseline=False)
            self.state.baseline_image = core.baseline_from_seconds(
                movie,
                self.state.fs,
                self.state.baseline_start_s,
                self.state.baseline_duration_s,
            )
            self.refresh_projection(preserve_view=False)
            self.update_frame_controls()
            self.log(f"Loaded {Path(path).name}: {movie.shape}, fs={fs:.3g}")
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))

    def open_stimulus(self):
        path = filedialog.askopenfilename(filetypes=[("Stimulus", "*.txt *.csv *.dat"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.state.stimulus = core.read_stimulus_file(path)
            self.log(f"Loaded stimulus {Path(path).name}: {self.state.stimulus.size} points")
        except Exception as exc:
            messagebox.showerror("Stimulus open failed", str(exc))

    def apply_protocol(self, update_baseline=True):
        try:
            self.state.fs = float(self.fs_var.get())
            self.state.stimulus_fs = float(self.stim_fs_var.get())
            self.state.baseline_start_s = float(self.baseline_start_var.get())
            self.state.baseline_duration_s = float(self.baseline_duration_var.get())
            self.state.pre_trigger_s = float(self.pre_trigger_var.get())
            self.state.post_trigger_s = float(self.post_trigger_var.get())
            if update_baseline and self.state.movie is not None:
                self.state.baseline_image = core.baseline_from_seconds(
                    self.state.movie,
                    self.state.fs,
                    self.state.baseline_start_s,
                    self.state.baseline_duration_s,
                )
                self.refresh_projection(preserve_view=False)
            self.log("Protocol parameters applied.")
        except Exception as exc:
            messagebox.showerror("Protocol failed", str(exc))

    def detect_triggers(self):
        if not self.require_movie():
            return
        self.apply_protocol(update_baseline=False)
        try:
            interval = float(self.trigger_interval_var.get())
            start = float(self.trigger_start_var.get())
            if interval > 0:
                frames = core.generate_interval_triggers(
                    start,
                    interval,
                    self.state.fs,
                    self.state.movie.shape[0],
                    self.state.pre_trigger_s,
                    self.state.post_trigger_s,
                )
            elif self.state.stimulus is not None:
                samples = core.detect_stimulus_triggers(
                    self.state.stimulus,
                    self.state.stimulus_fs,
                    threshold=float(self.trigger_threshold_var.get()),
                )
                frames = core.map_stimulus_triggers_to_frames(
                    samples,
                    self.state.stimulus_fs,
                    self.state.fs,
                    self.state.movie.shape[0],
                    self.state.pre_trigger_s,
                    self.state.post_trigger_s,
                )
            else:
                self.log("No stimulus loaded and interval is 0.")
                return
            self.state.trigger_frames = frames.astype(int)
            self.redraw()
            self.log(f"Detected {len(frames)} valid triggers.")
        except Exception as exc:
            messagebox.showerror("Trigger detection failed", str(exc))

    def refresh_projection(self, preserve_view=False):
        if not self.require_movie():
            return
        img = core.compute_projection(self.state.movie, self.projection_mode.get(), acceleration=self.acceleration())
        self.state.display_image = img
        if not preserve_view:
            self._view_limits = None
            self._view_is_fit = True
        self.redraw(preserve_view=preserve_view)

    def _on_axes_limits_changed(self, axes):
        if self._view_lock or self.state.display_image is None:
            return
        try:
            self._view_limits = (tuple(self.ax.get_xlim()), tuple(self.ax.get_ylim()))
            self._view_is_fit = False
        except Exception:
            pass

    def _full_image_limits(self, image_shape):
        h, w = image_shape[:2]
        return (-0.5, w - 0.5), (h - 0.5, -0.5)

    def _image_axes_position(self, image_shape):
        if self.canvas is None or image_shape is None:
            return [0, 0, 1, 1]
        h, w = image_shape[:2]
        canvas_widget = self.canvas.get_tk_widget()
        cw = max(1, int(canvas_widget.winfo_width()))
        ch = max(1, int(canvas_widget.winfo_height()))
        if cw <= 1 or ch <= 1 or h <= 0 or w <= 0:
            return [0, 0, 1, 1]
        canvas_ratio = cw / ch
        image_ratio = w / h
        if canvas_ratio >= image_ratio:
            width = image_ratio / canvas_ratio
            return [(1.0 - width) / 2.0, 0, width, 1]
        height = canvas_ratio / image_ratio
        return [0, (1.0 - height) / 2.0, 1, height]

    def _view_axes_shape(self, image_shape, view_limits=None):
        if view_limits is None:
            return image_shape
        xlim, ylim = view_limits
        width = abs(float(xlim[1]) - float(xlim[0]))
        height = abs(float(ylim[1]) - float(ylim[0]))
        if width <= 0 or height <= 0:
            return image_shape
        return (height, width)

    def _sanitize_view_limits(self, view_limits, image_shape):
        if view_limits is None or image_shape is None:
            return None
        xlim, ylim = view_limits
        h, w = image_shape[:2]

        def clamp_span(a, b, low, high):
            if a > b:
                lo, hi = b, a
                flipped = True
            else:
                lo, hi = a, b
                flipped = False
            span = hi - lo
            full = high - low
            if span >= full:
                lo, hi = low, high
            else:
                if lo < low:
                    hi += low - lo
                    lo = low
                if hi > high:
                    lo -= hi - high
                    hi = high
                lo = max(low, lo)
                hi = min(high, hi)
            if hi <= lo:
                lo, hi = low, high
            return (hi, lo) if flipped else (lo, hi)

        xlim = clamp_span(float(xlim[0]), float(xlim[1]), -0.5, w - 0.5)
        ylim = clamp_span(float(ylim[0]), float(ylim[1]), -0.5, h - 0.5)
        return xlim, ylim

    def _restore_view_limits(self, view_limits, image_shape):
        view_limits = self._sanitize_view_limits(view_limits, image_shape)
        if view_limits is None:
            return
        self.ax.set_xlim(*view_limits[0])
        self.ax.set_ylim(*view_limits[1])

    def _apply_image_axes(self, image_shape, view_limits=None):
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
        self.ax.set_position(self._image_axes_position(self._view_axes_shape(image_shape, view_limits)), which="both")
        self.ax.set_anchor("C")

    def redraw(self, extra=None, preserve_view=True):
        if preserve_view and self._view_limits is not None and not self._view_is_fit:
            view_limits = self._sanitize_view_limits(self._view_limits, self.state.display_image.shape if self.state.display_image is not None else None)
        else:
            view_limits = None
        self.ax.clear()
        self.ax.set_axis_off()
        self.ax.set_facecolor("#020617")
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=0, hspace=0)
        img = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        if img is not None:
            h, w = img.shape[:2]
            if view_limits is None:
                view_limits = self._full_image_limits(img.shape)
                self._view_limits = view_limits
                self._view_is_fit = True
            overlay = core.draw_roi_overlay(img, self.state.roi_masks, self.state.roi_names)
            self._view_lock = True
            try:
                self._apply_image_axes(img.shape, view_limits)
                self.ax.imshow(img, cmap="gray", interpolation="nearest", origin="upper", aspect="auto")
                if self.state.roi_masks:
                    self.ax.imshow(overlay, alpha=0.55, interpolation="nearest", origin="upper", aspect="auto")
                self.ax.set_aspect("auto")
                self.ax.set_xlim(*view_limits[0])
                self.ax.set_ylim(*view_limits[1])
            finally:
                self._view_lock = False
        if extra is not None:
            self.ax.imshow(extra, alpha=0.55, interpolation="nearest", origin="upper", aspect="auto")
        if self.current_polygon:
            xs, ys = zip(*self.current_polygon)
            self.ax.plot(xs, ys, color="cyan", linewidth=1.5)
            if len(self.current_polygon) >= 3 and not self.freehand_drawing:
                self.ax.plot([xs[-1], xs[0]], [ys[-1], ys[0]], color="cyan", linewidth=1.0, linestyle="--")
        self.canvas.draw_idle()

    def on_press(self, event):
        if event.inaxes != self.ax or self.state.display_image is None:
            return
        if self.mode.get() == "inspect" and event.xdata is not None and event.ydata is not None and event.button == 1:
            self.inspect_pan_start = (event.xdata, event.ydata, tuple(self.ax.get_xlim()), tuple(self.ax.get_ylim()))
        elif self.mode.get() == "circle":
            self.circle_start = (event.xdata, event.ydata)
        elif self.mode.get() == "freehand":
            if self.freehand_drawing:
                if event.xdata is not None and event.ydata is not None:
                    self.current_polygon.append((event.xdata, event.ydata))
                self.finish_freehand()
            else:
                self.current_polygon = [(event.xdata, event.ydata)]
                self.freehand_drawing = True
                self.log("Freehand drawing started; move mouse to draw, click again to confirm.")
        elif self.mode.get() == "delete_roi":
            self.delete_roi_at(event.xdata, event.ydata)

    def on_motion(self, event):
        if event.inaxes != self.ax:
            return
        if self.mode.get() == "inspect" and self.inspect_pan_start and event.xdata is not None and event.ydata is not None:
            start_x, start_y, xlim, ylim = self.inspect_pan_start
            dx = event.xdata - start_x
            dy = event.ydata - start_y
            self.apply_view_limits(((xlim[0] - dx, xlim[1] - dx), (ylim[0] - dy, ylim[1] - dy)))
        elif self.mode.get() == "freehand" and self.freehand_drawing and self.current_polygon and event.xdata is not None and event.ydata is not None:
            self.current_polygon.append((event.xdata, event.ydata))
            self.redraw()

    def on_release(self, event):
        if self.inspect_pan_start is not None:
            self.inspect_pan_start = None
            return
        if event.inaxes != self.ax or self.state.display_image is None:
            return
        if self.mode.get() == "circle" and self.circle_start:
            cx, cy = self.circle_start
            radius = ((event.xdata - cx) ** 2 + (event.ydata - cy) ** 2) ** 0.5
            if radius > 1:
                mask = core.circle_mask(self.state.display_image.shape, (cx, cy), radius)
                self.add_roi(mask, "Circle")
            self.circle_start = None

    def on_scroll(self, event):
        if event.inaxes != self.ax or self.state.display_image is None or event.xdata is None or event.ydata is None:
            return
        scale = 0.8 if event.button == "up" else 1.25
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        x = event.xdata
        y = event.ydata
        new_xlim = (x - (x - xlim[0]) * scale, x + (xlim[1] - x) * scale)
        new_ylim = (y - (y - ylim[0]) * scale, y + (ylim[1] - y) * scale)
        self.apply_view_limits((new_xlim, new_ylim))

    def finish_freehand(self):
        if self.state.display_image is None or len(self.current_polygon) < 3:
            self.log("Freehand ROI needs at least 3 points.")
            return
        mask = core.polygon_mask(self.state.display_image.shape, self.current_polygon)
        self.current_polygon = []
        self.freehand_drawing = False
        self.add_roi(mask, "Freehand")

    def cancel_freehand(self):
        self.current_polygon = []
        self.freehand_drawing = False
        self.redraw()
        self.log("Freehand ROI cancelled.")

    def add_roi(self, mask, prefix):
        if mask is None or not np.any(mask):
            self.log("Empty ROI ignored.")
            return
        self.state.roi_masks.append(mask.astype(bool))
        self.mark_rois_changed()
        self.redraw()
        self.log(f"Added ROI, total={len(self.state.roi_masks)}, renumbered ROI1-ROI{len(self.state.roi_masks)}.")

    def delete_last_roi(self):
        if self.state.roi_masks:
            idx = len(self.state.roi_masks)
            self.state.roi_masks.pop()
            self.mark_rois_changed()
            self.redraw()
            self.log(f"Deleted ROI{idx}; remaining ROIs renumbered.")

    def delete_roi_at(self, x, y):
        if x is None or y is None or not self.state.roi_masks:
            self.log("No ROI at clicked position.")
            return
        row = int(round(y))
        col = int(round(x))
        hit = None
        for i in range(len(self.state.roi_masks) - 1, -1, -1):
            mask = self.state.roi_masks[i]
            if 0 <= row < mask.shape[0] and 0 <= col < mask.shape[1] and mask[row, col]:
                hit = i
                break
        if hit is None:
            self.log("No ROI at clicked position.")
            return
        self.state.roi_masks.pop(hit)
        deleted = hit + 1
        self.mark_rois_changed()
        self.redraw()
        self.log(f"Deleted ROI{deleted} by click; remaining ROIs renumbered.")

    def clear_rois(self):
        self.state.roi_masks = []
        self.state.roi_names = []
        self.state.traces = None
        self.redraw()
        self.log("ROIs cleared.")

    def load_roi(self):
        if not self.require_movie():
            return
        path = filedialog.askopenfilename(
            filetypes=[
                ("ROI or atlas", "*.npz *.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("ROI npz", "*.npz"),
                ("Atlas image", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ]
        )
        if not path:
            return
        try:
            ext = Path(path).suffix.lower()
            if ext == ".npz":
                with np.load(path, allow_pickle=True) as data:
                    masks = [m.astype(bool) for m in data["masks"]]
                    names = list(data["names"]) if "names" in data else None
                self.set_rois(masks, "Loaded ROI file", names=names)
            elif ext in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
                vals = self.param_dialog("Atlas Image ROI", [("min_area", "Min area", 50)])
                if not vals:
                    return
                rois, names = core.process_atlas_image(path, self.state.baseline_image.shape, int(vals["min_area"]))
                self.set_rois(rois, "Loaded atlas image", names=names)
            else:
                raise ValueError(f"Unsupported ROI file type: {ext}")
        except Exception as exc:
            messagebox.showerror("Load ROI failed", str(exc))

    def atlas_roi(self):
        if not self.require_movie():
            return
        path = filedialog.askopenfilename(
            filetypes=[("Atlas image", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("All files", "*.*")]
        )
        if not path:
            return
        vals = self.param_dialog("Atlas Image ROI", [("min_area", "Min area", 50)])
        if not vals:
            return
        try:
            rois, names = core.process_atlas_image(path, self.state.baseline_image.shape, int(vals["min_area"]))
            self.set_rois(rois, "Atlas ROI", names=names)
        except Exception as exc:
            messagebox.showerror("Atlas ROI failed", str(exc))

    def save_roi(self):
        if not self.state.roi_masks:
            self.log("No ROIs to save.")
            return
        if len(self.state.roi_names) != len(self.state.roi_masks):
            self.sync_roi_names()
        path = filedialog.asksaveasfilename(defaultextension=".npz", filetypes=[("ROI npz", "*.npz")])
        if not path:
            return
        np.savez_compressed(path, masks=np.stack(self.state.roi_masks).astype(bool), names=np.array(self.state.roi_names))
        self.log(f"Saved ROIs: {path}")

    def save_current_movie(self):
        if not self.require_movie():
            return
        path = filedialog.asksaveasfilename(defaultextension=".tif", filetypes=[("TIFF", "*.tif")])
        if path:
            core.save_movie_tiff(self.state.movie, path)
            self.log(f"Saved movie: {path}")

    def param_dialog(self, title, fields):
        dlg = ParameterDialog(self.root, title, fields)
        return dlg.values

    def apply_movie_operation(self, label, func):
        if not self.require_movie():
            return
        try:
            self.apply_protocol(update_baseline=False)
            self.push_history(label)
            self.state.movie = func(self.state.movie)
            self.state.baseline_image = core.baseline_from_seconds(
                self.state.movie,
                self.state.fs,
                self.state.baseline_start_s,
                self.state.baseline_duration_s,
            )
            self.update_frame_controls()
            self.refresh_projection(preserve_view=False)
            self.log(f"Applied: {label}")
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror(label, str(exc))

    def gaussian_smooth(self):
        vals = self.param_dialog("Gaussian Smooth", [("sigma", "Spatial sigma", 1.0)])
        if vals:
            sigma = float(vals["sigma"])
            self.apply_movie_operation("Gaussian Smooth", lambda m: core.gaussian_smooth_movie(m, sigma, acceleration=self.acceleration()))

    def median_filter(self):
        vals = self.param_dialog("Median Filter", [("size", "Kernel size", 3)])
        if vals:
            size = int(vals["size"])
            self.apply_movie_operation("Median Filter", lambda m: core.median_filter_movie(m, size))

    def background_subtract(self):
        vals = self.param_dialog("Background Subtract", [("sigma", "Background sigma", 20)])
        if vals:
            sigma = float(vals["sigma"])
            self.apply_movie_operation("Background Subtract", lambda m: core.background_subtract(m, sigma))

    def bleach_correct(self):
        self.apply_movie_operation("Bleach Correction", core.bleach_correct)

    def enhance_contrast(self):
        self.apply_movie_operation("Enhance Contrast", core.enhance_contrast)

    def builtin_motion(self):
        vals = self.param_dialog("Rigid Motion", [("frames", "Template frames", 100)])
        if not vals:
            return
        frames = int(vals["frames"])
        def run(m):
            corrected, shifts = core.rigid_motion_correction(m, frames)
            self.log(f"Rigid correction shifts: median dy/dx={np.median(shifts, axis=0)}")
            return corrected
        self.apply_movie_operation("Rigid Motion", run)

    def detect_vessels(self):
        if not self.require_movie():
            return
        vals = self.param_dialog("Detect Vessels", [("threshold", "Threshold percentile", 90)])
        if not vals:
            return
        threshold = float(vals["threshold"])
        mask, vesselness = core.detect_vessels(self.state.movie, self.state.fs, threshold)
        self.vessel_mask = mask
        extra = np.zeros(mask.shape + (4,), dtype=np.float32)
        extra[..., 0] = mask
        extra[..., 3] = mask * 0.45
        self.redraw(extra=extra)
        self.log(f"Detected vessel/artifact pixels: {int(mask.sum())}")

    def remove_vessels(self):
        if not self.require_movie():
            return
        if not hasattr(self, "vessel_mask"):
            mask, _ = core.detect_vessels(self.state.movie, self.state.fs, 90)
            self.vessel_mask = mask
        self.apply_movie_operation("Remove Vessel Artifact", lambda m: core.suppress_vessels(m, self.vessel_mask))

    def show_dff_heatmap(self):
        if not self.require_movie():
            return
        dff = core.compute_dff(self.state.movie, self.state.baseline_image, acceleration=self.acceleration())
        self.state.display_image = np.mean(dff, axis=0)
        self.redraw(preserve_view=False)
        self.log("Showing mean dF/F heatmap.")

    def heatmap_mask(self, use_roi=True):
        if use_roi and self.state.roi_masks:
            return np.any(np.stack(self.state.roi_masks).astype(bool), axis=0)
        return np.ones(self.state.movie.shape[1:], dtype=bool)

    def generate_heatmap_avi(self):
        if not self.require_movie():
            return
        self.apply_protocol(update_baseline=False)
        HeatmapVideoDialog(self)

    def auto_roi(self):
        if not self.require_movie():
            return
        vals = self.param_dialog("Built-in Auto ROI", [("min_area", "Min area", 20), ("max_area", "Max area", 4000)])
        if not vals:
            return
        image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        rois = core.auto_roi_from_image(image, int(vals["min_area"]), int(vals["max_area"]))
        self.set_rois(rois, "Built-in auto ROI")

    def neuroseg3_roi(self):
        if not self.require_movie():
            return
        weights = core.available_neuroseg3_weights()
        default_weight = weights[0] if weights else ""
        for path in weights:
            if "segmentation" in path.lower():
                default_weight = path
                break
        dlg = NeuroSeg3Dialog(self.root, "NeuroSeg3 ROI", weights, default_weight=default_weight)
        vals = dlg.values
        if not vals:
            return
        image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        out_dir = Path(self.state.source_path).with_suffix("").parent / "NewLight_temp"
        conf = float(vals["conf"])
        mask_threshold = float(vals.get("mask_threshold", 0.5))
        weights_path = vals["weights"].strip() or None
        fallback = bool(vals["fallback"])
        self.run_worker(
            "NeuroSeg3 ROI",
            lambda: core.run_neuroseg3(image, str(out_dir), weights=weights_path, conf=conf, mask_threshold=mask_threshold),
            lambda result: self._finish_neuroseg3(result, fallback=fallback),
        )

    def _finish_neuroseg3(self, result, fallback=True):
        masks, log = result
        if not masks and fallback:
            image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
            masks = core.auto_roi_from_image(image, 20, 4000)
            self.set_rois(masks, "NeuroSeg3 returned 0; built-in fallback")
        else:
            self.set_rois(masks, "NeuroSeg3 ROI")
        if log.strip():
            self.log(log.strip()[-800:])

    def caiman_motion(self):
        if not self.require_movie():
            return
        vals = self.param_dialog("CaImAn Motion", [("mode", "rigid / piecewise", "rigid")])
        if not vals:
            return
        mode = vals["mode"].strip().lower()
        if mode not in {"rigid", "piecewise"}:
            mode = "rigid"
        out_dir = Path(self.state.source_path).with_suffix("").parent / "NewLight_temp"
        self.push_history("CaImAn Motion")
        self.run_worker("CaImAn Motion", lambda: core.run_caiman_motion(self.state.movie, str(out_dir), mode=mode), self._finish_caiman_motion)

    def _finish_caiman_motion(self, result):
        movie, log = result
        self.state.movie = movie
        self.state.baseline_image = core.baseline_from_seconds(
            movie,
            self.state.fs,
            self.state.baseline_start_s,
            self.state.baseline_duration_s,
        )
        self.update_frame_controls()
        self.refresh_projection()
        self.log("CaImAn motion correction applied.")
        if log.strip():
            self.log(log.strip()[-800:])

    def run_worker(self, label, func, callback):
        self.log(f"Running {label}...")
        def target():
            try:
                self.worker_queue.put((callback, func(), None))
            except Exception as exc:
                self.worker_queue.put((None, None, exc))
        threading.Thread(target=target, daemon=True).start()

    def _poll_worker(self):
        try:
            while True:
                callback, result, exc = self.worker_queue.get_nowait()
                if exc:
                    messagebox.showerror("Worker failed", str(exc))
                    self.log(f"Worker failed: {exc}")
                elif callback:
                    callback(result)
        except queue.Empty:
            pass
        self.root.after(200, self._poll_worker)

    def extract_traces(self):
        if not self.require_movie():
            return
        if not self.state.roi_masks:
            full_roi = np.ones(self.state.movie.shape[1:], dtype=bool)
            self.state.roi_masks = [full_roi]
            self.sync_roi_names()
            self.log("No ROI selected; using a full-frame global ROI.")
        self.apply_protocol(update_baseline=False)
        if len(self.state.roi_names) != len(self.state.roi_masks):
            self.sync_roi_names()
        traces = core.extract_traces(self.state.movie, self.state.roi_masks, "dff", self.state.baseline_image, acceleration=self.acceleration())
        traces = core.process_traces(
            traces,
            baseline_correct=self.trace_baseline_correct_var.get(),
            baseline_window=int(float(self.trace_baseline_window_var.get())),
            smooth_window=int(float(self.trace_smooth_window_var.get())),
        )
        self.state.traces = traces
        correction = "on" if self.trace_baseline_correct_var.get() else "off"
        self.log(
            f"Extracted traces: {traces.shape}, baseline correction={correction}, "
            f"smooth window={self.trace_smooth_window_var.get()}"
        )
        self.show_trace_window(traces)

    def show_trace_window(self, traces):
        win = tk.Toplevel(self.root)
        win.title("ROI dF/F Traces")
        win.configure(bg=THEME["bg"])
        fig = Figure(figsize=(9, 5), dpi=100)
        fig.patch.set_facecolor(THEME["bg"])
        ax = fig.add_subplot(111)
        ax.set_facecolor("#06101f")
        t = np.arange(traces.shape[0]) / self.state.fs
        offsets = np.arange(traces.shape[1]) * (np.nanstd(traces) * 4 + 0.1)
        for i in range(traces.shape[1]):
            ax.plot(t, traces[:, i] + offsets[i], lw=0.9)
        for frame in self.state.trigger_frames:
            if 0 <= frame < traces.shape[0]:
                ax.axvline(frame / self.state.fs, color="red", linestyle="--", linewidth=0.8, alpha=0.55)
        ax.set_yticks(offsets)
        ax.set_yticklabels(self.state.roi_names)
        ax.set_xlabel("Time (s)")
        ax.set_title("ROI dF/F Traces")
        ax.tick_params(colors=THEME["muted"])
        ax.xaxis.label.set_color(THEME["text"])
        ax.yaxis.label.set_color(THEME["text"])
        ax.title.set_color(THEME["text"])
        for spine in ax.spines.values():
            spine.set_color(THEME["border"])
        ax.grid(True, alpha=0.22, color="#5b789b")
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def show_roi_statistics(self):
        if self.state.traces is None:
            self.extract_traces()
        if self.state.traces is None or self.state.traces.size == 0:
            return
        stats = core.roi_statistics(self.state.traces, self.state.roi_names, self.state.fs, self.state.trigger_frames)
        win = tk.Toplevel(self.root)
        win.title("ROI Statistics")
        win.configure(bg=THEME["bg"])
        table = ttk.Treeview(win, columns=list(stats.columns), show="headings", height=min(18, max(4, len(stats))))
        for col in stats.columns:
            table.heading(col, text=col)
            table.column(col, width=110, anchor="center")
        for _, row in stats.iterrows():
            values = []
            for value in row:
                if isinstance(value, float):
                    values.append(f"{value:.5g}")
                else:
                    values.append(str(value))
            table.insert("", "end", values=values)
        table.pack(fill="both", expand=True)

    def show_trial_average(self):
        if self.state.traces is None:
            self.extract_traces()
        if self.state.traces is None or self.state.traces.size == 0:
            return
        if self.state.trigger_frames.size == 0:
            self.detect_triggers()
        if self.state.trigger_frames.size == 0:
            self.log("Trial average needs triggers.")
            return
        trials, trial_t = core.trial_average(
            self.state.traces,
            self.state.trigger_frames,
            self.state.fs,
            self.state.pre_trigger_s,
            self.state.post_trigger_s,
        )
        if trials.size == 0:
            self.log("No complete trials in selected pre/post window.")
            return
        mean_trial = np.nanmean(trials, axis=0)
        win = tk.Toplevel(self.root)
        win.title("Trial Average")
        win.configure(bg=THEME["bg"])
        fig = Figure(figsize=(9, 5), dpi=100)
        fig.patch.set_facecolor(THEME["bg"])
        ax = fig.add_subplot(111)
        ax.set_facecolor("#06101f")
        offsets = np.arange(mean_trial.shape[1]) * (np.nanstd(mean_trial) * 4 + 0.1)
        for i in range(mean_trial.shape[1]):
            ax.plot(trial_t, mean_trial[:, i] + offsets[i], lw=1.0)
        ax.axvline(0, color="red", linestyle="--", linewidth=1.0)
        ax.set_yticks(offsets)
        ax.set_yticklabels(self.state.roi_names)
        ax.set_xlabel("Time from trigger (s)")
        ax.set_title(f"Trial Average, n={trials.shape[0]}")
        ax.tick_params(colors=THEME["muted"])
        ax.xaxis.label.set_color(THEME["text"])
        ax.yaxis.label.set_color(THEME["text"])
        ax.title.set_color(THEME["text"])
        for spine in ax.spines.values():
            spine.set_color(THEME["border"])
        ax.grid(True, alpha=0.22, color="#5b789b")
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.log(f"Trial average shown, n={trials.shape[0]}.")

    def peak_detection(self):
        if self.state.traces is None:
            self.extract_traces()
        if self.state.traces is None or self.state.traces.size == 0:
            return
        counts = []
        for i in range(self.state.traces.shape[1]):
            peaks = core.detect_trace_peaks(self.state.traces[:, i], self.state.fs)
            counts.append((self.state.roi_names[i], len(peaks)))
        messagebox.showinfo("Peak Detection", "\n".join(f"{n}: {c} peaks" for n, c in counts))
        self.log("Peak detection finished.")

    def roi_correlation(self):
        if self.state.traces is None:
            self.extract_traces()
        if self.state.traces is None or self.state.traces.shape[1] < 2:
            self.log("Need at least two ROI traces.")
            return
        corr = np.corrcoef(self.state.traces.T)
        win = tk.Toplevel(self.root)
        win.title("ROI Correlation")
        win.configure(bg=THEME["bg"])
        fig = Figure(figsize=(6, 5), dpi=100)
        fig.patch.set_facecolor(THEME["bg"])
        ax = fig.add_subplot(111)
        ax.set_facecolor("#06101f")
        im = ax.imshow(corr, cmap="hot", vmin=-1, vmax=1)
        ax.set_xticks(np.arange(len(self.state.roi_names)))
        ax.set_yticks(np.arange(len(self.state.roi_names)))
        ax.set_xticklabels(self.state.roi_names, rotation=45, ha="right")
        ax.set_yticklabels(self.state.roi_names)
        ax.tick_params(colors=THEME["muted"])
        for spine in ax.spines.values():
            spine.set_color(THEME["border"])
        cbar = fig.colorbar(im, ax=ax)
        cbar.ax.tick_params(colors=THEME["muted"])
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def export_analysis(self):
        if not self.require_movie():
            return
        if self.state.traces is None and self.state.roi_masks:
            self.extract_traces()
        out_dir = filedialog.askdirectory()
        if not out_dir:
            return
        name = Path(self.state.source_path).stem or "NewLight"
        try:
            self.apply_protocol(update_baseline=False)
            if len(self.state.roi_names) != len(self.state.roi_masks):
                self.sync_roi_names()
            traces = self.state.traces if self.state.traces is not None else np.empty((self.state.movie.shape[0], 0))
            paths = core.export_results(
                out_dir,
                name,
                self.state.movie,
                self.state.baseline_image,
                self.state.roi_masks,
                self.state.roi_names,
                traces,
                self.state.fs,
                self.state.trigger_frames,
                self.state.pre_trigger_s,
                self.state.post_trigger_s,
            )
            self.log(f"Exported {len(paths)} files to {out_dir}")
            messagebox.showinfo("Export complete", f"Results exported to:\n{out_dir}")
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror("Export failed", str(exc))


def main():
    root = tk.Tk()
    apply_dark_theme(root)
    NewLightApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
