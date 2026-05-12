from __future__ import annotations

import json
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
from PIL import Image, ImageTk

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

APP_DIR = Path(__file__).resolve().parent
NEUROALIGN_DIR = core.WORKSPACE / "2cafe_analysis" / "NeuroAlign"
NEUROALIGN_ENV = "caiman_latest"
NEUROALIGN_HELP_PATH = APP_DIR / "NeuroAlign_atlas_registration_help.txt"
NEUROALIGN_SUMMARY_PATH = APP_DIR / "NeuroAlign_atlas_registration_summary.json"
NEUROALIGN_RUNS_DIR = APP_DIR / "NeuroAlign_runs"
USER_SETTINGS_PATH = APP_DIR / "NewLight_user_settings.json"


def load_user_settings() -> dict:
    if not USER_SETTINGS_PATH.exists():
        return {}
    try:
        with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def save_user_settings(settings: dict) -> None:
    try:
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_neuroalign_summary() -> dict:
    if not NEUROALIGN_SUMMARY_PATH.exists():
        return {}
    try:
        with open(NEUROALIGN_SUMMARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def atlas_builder_defaults() -> dict:
    fallback = {
        "line_threshold": 180,
        "auto_gap_bridge_dist": 8,
        "barrier_radius": 1,
        "min_region_area": 300,
        "detect_dark_lines": False,
    }
    summary = load_neuroalign_summary()
    cfg = summary.get("build_atlas_from_lines_autocomplete", {}).get("cli_defaults", {})
    out = dict(fallback)
    out.update({k: cfg[k] for k in out if k in cfg})
    return out


def neuroalign_recommended_cfg() -> dict:
    fallback = {
        "brain_mask_percentile": 72,
        "midline_anchor_count": 14,
        "midline_anchor_weight": 8,
        "outer_anchor_weight": 0.5,
        "tps_smooth": 3,
        "tps_smooth_candidates": "12,8,5,3,1",
        "min_inner_ctrl_for_tps": 4,
        "max_ctrl_shift_px": 24,
        "auto_rerun_max_attempts": 8,
        "auto_rerun_force_min_inner": 5,
        "adaptive_search_quantile_min": 0.60,
        "adaptive_search_quantile_max": 0.95,
        "final_score_inner_weight": 0.55,
        "final_score_iou_weight": 0.10,
        "final_score_outer_weight": 0.08,
    }
    summary = load_neuroalign_summary()
    cfg = summary.get("atlas_registration_merged_bilateral_midline", {}).get("readme_recommended_trial_cfg", {})
    out = dict(fallback)
    out.update({k: cfg[k] for k in out if k in cfg})
    return out


def default_neuroalign_outdir(prefix: str) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return str(NEUROALIGN_RUNS_DIR / f"{prefix}_{stamp}")


def load_neuroalign_help_text() -> str:
    if NEUROALIGN_HELP_PATH.exists():
        try:
            return NEUROALIGN_HELP_PATH.read_text(encoding="utf-8")
        except Exception:
            pass
    return (
        "NeuroAlign help is not available.\n\n"
        "Please check NeuroAlign_atlas_registration_summary.json in the NewLight_Analysis directory."
    )


def run_backend_script(script_path: Path, args: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
    proc = core.run_conda_worker(
        NEUROALIGN_ENV,
        str(script_path),
        [str(arg) for arg in args],
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )
    log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        if (
            "No module named 'igraph'" in log
            or "No module named 'leidenalg'" in log
            or "igraph is required" in log
            or "leidenalg is required" in log
        ):
            log = (
                log.strip()
                + "\n\nNeuroAlign backend is missing graph clustering packages. "
                + f"Install them in the `{NEUROALIGN_ENV}` environment, then retry."
            )
        raise RuntimeError(log.strip() or f"{script_path.name} failed with exit code {proc.returncode}")
    return log.strip()


def check_neuroalign_registration_backend() -> None:
    proc = core.run_conda_worker(
        NEUROALIGN_ENV,
        "-c",
        ["import cv2, numpy, scipy, skimage, matplotlib, sklearn, igraph, leidenalg; print('NeuroAlign backend OK')"],
        cwd=str(NEUROALIGN_DIR) if NEUROALIGN_DIR.exists() else None,
        timeout=60,
    )
    if proc.returncode != 0:
        log = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        raise RuntimeError(
            log.strip()
            + f"\n\nNeuroAlign registration needs `python-igraph` and `leidenalg` in the `{NEUROALIGN_ENV}` environment."
        )


class ImageToolbar(NavigationToolbar2Tk):
    toolitems = tuple(item for item in NavigationToolbar2Tk.toolitems if item[0] != "Subplots")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_message_label()

    def _style_message_label(self):
        label = getattr(self, "_message_label", None)
        if label is None:
            return
        try:
            label.configure(background=THEME["panel"], foreground="#ffffff", fg="#ffffff", bg=THEME["panel"])
        except tk.TclError:
            pass

    def set_message(self, s):
        super().set_message(s)
        self._style_message_label()


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
    style.configure("Accent.TLabel", background=THEME["bg"], foreground=THEME["accent"], font=("Segoe UI Semibold", 11))
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


class TextDisplayDialog(tk.Toplevel):
    def __init__(self, parent, title, text, width=92, height=34):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=THEME["bg"])
        self.geometry("880x680")
        self.minsize(680, 480)
        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        text_widget = tk.Text(body, width=width, height=height, wrap="word")
        text_widget.configure(
            bg=THEME["entry"],
            fg=THEME["text"],
            insertbackground=THEME["accent"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=THEME["border"],
            padx=10,
            pady=8,
        )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        text_widget.insert("1.0", text)
        text_widget.configure(state="disabled")

        buttons = ttk.Frame(body)
        buttons.grid(row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Close", command=self.destroy).grid(row=0, column=0)
        self.transient(parent)


class AtlasReferenceBuilderDialog(tk.Toplevel):
    def __init__(self, parent, app, default_image="", default_outdir=""):
        super().__init__(parent)
        self.title("Atlas Reference Builder")
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.app = app
        self.values = None
        defaults = atlas_builder_defaults()
        saved = getattr(app, "user_settings", {}).get("atlas_reference_builder", {})
        self.image_var = tk.StringVar(value=saved.get("image") or default_image)
        self.outdir_var = tk.StringVar(value=saved.get("outdir") or default_outdir or default_neuroalign_outdir("atlas_reference"))
        self.line_threshold_var = tk.StringVar(value=str(saved.get("line_threshold", defaults["line_threshold"])))
        self.bridge_dist_var = tk.StringVar(value=str(saved.get("auto_gap_bridge_dist", defaults["auto_gap_bridge_dist"])))
        self.barrier_radius_var = tk.StringVar(value=str(saved.get("barrier_radius", defaults["barrier_radius"])))
        self.min_region_area_var = tk.StringVar(value=str(saved.get("min_region_area", defaults["min_region_area"])))
        self.detect_dark_lines_var = tk.BooleanVar(value=bool(saved.get("detect_dark_lines", defaults["detect_dark_lines"])))

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        image_entry = self._path_row(body, 0, "Atlas line image", self.image_var, self.browse_image)
        self._path_row(body, 1, "Output dir", self.outdir_var, self.browse_outdir)

        fields = [
            ("Line threshold", self.line_threshold_var),
            ("Bridge gap px", self.bridge_dist_var),
            ("Barrier radius", self.barrier_radius_var),
            ("Min region area", self.min_region_area_var),
        ]
        for idx, (label, var) in enumerate(fields, start=2):
            ttk.Label(body, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Entry(body, textvariable=var, width=16).grid(row=idx, column=1, sticky="ew", pady=4, padx=(8, 0))

        ttk.Checkbutton(body, text="Detect dark lines", variable=self.detect_dark_lines_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(8, 2)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Help", command=self.show_help).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Run", command=self._apply).grid(row=0, column=2)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._apply())
        self.after(0, image_entry.focus_set)
        self.wait_window(self)

    def _path_row(self, body, row, label, var, browse_command):
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=4)
        path_row = ttk.Frame(body)
        path_row.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        path_row.columnconfigure(0, weight=1)
        entry = ttk.Entry(path_row, textvariable=var, width=46)
        entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(path_row, text="Browse", command=browse_command).grid(row=0, column=1, padx=(8, 0))
        return entry

    def browse_image(self):
        path = filedialog.askopenfilename(
            title="Select atlas line image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("All files", "*.*")],
        )
        if path:
            self.image_var.set(path)

    def browse_outdir(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.outdir_var.set(path)

    def show_help(self):
        TextDisplayDialog(self, "NeuroAlign Help", load_neuroalign_help_text())

    def _apply(self):
        try:
            image = Path(self.image_var.get().strip())
            outdir = Path(self.outdir_var.get().strip())
            if not image.exists():
                raise ValueError("Atlas line image does not exist.")
            if not str(outdir):
                raise ValueError("Output dir is required.")
            self.values = {
                "image": str(image),
                "outdir": str(outdir),
                "line_threshold": int(float(self.line_threshold_var.get())),
                "auto_gap_bridge_dist": int(float(self.bridge_dist_var.get())),
                "barrier_radius": int(float(self.barrier_radius_var.get())),
                "min_region_area": int(float(self.min_region_area_var.get())),
                "detect_dark_lines": bool(self.detect_dark_lines_var.get()),
            }
        except Exception as exc:
            messagebox.showerror("Atlas Reference Builder", str(exc))
            return
        self.destroy()

    def destroy(self):
        try:
            self.app.user_settings["atlas_reference_builder"] = {
                "image": self.image_var.get().strip(),
                "outdir": self.outdir_var.get().strip(),
                "line_threshold": self.line_threshold_var.get().strip(),
                "auto_gap_bridge_dist": self.bridge_dist_var.get().strip(),
                "barrier_radius": self.barrier_radius_var.get().strip(),
                "min_region_area": self.min_region_area_var.get().strip(),
                "detect_dark_lines": bool(self.detect_dark_lines_var.get()),
            }
            save_user_settings(self.app.user_settings)
        except Exception:
            pass
        super().destroy()


class NeuroAlignDialog(tk.Toplevel):
    def __init__(self, parent, app, default_video="", default_atlas_json="", default_outdir=""):
        super().__init__(parent)
        self.title("NeuroAlign")
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.app = app
        self.values = None
        cfg = neuroalign_recommended_cfg()
        self.video_var = tk.StringVar(value=default_video)
        self.atlas_json_var = tk.StringVar(value=default_atlas_json)
        self.outdir_var = tk.StringVar(value=default_outdir or default_neuroalign_outdir("neuroalign"))
        self.cfg_vars = {
            "brain_mask_percentile": tk.StringVar(value=str(cfg["brain_mask_percentile"])),
            "midline_anchor_count": tk.StringVar(value=str(cfg["midline_anchor_count"])),
            "midline_anchor_weight": tk.StringVar(value=str(cfg["midline_anchor_weight"])),
            "outer_anchor_weight": tk.StringVar(value=str(cfg["outer_anchor_weight"])),
            "tps_smooth": tk.StringVar(value=str(cfg["tps_smooth"])),
            "max_ctrl_shift_px": tk.StringVar(value=str(cfg["max_ctrl_shift_px"])),
            "min_inner_ctrl_for_tps": tk.StringVar(value=str(cfg["min_inner_ctrl_for_tps"])),
            "auto_rerun_max_attempts": tk.StringVar(value=str(cfg["auto_rerun_max_attempts"])),
        }

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        video_entry = self._path_row(body, 0, "Video", self.video_var, self.browse_video)
        self._path_row(body, 1, "Atlas JSON", self.atlas_json_var, self.browse_atlas_json)
        self._path_row(body, 2, "Output dir", self.outdir_var, self.browse_outdir)

        labels = [
            ("brain_mask_percentile", "Brain mask percentile"),
            ("midline_anchor_count", "Midline anchors"),
            ("midline_anchor_weight", "Midline weight"),
            ("outer_anchor_weight", "Outer weight"),
            ("tps_smooth", "TPS smooth"),
            ("max_ctrl_shift_px", "Max ctrl shift px"),
            ("min_inner_ctrl_for_tps", "Min inner ctrl"),
            ("auto_rerun_max_attempts", "Auto rerun attempts"),
        ]
        for idx, (key, label) in enumerate(labels, start=3):
            ttk.Label(body, text=label).grid(row=idx, column=0, sticky="w", pady=3)
            ttk.Entry(body, textvariable=self.cfg_vars[key], width=16).grid(
                row=idx, column=1, sticky="ew", padx=(8, 0), pady=3
            )

        buttons = ttk.Frame(body)
        buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Help", command=self.show_help).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="Run", command=self._apply).grid(row=0, column=2)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._apply())
        self.after(0, video_entry.focus_set)
        self.wait_window(self)

    def _path_row(self, body, row, label, var, browse_command):
        ttk.Label(body, text=label).grid(row=row, column=0, sticky="w", pady=4)
        path_row = ttk.Frame(body)
        path_row.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
        path_row.columnconfigure(0, weight=1)
        entry = ttk.Entry(path_row, textvariable=var, width=46)
        entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(path_row, text="Browse", command=browse_command).grid(row=0, column=1, padx=(8, 0))
        return entry

    def browse_video(self):
        path = filedialog.askopenfilename(
            title="Select subject video",
            filetypes=[("Video files", "*.avi *.mp4"), ("All files", "*.*")],
        )
        if path:
            self.video_var.set(path)

    def browse_atlas_json(self):
        path = filedialog.askopenfilename(
            title="Select atlas JSON",
            filetypes=[("Atlas JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.atlas_json_var.set(path)

    def browse_outdir(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.outdir_var.set(path)

    def show_help(self):
        TextDisplayDialog(self, "NeuroAlign Help", load_neuroalign_help_text())

    def _apply(self):
        try:
            video = Path(self.video_var.get().strip())
            atlas_json = Path(self.atlas_json_var.get().strip())
            outdir = Path(self.outdir_var.get().strip())
            if not video.exists():
                raise ValueError("Video path does not exist.")
            if not atlas_json.exists():
                raise ValueError("Atlas JSON does not exist.")
            cfg = neuroalign_recommended_cfg()
            for key, var in self.cfg_vars.items():
                value = float(var.get())
                if key in {"midline_anchor_count", "min_inner_ctrl_for_tps", "auto_rerun_max_attempts"}:
                    value = int(value)
                cfg[key] = value
            self.values = {
                "video": str(video),
                "atlas_json": str(atlas_json),
                "outdir": str(outdir),
                "cfg": cfg,
            }
        except Exception as exc:
            messagebox.showerror("NeuroAlign", str(exc))
            return
        self.destroy()


class NeuroAlignWizard(tk.Toplevel):
    STAGES = ("outer", "cluster", "final")

    def __init__(self, parent, app, defaults: dict):
        super().__init__(parent)
        self.app = app
        self.values = None
        self.title("NeuroAlign")
        self.configure(bg=THEME["bg"])
        self.geometry("1180x820")
        self.minsize(960, 680)
        self.current_stage = "outer"
        self.current_result = None
        self.preview_image_ref = None
        self.last_run_log = ""
        self.running = False

        cfg = dict(defaults.get("cfg") or neuroalign_recommended_cfg())
        self.video_var = tk.StringVar(value=defaults.get("video", ""))
        self.atlas_json_var = tk.StringVar(value=defaults.get("atlas_json", ""))
        self.outdir_var = tk.StringVar(value=defaults.get("outdir", default_neuroalign_outdir("neuroalign")))
        self.cfg_vars = {
            key: tk.StringVar(value=str(cfg.get(key, neuroalign_recommended_cfg().get(key, ""))))
            for key in [
                "brain_mask_percentile",
                "midline_anchor_count",
                "midline_anchor_weight",
                "outer_anchor_weight",
                "tps_smooth",
                "max_ctrl_shift_px",
                "min_inner_ctrl_for_tps",
                "auto_rerun_max_attempts",
                "resolution",
                "compactness",
                "min_n_segments",
                "max_n_segments",
                "inner_max_pairs_per_hemi",
                "adaptive_search_quantile_min",
                "adaptive_search_quantile_max",
            ]
        }

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, minsize=330)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.columnconfigure(0, weight=1)
        self.stage_var = tk.StringVar()
        ttk.Label(left, textvariable=self.stage_var, style="Accent.TLabel").grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.input_frame = ttk.LabelFrame(left, text="Inputs", padding=8)
        self.input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.input_frame.columnconfigure(1, weight=1)
        self._path_row(self.input_frame, 0, "Video", self.video_var, self.browse_video)
        self._path_row(self.input_frame, 1, "Atlas JSON", self.atlas_json_var, self.browse_atlas_json)
        self._path_row(self.input_frame, 2, "Output dir", self.outdir_var, self.browse_outdir)

        self.param_frame = ttk.LabelFrame(left, text="Parameters", padding=8)
        self.param_frame.grid(row=2, column=0, sticky="nsew")
        self.param_frame.columnconfigure(1, weight=1)
        left.rowconfigure(2, weight=1)

        buttons = ttk.Frame(left)
        buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        buttons.columnconfigure((0, 1, 2), weight=1)
        ttk.Button(buttons, text="Help", command=self.show_help).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.rebuild_button = ttk.Button(buttons, text="Rebuild", command=self.rebuild)
        self.rebuild_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.next_button = ttk.Button(buttons, text="Next", command=self.next_stage)
        self.next_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 4))
        ttk.Button(buttons, text="Use Result", command=self.accept).grid(row=1, column=1, columnspan=2, sticky="ew", pady=(6, 0), padx=(4, 0))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(right, bg="#020617", highlightthickness=1, highlightbackground=THEME["border"])
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_caption = tk.StringVar(value="Click Rebuild to generate preview.")
        ttk.Label(right, textvariable=self.preview_caption, style="Muted.TLabel").grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.log_text = tk.Text(right, height=6, wrap="word")
        self.log_text.configure(bg=THEME["entry"], fg=THEME["text"], insertbackground=THEME["accent"], relief="flat", highlightthickness=1, highlightbackground=THEME["border"])
        self.log_text.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.preview_canvas.bind("<Configure>", lambda _event: self.refresh_preview())
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.render_stage()

    def _path_row(self, parent, row, label, var, command):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="ew", pady=3, padx=(6, 0))
        holder.columnconfigure(0, weight=1)
        ttk.Entry(holder, textvariable=var, width=32).grid(row=0, column=0, sticky="ew")
        ttk.Button(holder, text="Browse", command=command).grid(row=0, column=1, padx=(6, 0))

    def browse_video(self):
        path = filedialog.askopenfilename(title="Select subject video", filetypes=[("Video files", "*.avi *.mp4 *.mov *.mkv"), ("All files", "*.*")])
        if path:
            self.video_var.set(path)

    def browse_atlas_json(self):
        path = filedialog.askopenfilename(title="Select atlas JSON", filetypes=[("Atlas JSON", "*.json"), ("All files", "*.*")])
        if path:
            self.atlas_json_var.set(path)

    def browse_outdir(self):
        path = filedialog.askdirectory(title="Select output directory")
        if path:
            self.outdir_var.set(path)

    def show_help(self):
        TextDisplayDialog(self, "NeuroAlign Help", load_neuroalign_help_text())

    def stage_fields(self):
        if self.current_stage == "outer":
            return [
                ("brain_mask_percentile", "Brain mask percentile"),
                ("midline_anchor_count", "Midline anchors"),
                ("midline_anchor_weight", "Midline weight"),
                ("outer_anchor_weight", "Outer weight"),
                ("max_ctrl_shift_px", "Max ctrl shift px"),
            ]
        if self.current_stage == "cluster":
            return [
                ("resolution", "Cluster resolution"),
                ("compactness", "SLIC compactness"),
                ("min_n_segments", "Min segments"),
                ("max_n_segments", "Max segments"),
                ("inner_max_pairs_per_hemi", "Inner pairs / hemi"),
            ]
        return [
            ("tps_smooth", "TPS smooth"),
            ("min_inner_ctrl_for_tps", "Min inner ctrl"),
            ("adaptive_search_quantile_min", "Search quantile min"),
            ("adaptive_search_quantile_max", "Search quantile max"),
            ("auto_rerun_max_attempts", "Auto rerun attempts"),
        ]

    def render_stage(self):
        for child in self.param_frame.winfo_children():
            child.destroy()
        stage_name = {"outer": "Step 1 / 3: Outer contour preview", "cluster": "Step 2 / 3: Clustering preview", "final": "Step 3 / 3: Final atlas preview"}[self.current_stage]
        self.stage_var.set(stage_name)
        for row, (key, label) in enumerate(self.stage_fields()):
            ttk.Label(self.param_frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(self.param_frame, textvariable=self.cfg_vars[key], width=14).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.next_button.configure(text="Finish" if self.current_stage == "final" else "Next")
        self.refresh_preview()

    def current_config(self):
        cfg = neuroalign_recommended_cfg()
        for key, var in self.cfg_vars.items():
            raw = var.get().strip()
            if raw == "":
                continue
            if key in {"midline_anchor_count", "min_inner_ctrl_for_tps", "auto_rerun_max_attempts", "min_n_segments", "max_n_segments", "inner_max_pairs_per_hemi"}:
                cfg[key] = int(float(raw))
            else:
                cfg[key] = float(raw)
        return cfg

    def collect_values(self):
        video = Path(self.video_var.get().strip())
        atlas_json = Path(self.atlas_json_var.get().strip())
        outdir = Path(self.outdir_var.get().strip())
        if not video.exists():
            raise ValueError("Video path does not exist.")
        if not atlas_json.exists():
            raise ValueError("Atlas JSON does not exist.")
        return {"video": str(video), "atlas_json": str(atlas_json), "outdir": str(outdir), "cfg": self.current_config()}

    def save_settings_snapshot(self):
        vals = self.collect_values()
        self.app.user_settings["neuroalign"] = vals
        save_user_settings(self.app.user_settings)

    def log(self, text):
        stamp = time.strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{stamp}] {text}\n")
        self.log_text.see("end")

    def rebuild(self):
        if self.running:
            return
        try:
            vals = self.collect_values()
        except Exception as exc:
            messagebox.showerror("NeuroAlign", str(exc))
            return
        self.app.user_settings["neuroalign"] = vals
        save_user_settings(self.app.user_settings)
        self.running = True
        self.rebuild_button.configure(state="disabled")
        self.preview_caption.set("Running NeuroAlign rebuild...")
        self.log(f"Rebuild started for {self.current_stage}.")

        def target():
            try:
                result = self.app.run_neuroalign_backend(vals)
                try:
                    self.after(0, lambda result=result: self.rebuild_done(result, None))
                except tk.TclError:
                    pass
            except Exception as exc:
                try:
                    self.after(0, lambda exc=exc: self.rebuild_done(None, exc))
                except tk.TclError:
                    pass

        threading.Thread(target=target, daemon=True).start()

    def rebuild_done(self, result, exc):
        self.running = False
        self.rebuild_button.configure(state="normal")
        if exc:
            self.log(f"Worker failed: {exc}")
            messagebox.showerror("NeuroAlign", self.app.worker_error_summary(str(exc)))
            self.preview_caption.set("Rebuild failed. See log.")
            return
        self.current_result = result
        self.last_run_log = str(result.get("log", "")).strip()
        outdir = Path(result["outdir"])
        self.create_outer_preview(outdir)
        self.create_cluster_preview(outdir)
        self.log(f"Rebuild finished: {result.get('outdir')}")
        if self.last_run_log:
            self.log(self.last_run_log[-1200:])
        self.refresh_preview()

    def preview_path(self):
        if not self.current_result:
            return None
        outdir = Path(self.current_result["outdir"])
        if self.current_stage == "outer":
            for name in ("outer_fit_preview.png", "outer_registration_overlay.png", "subject_outer_mask.png", "midline_profile_overlay.png"):
                path = outdir / name
                if path.exists():
                    return path
        if self.current_stage == "cluster":
            path = outdir / "cluster_on_affine_preview.png"
            if not path.exists():
                self.create_cluster_preview(outdir)
            return path if path.exists() else outdir / "subject_inner_boundaries.png"
        return outdir / "final_warp_overlay.png"

    def preview_mean_image(self, shape_hw):
        img = self.app.state.display_image if self.app.state.display_image is not None else self.app.state.baseline_image
        if img is None and self.app.state.movie is not None:
            img = np.mean(self.app.state.movie, axis=0)
        if img is None:
            return None
        img = np.asarray(img, dtype=np.float32)
        if img.ndim == 3:
            img = np.mean(img, axis=2)
        if tuple(img.shape[:2]) != tuple(shape_hw):
            img = core.cv2.resize(img, (int(shape_hw[1]), int(shape_hw[0])), interpolation=core.cv2.INTER_AREA)
        return img

    def create_outer_preview(self, outdir: Path):
        mask_path = outdir / "subject_mask.npy"
        affine_json_path = outdir / "affine_atlas_regions.json"
        if not mask_path.exists() or not affine_json_path.exists():
            return
        subject_mask = np.load(mask_path).astype(np.uint8)
        with open(affine_json_path, "r", encoding="utf-8") as f:
            atlas = json.load(f)
        mean_img = self.preview_mean_image(subject_mask.shape)
        fig = Figure(figsize=(8, 8), dpi=160)
        ax = fig.add_subplot(111)
        ax.set_facecolor("#020617")
        ax.set_axis_off()
        if mean_img is not None:
            vmin, vmax = np.percentile(mean_img, [2, 98])
            ax.imshow(mean_img, cmap="gray", vmin=vmin, vmax=vmax, alpha=0.30, interpolation="bilinear")
        contours, _ = core.cv2.findContours(subject_mask, core.cv2.RETR_EXTERNAL, core.cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            pts = contour[:, 0, :]
            ax.plot(pts[:, 0], pts[:, 1], color="#38bdf8", linewidth=1.0)
        outer = np.asarray(atlas.get("brain_outer_polygon", []), dtype=np.float32)
        if outer.ndim == 2 and len(outer) >= 3:
            ax.plot(np.r_[outer[:, 0], outer[0, 0]], np.r_[outer[:, 1], outer[0, 1]], color="#fb7185", linewidth=1.4)
        midline = np.asarray(atlas.get("midline_polyline", []), dtype=np.float32)
        if midline.ndim == 2 and len(midline) >= 2:
            ax.plot(midline[:, 0], midline[:, 1], color="#a3e635", linewidth=1.2)
        ax.set_xlim(-0.5, subject_mask.shape[1] - 0.5)
        ax.set_ylim(subject_mask.shape[0] - 0.5, -0.5)
        fig.tight_layout(pad=0)
        fig.savefig(outdir / "outer_fit_preview.png", bbox_inches="tight", pad_inches=0)
        fig.clear()

    def create_cluster_preview(self, outdir: Path):
        label_map_path = outdir / "leiden_label_map.npy"
        affine_path = outdir / "affine_atlas_label_map.npy"
        if not label_map_path.exists():
            return
        label_map = np.load(label_map_path)
        affine = np.load(affine_path) if affine_path.exists() else None
        fig = Figure(figsize=(8, 8), dpi=160)
        ax = fig.add_subplot(111)
        ax.set_axis_off()
        ax.imshow(np.ma.masked_where(label_map == 0, label_map), cmap="tab20b", interpolation="nearest")
        if affine is not None:
            from skimage.segmentation import find_boundaries
            boundary = find_boundaries(affine, mode="outer") & (affine > 0)
            ax.contour(boundary.astype(np.uint8), levels=[0.5], colors="white", linewidths=0.35)
        fig.tight_layout(pad=0)
        fig.savefig(outdir / "cluster_on_affine_preview.png", bbox_inches="tight", pad_inches=0)
        fig.clear()

    def raw_settings_snapshot(self):
        self.app.user_settings["neuroalign"] = {
            "video": self.video_var.get().strip(),
            "atlas_json": self.atlas_json_var.get().strip(),
            "outdir": self.outdir_var.get().strip(),
            "cfg": {key: var.get().strip() for key, var in self.cfg_vars.items()},
        }
        save_user_settings(self.app.user_settings)

    def destroy(self):
        try:
            self.raw_settings_snapshot()
        except Exception:
            pass
        super().destroy()

    def refresh_preview(self):
        self.preview_canvas.delete("all")
        path = self.preview_path()
        if path is None:
            self.preview_canvas.create_text(20, 20, anchor="nw", text="Click Rebuild to generate this preview.", fill=THEME["text"], font=("Segoe UI", 12))
            return
        if not Path(path).exists():
            self.preview_canvas.create_text(20, 20, anchor="nw", text=f"Preview not found:\n{path}", fill=THEME["text"], font=("Segoe UI", 12))
            return
        cw = max(1, self.preview_canvas.winfo_width())
        ch = max(1, self.preview_canvas.winfo_height())
        img = Image.open(path).convert("RGB")
        scale = min(cw / img.width, ch / img.height, 1.0)
        size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
        img = img.resize(size, Image.Resampling.LANCZOS)
        self.preview_image_ref = ImageTk.PhotoImage(img)
        self.preview_canvas.create_image(cw // 2, ch // 2, image=self.preview_image_ref, anchor="center")
        captions = {
            "outer": "Outer contour preview: affine atlas outline over mean image.",
            "cluster": "Clustering preview: Leiden clusters with affine atlas boundary overlay, mean image hidden.",
            "final": "Final atlas preview: warped atlas over subject image.",
        }
        self.preview_caption.set(captions[self.current_stage])

    def next_stage(self):
        if self.current_stage == "outer":
            self.current_stage = "cluster"
        elif self.current_stage == "cluster":
            self.current_stage = "final"
        else:
            self.accept()
            return
        self.render_stage()

    def accept(self):
        if not self.current_result:
            messagebox.showwarning("NeuroAlign", "Please run Rebuild before using the result.")
            return
        self.values = self.current_result
        self.destroy()


class BuiltInAutoROIDialog(tk.Toplevel):
    def __init__(self, parent, app, title, default_min_area=20, default_max_area=4000):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.app = app
        self.values = None
        self._default_min_area = max(3, int(default_min_area))
        self._default_max_area = max(self._default_min_area + 1, int(default_max_area))
        self.min_area_var = tk.StringVar(value=str(self._default_min_area))
        self.max_area_var = tk.StringVar(value=str(self._default_max_area))
        self.status_var = tk.StringVar(value="")

        body = ttk.Frame(self, padding=12)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text="Min area (px^2)").grid(row=0, column=0, sticky="w", pady=4)
        min_entry = ttk.Entry(body, textvariable=self.min_area_var, width=18)
        min_entry.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))

        ttk.Label(body, text="Max area (px^2)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.max_area_var, width=18).grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))

        sample_row = ttk.Frame(body)
        sample_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        sample_row.columnconfigure(0, weight=1)
        ttk.Button(sample_row, text="Use last 2 ROIs", command=self.use_current_rois).grid(row=0, column=0, sticky="ew")
        ttk.Button(sample_row, text="Reset defaults", command=self.reset_defaults).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel", wraplength=300).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Apply", command=self._apply).grid(row=0, column=1)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._apply())
        self.after(0, min_entry.focus_set)
        self.wait_window(self)

    def reset_defaults(self):
        self.min_area_var.set(str(self._default_min_area))
        self.max_area_var.set(str(self._default_max_area))
        self.status_var.set("Restored seed-based defaults.")

    def use_current_rois(self):
        masks = list(getattr(self.app.state, "roi_masks", []))
        if len(masks) < 2:
            messagebox.showwarning("Built-in Auto ROI", "Draw at least two sample ROIs first.")
            return
        areas = [int(np.count_nonzero(np.asarray(mask, dtype=bool))) for mask in masks[-2:]]
        areas = [area for area in areas if area > 0]
        if len(areas) < 2:
            messagebox.showwarning("Built-in Auto ROI", "The last two ROIs must both have nonzero area.")
            return
        sample_min = max(3, int(round(min(areas) * 0.9)))
        sample_max = max(sample_min + 1, int(round(max(areas) * 1.1)))
        self.min_area_var.set(str(sample_min))
        self.max_area_var.set(str(sample_max))
        self.status_var.set(f"Filled from the last two ROIs: {areas[0]} and {areas[1]} px^2.")
        self.app.log(f"Built-in auto ROI filled from last two ROIs: {areas[0]} and {areas[1]} px^2 -> {sample_min}-{sample_max} px^2.")

    def _apply(self):
        try:
            min_area = max(3, int(float(self.min_area_var.get())))
            max_area = max(min_area + 1, int(float(self.max_area_var.get())))
        except Exception:
            messagebox.showerror("Built-in Auto ROI", "Please enter valid numeric area bounds.")
            return
        self.values = {"min_area": min_area, "max_area": max_area}
        self.destroy()


class NeuroSeg3Dialog(tk.Toplevel):
    def __init__(self, parent, title, weights, default_weight="", default_conf=0.002, mask_threshold=0.5, fallback_default=True):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.values = None
        self.conf_var = tk.StringVar(value=f"{float(default_conf):.4f}".rstrip("0").rstrip("."))
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
        self.conf_entry = ttk.Entry(conf_row, textvariable=self.conf_var, width=14)
        self.conf_entry.grid(row=0, column=0, sticky="ew")
        ttk.Label(conf_row, text="e.g. 0.002", style="Muted.TLabel").grid(row=0, column=1, padx=(8, 0))

        ttk.Label(body, text="Mask pixel cutoff").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(body, text=f"Fixed at {self._mask_threshold:.2f}", style="Muted.TLabel").grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(body, text="Weights .pt").grid(row=2, column=0, sticky="w", pady=4)
        weight_row = ttk.Frame(body)
        weight_row.grid(row=2, column=1, sticky="ew", pady=4)
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
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Apply", command=self._apply).grid(row=0, column=1)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", lambda _event: self._apply())
        self.after(0, self._focus_default)
        self.wait_window(self)

    def _focus_default(self):
        self.conf_entry.focus_set()
        self.conf_entry.selection_range(0, "end")

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
        try:
            conf = float(self.conf_var.get())
        except Exception:
            messagebox.showerror("NeuroSeg3 ROI", "Detection conf must be a number.")
            return
        if not (0.0 <= conf <= 1.0):
            messagebox.showerror("NeuroSeg3 ROI", "Detection conf must be between 0 and 1.")
            return
        self.values = {
            "conf": round(conf, 6),
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
        self.last_cursor_image_xy = None
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
        self.user_settings = load_user_settings()
        self.last_atlas_reference_json = ""
        self.last_neuroalign_output_dir = ""
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
        ttk.Button(roi_box, text="Atlas Reference Builder", command=self.atlas_reference_builder).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="NeuroAlign", command=self.neuroalign).grid(row=3, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Atlas Image ROI", command=self.atlas_roi).grid(row=4, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Load ROI / Atlas", command=self.load_roi).grid(row=5, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Save ROI .npz", command=self.save_roi).grid(row=6, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="Clear ROIs", command=self.clear_rois).grid(row=7, column=0, sticky="ew", pady=2)

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
        try:
            self.nav_toolbar._message_label.configure(background=THEME["panel"], foreground="#ffffff")
        except tk.TclError:
            pass
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
        self.status.set(self.status_summary(text))
        self.root.update_idletasks()

    def status_summary(self, text, max_chars=140):
        line = str(text).strip().splitlines()[0] if str(text).strip() else ""
        if len(line) > max_chars:
            return line[: max_chars - 3].rstrip() + "..."
        return line

    def worker_error_summary(self, text):
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        if not lines:
            return "Worker failed. See Run Log for details."
        for line in reversed(lines):
            if line.startswith(("FileNotFoundError", "ValueError", "RuntimeError", "PermissionError")):
                return self.status_summary(line, max_chars=420) + "\n\nFull details are in Run Log."
        return self.status_summary(lines[-1], max_chars=420) + "\n\nFull details are in Run Log."

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
        if event.inaxes == self.ax and event.xdata is not None and event.ydata is not None:
            self.last_cursor_image_xy = (float(event.xdata), float(event.ydata))
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
        if event.inaxes == self.ax and event.xdata is not None and event.ydata is not None:
            self.last_cursor_image_xy = (float(event.xdata), float(event.ydata))
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
                ("ROI or atlas", "*.npz *.json *.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("ROI npz", "*.npz"),
                ("Atlas JSON", "*.json"),
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
            elif ext == ".json":
                vals = self.param_dialog("Atlas JSON ROI", [("min_area", "Min area", 50)])
                if not vals:
                    return
                rois, names = core.process_atlas_json(path, self.state.baseline_image.shape, int(vals["min_area"]))
                self.set_rois(rois, "Loaded atlas JSON", names=names)
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

    def atlas_reference_builder(self):
        if not NEUROALIGN_DIR.exists():
            messagebox.showerror("Atlas Reference Builder", f"NeuroAlign folder not found:\n{NEUROALIGN_DIR}")
            return
        dlg = AtlasReferenceBuilderDialog(self.root, self)
        vals = dlg.values
        if not vals:
            return
        self.user_settings["atlas_reference_builder"] = vals
        save_user_settings(self.user_settings)
        script = NEUROALIGN_DIR / "build_atlas_from_lines_autocomplete.py"

        def run():
            outdir = Path(vals["outdir"])
            args = [
                "--image", vals["image"],
                "--outdir", str(outdir),
                "--line_threshold", str(vals["line_threshold"]),
                "--auto_gap_bridge_dist", str(vals["auto_gap_bridge_dist"]),
                "--barrier_radius", str(vals["barrier_radius"]),
                "--min_region_area", str(vals["min_region_area"]),
            ]
            if vals["detect_dark_lines"]:
                args.append("--detect_dark_lines")
            log = run_backend_script(script, args, cwd=NEUROALIGN_DIR, timeout=600)
            atlas_json = outdir / "atlas_regions_raw.json"
            if not atlas_json.exists():
                raise RuntimeError("Atlas builder finished but did not create atlas_regions_raw.json")
            return {"atlas_json": str(atlas_json), "outdir": str(outdir), "log": log}

        self.run_worker("Atlas Reference Builder", run, self._finish_atlas_reference_builder)

    def _finish_atlas_reference_builder(self, result):
        self.last_atlas_reference_json = result["atlas_json"]
        self.log(f"Atlas Reference Builder saved: {result['atlas_json']}")
        try:
            rois, names = core.process_atlas_json(result["atlas_json"], self.state.baseline_image.shape, 50)
            self.set_rois(rois, "Atlas reference preview", names=names)
        except Exception as exc:
            self.log(f"Atlas reference built, but preview import failed: {exc}")
        log = str(result.get("log", "")).strip()
        if log:
            self.log(log[-800:])

    def neuroalign(self):
        if not self.require_movie():
            return
        if not NEUROALIGN_DIR.exists():
            messagebox.showerror("NeuroAlign", f"NeuroAlign folder not found:\n{NEUROALIGN_DIR}")
            return
        default_video = self.state.source_path if self.state.source_path else ""
        default_atlas = self.last_atlas_reference_json
        if not default_atlas:
            candidate = NEUROALIGN_DIR / "atlas_regions_raw.json"
            default_atlas = str(candidate) if candidate.exists() else ""
        saved = self.user_settings.get("neuroalign", {})
        defaults = {
            "video": saved.get("video") or default_video,
            "atlas_json": saved.get("atlas_json") or default_atlas,
            "outdir": saved.get("outdir") or default_neuroalign_outdir("neuroalign"),
            "cfg": saved.get("cfg", neuroalign_recommended_cfg()),
        }
        wizard = NeuroAlignWizard(self.root, self, defaults)
        self.root.wait_window(wizard)
        if wizard.values:
            self._finish_neuroalign(wizard.values)

    def run_neuroalign_backend(self, vals):
        script = NEUROALIGN_DIR / "atlas_registration_merged_bilateral_midline.py"
        outdir = Path(vals["outdir"])
        cfg_path = outdir / "neuroalign_config.json"
        outdir.mkdir(parents=True, exist_ok=True)
        check_neuroalign_registration_backend()
        bundle = {
            "preset": "balanced",
            "video": vals["video"],
            "atlas_json": vals["atlas_json"],
            "outdir": str(outdir),
            "cfg": vals["cfg"],
        }
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        log = run_backend_script(
            script,
            [
                "--config", str(cfg_path),
                "--video", vals["video"],
                "--atlas_json", vals["atlas_json"],
                "--outdir", str(outdir),
            ],
            cwd=NEUROALIGN_DIR,
            timeout=None,
        )
        warped_json = outdir / "warped_atlas_regions.json"
        if not warped_json.exists():
            raise RuntimeError("NeuroAlign finished but did not create warped_atlas_regions.json")
        return {"warped_json": str(warped_json), "outdir": str(outdir), "config": str(cfg_path), "log": log}

    def _finish_neuroalign(self, result):
        self.last_neuroalign_output_dir = result["outdir"]
        rois, names = core.process_atlas_json(result["warped_json"], self.state.baseline_image.shape, 50)
        self.set_rois(rois, "NeuroAlign", names=names)
        self.log(f"NeuroAlign loaded warped atlas ROIs: {result['warped_json']}")
        log = str(result.get("log", "")).strip()
        if log:
            self.log(log[-800:])

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
        image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        min_area_default = 20
        max_area_default = 4000
        if image is not None and self.last_cursor_image_xy is not None:
            estimate = core.estimate_auto_roi_area_range(image, self.last_cursor_image_xy)
            if estimate is not None:
                min_area_default, max_area_default = estimate
                x, y = self.last_cursor_image_xy
                cell_area_est = (min_area_default / 0.5 + max_area_default / 2.5) / 2.0
                cell_diameter_est = 2.0 * float(np.sqrt(cell_area_est / np.pi))
                self.log(
                    f"Built-in auto ROI seed ({x:.1f}, {y:.1f}) suggests area {min_area_default}-{max_area_default} px^2 "
                    f"(~{cell_area_est:.0f} px^2, ~{cell_diameter_est:.1f} px diameter)."
                )
        dlg = BuiltInAutoROIDialog(
            self.root,
            self,
            "Built-in Auto ROI",
            default_min_area=min_area_default,
            default_max_area=max_area_default,
        )
        vals = dlg.values
        if not vals:
            return
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
        dlg = NeuroSeg3Dialog(self.root, "NeuroSeg3 ROI", weights, default_weight=default_weight, default_conf=0.002)
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
                    messagebox.showerror("Worker failed", self.worker_error_summary(str(exc)))
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
