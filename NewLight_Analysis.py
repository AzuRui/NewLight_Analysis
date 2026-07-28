from __future__ import annotations

import atexit
import json
import os
import queue
import random
import shutil
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
import roi_adaptation as roi_fit
import ui_background
from task_queue import TaskCancelled, TaskController, TaskState
from ui_text_zh import MODEL_NAMES, PREPROCESS_PANEL_SPECS, ROI_STAT_COLUMN_LABELS


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

CHANNEL_COLOR_HEX = {
    "green": "#22c55e",
    "red": "#ef4444",
    "yellow": "#facc15",
    "blue": "#3b82f6",
    "purple": "#a855f7",
    "gray": "#9ca3af",
}
CHANNEL_COLOR_LABELS = {
    "green": "绿色",
    "red": "红色",
    "yellow": "黄色",
    "blue": "蓝色",
    "purple": "紫色",
    "gray": "灰色",
}
CHANNEL_COLOR_ORDER = ("green", "red", "yellow", "blue", "purple", "gray")
MAX_CHANNELS = 5
SIDEBAR_WIDTH = 300
PARAM_PANEL_WIDTH = 290
PARAMETER_TEXT_WIDTH = PARAM_PANEL_WIDTH - 56

APP_DIR = Path(__file__).resolve().parent
NEUROALIGN_DIR = core.NEUROALIGN_DIR
NEUROALIGN_ENV = "caiman_latest"
NEUROALIGN_HELP_PATH = core.APP_RESOURCE_DIR / "NeuroAlign_atlas_registration_help.txt"
NEUROALIGN_SUMMARY_PATH = core.APP_RESOURCE_DIR / "NeuroAlign_atlas_registration_summary.json"
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
        "mask_min_area_frac": 0.06,
        "mask_max_area_frac": 0.78,
        "mask_max_center_fill_frac": 0.45,
        "outer_resample_n": 128,
        "outer_anchor_count": 16,
        "midline_anchor_count": 14,
        "midline_anchor_weight": 8,
        "outer_anchor_weight": 0.5,
        "functional_unit_mm": 1.20,
        "compactness": 9.0,
        "resolution": 0.38,
        "min_n_segments": 320,
        "max_n_segments": 3600,
        "min_cluster_size_superpixels": 12,
        "sparsity_percentile": 94.0,
        "symmetry_reward": 0.30,
        "distance_decay_scale": 0.50,
        "inner_max_pairs_per_hemi": 180,
        "tps_smooth": 3,
        "tps_smooth_candidates": "12,8,5,3,1",
        "min_inner_ctrl_for_tps": 4,
        "max_ctrl_shift_px": 24,
        "auto_rerun_max_attempts": 8,
        "auto_rerun_force_min_inner": 5,
        "adaptive_search_dist_min": 6.0,
        "adaptive_search_dist_max": 40.0,
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
        "NeuroAlign 帮助文件不可用。\n\n"
        "请检查 NewLight_Analysis 目录中的 NeuroAlign_atlas_registration_summary.json。"
    )


def clean_backend_log(text: str) -> str:
    cleaned = []
    skip_next = False
    for line in str(text).splitlines():
        stripped = line.strip()
        if skip_next:
            skip_next = False
            continue
        if "FutureWarning:" in line:
            skip_next = True
            continue
        if "OpenCL" in line and "vendors" in line and "temp.txt" in line:
            continue
        if stripped in {"Access is denied.", "The system cannot find the file specified."}:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def run_backend_script(script_path: Path, args: list[str], cwd: Path | None = None, timeout: int | None = None) -> str:
    proc = core.run_conda_worker(
        NEUROALIGN_ENV,
        str(script_path),
        [str(arg) for arg in args],
        cwd=str(cwd) if cwd else None,
        timeout=timeout,
    )
    log = clean_backend_log((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else ""))
    if proc.returncode != 0:
        if (
            "No module named 'igraph'" in log
            or "No module named 'leidenalg'" in log
            or "igraph is required" in log
            or "leidenalg is required" in log
        ):
            log = (
                log.strip()
                + "\n\nNeuroAlign 后端缺少图聚类依赖。"
                + f"请在 `{NEUROALIGN_ENV}` 环境中安装后重试。"
            )
        raise RuntimeError(log.strip() or f"{script_path.name} 运行失败，退出码 {proc.returncode}")
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
            + f"\n\nNeuroAlign 配准需要 `{NEUROALIGN_ENV}` 环境中的 `python-igraph` 和 `leidenalg`。"
        )


def translated_toolbar_items():
    translations = {
        "Home": ("主页", "重置到原始视图"),
        "Back": ("后退", "返回上一视图"),
        "Forward": ("前进", "前往下一视图"),
        "Pan": ("平移", "按住左键平移，按住右键缩放"),
        "Zoom": ("缩放", "框选区域进行缩放"),
        "Save": ("保存", "保存图像"),
    }
    items = []
    for text, tooltip, image_file, callback in NavigationToolbar2Tk.toolitems:
        if text == "Subplots":
            continue
        shown_text, shown_tooltip = translations.get(text, (text, tooltip))
        items.append((shown_text, shown_tooltip, image_file, callback))
    return tuple(items)


class ImageToolbar(NavigationToolbar2Tk):
    toolitems = translated_toolbar_items()

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
    style.configure("Sidebar.TButton", anchor="center", padding=(8, 5))
    style.map("TButton", background=[("active", THEME["panel_3"]), ("pressed", "#0f2742")], foreground=[("active", "#ffffff")])
    style.configure("Accent.TButton", background="#0e7490", foreground="#ecfeff", bordercolor=THEME["accent"], padding=(10, 5))
    style.map("Accent.TButton", background=[("active", "#0891b2"), ("pressed", "#155e75")])
    style.configure("TRadiobutton", background=THEME["panel"], foreground=THEME["text"], indicatorcolor=THEME["entry"], padding=2)
    style.map("TRadiobutton", background=[("active", THEME["panel_2"])], foreground=[("active", "#ffffff")])
    style.configure("TCheckbutton", background=THEME["panel"], foreground=THEME["text"], indicatorcolor=THEME["entry"], padding=2)
    style.map("TCheckbutton", background=[("active", THEME["panel_2"])])
    style.configure("TEntry", fieldbackground=THEME["entry"], foreground=THEME["text"], insertcolor=THEME["accent"], bordercolor=THEME["border"])
    # Tk does not support true per-pixel transparency for ttk comboboxes;
    # matching the parent panel makes every combobox blend into the UI.
    style.configure(
        "TCombobox",
        fieldbackground=THEME["panel"],
        background=THEME["panel"],
        foreground=THEME["text"],
        arrowcolor=THEME["accent"],
        bordercolor=THEME["border"],
        lightcolor=THEME["panel"],
        darkcolor=THEME["panel"],
        selectbackground=THEME["panel_2"],
        selectforeground=THEME["text"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", THEME["panel"]), ("disabled", THEME["panel"])],
        background=[("active", THEME["panel_2"]), ("readonly", THEME["panel"])],
        foreground=[("readonly", THEME["text"]), ("disabled", THEME["muted"])],
    )
    root.option_add("*TCombobox*Listbox.background", THEME["panel"])
    root.option_add("*TCombobox*Listbox.foreground", THEME["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", THEME["panel_2"])
    root.option_add("*TCombobox*Listbox.selectForeground", THEME["text"])
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
        for _ in range(24):
            self.stars.append({
                "x": rng.randint(4, width - 4),
                "y": rng.randint(4, height - 4),
                "r": rng.choice([0.45, 0.55, 0.65]),
                "phase": rng.random() * 6.28,
                "speed": rng.uniform(0.012, 0.038),
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
            color = s["tone"] if pulse > 0.70 else "#24415f"
            r = s["r"]
            self.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="")
            if pulse > 0.992 and idx % 13 == 0:
                self.create_line(x - 2, y, x + 2, y, fill=color)
                self.create_line(x, y - 2, x, y + 2, fill=color)
        self.create_text(16, 26, anchor="w", text="NewLight_Analysis", fill="#f8fafc", font=("Segoe UI Semibold", 17))
        self.create_text(16, 54, anchor="w", text="神经影像分析工作站", fill=THEME["accent"], font=("Segoe UI", 9))
        self.create_text(16, 80, anchor="w", text="ROI | 运动矫正 | dF/F | 热图", fill=THEME["muted"], font=("Segoe UI", 9))

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
        ttk.Button(buttons, text="取消", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="应用", command=self._apply).grid(row=0, column=1)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _apply(self):
        self.values = {k: e.get() for k, e in self.entries.items()}
        self.destroy()


class SourcePickerDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("打开数据")
        self.configure(bg=THEME["bg"])
        self.resizable(False, False)
        self.choice = None
        body = ttk.Frame(self, padding=14)
        body.grid(row=0, column=0, sticky="nsew")
        ttk.Label(body, text="请选择视频文件或双光子原始数据文件夹。").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        ttk.Button(body, text="选择文件", command=lambda: self._choose("file")).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(body, text="选择文件夹", command=lambda: self._choose("folder")).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(body, text="取消", command=self.destroy).grid(row=1, column=2, sticky="ew")
        self.transient(parent)
        self.grab_set()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.wait_window(self)

    def _choose(self, choice):
        self.choice = choice
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
        ttk.Button(buttons, text="关闭", command=self.destroy).grid(row=0, column=0)
        self.transient(parent)


class AtlasReferenceBuilderDialog(tk.Toplevel):
    def __init__(self, parent, app, default_image="", default_outdir=""):
        super().__init__(parent)
        self.title("标准图谱构建")
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

        image_entry = self._path_row(body, 0, "图谱线稿图像", self.image_var, self.browse_image)
        self._path_row(body, 1, "输出文件夹", self.outdir_var, self.browse_outdir)

        fields = [
            ("线条阈值", self.line_threshold_var),
            ("断点连接距离 (px)", self.bridge_dist_var),
            ("边界扩张半径", self.barrier_radius_var),
            ("最小区域面积", self.min_region_area_var),
        ]
        for idx, (label, var) in enumerate(fields, start=2):
            ttk.Label(body, text=label).grid(row=idx, column=0, sticky="w", pady=4)
            ttk.Entry(body, textvariable=var, width=16).grid(row=idx, column=1, sticky="ew", pady=4, padx=(8, 0))

        ttk.Checkbutton(body, text="检测深色线条", variable=self.detect_dark_lines_var).grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(8, 2)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="帮助", command=self.show_help).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="取消", command=self.destroy).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="运行", command=self._apply).grid(row=0, column=2)

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
        ttk.Button(path_row, text="浏览", command=browse_command).grid(row=0, column=1, padx=(8, 0))
        return entry

    def browse_image(self):
        path = filedialog.askopenfilename(
            title="选择图谱线稿图像",
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("所有文件", "*.*")],
        )
        if path:
            self.image_var.set(path)

    def browse_outdir(self):
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.outdir_var.set(path)

    def show_help(self):
        TextDisplayDialog(self, "NeuroAlign 帮助", load_neuroalign_help_text())

    def _apply(self):
        try:
            image = Path(self.image_var.get().strip())
            outdir = Path(self.outdir_var.get().strip())
            if not image.exists():
                raise ValueError("图谱线稿图像不存在。")
            if not str(outdir):
                raise ValueError("必须选择输出文件夹。")
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
            messagebox.showerror("标准图谱构建", str(exc))
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
        self.title("NeuroAlign 脑图谱配准")
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

        video_entry = self._path_row(body, 0, "待配准视频", self.video_var, self.browse_video)
        self._path_row(body, 1, "Atlas JSON", self.atlas_json_var, self.browse_atlas_json)
        self._path_row(body, 2, "输出文件夹", self.outdir_var, self.browse_outdir)

        labels = [
            ("brain_mask_percentile", "脑区蒙版百分位"),
            ("midline_anchor_count", "中线锚点数量"),
            ("midline_anchor_weight", "中线权重"),
            ("outer_anchor_weight", "外轮廓权重"),
            ("tps_smooth", "TPS 平滑度"),
            ("max_ctrl_shift_px", "最大控制点位移 (px)"),
            ("min_inner_ctrl_for_tps", "最少内部控制点"),
            ("auto_rerun_max_attempts", "自动重试次数"),
        ]
        for idx, (key, label) in enumerate(labels, start=3):
            ttk.Label(body, text=label).grid(row=idx, column=0, sticky="w", pady=3)
            ttk.Entry(body, textvariable=self.cfg_vars[key], width=16).grid(
                row=idx, column=1, sticky="ew", padx=(8, 0), pady=3
            )

        buttons = ttk.Frame(body)
        buttons.grid(row=11, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="帮助", command=self.show_help).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="取消", command=self.destroy).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(buttons, text="运行", command=self._apply).grid(row=0, column=2)

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
        ttk.Button(path_row, text="浏览", command=browse_command).grid(row=0, column=1, padx=(8, 0))
        return entry

    def browse_video(self):
        path = filedialog.askopenfilename(
            title="选择待配准视频",
            filetypes=[("视频文件", "*.avi *.mp4"), ("所有文件", "*.*")],
        )
        if path:
            self.video_var.set(path)

    def browse_atlas_json(self):
        path = filedialog.askopenfilename(
            title="选择 Atlas JSON",
            filetypes=[("Atlas JSON", "*.json"), ("所有文件", "*.*")],
        )
        if path:
            self.atlas_json_var.set(path)

    def browse_outdir(self):
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.outdir_var.set(path)

    def show_help(self):
        TextDisplayDialog(self, "NeuroAlign 帮助", load_neuroalign_help_text())

    def _apply(self):
        try:
            video = Path(self.video_var.get().strip())
            atlas_json = Path(self.atlas_json_var.get().strip())
            outdir = Path(self.outdir_var.get().strip())
            if not video.exists():
                raise ValueError("待配准视频不存在。")
            if not atlas_json.exists():
                raise ValueError("Atlas JSON 不存在。")
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
            messagebox.showerror("NeuroAlign 脑图谱配准", str(exc))
            return
        self.destroy()


class NeuroAlignWizard(tk.Toplevel):
    STAGES = ("outer", "cluster", "final")

    def __init__(self, parent, app, defaults: dict):
        super().__init__(parent)
        self.app = app
        self.values = None
        self.title("NeuroAlign 脑图谱配准")
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
        recommended_cfg = neuroalign_recommended_cfg()
        cfg_keys = [
            "brain_mask_percentile",
            "mask_min_area_frac",
            "mask_max_area_frac",
            "mask_max_center_fill_frac",
            "outer_resample_n",
            "outer_anchor_count",
            "midline_anchor_count",
            "midline_anchor_weight",
            "outer_anchor_weight",
            "functional_unit_mm",
            "resolution",
            "compactness",
            "min_n_segments",
            "max_n_segments",
            "min_cluster_size_superpixels",
            "sparsity_percentile",
            "symmetry_reward",
            "distance_decay_scale",
            "inner_max_pairs_per_hemi",
            "tps_smooth",
            "max_ctrl_shift_px",
            "min_inner_ctrl_for_tps",
            "auto_rerun_max_attempts",
            "adaptive_search_dist_min",
            "adaptive_search_dist_max",
            "adaptive_search_quantile_min",
            "adaptive_search_quantile_max",
        ]
        self.cfg_vars = {}
        for key in cfg_keys:
            value = cfg.get(key, recommended_cfg.get(key, ""))
            if value is None or str(value).strip() == "":
                value = recommended_cfg.get(key, "")
            self.cfg_vars[key] = tk.StringVar(value=str(value))

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

        self.input_frame = ttk.LabelFrame(left, text="输入", padding=8)
        self.input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.input_frame.columnconfigure(1, weight=1)
        self._path_row(self.input_frame, 0, "待配准视频", self.video_var, self.browse_video)
        self._path_row(self.input_frame, 1, "Atlas JSON", self.atlas_json_var, self.browse_atlas_json)
        self._path_row(self.input_frame, 2, "输出文件夹", self.outdir_var, self.browse_outdir)

        self.param_frame = ttk.LabelFrame(left, text="参数", padding=8)
        self.param_frame.grid(row=2, column=0, sticky="nsew")
        self.param_frame.columnconfigure(1, weight=1)
        left.rowconfigure(2, weight=1)

        buttons = ttk.Frame(left)
        buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        buttons.columnconfigure((0, 1, 2, 3), weight=1)
        ttk.Button(buttons, text="帮助", command=self.show_help).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.back_button = ttk.Button(buttons, text="上一步", command=self.prev_stage)
        self.back_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.rebuild_button = ttk.Button(buttons, text="重新构建", command=self.rebuild)
        self.rebuild_button.grid(row=0, column=2, sticky="ew", padx=4)
        self.next_button = ttk.Button(buttons, text="下一步", command=self.next_stage)
        self.next_button.grid(row=0, column=3, sticky="ew", padx=(4, 0))
        ttk.Button(buttons, text="取消", command=self.destroy).grid(row=1, column=0, sticky="ew", pady=(6, 0), padx=(0, 4))
        ttk.Button(buttons, text="使用结果", command=self.accept).grid(row=1, column=1, columnspan=3, sticky="ew", pady=(6, 0), padx=(4, 0))

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(right, bg="#020617", highlightthickness=1, highlightbackground=THEME["border"])
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_caption = tk.StringVar(value="点击“重新构建”生成预览。")
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
        ttk.Button(holder, text="浏览", command=command).grid(row=0, column=1, padx=(6, 0))

    def browse_video(self):
        path = filedialog.askopenfilename(title="选择待配准视频", filetypes=[("视频文件", "*.avi *.mp4 *.mov *.mkv"), ("所有文件", "*.*")])
        if path:
            self.video_var.set(path)

    def browse_atlas_json(self):
        path = filedialog.askopenfilename(title="选择 Atlas JSON", filetypes=[("Atlas JSON", "*.json"), ("所有文件", "*.*")])
        if path:
            self.atlas_json_var.set(path)

    def browse_outdir(self):
        path = filedialog.askdirectory(title="选择输出文件夹")
        if path:
            self.outdir_var.set(path)

    def show_help(self):
        TextDisplayDialog(self, "NeuroAlign 帮助", load_neuroalign_help_text())

    def stage_fields(self):
        if self.current_stage == "outer":
            return [
                ("brain_mask_percentile", "脑区蒙版百分位"),
                ("mask_min_area_frac", "蒙版最小面积比例"),
                ("mask_max_area_frac", "蒙版最大面积比例"),
                ("mask_max_center_fill_frac", "中心最大填充比例"),
                ("outer_resample_n", "外轮廓重采样点数"),
                ("outer_anchor_count", "外轮廓锚点数量"),
                ("outer_anchor_weight", "外轮廓权重"),
            ]
        if self.current_stage == "cluster":
            return [
                ("functional_unit_mm", "功能单元尺寸 (mm)"),
                ("resolution", "聚类分辨率"),
                ("compactness", "SLIC 紧凑度"),
                ("min_n_segments", "最少分割数"),
                ("max_n_segments", "最多分割数"),
                ("min_cluster_size_superpixels", "最小聚类大小"),
                ("sparsity_percentile", "稀疏度百分位"),
                ("symmetry_reward", "对称性奖励"),
                ("distance_decay_scale", "距离衰减尺度"),
                ("inner_max_pairs_per_hemi", "单侧最大内部配对"),
            ]
        return [
            ("midline_anchor_count", "中线锚点数量"),
            ("midline_anchor_weight", "中线权重"),
            ("max_ctrl_shift_px", "最大控制点位移 (px)"),
            ("tps_smooth", "TPS 平滑度"),
            ("min_inner_ctrl_for_tps", "最少内部控制点"),
            ("adaptive_search_dist_min", "最小搜索距离"),
            ("adaptive_search_dist_max", "最大搜索距离"),
            ("adaptive_search_quantile_min", "最小搜索分位"),
            ("adaptive_search_quantile_max", "最大搜索分位"),
            ("auto_rerun_max_attempts", "自动重试次数"),
        ]

    def render_stage(self):
        for child in self.param_frame.winfo_children():
            child.destroy()
        stage_name = {"outer": "第 1/3 步：外轮廓拟合", "cluster": "第 2/3 步：聚类预览", "final": "第 3/3 步：最终图谱预览"}[self.current_stage]
        self.stage_var.set(stage_name)
        for row, (key, label) in enumerate(self.stage_fields()):
            ttk.Label(self.param_frame, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(self.param_frame, textvariable=self.cfg_vars[key], width=14).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        self.back_button.configure(state="disabled" if self.current_stage == "outer" else "normal")
        self.next_button.configure(text="完成" if self.current_stage == "final" else "下一步")
        self.refresh_preview()

    def current_config(self):
        cfg = neuroalign_recommended_cfg()
        for key, var in self.cfg_vars.items():
            raw = var.get().strip()
            if raw == "":
                continue
            if key in {
                "outer_resample_n",
                "outer_anchor_count",
                "midline_anchor_count",
                "min_inner_ctrl_for_tps",
                "auto_rerun_max_attempts",
                "min_n_segments",
                "max_n_segments",
                "min_cluster_size_superpixels",
                "inner_max_pairs_per_hemi",
            }:
                cfg[key] = int(float(raw))
            else:
                cfg[key] = float(raw)
        return cfg

    def collect_values(self):
        video = Path(self.video_var.get().strip())
        atlas_json = Path(self.atlas_json_var.get().strip())
        outdir = Path(self.outdir_var.get().strip())
        if not video.exists():
            raise ValueError("待配准视频不存在。")
        if not atlas_json.exists():
            raise ValueError("Atlas JSON 不存在。")
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
            messagebox.showerror("NeuroAlign 脑图谱配准", str(exc))
            return
        self.app.user_settings["neuroalign"] = vals
        save_user_settings(self.app.user_settings)
        stage = self.current_stage
        self.running = True
        self.rebuild_button.configure(state="disabled")
        stage_name = {"outer": "外轮廓", "cluster": "聚类", "final": "最终图谱"}[stage]
        self.preview_caption.set(f"正在运行 NeuroAlign {stage_name}阶段...")
        self.log(f"开始重新构建：{stage_name}阶段。")

        self.app.run_worker(
            f"NeuroAlign {stage_name}阶段",
            lambda: self.app.run_neuroalign_backend(vals, stage=stage),
            lambda result: self.rebuild_done(result, None),
            on_error=lambda exc: self.rebuild_done(None, exc),
            on_cancel=self.rebuild_cancelled,
        )

    def rebuild_cancelled(self):
        self.running = False
        self.rebuild_button.configure(state="normal")
        self.preview_caption.set("已取消重新构建，可调整参数后再次运行。")
        self.log("NeuroAlign 重新构建已取消。")

    def rebuild_done(self, result, exc):
        self.running = False
        self.rebuild_button.configure(state="normal")
        if exc:
            self.log(f"后台处理失败：{exc}")
            messagebox.showerror("NeuroAlign 脑图谱配准", self.app.worker_error_summary(str(exc)))
            self.preview_caption.set("重新构建失败，请查看日志。")
            return
        self.current_result = result
        self.last_run_log = str(result.get("log", "")).strip()
        outdir = Path(result["outdir"])
        result_stage = result.get("stage", self.current_stage)
        if result_stage == "outer":
            self.create_outer_preview(outdir)
        elif result_stage == "cluster":
            self.create_cluster_preview(outdir)
        self.log(f"重新构建完成：{result.get('outdir')}")
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
            if path.exists():
                return path
            if self.current_result.get("stage") == "outer":
                for name in ("outer_fit_preview.png", "outer_registration_overlay.png", "subject_outer_mask.png"):
                    fallback = outdir / name
                    if fallback.exists():
                        return fallback
            return None
        final_path = outdir / "final_warp_overlay.png"
        if final_path.exists():
            return final_path
        cluster_path = outdir / "cluster_on_affine_preview.png"
        if not cluster_path.exists():
            self.create_cluster_preview(outdir)
        if cluster_path.exists():
            return cluster_path
        for name in ("outer_fit_preview.png", "outer_registration_overlay.png", "subject_outer_mask.png"):
            fallback = outdir / name
            if fallback.exists():
                return fallback
        return None

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
            self.preview_canvas.create_text(20, 20, anchor="nw", text="点击“重新构建”生成此预览。", fill=THEME["text"], font=("Segoe UI", 12))
            if self.current_stage == "cluster":
                self.preview_caption.set("尚未生成第 2 步预览，请点击“重新构建”生成聚类结果。")
            elif self.current_stage == "final":
                self.preview_caption.set("尚未生成第 3 步预览，请点击“重新构建”生成最终图谱。")
            return
        if not Path(path).exists():
            self.preview_canvas.create_text(20, 20, anchor="nw", text=f"未找到预览文件：\n{path}", fill=THEME["text"], font=("Segoe UI", 12))
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
            "outer": "外轮廓预览：仿射图谱轮廓叠加在均值图像上。",
            "cluster": "聚类预览：Leiden 聚类叠加仿射图谱边界，不显示均值图像。",
            "final": "最终图谱预览：变形后的图谱叠加在目标图像上。",
        }
        if self.current_stage == "cluster" and self.current_result and self.current_result.get("stage") == "outer" and path.name.startswith("outer_"):
            captions["cluster"] = "当前显示第 1 步外轮廓结果；重新构建后显示聚类预览。"
        if self.current_stage == "final" and path.name == "cluster_on_affine_preview.png":
            captions["final"] = "当前显示第 2 步聚类结果；重新构建后显示最终图谱。"
        elif self.current_stage == "final" and path.name.startswith("outer_"):
            captions["final"] = "当前显示前一阶段结果；重新构建后显示最终图谱。"
        self.preview_caption.set(captions[self.current_stage])

    def prev_stage(self):
        if self.current_stage == "final":
            self.current_stage = "cluster"
        elif self.current_stage == "cluster":
            self.current_stage = "outer"
        else:
            return
        self.render_stage()

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
        if not self.current_result or not self.current_result.get("warped_json"):
            messagebox.showwarning("NeuroAlign 脑图谱配准", "请先运行最终步骤，再使用配准结果。")
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

        ttk.Label(body, text="最小面积 (px^2)").grid(row=0, column=0, sticky="w", pady=4)
        min_entry = ttk.Entry(body, textvariable=self.min_area_var, width=18)
        min_entry.grid(row=0, column=1, sticky="ew", pady=4, padx=(8, 0))

        ttk.Label(body, text="最大面积 (px^2)").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(body, textvariable=self.max_area_var, width=18).grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))

        sample_row = ttk.Frame(body)
        sample_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        sample_row.columnconfigure(0, weight=1)
        ttk.Button(sample_row, text="使用最后 2 个 ROI", command=self.use_current_rois).grid(row=0, column=0, sticky="ew")
        ttk.Button(sample_row, text="恢复默认", command=self.reset_defaults).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ttk.Label(body, textvariable=self.status_var, style="Muted.TLabel", wraplength=300).grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0)
        )

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="应用", command=self._apply).grid(row=0, column=1)

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
        self.status_var.set("已恢复基于种子点估算的默认值。")

    def use_current_rois(self):
        masks = list(getattr(self.app.state, "roi_masks", []))
        if len(masks) < 2:
            messagebox.showwarning("内置自动 ROI", "请先绘制至少两个示例 ROI。")
            return
        areas = [int(np.count_nonzero(np.asarray(mask, dtype=bool))) for mask in masks[-2:]]
        areas = [area for area in areas if area > 0]
        if len(areas) < 2:
            messagebox.showwarning("内置自动 ROI", "最后两个 ROI 的面积必须大于 0。")
            return
        sample_min = max(3, int(round(min(areas) * 0.9)))
        sample_max = max(sample_min + 1, int(round(max(areas) * 1.1)))
        self.min_area_var.set(str(sample_min))
        self.max_area_var.set(str(sample_max))
        self.status_var.set(f"已根据最后两个 ROI 填入：{areas[0]} 和 {areas[1]} px^2。")
        self.app.log(f"内置自动 ROI 已根据最后两个 ROI 填入面积范围：{areas[0]}、{areas[1]} px^2 -> {sample_min}-{sample_max} px^2。")

    def _apply(self):
        try:
            min_area = max(3, int(float(self.min_area_var.get())))
            max_area = max(min_area + 1, int(float(self.max_area_var.get())))
        except Exception:
            messagebox.showerror("内置自动 ROI", "请输入有效的数字面积范围。")
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

        ttk.Label(body, text="检测置信度").grid(row=0, column=0, sticky="w", pady=4)
        conf_row = ttk.Frame(body)
        conf_row.grid(row=0, column=1, sticky="ew", pady=4)
        conf_row.columnconfigure(0, weight=1)
        self.conf_entry = ttk.Entry(conf_row, textvariable=self.conf_var, width=14)
        self.conf_entry.grid(row=0, column=0, sticky="ew")
        ttk.Label(conf_row, text="例如 0.002", style="Muted.TLabel").grid(row=0, column=1, padx=(8, 0))

        ttk.Label(body, text="蒙版像素阈值").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Label(body, text=f"固定为 {self._mask_threshold:.2f}", style="Muted.TLabel").grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(body, text="模型权重 (.pt)").grid(row=2, column=0, sticky="w", pady=4)
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
        ttk.Button(weight_row, text="浏览", command=self.browse_weights).grid(row=0, column=1, padx=(8, 0))

        ttk.Checkbutton(
            body,
            text="未检测到蒙版时使用内置方法",
            variable=self.fallback_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 4))

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="应用", command=self._apply).grid(row=0, column=1)

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
            "title": "选择 NeuroSeg3 模型权重",
            "filetypes": [("PyTorch 权重", "*.pt"), ("所有文件", "*.*")],
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
            messagebox.showerror("NeuroSeg3 自动 ROI 分割", "检测置信度必须是数字。")
            return
        if not (0.0 <= conf <= 1.0):
            messagebox.showerror("NeuroSeg3 自动 ROI 分割", "检测置信度必须位于 0 到 1 之间。")
            return
        self.values = {
            "conf": round(conf, 6),
            "weights": self.weights_var.get(),
            "fallback": bool(self.fallback_var.get()),
            "mask_threshold": self._mask_threshold,
        }
        self.destroy()


class HeatmapVideoDialog(tk.Toplevel):
    def __init__(self, app, dff):
        super().__init__(app.root)
        self.app = app
        self.title("生成热图 AVI")
        self.geometry("920x680")
        self.configure(bg=THEME["bg"])
        self.task = None
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
        self.status = tk.StringVar(value="就绪")
        self.dff = np.asarray(dff, dtype=np.float32)
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
            ("叠加透明度", self.alpha),
            ("平滑 sigma", self.sigma),
            ("低百分位", self.low),
            ("高百分位", self.high),
            ("最大显示强度", self.max_display),
        ]
        for r, (label, var) in enumerate(rows):
            ttk.Label(panel, text=label).grid(row=r, column=0, sticky="w", pady=3)
            entry = ttk.Entry(panel, textvariable=var, width=12)
            entry.grid(row=r, column=1, sticky="ew", pady=3, padx=(6, 0))
            entry.bind("<KeyRelease>", self.schedule_preview)
        ttk.Checkbutton(panel, text="显示色条", variable=self.show_colorbar, command=self.update_preview).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 2))
        ttk.Checkbutton(panel, text="仅显示热图", variable=self.heatmap_only, command=self.update_preview).grid(row=6, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Checkbutton(panel, text="仅显示 ROI", variable=self.roi_only, command=self.update_preview).grid(row=7, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(panel, text="预览帧").grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 2))
        self.frame_scale = ttk.Scale(panel, from_=0, to=self.app.state.movie.shape[0] - 1, orient="horizontal", command=self.on_frame_change)
        self.frame_scale.set(self.frame.get())
        self.frame_scale.grid(row=9, column=0, columnspan=2, sticky="ew")
        self.frame_label = ttk.Label(panel, text="")
        self.frame_label.grid(row=10, column=0, columnspan=2, sticky="w")
        ttk.Button(panel, text="刷新预览", command=self.update_preview).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(12, 3))
        ttk.Button(panel, text="保存 AVI", command=self.start_save).grid(row=12, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Button(panel, text="取消生成", command=self.cancel_generation).grid(row=13, column=0, columnspan=2, sticky="ew", pady=3)
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
            self.frame_label.configure(text=f"帧 {frame + 1}/{self.app.state.movie.shape[0]}")
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
            self.status.set("预览已更新")
        except Exception as exc:
            self.status.set(f"预览失败：{exc}")

    def start_save(self):
        if self.task is not None and self.task.state in {TaskState.QUEUED, TaskState.RUNNING, TaskState.CANCELLING}:
            return
        path = filedialog.asksaveasfilename(defaultextension=".avi", filetypes=[("AVI 视频", "*.avi")])
        if not path:
            return
        try:
            alpha, sigma, low, high, max_display = self.params()
        except Exception as exc:
            messagebox.showerror("热图 AVI", f"热图参数无效：{exc}")
            return
        mask = self.current_mask()
        movie = self.app.state.movie
        dff = self.dff
        fs = float(self.app.state.fs)
        show_colorbar = bool(self.show_colorbar.get())
        heatmap_only = bool(self.heatmap_only.get())
        self.progress.set(0)
        self.status.set("已加入任务流，等待生成 AVI...")

        def progress(done, total):
            self.app.post_ui_callback(self.on_progress, done, total)

        def worker(cancel_event):
            completed = core.save_heatmap_video(
                path,
                dff,
                movie,
                mask,
                fs,
                alpha=alpha,
                sigma=sigma,
                low_percentile=low,
                high_percentile=high,
                max_display=max_display,
                show_colorbar=show_colorbar,
                heatmap_only=heatmap_only,
                cancel_event=cancel_event,
                progress_callback=progress,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return path, completed

        self.task = self.app.enqueue_task(
            "生成热图 AVI",
            worker,
            lambda result: self.on_done(*result),
            on_cancel=self.on_cancelled,
        )

    def on_progress(self, done, total):
        self.progress.set(100 * done / max(1, total))
        self.status.set(f"正在生成 {done}/{total}")

    def on_done(self, path, completed):
        if completed:
            self.progress.set(100)
            self.status.set(f"已保存：{path}")
            self.app.log(f"热图 AVI 已保存：{path}")
        else:
            self.status.set("已取消生成")
            self.app.log("已取消生成热图 AVI。")

    def cancel_generation(self):
        if self.task is None:
            return
        self.task.cancel_event.set()
        if self.task is self.app.task_controller.current_task:
            self.app.cancel_current_task()
        self.status.set("正在取消热图 AVI 生成...")

    def on_cancelled(self):
        self.status.set("已取消生成")
        self.app.log("已取消生成热图 AVI。")


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
        self.session_temp_dir = Path(tempfile.mkdtemp(prefix="newlight_session_"))
        self._session_temp_cleaned = False
        atexit.register(self.cleanup_session_temp)
        self.mode = tk.StringVar(value="inspect")
        self.projection_mode = tk.StringVar(value="mean")
        self.status = tk.StringVar(value="就绪")
        self.task_controller = TaskController()
        self.ui_callback_queue = queue.Queue()
        self._task_flow_signature = None
        self.current_polygon = []
        self.freehand_drawing = False
        self.circle_start = None
        self.roi_view_refresh_pending = False
        self.inspect_pan_start = None
        self.last_cursor_image_xy = None
        self.preview_overlay = None
        self.current_frame = tk.IntVar(value=0)
        self.frame_label_var = tk.StringVar(value="帧 1/1")
        self.fs_var = tk.StringVar(value="10")
        self.stim_fs_var = tk.StringVar(value="2000")
        self.invalid_start_frames_var = tk.StringVar(value="0")
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
        self.deepcad_enabled_var = tk.BooleanVar(value=False)
        self.deepcad_weight_var = tk.StringVar(value="0.5")
        self.display_shadows_var = tk.StringVar(value="1")
        self.display_highlights_var = tk.StringVar(value="99")
        self.display_brightness_var = tk.StringVar(value="0")
        self.display_contrast_var = tk.StringVar(value="100")
        self.movie_import_depth_var = tk.StringVar(value="自动")
        self.deepcad_denoised_movie = None
        self.deepcad_cache_movie_id = None
        self.deepcad_cache_invalid_start_frames = None
        self.deepcad_projection_cache = {}
        self.deepcad_last_preview_weight = None
        self.deepcad_running = False
        self.deepcad_running_token = None
        self.deepcad_last_error = ""
        self.deepcad_request_token = 0
        self._display_limits_cache = {}
        self.display_source = ("projection", "mean")
        self._converted_frame_cache = (None, None, None)
        self._converted_projection_cache = {}
        self.channel_color_buttons = []
        self.channel_palette_popup = None
        self.parameter_panel = None
        self.parameter_scroll_canvas = None
        self.parameter_scrollbar = None
        self.parameter_scroll_window = None
        self.parameter_content = None
        self.task_flow_panel = None
        self.parameter_entries = {}
        self.parameter_vars = {}
        self.parameter_defaults = {}
        self.parameter_choice_values = {}
        self.parameter_choice_displays = {}
        self.parameter_apply_command = None
        self.parameter_cancel_command = None
        self.active_parameter_panel_id = None
        self.roi_table_images = []
        self.highlighted_roi_index = None
        self._view_limits = None
        self._view_is_fit = True
        self._view_lock = False
        self._setting_frame_scale = False
        self.user_settings = load_user_settings()
        self.last_roi_backend_result = None
        self.roi_candidate_banks = {"fast": None, "caiman": None}
        self.movie_generation = 0
        self.last_atlas_reference_json = ""
        self.last_neuroalign_output_dir = ""
        self.window_background = None
        self._build_ui()
        self.redraw(preserve_view=False)
        self._poll_worker()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(600, self.check_cuda_status_quick)

    def _build_ui(self):
        self.window_background = ui_background.WindowBackground(self.root, APP_DIR / "background.png")
        self.root.configure(bg=THEME["bg"])
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        side = ui_background.BackgroundPane(
            self.root,
            APP_DIR / "background.png",
            fallback_bg=THEME["panel"],
            overlay_color=THEME["panel"],
            overlay_alpha=0.45,
        )
        side.grid(row=0, column=0, sticky="ns")
        side.configure(width=SIDEBAR_WIDTH)
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)

        StarfieldCanvas(side).grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 12))

        tabs = ttk.Notebook(side)
        tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        flow_tab = ttk.Frame(tabs, padding=4)
        pre_tab = ttk.Frame(tabs, padding=4)
        roi_tab = ttk.Frame(tabs, padding=4)
        analysis_tab = ttk.Frame(tabs, padding=4)
        tabs.add(flow_tab, text="数据")
        tabs.add(pre_tab, text="预处理")
        tabs.add(roi_tab, text="ROI")
        tabs.add(analysis_tab, text="分析")
        for tab in (flow_tab, pre_tab, roi_tab, analysis_tab):
            tab.columnconfigure(0, weight=1)

        file_box = ttk.LabelFrame(flow_tab, text="数据", padding=8)
        file_box.grid(row=0, column=0, sticky="ew", pady=6)
        file_box.columnconfigure(1, weight=1)
        ttk.Button(file_box, text="打开数据", style="Sidebar.TButton", command=self.open_movie).grid(row=0, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(file_box, text="添加通道", style="Sidebar.TButton", command=self.add_channel_data).grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Label(file_box, text="导入位深").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Combobox(
            file_box,
            textvariable=self.movie_import_depth_var,
            values=("自动", "16-bit", "8-bit"),
            state="readonly",
            width=8,
        ).grid(row=2, column=1, sticky="ew", pady=2, padx=(6, 0))
        ttk.Button(file_box, text="打开刺激数据", style="Sidebar.TButton", command=self.open_stimulus).grid(row=3, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Button(file_box, text="保存当前视频", style="Sidebar.TButton", command=self.save_current_movie).grid(row=4, column=0, columnspan=2, sticky="ew", pady=2)

        view_box = ttk.LabelFrame(flow_tab, text="视图", padding=8)
        view_box.grid(row=1, column=0, sticky="ew", pady=6)
        view_box.columnconfigure(1, weight=1)
        for i, (text, value) in enumerate([("均值", "mean"), ("最大值", "max"), ("标准差", "std"), ("25% 分位", "p25")]):
            ttk.Radiobutton(view_box, text=text, variable=self.projection_mode, value=value, command=self.refresh_projection).grid(row=i // 2, column=i % 2, sticky="w")
        ttk.Checkbutton(view_box, text=MODEL_NAMES["deepcad_rt"], variable=self.deepcad_enabled_var, command=self.on_deepcad_toggle).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        weight_box = ttk.Frame(view_box)
        weight_box.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        weight_box.columnconfigure(1, weight=1)
        ttk.Label(weight_box, text="混合权重").grid(row=0, column=0, sticky="w", padx=(0, 4))
        weight_entry = ttk.Entry(weight_box, textvariable=self.deepcad_weight_var, width=6)
        weight_entry.grid(row=0, column=1, sticky="ew")
        weight_entry.bind("<KeyRelease>", lambda _event: self.on_deepcad_weight_edited())
        weight_entry.bind("<Return>", lambda _event: self.on_deepcad_weight_changed())
        weight_entry.bind("<FocusOut>", lambda _event: self.on_deepcad_weight_changed())
        ttk.Label(view_box, text="通道伪彩").grid(row=4, column=0, sticky="w", pady=(8, 0))
        channel_row = ttk.Frame(view_box)
        channel_row.grid(row=4, column=1, sticky="w", pady=(8, 0))
        self.channel_color_buttons = []
        for idx in range(MAX_CHANNELS):
            btn = tk.Button(
                channel_row,
                text=str(idx + 1),
                width=2,
                height=1,
                relief="solid",
                bd=1,
                command=lambda i=idx: self.choose_channel_color(i),
            )
            btn.grid(row=0, column=idx, padx=2)
            self.channel_color_buttons.append(btn)
        self.update_channel_color_buttons()

        protocol_box = ttk.LabelFrame(flow_tab, text="实验协议", padding=8)
        protocol_box.grid(row=2, column=0, sticky="ew", pady=6)
        protocol_box.columnconfigure(1, weight=1)
        protocol_rows = [
            ("视频帧率 (Hz)", self.fs_var),
            ("刺激采样率 (Hz)", self.stim_fs_var),
            ("无效起始帧数", self.invalid_start_frames_var),
            ("基线起始帧", self.baseline_start_var),
            ("基线持续帧数", self.baseline_duration_var),
            ("触发阈值", self.trigger_threshold_var),
            ("触发起始 (s)", self.trigger_start_var),
            ("触发间隔 (s)", self.trigger_interval_var),
            ("刺激前 (s)", self.pre_trigger_var),
            ("刺激后 (s)", self.post_trigger_var),
        ]
        for r, (label, var) in enumerate(protocol_rows):
            ttk.Label(protocol_box, text=label).grid(row=r, column=0, sticky="w", pady=1)
            ttk.Entry(protocol_box, textvariable=var, width=10).grid(row=r, column=1, sticky="ew", pady=1, padx=(6, 0))
        ttk.Button(protocol_box, text="应用协议", style="Sidebar.TButton", command=self.apply_protocol).grid(row=len(protocol_rows), column=0, columnspan=2, sticky="ew", pady=(6, 2))
        ttk.Button(protocol_box, text="检测刺激触发", style="Sidebar.TButton", command=self.detect_triggers).grid(row=len(protocol_rows) + 1, column=0, columnspan=2, sticky="ew", pady=2)

        pre_box = ttk.LabelFrame(pre_tab, text="预处理", padding=8)
        pre_box.grid(row=0, column=0, sticky="ew", pady=6)
        accel_box = ttk.LabelFrame(pre_tab, text="计算加速", padding=8)
        accel_box.grid(row=1, column=0, sticky="ew", pady=6)
        ttk.Radiobutton(accel_box, text="自动", variable=self.acceleration_var, value="auto").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(accel_box, text="CPU", variable=self.acceleration_var, value="cpu").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(accel_box, text="GPU", variable=self.acceleration_var, value="gpu").grid(row=0, column=2, sticky="w")
        ttk.Button(accel_box, text="检查 CUDA", style="Sidebar.TButton", command=self.check_cuda_status).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        for action_id, spec in PREPROCESS_PANEL_SPECS.items():
            row = len(pre_box.grid_slaves())
            ttk.Button(
                pre_box,
                text=spec["label"],
                style="Sidebar.TButton",
                command=lambda key=action_id: self.show_preprocess_parameters(key),
            ).grid(row=row, column=0, sticky="ew", pady=2)

        roi_box = ttk.LabelFrame(roi_tab, text="ROI 工具", padding=8)
        roi_box.grid(row=0, column=0, sticky="ew", pady=6)
        ttk.Button(roi_box, text=MODEL_NAMES["caiman_roi"], style="Sidebar.TButton", command=self.caiman_roi).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text=MODEL_NAMES["fast_roi"], style="Sidebar.TButton", command=self.fast_roi).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text=MODEL_NAMES["atlas_builder"], style="Sidebar.TButton", command=self.atlas_reference_builder).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text=MODEL_NAMES["neuroalign"], style="Sidebar.TButton", command=self.neuroalign).grid(row=3, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="图谱图像转 ROI", style="Sidebar.TButton", command=self.atlas_roi).grid(row=4, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="载入 ROI/图谱", style="Sidebar.TButton", command=self.load_roi).grid(row=5, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="保存 ROI (.npz)", style="Sidebar.TButton", command=self.save_roi).grid(row=6, column=0, sticky="ew", pady=2)
        ttk.Button(roi_box, text="清空 ROI", style="Sidebar.TButton", command=self.clear_rois).grid(row=7, column=0, sticky="ew", pady=2)

        analysis_box = ttk.LabelFrame(analysis_tab, text="分析", padding=8)
        analysis_box.grid(row=0, column=0, sticky="ew", pady=6)
        ttk.Button(analysis_box, text="提取 dF/F 曲线", style="Sidebar.TButton", command=self.extract_traces).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="峰值检测", style="Sidebar.TButton", command=self.peak_detection).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="ROI 相关性", style="Sidebar.TButton", command=self.roi_correlation).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="ROI 统计", style="Sidebar.TButton", command=self.show_roi_statistics).grid(row=3, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="刺激事件对齐平均", style="Sidebar.TButton", command=self.stimulus_event_average).grid(row=4, column=0, sticky="ew", pady=2)
        ttk.Button(analysis_box, text="生成热图 AVI", style="Sidebar.TButton", command=self.generate_heatmap_avi).grid(row=5, column=0, sticky="ew", pady=2)
        trace_box = ttk.LabelFrame(analysis_tab, text="dF/F 选项", padding=8)
        trace_box.grid(row=1, column=0, sticky="ew", pady=6)
        trace_box.columnconfigure(1, weight=1)
        ttk.Checkbutton(trace_box, text="基线校正", variable=self.trace_baseline_correct_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        ttk.Label(trace_box, text="基线窗口").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(trace_box, textvariable=self.trace_baseline_window_var, width=10).grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=2)
        ttk.Label(trace_box, text="移动平均窗口").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(trace_box, textvariable=self.trace_smooth_window_var, width=10).grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=2)

        export_box = ttk.LabelFrame(analysis_tab, text="导出", padding=8)
        export_box.grid(row=2, column=0, sticky="ew", pady=6)
        ttk.Button(export_box, text="导出曲线 CSV", style="Sidebar.TButton", command=self.export_traces_csv).grid(row=0, column=0, sticky="ew", pady=2)
        ttk.Button(export_box, text="导出曲线图 PNG", style="Sidebar.TButton", command=self.export_trace_plot_png).grid(row=1, column=0, sticky="ew", pady=2)
        ttk.Button(export_box, text="导出 ROI 统计", style="Sidebar.TButton", command=self.export_roi_statistics_table).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(export_box, text="导出相关性", style="Sidebar.TButton", command=self.export_correlation_outputs).grid(row=3, column=0, sticky="ew", pady=2)
        ttk.Button(export_box, text="导出 dF/F 热图", style="Sidebar.TButton", command=self.export_heatmap_png).grid(row=4, column=0, sticky="ew", pady=2)
        ttk.Button(export_box, text="导出 ROI 快照", style="Sidebar.TButton", command=self.export_roi_snapshot).grid(row=5, column=0, sticky="ew", pady=2)
        ttk.Button(export_box, text="导出摘要 JSON", style="Sidebar.TButton", command=self.export_summary_json).grid(row=6, column=0, sticky="ew", pady=2)

        main = ui_background.BackgroundPane(
            self.root,
            APP_DIR / "background.png",
            fallback_bg=THEME["bg"],
            overlay_color=THEME["bg"],
            overlay_alpha=0.32,
        )
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, minsize=PARAM_PANEL_WIDTH)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)
        self.parameter_panel = ttk.LabelFrame(main, text="参数", padding=8)
        self.parameter_panel.grid(row=0, column=0, rowspan=5, sticky="nsew", padx=(0, 10), pady=(10, 10))
        self.parameter_panel.configure(width=PARAM_PANEL_WIDTH)
        self.parameter_panel.grid_propagate(False)
        self.parameter_panel.columnconfigure(0, weight=1)
        self.parameter_panel.rowconfigure(0, weight=1)
        parameter_scroll_area = ttk.Frame(self.parameter_panel)
        parameter_scroll_area.grid(row=0, column=0, sticky="nsew")
        parameter_scroll_area.columnconfigure(0, weight=1)
        parameter_scroll_area.rowconfigure(0, weight=1)
        self.parameter_scroll_canvas = tk.Canvas(
            parameter_scroll_area,
            bg=THEME["panel"],
            highlightthickness=0,
            bd=0,
        )
        self.parameter_scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self.parameter_scrollbar = ttk.Scrollbar(
            parameter_scroll_area,
            orient="vertical",
            command=self.parameter_scroll_canvas.yview,
        )
        self.parameter_scrollbar.grid(row=0, column=1, sticky="ns", padx=(5, 0))
        self.parameter_scroll_canvas.configure(yscrollcommand=self.parameter_scrollbar.set)
        self.parameter_content = ttk.Frame(self.parameter_scroll_canvas)
        self.parameter_scroll_window = self.parameter_scroll_canvas.create_window(
            (0, 0),
            window=self.parameter_content,
            anchor="nw",
        )
        self.parameter_content.bind("<Configure>", self._on_parameter_content_configure)
        self.parameter_scroll_canvas.bind("<Configure>", self._on_parameter_scroll_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_parameter_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_parameter_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self._on_parameter_mousewheel, add="+")
        self.parameter_content.columnconfigure(0, weight=1)
        self._build_task_flow_panel()
        self.clear_parameter_panel()
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
        self.canvas.get_tk_widget().grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=(10, 0))
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
        self.nav_toolbar.grid(row=1, column=1, sticky="ew", padx=(0, 10))

        bottom = ttk.Frame(main, style="Toolbar.TFrame")
        bottom.grid(row=2, column=1, sticky="ew", padx=(0, 10), pady=(6, 0))
        bottom.columnconfigure(9, weight=1)
        ttk.Button(bottom, text="撤销", command=self.undo).grid(row=0, column=0, padx=3)
        ttk.Radiobutton(bottom, text="查看", variable=self.mode, value="inspect", command=self.on_mode_changed).grid(row=0, column=1, padx=3)
        ttk.Radiobutton(bottom, text="圆形 ROI", variable=self.mode, value="circle", command=self.on_mode_changed).grid(row=0, column=2, padx=3)
        ttk.Radiobutton(bottom, text="自由绘制 ROI", variable=self.mode, value="freehand", command=self.on_mode_changed).grid(row=0, column=3, padx=3)
        ttk.Radiobutton(bottom, text="点击删除 ROI", variable=self.mode, value="delete_roi", command=self.on_mode_changed).grid(row=0, column=4, padx=3)
        ttk.Button(bottom, text="取消绘制", command=self.cancel_freehand).grid(row=0, column=5, padx=3)
        ttk.Button(bottom, text="删除最后 ROI", command=self.delete_last_roi).grid(row=0, column=6, padx=3)
        ttk.Button(bottom, text="显示 ROI 列表", command=self.show_roi_list).grid(row=0, column=7, padx=3)
        ttk.Label(bottom, textvariable=self.status).grid(row=0, column=9, sticky="e")

        frame_bar = ttk.Frame(main, style="Toolbar.TFrame")
        frame_bar.grid(row=3, column=1, sticky="ew", padx=(0, 10), pady=(6, 0))
        frame_bar.columnconfigure(1, weight=1)
        ttk.Label(frame_bar, text="帧").grid(row=0, column=0, padx=(0, 6))
        self.frame_scale = ttk.Scale(frame_bar, from_=0, to=0, orient="horizontal", command=self.on_frame_slider)
        self.frame_scale.grid(row=0, column=1, sticky="ew")
        ttk.Label(frame_bar, textvariable=self.frame_label_var, width=14).grid(row=0, column=2, padx=(6, 0))

        log_box = ttk.LabelFrame(main, text="运行日志", padding=4)
        log_box.grid(row=4, column=1, sticky="ew", padx=(0, 10), pady=(8, 10))
        self.log_text = tk.Text(log_box, height=7, wrap="word")
        self.log_text.configure(bg=THEME["entry"], fg=THEME["text"], insertbackground=THEME["accent"], relief="flat", highlightthickness=1, highlightbackground=THEME["border"])
        self.log_text.pack(fill="both", expand=True)

        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)

    def _build_task_flow_panel(self):
        self.task_flow_panel = ttk.LabelFrame(self.parameter_panel, text="当前数据任务流", padding=5)
        self.task_flow_panel.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.task_flow_panel.columnconfigure(0, weight=1)

        controls = ttk.Frame(self.task_flow_panel)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        controls.columnconfigure(0, weight=1)
        self.task_flow_status_var = tk.StringVar(value="当前没有任务")
        ttk.Label(controls, textvariable=self.task_flow_status_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.cancel_task_button = ttk.Button(controls, text="取消当前任务", command=self.cancel_current_task)
        self.cancel_task_button.grid(row=0, column=1, sticky="e")

        body = tk.Frame(self.task_flow_panel, bg=THEME["panel"])
        body.grid(row=1, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)
        self.task_flow_canvas = tk.Canvas(
            body,
            height=185,
            bg=THEME["panel"],
            highlightthickness=1,
            highlightbackground=THEME["border"],
            bd=0,
        )
        self.task_flow_canvas.grid(row=0, column=0, sticky="ew")
        self.task_flow_scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.task_flow_canvas.yview)
        self.task_flow_scrollbar.grid(row=0, column=1, sticky="ns")
        self.task_flow_canvas.configure(yscrollcommand=self.task_flow_scrollbar.set)
        self.task_flow_inner = tk.Frame(self.task_flow_canvas, bg=THEME["panel"])
        self.task_flow_window = self.task_flow_canvas.create_window((0, 0), window=self.task_flow_inner, anchor="nw")
        self.task_flow_inner.bind("<Configure>", self._on_task_flow_inner_configure)
        self.task_flow_canvas.bind("<Configure>", self._on_task_flow_canvas_configure)
        self.render_task_flow(force=True)

    def _on_task_flow_inner_configure(self, _event=None):
        if self.task_flow_canvas is not None:
            self.task_flow_canvas.configure(scrollregion=self.task_flow_canvas.bbox("all"))

    def _on_task_flow_canvas_configure(self, event):
        if self.task_flow_canvas is not None:
            self.task_flow_canvas.itemconfigure(self.task_flow_window, width=event.width)

    def _on_parameter_content_configure(self, _event=None):
        if self.parameter_scroll_canvas is not None:
            self.parameter_scroll_canvas.configure(scrollregion=self.parameter_scroll_canvas.bbox("all"))

    def _on_parameter_scroll_canvas_configure(self, event):
        if self.parameter_scroll_canvas is not None:
            self.parameter_scroll_canvas.itemconfigure(self.parameter_scroll_window, width=event.width)
            self._on_parameter_content_configure()

    def _reset_parameter_scroll_position(self):
        if self.parameter_scroll_canvas is None:
            return
        self.root.after_idle(lambda: self.parameter_scroll_canvas.yview_moveto(0.0))

    def _on_parameter_mousewheel(self, event):
        canvas = self.parameter_scroll_canvas
        if canvas is None or not canvas.winfo_exists():
            return None
        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        left = canvas.winfo_rootx()
        top = canvas.winfo_rooty()
        if not (left <= pointer_x <= left + canvas.winfo_width() and top <= pointer_y <= top + canvas.winfo_height()):
            return None
        if getattr(event, "num", None) == 4:
            amount = -1
        elif getattr(event, "num", None) == 5:
            amount = 1
        else:
            delta = getattr(event, "delta", 0)
            if not delta:
                return None
            amount = -max(1, abs(delta) // 120) if delta > 0 else max(1, abs(delta) // 120)
        canvas.yview_scroll(amount, "units")
        return "break"

    def _task_flow_entry_style(self, task, is_last_completed):
        if task.state in {TaskState.RUNNING, TaskState.CANCELLING}:
            return "#ffffff", THEME["success"] if task.state == TaskState.RUNNING else THEME["warning"]
        if task.state == TaskState.QUEUED:
            return "#ffffff", THEME["border"]
        if task.state == TaskState.COMPLETED:
            return "#94a3b8", THEME["accent"] if is_last_completed else THEME["border"]
        if task.state == TaskState.FAILED:
            return THEME["warning"], THEME["warning"]
        return "#94a3b8", THEME["border"]

    def render_task_flow(self, force=False):
        if self.task_flow_panel is None:
            return
        history = self.task_controller.history
        current = self.task_controller.current_task
        pending = self.task_controller.pending_tasks
        signature = tuple((task.identifier, task.state.value, task.error or "") for task in history)
        if not force and signature == self._task_flow_signature:
            return
        self._task_flow_signature = signature
        for child in self.task_flow_inner.winfo_children():
            child.destroy()

        if current is not None:
            self.task_flow_status_var.set(f"正在执行：{current.label}")
            self.cancel_task_button.configure(state="normal" if current.cancellable else "disabled")
        elif pending:
            self.task_flow_status_var.set(f"等待执行：{len(pending)} 项")
            self.cancel_task_button.configure(state="disabled")
        else:
            self.task_flow_status_var.set("当前没有执行中的任务")
            self.cancel_task_button.configure(state="disabled")

        last_completed = history[-1] if history and current is None and not pending else None
        labels = {
            TaskState.QUEUED: "待执行",
            TaskState.RUNNING: "正在执行",
            TaskState.CANCELLING: "正在取消",
            TaskState.COMPLETED: "已完成",
            TaskState.CANCELLED: "已取消",
            TaskState.FAILED: "失败",
        }
        if not history:
            tk.Label(
                self.task_flow_inner,
                text="尚未提交任务",
                bg=THEME["panel"],
                fg=THEME["muted"],
                anchor="w",
            ).pack(fill="x", padx=5, pady=5)
        for task in history:
            fg, border = self._task_flow_entry_style(task, task is last_completed)
            item = tk.Frame(
                self.task_flow_inner,
                bg=THEME["panel_2"],
                highlightthickness=2 if task is current or task is last_completed else 1,
                highlightbackground=border,
                highlightcolor=border,
            )
            item.pack(fill="x", padx=3, pady=3)
            suffix = labels[task.state]
            if task.error:
                suffix = f"{suffix}: {self.status_summary(task.error, max_chars=70)}"
            tk.Label(item, text=task.label, bg=THEME["panel_2"], fg=fg, anchor="w").pack(fill="x", padx=6, pady=(4, 0))
            tk.Label(item, text=suffix, bg=THEME["panel_2"], fg=fg, anchor="w").pack(fill="x", padx=6, pady=(0, 4))
        self._on_task_flow_inner_configure()

    def cancel_current_task(self):
        if self.task_controller.cancel_current_task():
            self.log("已请求取消当前任务；后续已排队任务会继续保留。")
            self.render_task_flow(force=True)
        else:
            self.log("当前任务不支持立即取消，或没有正在执行的任务。")

    def post_ui_callback(self, callback, *args):
        """Allow a worker to request a small Tk-only progress update."""
        self.ui_callback_queue.put((callback, args))

    def clear_parameter_panel(self):
        leaving_roi_list = self.active_parameter_panel_id == "roi_list"
        self.active_parameter_panel_id = None
        self.roi_table_images = []
        if leaving_roi_list:
            self.clear_roi_highlight()
        if self.parameter_content is None:
            return
        for child in self.parameter_content.winfo_children():
            child.destroy()
        self.parameter_entries = {}
        self.parameter_vars = {}
        self.parameter_defaults = {}
        self.parameter_choice_values = {}
        self.parameter_choice_displays = {}
        self.parameter_apply_command = None
        self.parameter_cancel_command = None
        self.parameter_feedback_var = None
        self.parameter_feedback_label = None
        placeholder = ttk.Label(
            self.parameter_content,
            text="请从左侧选择功能，并在此调整参数。",
            style="Muted.TLabel",
            wraplength=PARAMETER_TEXT_WIDTH,
            justify="left",
        )
        placeholder.grid(row=0, column=0, sticky="new", pady=(0, 8))
        self._reset_parameter_scroll_position()

    @staticmethod
    def _parameter_field_spec(field):
        """Normalize compact legacy tuples and richer panel field dictionaries."""
        if isinstance(field, dict):
            spec = dict(field)
            spec.setdefault("type", "entry")
            return spec
        key, label, default = field[:3]
        return {
            "key": key,
            "label": label,
            "default": default,
            "choices": tuple(field[3]) if len(field) > 3 else (),
            "type": "entry",
        }

    def set_parameter_feedback(self, text="", error=False):
        if self.parameter_feedback_var is None:
            if text:
                self.log(text)
            return
        self.parameter_feedback_var.set(str(text))
        if self.parameter_feedback_label is not None:
            self.parameter_feedback_label.configure(fg=THEME["warning"] if error else THEME["muted"])

    def _browse_parameter_path(self, key, options):
        options = dict(options or {})
        directory = bool(options.pop("directory", False))
        if directory:
            path = filedialog.askdirectory(**options)
        else:
            path = filedialog.askopenfilename(**options)
        if path and key in self.parameter_vars:
            self.parameter_vars[key].set(path)

    def show_parameter_panel(
        self,
        title,
        fields,
        apply_command=None,
        description="",
        apply_text="运行",
        cancel_command=None,
        help_text="",
        panel_id=None,
    ):
        if self.parameter_content is None:
            return
        if self.active_parameter_panel_id == "roi_list" and panel_id != "roi_list":
            self.clear_roi_highlight()
        self.active_parameter_panel_id = panel_id
        self.roi_table_images = []
        for child in self.parameter_content.winfo_children():
            child.destroy()
        specs = [self._parameter_field_spec(field) for field in fields]
        self.parameter_entries = {}
        self.parameter_vars = {}
        self.parameter_defaults = {
            spec["key"]: spec.get("default")
            for spec in specs
            if spec.get("type", "entry") in {"entry", "checkbox", "path", "readonly"} and spec.get("key")
        }
        self.parameter_choice_values = {}
        self.parameter_choice_displays = {}
        self.parameter_apply_command = apply_command
        self.parameter_cancel_command = cancel_command
        self.parameter_feedback_var = tk.StringVar(value="")
        self.parameter_feedback_label = None
        self.parameter_panel.configure(text="参数")
        self.parameter_content.columnconfigure(0, weight=1)

        ttk.Label(self.parameter_content, text=title, style="Accent.TLabel", wraplength=PARAMETER_TEXT_WIDTH).grid(row=0, column=0, sticky="ew")
        row = 1
        if description:
            ttk.Label(
                self.parameter_content,
                text=description,
                style="Muted.TLabel",
                wraplength=PARAMETER_TEXT_WIDTH,
                justify="left",
            ).grid(row=row, column=0, sticky="ew", pady=(6, 10))
            row += 1
        if help_text:
            help_holder = ttk.Frame(self.parameter_content)
            help_holder.grid(row=row, column=0, sticky="ew", pady=(0, 6))
            help_holder.columnconfigure(0, weight=1)
            help_body = ttk.Label(
                help_holder,
                text=help_text,
                style="Muted.TLabel",
                wraplength=PARAMETER_TEXT_WIDTH,
                justify="left",
            )
            help_visible = tk.BooleanVar(value=False)

            def toggle_help():
                visible = not help_visible.get()
                help_visible.set(visible)
                if visible:
                    help_body.grid(row=1, column=0, sticky="ew", pady=(6, 0))
                    help_button.configure(text="收起参数说明")
                else:
                    help_body.grid_remove()
                    help_button.configure(text="查看参数说明")

            help_button = ttk.Button(help_holder, text="查看参数说明", command=toggle_help)
            help_button.grid(row=0, column=0, sticky="ew")
            row += 1
        for spec in specs:
            field_type = spec.get("type", "entry")
            key = spec.get("key")
            label = spec.get("label", "")
            default = spec.get("default", "")
            if field_type == "note":
                ttk.Label(
                    self.parameter_content,
                    text=spec.get("text", label),
                    style="Muted.TLabel",
                    wraplength=PARAMETER_TEXT_WIDTH,
                    justify="left",
                ).grid(row=row, column=0, sticky="ew", pady=4)
                row += 1
                continue
            if field_type == "action":
                ttk.Button(
                    self.parameter_content,
                    text=spec.get("text", label),
                    style=spec.get("style", "TButton"),
                    command=spec["command"],
                ).grid(row=row, column=0, sticky="ew", pady=4)
                row += 1
                continue
            if field_type == "color_palette":
                if label:
                    ttk.Label(self.parameter_content, text=label).grid(row=row, column=0, sticky="w", pady=(4, 2))
                    row += 1
                palette = tk.Frame(self.parameter_content, bg=THEME["panel"])
                palette.grid(row=row, column=0, sticky="ew", pady=2)
                for column in range(3):
                    palette.columnconfigure(column, weight=1)
                command = spec["command"]
                for index, color_name in enumerate(spec.get("colors", CHANNEL_COLOR_ORDER)):
                    color = CHANNEL_COLOR_HEX[color_name]
                    tk.Button(
                        palette,
                        text="",
                        height=2,
                        bg=color,
                        activebackground=color,
                        relief="solid",
                        bd=1,
                        command=lambda name=color_name: command(name),
                    ).grid(row=index // 3, column=index % 3, sticky="ew", padx=3, pady=3)
                delete_command = spec.get("delete_command")
                if delete_command is not None:
                    tk.Button(
                        palette,
                        text="删除通道",
                        bg=THEME["panel_2"],
                        activebackground=THEME["panel_3"],
                        fg=THEME["text"],
                        activeforeground="#ffffff",
                        relief="solid",
                        bd=1,
                        command=delete_command,
                    ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=3, pady=(7, 3))
                row += 1
                continue
            if field_type == "buttons":
                item = ttk.Frame(self.parameter_content)
                item.grid(row=row, column=0, sticky="ew", pady=4)
                actions = tuple(spec.get("actions", ()))
                columns = max(1, int(spec.get("columns", 2)))
                for column in range(columns):
                    item.columnconfigure(column, weight=1)
                for index, action in enumerate(actions):
                    action_text, action_command = action[:2]
                    action_style = action[2] if len(action) > 2 else "TButton"
                    ttk.Button(item, text=action_text, style=action_style, command=action_command).grid(
                        row=index // columns,
                        column=index % columns,
                        sticky="ew",
                        padx=(0 if index % columns == 0 else 3, 3 if index % columns < columns - 1 else 0),
                        pady=2,
                    )
                row += 1
                continue
            if field_type == "roi_table":
                rows = tuple(spec.get("rows", ()))
                if not rows:
                    ttk.Label(
                        self.parameter_content,
                        text="当前没有 ROI。",
                        style="Muted.TLabel",
                    ).grid(row=row, column=0, sticky="ew", pady=4)
                    row += 1
                    continue
                table_holder = ttk.Frame(self.parameter_content)
                table_holder.grid(row=row, column=0, sticky="ew", pady=4)
                table_holder.columnconfigure(0, weight=1)
                table = ttk.Treeview(
                    table_holder,
                    columns=("roi", "area", "quality"),
                    show="tree headings",
                    height=min(14, len(rows)),
                )
                table.heading("#0", text="颜色")
                table.heading("roi", text="ROI")
                table.heading("area", text="面积 (px^2)")
                table.heading("quality", text="质量")
                table.column("#0", width=42, minwidth=42, stretch=False, anchor="center")
                table.column("roi", width=96, minwidth=72, anchor="w")
                table.column("area", width=72, minwidth=62, anchor="e")
                table.column("quality", width=70, minwidth=62, anchor="center")
                scrollbar = ttk.Scrollbar(table_holder, orient="vertical", command=table.yview)
                table.configure(yscrollcommand=scrollbar.set)
                table.grid(row=0, column=0, sticky="ew")
                scrollbar.grid(row=0, column=1, sticky="ns")
                roi_indices = {}
                for roi_row in rows:
                    swatch = tk.PhotoImage(width=14, height=14)
                    swatch.put(roi_row["color"], to=(0, 0, 14, 14))
                    self.roi_table_images.append(swatch)
                    item_id = f"roi_{roi_row['index']}"
                    roi_indices[item_id] = int(roi_row["index"])
                    table.insert(
                        "",
                        "end",
                        iid=f"roi_{roi_row['index']}",
                        image=swatch,
                        values=(roi_row["name"], roi_row["area"], roi_row["quality"]),
                    )
                on_select = spec.get("on_select")
                if callable(on_select):
                    def handle_roi_selection(_event, tree=table, mapping=roi_indices, callback=on_select):
                        selection = tree.selection()
                        if selection and selection[0] in mapping:
                            callback(mapping[selection[0]])

                    table.bind("<<TreeviewSelect>>", handle_roi_selection)
                selected_index = spec.get("selected_index")
                selected_item = f"roi_{selected_index}"
                if selected_index is not None and selected_item in roi_indices:
                    table.selection_set(selected_item)
                    table.see(selected_item)
                row += 1
                continue
            item = ttk.Frame(self.parameter_content)
            item.grid(row=row, column=0, sticky="ew", pady=4)
            item.columnconfigure(0, weight=1)
            if field_type == "checkbox":
                value_var = tk.BooleanVar(value=bool(default))
                entry = ttk.Checkbutton(item, text=label, variable=value_var)
                entry.grid(row=0, column=0, sticky="w")
                self.parameter_entries[key] = entry
                self.parameter_vars[key] = value_var
                row += 1
                continue
            ttk.Label(item, text=label).grid(row=0, column=0, sticky="w")
            if field_type == "readonly":
                value_var = tk.StringVar(value=str(default))
                entry = ttk.Label(item, textvariable=value_var, style="Muted.TLabel", wraplength=PARAMETER_TEXT_WIDTH)
                entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
                self.parameter_entries[key] = entry
                self.parameter_vars[key] = value_var
                row += 1
                continue
            choices = tuple(spec.get("choices", ()))
            input_row = ttk.Frame(item)
            input_row.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            input_row.columnconfigure(0, weight=1)
            if choices:
                value_to_display = {str(value): display for value, display in choices}
                display_to_value = {display: str(value) for value, display in choices}
                value_var = tk.StringVar(value=value_to_display.get(str(default), str(default)))
                entry = ttk.Combobox(
                    input_row,
                    textvariable=value_var,
                    values=tuple(display_to_value),
                    state="readonly",
                )
                self.parameter_choice_values[key] = display_to_value
                self.parameter_choice_displays[key] = value_to_display
                on_change = spec.get("on_change")
                if callable(on_change):
                    entry.bind("<<ComboboxSelected>>", lambda _event, callback=on_change: callback())
            else:
                value_var = tk.StringVar(value=str(default))
                entry = ttk.Entry(input_row, textvariable=value_var)
            entry.grid(row=0, column=0, sticky="ew")
            browse_options = spec.get("browse")
            if browse_options is not None:
                if callable(browse_options):
                    browse_command = browse_options
                else:
                    browse_command = lambda field_key=key, dialog_options=browse_options: self._browse_parameter_path(
                        field_key,
                        dialog_options,
                    )
                ttk.Button(input_row, text="浏览", command=browse_command).grid(row=0, column=1, padx=(6, 0))
            self.parameter_entries[key] = entry
            self.parameter_vars[key] = value_var
            row += 1
        feedback_label = tk.Label(
            self.parameter_content,
            textvariable=self.parameter_feedback_var,
            bg=THEME["panel"],
            fg=THEME["muted"],
            anchor="w",
            justify="left",
            wraplength=PARAMETER_TEXT_WIDTH,
        )
        feedback_label.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        self.parameter_feedback_label = feedback_label
        row += 1
        if apply_command is not None:
            button_row = ttk.Frame(self.parameter_content)
            button_row.grid(row=row, column=0, sticky="ew", pady=(12, 0))
            button_row.columnconfigure(0, weight=1)
            button_row.columnconfigure(1, weight=1)
            ttk.Button(button_row, text="恢复默认", command=self.reset_parameter_panel).grid(row=0, column=0, sticky="ew", padx=(0, 4))
            ttk.Button(button_row, text=apply_text, style="Accent.TButton", command=self.run_parameter_action).grid(row=0, column=1, sticky="ew", padx=(4, 0))
            row += 1
        close_text = "取消" if cancel_command is not None else "清空"
        close_command = cancel_command if cancel_command is not None else self.clear_parameter_panel
        ttk.Button(self.parameter_content, text=close_text, command=close_command).grid(row=row, column=0, sticky="ew", pady=(8, 0))
        self._reset_parameter_scroll_position()

    def show_roi_list(self):
        rows = []
        for index, mask in enumerate(self.state.roi_masks):
            name = self.state.roi_names[index] if index < len(self.state.roi_names) else f"ROI{index + 1}"
            metadata = self.state.roi_metadata[index] if index < len(self.state.roi_metadata) else {}
            rows.append(
                {
                    "index": index,
                    "color": core.roi_color_hex(index),
                    "name": name,
                    "area": int(np.count_nonzero(mask)),
                    "quality": "低质量*" if metadata.get("low_quality") else "正常",
                }
            )
        description = (
            f"当前共 {len(rows)} 个 ROI。名称末尾的 * 表示该 ROI 按用户意图保留，但未达到当前质量预设。"
            if rows
            else "当前尚未绘制或载入 ROI。"
        )
        self.show_parameter_panel(
            "当前 ROI 列表",
            [{
                "type": "roi_table",
                "rows": rows,
                "on_select": self.select_roi_from_list,
                "selected_index": self.highlighted_roi_index,
            }],
            description=description,
            panel_id="roi_list",
        )

    def clear_roi_highlight(self, redraw=True):
        self.highlighted_roi_index = None
        if redraw:
            self.redraw(preserve_view=True)

    def select_roi_from_list(self, index):
        index = int(index)
        if index < 0 or index >= len(self.state.roi_masks):
            self.clear_roi_highlight()
            return
        self.highlighted_roi_index = index
        self.redraw(preserve_view=True)

    def refresh_roi_list_if_visible(self):
        if self.active_parameter_panel_id == "roi_list":
            self.clear_roi_highlight(redraw=False)
            self.show_roi_list()
            self.redraw(preserve_view=True)

    def reset_parameter_panel(self):
        for key, default in self.parameter_defaults.items():
            value_var = self.parameter_vars.get(key)
            if value_var is not None:
                shown = bool(default) if isinstance(value_var, tk.BooleanVar) else self.parameter_choice_displays.get(key, {}).get(str(default), str(default))
                value_var.set(shown)
        self.set_parameter_feedback("")

    def panel_parameter_values(self):
        values = {}
        for key, value_var in self.parameter_vars.items():
            display_value = value_var.get()
            values[key] = self.parameter_choice_values.get(key, {}).get(display_value, display_value)
        return values

    def run_parameter_action(self):
        if self.parameter_apply_command is None:
            return
        self.parameter_apply_command(self.panel_parameter_values())

    def on_canvas_resize(self, event):
        if self.state.display_image is not None or self.state.baseline_image is not None:
            self.redraw(preserve_view=True)
        else:
            self.redraw(preserve_view=False)

    def update_frame_controls(self):
        if self.state.movie is None:
            self.frame_scale.configure(from_=0, to=0)
            self.current_frame.set(0)
            self.frame_label_var.set("帧 1/1")
            return
        last = max(0, self.state.movie.shape[0] - 1)
        self.frame_scale.configure(from_=0, to=last)
        frame = min(max(0, int(self.current_frame.get())), last)
        self._setting_frame_scale = True
        try:
            self.current_frame.set(frame)
            self.frame_scale.set(frame)
            self.frame_label_var.set(f"帧 {frame + 1}/{last + 1}")
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
            self.frame_label_var.set(f"帧 {frame + 1}/{self.state.movie.shape[0]}")
            return
        self.current_frame.set(frame)
        self.frame_label_var.set(f"帧 {frame + 1}/{self.state.movie.shape[0]}")
        self.show_frame(frame)

    def show_frame(self, frame=None):
        if not self.require_movie():
            return
        if frame is None:
            frame = self.current_frame.get()
        frame = min(max(0, int(frame)), self.state.movie.shape[0] - 1)
        self.current_frame.set(frame)
        self.frame_label_var.set(f"帧 {frame + 1}/{self.state.movie.shape[0]}")
        self.state.display_image = self.state.movie[frame]
        self.display_source = ("frame", frame)
        self.redraw()

    def _restore_movie_display_source(self, source):
        if self.state.movie is None:
            return
        source = source or ("frame", int(self.current_frame.get()))
        if source[0] == "frame":
            self.show_frame(source[1])
        elif source[0] == "projection":
            self.queue_movie_view_refresh("恢复视频预览", preserve_view=False)
        else:
            self.show_frame(self.current_frame.get())

    def on_mode_changed(self):
        """Keep ROI interaction on the user-selected projection rather than a frame."""
        mode = self.mode.get()
        if mode not in {"circle", "freehand", "delete_roi"} or self.state.movie is None:
            self.roi_view_refresh_pending = False
            return
        self.roi_view_refresh_pending = True
        selected_view = self.projection_mode.get()

        def ready():
            if self.mode.get() in {"circle", "freehand", "delete_roi"}:
                self.roi_view_refresh_pending = False
                self.log(f"ROI 交互视图已切换为{self.view_label(selected_view)}。")

        self.queue_movie_view_refresh("切换 ROI 交互视图", preserve_view=True, on_complete=ready)

    @staticmethod
    def view_label(mode):
        return {"mean": "均值", "max": "最大值", "std": "标准差", "p25": "25% 分位"}.get(mode, str(mode))

    def fit_view(self):
        if self.state.display_image is None and self.state.baseline_image is None:
            return
        self._view_limits = None
        self._view_is_fit = True
        self.redraw(preserve_view=False)
        self.log("图像已适配并居中显示。")

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
            return "后台处理失败，请查看运行日志。"
        for line in reversed(lines):
            if line.startswith(("FileNotFoundError", "ValueError", "RuntimeError", "PermissionError")):
                return self.status_summary(line, max_chars=420) + "\n\n完整信息请查看运行日志。"
        return self.status_summary(lines[-1], max_chars=420) + "\n\n完整信息请查看运行日志。"

    def cleanup_session_temp(self):
        if self._session_temp_cleaned:
            return
        self._session_temp_cleaned = True
        self.release_movie_resources()
        try:
            shutil.rmtree(self.session_temp_dir, ignore_errors=True)
        except Exception:
            pass

    def on_close(self):
        self.cleanup_session_temp()
        self.root.destroy()

    def temp_work_dir(self, name):
        path = self.session_temp_dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def release_movie_resources(self):
        movies = [getattr(self.state, "movie", None)]
        movies.extend(getattr(self.state, "converted_channel_movies", ()) or ())
        for movie in movies:
            mmap_obj = getattr(movie, "_mmap", None)
            if mmap_obj is not None:
                try:
                    mmap_obj.close()
                except Exception:
                    pass
        self._converted_frame_cache = (None, None, None)
        self._converted_projection_cache = {}

    def mark_movie_changed(self):
        self.movie_generation += 1
        self.roi_candidate_banks = {"fast": None, "caiman": None}

    def clear_converted_color_source(self):
        self.state.converted_color_avi_path = ""
        self.state.converted_source_folder = ""
        self.state.converted_channel_avi_paths = ()
        self.state.converted_channel_movies = ()
        self.state.channel_colors = ()
        self._converted_frame_cache = (None, None, None)
        self._converted_projection_cache = {}
        self.update_channel_color_buttons()

    def channel_movies(self):
        return tuple(movie for movie in self.state.converted_channel_movies if movie is not None)

    def channel_colors(self):
        return core.channel_colors_for_count(self.state.channel_colors, len(self.channel_movies()))

    def channel_pseudocolor_enabled(self):
        return bool(self.channel_movies()) and core.has_pseudocolor(self.channel_colors())

    def clear_channel_render_cache(self):
        self._converted_frame_cache = (None, None, None)
        self._converted_projection_cache = {}

    def update_channel_color_buttons(self):
        if not getattr(self, "channel_color_buttons", None):
            return
        colors = self.channel_colors()
        count = len(self.channel_movies())
        for idx, button in enumerate(self.channel_color_buttons):
            if idx < count:
                color_name = colors[idx]
                bg = CHANNEL_COLOR_HEX.get(color_name, CHANNEL_COLOR_HEX["gray"])
                fg = "#020617" if color_name in {"yellow", "gray"} else "#ffffff"
                button.configure(
                    bg=bg,
                    activebackground=bg,
                    fg=fg,
                    activeforeground=fg,
                    state="normal",
                    text=str(idx + 1),
                )
            else:
                button.configure(
                    bg="#000000",
                    activebackground="#000000",
                    fg="#64748b",
                    activeforeground="#64748b",
                    state="normal",
                    text=str(idx + 1),
                )

    def choose_channel_color(self, channel_index):
        if channel_index >= len(self.channel_movies()):
            return
        self.show_parameter_panel(
            f"通道 {channel_index + 1} 伪彩",
            [
                {
                    "type": "color_palette",
                    "label": "选择显示与保存伪彩",
                    "command": lambda color_name: self.set_channel_color(channel_index, color_name),
                    "delete_command": lambda: self.delete_channel(channel_index),
                },
            ],
            cancel_command=self.clear_parameter_panel,
        )

    def set_channel_color(self, channel_index, color_name):
        movies = self.channel_movies()
        if channel_index >= len(movies):
            return
        colors = list(self.channel_colors())
        colors[channel_index] = core.normalized_channel_color(color_name)
        self.state.channel_colors = tuple(colors)
        self.clear_channel_render_cache()
        self.update_channel_color_buttons()
        self.redraw(preserve_view=True)
        self.log(f"通道 {channel_index + 1} 伪彩：{CHANNEL_COLOR_LABELS[colors[channel_index]]}")
        self.set_parameter_feedback(f"通道 {channel_index + 1} 已更新伪彩。")

    def delete_channel(self, channel_index):
        movies = list(self.channel_movies())
        if channel_index >= len(movies):
            return
        colors = list(self.channel_colors())
        removed_label = f"Ch{channel_index + 1}"
        movies.pop(channel_index)
        colors.pop(channel_index)
        self.clear_channel_render_cache()
        self.clear_deepcad_cache()
        if not movies:
            self.release_movie_resources()
            self.state = core.AnalysisState(fs=float(self.fs_var.get() or 10.0))
            self.state.display_image = None
            self.state.baseline_image = None
            self.mark_movie_changed()
            self.display_source = ("projection", self.projection_mode.get())
            self.update_frame_controls()
            self.update_channel_color_buttons()
            self.redraw(preserve_view=False)
            self.log(f"已删除 {removed_label}；当前没有剩余通道。")
            return
        self.state.converted_channel_movies = tuple(movies)
        self.state.channel_colors = tuple(colors)
        self.state.movie = core.two_photon_analysis_movie(self.state.converted_channel_movies)
        self.mark_movie_changed()
        self.state.baseline_image = None
        self.state.dff_movie = None
        self.update_frame_controls()
        self.update_channel_color_buttons()
        self.queue_movie_view_refresh("刷新删除通道后的预览", preserve_view=False)
        self.log(f"已删除 {removed_label}；当前通道数={len(movies)}。")

    def acceleration(self):
        return self.acceleration_var.get()

    def import_bit_depth(self):
        try:
            display_value = self.movie_import_depth_var.get()
            return core.normalized_movie_bit_depth("auto" if display_value == "自动" else display_value)
        except ValueError:
            self.movie_import_depth_var.set("自动")
            return "auto"

    def deepcad_weight(self):
        try:
            weight = float(self.deepcad_weight_var.get())
        except ValueError:
            weight = 0.5
        weight = max(0.0, min(1.0, weight))
        self.deepcad_weight_var.set(f"{weight:.3g}")
        return weight

    def display_controls(self):
        try:
            values = core.normalized_display_controls(
                self.display_shadows_var.get(),
                self.display_highlights_var.get(),
                self.display_brightness_var.get(),
                self.display_contrast_var.get(),
            )
        except (TypeError, ValueError):
            values = (1.0, 99.0, 0.0, 100.0)
        return values

    def display_limits_for_current_movie(self):
        if self.state.movie is None:
            return 0.0, 1.0
        shadows, highlights, _brightness, _contrast = self.display_controls()
        denoised = self.deepcad_denoised_movie if self.deepcad_enabled_var.get() and self.deepcad_cache_is_current() else None
        weight = self.deepcad_weight() if denoised is not None else 0.0
        cache_key = (id(self.state.movie), id(denoised) if denoised is not None else None, weight, shadows, highlights)
        if cache_key not in self._display_limits_cache:
            self._display_limits_cache[cache_key] = core.movie_display_limits(
                self.state.movie,
                shadows=shadows,
                highlights=highlights,
                overlay_movie=denoised,
                overlay_weight=weight,
            )
        return self._display_limits_cache[cache_key]

    def render_image_for_display(self, image):
        if image is None:
            return image
        shadows, highlights, brightness, contrast = self.display_controls()
        arr = np.asarray(image)
        if arr.ndim == 3 and arr.shape[-1] == 3:
            return core.render_rgb_display(arr, shadows, highlights, brightness, contrast)
        return core.render_grayscale_display(
            arr,
            self.display_limits_for_current_movie(),
            brightness=brightness,
            contrast=contrast,
        )

    def deepcad_cache_is_current(self):
        return (
            self.deepcad_denoised_movie is not None
            and self.state.movie is not None
            and self.deepcad_cache_movie_id == id(self.state.movie)
            and self.deepcad_cache_invalid_start_frames == self.state.invalid_start_frames
            and self.deepcad_denoised_movie.shape == self.state.movie.shape
        )

    def clear_deepcad_cache(self):
        self.deepcad_denoised_movie = None
        self.deepcad_cache_movie_id = None
        self.deepcad_cache_invalid_start_frames = None
        self.deepcad_projection_cache = {}
        self.deepcad_last_preview_weight = None
        self.deepcad_running = False
        self.deepcad_running_token = None
        self.deepcad_last_error = ""
        self.deepcad_request_token += 1
        self._display_limits_cache = {}

    def on_deepcad_toggle(self):
        if self.deepcad_enabled_var.get():
            self.deepcad_last_error = ""
            self.ensure_deepcad_cache_async()
        else:
            self.deepcad_request_token += 1
            self.deepcad_running = False
            self.deepcad_running_token = None
        self.redraw(preserve_view=True)

    def on_deepcad_weight_edited(self):
        try:
            weight = float(self.deepcad_weight_var.get())
        except ValueError:
            return
        weight = max(0.0, min(1.0, weight))
        if self.deepcad_last_preview_weight is None or abs(weight - self.deepcad_last_preview_weight) > 1e-6:
            self.deepcad_last_preview_weight = weight
            self.redraw(preserve_view=True)

    def on_deepcad_weight_changed(self):
        self.deepcad_weight()
        self.redraw(preserve_view=True)

    def deepcad_temp_dir(self):
        return self.temp_work_dir("DeepCAD-RT")

    def ensure_deepcad_cache_async(self):
        if not self.deepcad_enabled_var.get() or not self.require_movie():
            return
        if self.deepcad_cache_is_current() or self.deepcad_running or self.deepcad_last_error:
            return
        movie = np.asarray(self.state.movie, dtype=np.float32).copy()
        movie_id = id(self.state.movie)
        invalid_start_frames = int(self.state.invalid_start_frames)
        self.deepcad_request_token += 1
        token = self.deepcad_request_token
        out_dir = self.deepcad_temp_dir()
        self.deepcad_running = True
        self.deepcad_running_token = token
        self.log("已加入任务流：DeepCAD-RT 深度学习降噪预览。")

        def worker(cancel_event):
            payload = {
                "token": token,
                "movie_id": movie_id,
                "invalid_start_frames": invalid_start_frames,
                "movie": None,
                "log": "",
                "error": "",
            }
            try:
                denoised, log = core.run_deepcadrt_denoise(
                    movie,
                    str(out_dir),
                    invalid_start_frames=invalid_start_frames,
                )
                payload.update({"movie": denoised, "log": log})
            except Exception as exc:
                payload["error"] = str(exc)
            if cancel_event.is_set():
                raise TaskCancelled()
            return payload

        def cancelled():
            if self.deepcad_running_token == token:
                self.deepcad_running = False
                self.deepcad_running_token = None
            self.log("已取消 DeepCAD-RT 降噪预览。")

        self.enqueue_task("DeepCAD-RT 降噪预览", worker, self._finish_deepcad_cache, on_cancel=cancelled)

    def _finish_deepcad_cache(self, payload):
        token = payload.get("token")
        current = (
            token == self.deepcad_request_token
            and payload.get("movie_id") == id(self.state.movie)
            and payload.get("invalid_start_frames") == self.state.invalid_start_frames
        )
        if self.deepcad_running_token == token:
            self.deepcad_running = False
            self.deepcad_running_token = None
        if not current:
            self.log("视频已经变化，已忽略过期的 DeepCAD-RT 预览结果。")
            return
        if payload.get("error"):
            self.deepcad_last_error = payload["error"]
            self.log(f"DeepCAD-RT 预览失败：{payload['error']}")
            return
        self.deepcad_denoised_movie = payload["movie"]
        self.deepcad_cache_movie_id = id(self.state.movie)
        self.deepcad_cache_invalid_start_frames = int(self.state.invalid_start_frames)
        self.deepcad_projection_cache = {}
        self.deepcad_last_preview_weight = self.deepcad_weight()
        self.log("DeepCAD-RT 预览缓存已就绪。")
        log = str(payload.get("log", "")).strip()
        if log:
            self.log(log[-800:])
        self.redraw(preserve_view=True)

    def display_image_for_render(self):
        img = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        if img is None:
            return img
        source = getattr(self, "display_source", ("custom", None))
        color = self.converted_color_image(source) if self.channel_pseudocolor_enabled() else None
        if color is not None:
            return self.render_image_for_display(color)
        if not self.deepcad_enabled_var.get():
            return self.render_image_for_display(img)
        if not self.deepcad_cache_is_current():
            return self.render_image_for_display(img)
        weight = self.deepcad_weight()
        if source[0] == "frame":
            frame = min(max(0, int(source[1])), self.deepcad_denoised_movie.shape[0] - 1)
            return self.render_image_for_display(core.blend_images(img, self.deepcad_denoised_movie[frame], weight))
        if source[0] == "projection":
            mode = source[1]
            mean_start = int(self.state.baseline_start_frame)
            mean_duration = int(self.state.baseline_duration_frames)
            cache_key = (
                mode,
                mean_start if mode == "mean" else 0,
                mean_duration if mode == "mean" else 0,
                int(self.state.invalid_start_frames),
            )
            if cache_key not in self.deepcad_projection_cache:
                self.deepcad_projection_cache[cache_key] = core.compute_projection(
                    self.deepcad_denoised_movie,
                    mode,
                    acceleration=self.acceleration(),
                    mean_start_frame=mean_start,
                    mean_duration_frames=mean_duration,
                    invalid_start_frames=self.state.invalid_start_frames,
                )
            return self.render_image_for_display(core.blend_images(img, self.deepcad_projection_cache[cache_key], weight))
        return self.render_image_for_display(img)

    def converted_color_image(self, source):
        if not source:
            return None
        channel_movies = self.channel_movies()
        if channel_movies:
            colors = self.channel_colors()
            if source[0] == "frame":
                frame = min(max(0, int(source[1])), channel_movies[0].shape[0] - 1)
                cached_path, cached_frame, cached_image = self._converted_frame_cache
                cache_key = ("channels", tuple(id(movie) for movie in channel_movies), colors)
                if cached_path == cache_key and cached_frame == frame:
                    return cached_image
                image = core.compose_channel_pseudocolor_rgb([movie[frame] for movie in channel_movies], colors)
                self._converted_frame_cache = (cache_key, frame, image)
                return image
            if source[0] == "projection":
                mode = source[1]
                mean_start = int(self.state.baseline_start_frame)
                mean_duration = int(self.state.baseline_duration_frames)
                cache_key = (
                    tuple(id(movie) for movie in channel_movies),
                    colors,
                    mode,
                    mean_start if mode == "mean" else 0,
                    mean_duration if mode == "mean" else 0,
                    int(self.state.invalid_start_frames),
                    self.acceleration(),
                )
                if cache_key not in self._converted_projection_cache:
                    projections = tuple(
                        core.compute_projection(
                            movie,
                            mode,
                            acceleration=self.acceleration(),
                            mean_start_frame=mean_start,
                            mean_duration_frames=mean_duration,
                            invalid_start_frames=self.state.invalid_start_frames,
                        )
                        for movie in channel_movies
                    )
                    self._converted_projection_cache[cache_key] = core.compose_channel_pseudocolor_rgb(projections, colors)
                return self._converted_projection_cache[cache_key]
            return None
        if source[0] != "frame" or not self.state.converted_color_avi_path:
            return None
        path = self.state.converted_color_avi_path
        frame = int(source[1])
        cached_path, cached_frame, cached_image = self._converted_frame_cache
        if cached_path == path and cached_frame == frame:
            return cached_image
        image = core.read_video_frame_rgb(path, frame)
        if image is not None:
            self._converted_frame_cache = (path, frame, image)
        return image

    def check_cuda_status_quick(self):
        self.log(f"计算加速后端：{core.acceleration_label(self.acceleration())}")

    def check_cuda_status(self):
        try:
            status = core.cuda_status(check_neuroseg3=True)
            lines = [
                f"主 dF/F GPU (CuPy)：{'可用' if status['cupy_available'] else '不可用'} {status['cupy_device']}",
                f"主 Python torch CUDA：{'可用' if status['torch_cuda_available'] else '不可用'} {status['torch_device']}",
                f"OpenCV CUDA 设备数：{status['opencv_cuda_devices']}",
                f"NeuroSeg3 CUDA：{'可用' if status['neuroseg3_cuda_available'] else '不可用'} {status['neuroseg3_device']}",
            ]
            message = "\n".join(lines)
            self.log(message.replace("\n", " | "))
            messagebox.showinfo("CUDA 状态", message)
        except Exception as exc:
            messagebox.showerror("CUDA 状态", str(exc))

    def require_movie(self):
        if self.state.movie is None:
            messagebox.showwarning("尚未打开视频", "请先打开视频。")
            return False
        return True

    def push_history(self, label):
        if self.state.movie is not None:
            channel_snapshot = tuple(np.asarray(movie).copy() for movie in self.state.converted_channel_movies)
            self.state.history.append((label, self.state.movie.copy(), channel_snapshot, tuple(self.state.channel_colors)))
            if len(self.state.history) > 12:
                self.state.history.pop(0)

    @staticmethod
    def roi_source_kind(source):
        text = str(source).lower()
        if "caiman" in text:
            return "caiman"
        if "快速" in text or "fast" in text or "neuroseg" in text:
            return "fast"
        if "atlas" in text or "图谱" in text or "neuroalign" in text:
            return "atlas"
        if "文件" in text or "load" in text:
            return "loaded"
        return "loaded"

    def next_roi_base_name(self, metadata=None):
        values = self.state.roi_metadata if metadata is None else metadata
        maximum = 0
        for item in values:
            name = str(item.get("base_name", "")).rstrip("*")
            if name.startswith("ROI") and name[3:].isdigit():
                maximum = max(maximum, int(name[3:]))
        return f"ROI{maximum + 1}"

    def sync_roi_names(self):
        existing = list(self.state.roi_metadata)
        metadata = []
        for index in range(len(self.state.roi_masks)):
            fallback_name = self.next_roi_base_name(metadata)
            item = roi_fit.normalized_roi_metadata(
                existing[index] if index < len(existing) else None,
                "loaded",
                fallback_name,
            )
            metadata.append(item)
        self.state.roi_metadata = metadata
        self.state.roi_names = [roi_fit.display_roi_name(item) for item in metadata]

    def ensure_global_roi(self):
        if self.state.roi_masks:
            return False
        full_roi = np.ones(self.state.movie.shape[1:], dtype=bool)
        metadata = [{"source": "loaded", "base_name": "Global_ROI"}]
        self.set_rois([full_roi], source="全局 ROI", names=["Global_ROI"], metadata=metadata)
        self.log("未选择 ROI，已自动使用全画面全局 ROI。")
        return True

    def set_rois(self, masks, source="ROI", names=None, metadata=None):
        source_kind = self.roi_source_kind(source)
        masks, display_names, metadata_values = roi_fit.normalize_roi_collection(
            masks,
            names=names,
            metadata=metadata,
            source=source_kind,
        )
        self.state.roi_masks = list(masks)
        self.state.roi_names = list(display_names)
        self.state.roi_metadata = [dict(item) for item in metadata_values]
        self.state.roi_revision += 1
        self.state.traces = None
        self.redraw()
        if self.state.roi_masks:
            if names is not None and len(names) == len(self.state.roi_masks):
                self.log(f"{source}：已载入 {len(self.state.roi_masks)} 个 ROI，并保留原名称。")
            else:
                self.log(f"{source}：已载入 {len(self.state.roi_masks)} 个 ROI，并重新编号为 ROI1-ROI{len(self.state.roi_masks)}。")
        else:
            self.log(f"{source}：未载入 ROI。")
        self.refresh_roi_list_if_visible()

    def mark_rois_changed(self):
        self.sync_roi_names()
        self.state.roi_revision += 1
        self.state.traces = None
        self.refresh_roi_list_if_visible()

    def recompute_baseline_image(self):
        if self.state.movie is None:
            return None
        self.state.baseline_image = core.baseline_from_frames(
            self.state.movie,
            self.state.baseline_start_frame,
            self.state.baseline_duration_frames,
            invalid_start_frames=self.state.invalid_start_frames,
        )
        self.state.dff_movie = None
        return self.state.baseline_image

    def queue_movie_view_refresh(self, label="刷新视频预览", preserve_view=False, on_complete=None):
        if self.state.movie is None:
            return None
        baseline_start = int(self.state.baseline_start_frame)
        baseline_duration = int(self.state.baseline_duration_frames)
        invalid_start_frames = int(self.state.invalid_start_frames)
        projection_mode = self.projection_mode.get()
        acceleration = self.acceleration()

        def worker(cancel_event):
            source_id = id(self.state.movie)
            movie = np.asarray(self.state.movie, dtype=np.float32)
            baseline = core.baseline_from_frames(
                movie,
                baseline_start,
                baseline_duration,
                invalid_start_frames=invalid_start_frames,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            projection = core.compute_projection(
                movie,
                projection_mode,
                acceleration=acceleration,
                mean_start_frame=baseline_start,
                mean_duration_frames=baseline_duration,
                invalid_start_frames=invalid_start_frames,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return source_id, baseline, projection

        def finish(result):
            source_id, baseline, projection = result
            if source_id != id(self.state.movie):
                self.log(f"已忽略过期的预览结果：{label}")
                return
            self.state.baseline_image = baseline
            self.state.dff_movie = None
            self.state.display_image = projection
            self.display_source = ("projection", projection_mode)
            if not preserve_view:
                self._view_limits = None
                self._view_is_fit = True
            if self.deepcad_enabled_var.get():
                self.ensure_deepcad_cache_async()
            self.redraw(preserve_view=preserve_view)
            if on_complete is not None:
                on_complete()

        return self.enqueue_task(label, worker, finish)

    def undo(self):
        if not self.state.history:
            self.log("没有可撤销的操作。")
            return
        entry = self.state.history.pop()
        label, movie = entry[0], entry[1]
        self.state.movie = movie
        self.mark_movie_changed()
        if len(entry) > 2:
            self.state.converted_channel_movies = tuple(entry[2])
        if len(entry) > 3:
            self.state.channel_colors = tuple(entry[3])
        self._converted_frame_cache = (None, None, None)
        self._converted_projection_cache = {}
        self.clear_deepcad_cache()
        self.update_frame_controls()
        self.update_channel_color_buttons()
        self.queue_movie_view_refresh("刷新撤销后预览")
        self.log(f"已撤销：{label}")

    def reset_loaded_movie_view(self, fs, preserve_view=False):
        self.clear_channel_render_cache()
        self.clear_deepcad_cache()
        self.fs_var.set(f"{float(fs):.6g}")
        self.apply_protocol(update_baseline=False)
        self.state.baseline_image = None
        self.state.dff_movie = None
        self.update_frame_controls()
        self.update_channel_color_buttons()
        self.queue_movie_view_refresh("生成视频预览", preserve_view=preserve_view)

    def append_channel_movies(self, new_movies, fs, source_label, import_bit_depth=None):
        new_movies = tuple(np.asarray(movie, dtype=np.float32) for movie in new_movies if movie is not None)
        if not new_movies:
            raise ValueError("没有载入任何通道视频。")
        existing_channels = self.channel_movies()
        existing_colors = list(self.channel_colors())
        import_bit_depth = import_bit_depth or getattr(self.state, "import_bit_depth", "auto")
        if not existing_channels and self.state.movie is not None:
            existing_channels = (np.asarray(self.state.movie, dtype=np.float32),)
            existing_colors = ["gray"]
        if len(existing_channels) + len(new_movies) > MAX_CHANNELS:
            raise ValueError(f"最多支持 {MAX_CHANNELS} 个通道。")
        if existing_channels:
            expected_shape = existing_channels[0].shape
            for movie in new_movies:
                if movie.shape != expected_shape:
                    raise ValueError(f"通道尺寸不一致：需要 {expected_shape}，实际为 {movie.shape}")
            combined = existing_channels + new_movies
            self.state.converted_channel_movies = combined
            self.state.channel_colors = tuple(existing_colors + ["gray"] * len(new_movies))
            self.state.movie = core.two_photon_analysis_movie(combined)
            self.mark_movie_changed()
            self.state.import_bit_depth = import_bit_depth
            self.state.converted_color_avi_path = ""
            self.state.converted_channel_avi_paths = ()
            self.state.converted_source_folder = source_label
            if abs(float(fs) - float(self.state.fs)) > 1e-6:
                self.log(f"新增通道帧率为 {float(fs):.3g} Hz；当前视频帧率仍为 {self.state.fs:.3g} Hz。")
            self.reset_loaded_movie_view(self.state.fs, preserve_view=False)
            self.log(f"已从 {source_label} 添加 {len(new_movies)} 个通道；当前通道数={len(combined)}。")
            return
        self.release_movie_resources()
        self.state = core.AnalysisState(
            movie=core.two_photon_analysis_movie(new_movies),
            converted_channel_movies=new_movies,
            channel_colors=tuple("gray" for _ in new_movies),
            fs=float(fs),
            source_path=source_label,
            import_bit_depth=import_bit_depth,
            converted_source_folder=source_label,
        )
        self.mark_movie_changed()
        self.reset_loaded_movie_view(fs, preserve_view=False)
        self.log(f"已从 {source_label} 载入 {len(new_movies)} 个通道：{self.state.movie.shape}，帧率={float(fs):.3g} Hz")

    def _show_source_picker_panel(self, append=False):
        title = "添加通道数据" if append else "打开数据"
        file_label = "选择通道视频/成像文件" if append else "选择视频/成像文件"
        folder_label = "选择通道双光子文件夹" if append else "选择双光子数据文件夹"
        self.show_parameter_panel(
            title,
            [
                {
                    "type": "note",
                    "text": "从文件载入视频、TIFF 或 TDMS；从文件夹载入双光子原始数据。",
                },
                {
                    "type": "buttons",
                    "columns": 1,
                    "actions": (
                        (file_label, lambda: self._pick_movie_source("file", append)),
                        (folder_label, lambda: self._pick_movie_source("folder", append)),
                    ),
                },
            ],
            cancel_command=self.clear_parameter_panel,
        )

    def _pick_movie_source(self, selection, append=False):
        if selection == "folder":
            path = filedialog.askdirectory(title="选择通道数据文件夹" if append else "选择双光子数据文件夹")
        else:
            path = filedialog.askopenfilename(
                title="选择通道视频文件" if append else "选择视频文件",
                filetypes=[("视频/成像数据", "*.tif *.tiff *.avi *.mp4 *.mov *.mkv *.tdms"), ("所有文件", "*.*")],
            )
        if not path:
            return
        path_obj = Path(path)
        if path_obj.is_dir() or path_obj.suffix.lower() == ".tdms":
            folder = path_obj if path_obj.is_dir() else path_obj.parent
            self.open_two_photon_folder(folder, append=append)
            return
        import_depth = self.import_bit_depth()
        if append:
            def finish(result):
                movie, fs = result
                self.append_channel_movies((movie,), fs, str(path_obj), import_bit_depth=import_depth)

            self.run_worker("载入附加通道", lambda: core.load_movie(path, bit_depth=import_depth), finish)
            return

        def finish(result):
            movie, fs = result
            self.release_movie_resources()
            self.state = core.AnalysisState(
                movie=movie,
                converted_channel_movies=(movie,),
                channel_colors=("gray",),
                fs=fs,
                source_path=path,
                import_bit_depth=import_depth,
            )
            self.mark_movie_changed()
            self.reset_loaded_movie_view(fs, preserve_view=False)
            self.log(f"已载入 {Path(path).name}：{movie.shape}，帧率={fs:.3g} Hz，导入位深={import_depth}")
            self.task_controller.reset_history_for_new_dataset()
            self.render_task_flow(force=True)

        self.run_worker("载入视频数据", lambda: core.load_movie(path, bit_depth=import_depth), finish)

    def open_movie(self):
        self._show_source_picker_panel(append=False)

    def add_channel_data(self):
        self._show_source_picker_panel(append=True)

    def open_two_photon_folder(self, folder, append=False):
        folder = Path(folder)
        if not core.is_two_photon_folder(folder):
            messagebox.showerror("打开文件夹失败", f"无法识别为双光子数据文件夹：\n{folder}")
            return
        out_dir = self.temp_work_dir("TwoPhotonConverter") / f"{folder.name}_{int(time.time())}_{random.randint(1000, 9999)}"
        action = "正在从文件夹添加通道" if append else "正在转换双光子数据文件夹"
        self.log(f"{action}：{folder}")

        def target():
            return core.convert_two_photon_folder_to_movie(folder, out_dir)

        self.run_worker("双光子数据转换", target, lambda result: self._finish_two_photon_folder(result, append=append))

    def _finish_two_photon_folder(self, result, append=False):
        if append:
            try:
                self.append_channel_movies(result.channel_movies, result.fs, str(result.source_folder), import_bit_depth="16-bit")
            except Exception as exc:
                messagebox.showerror("添加通道失败", str(exc))
            return
        self.release_movie_resources()
        self.state = core.AnalysisState(
            movie=result.movie,
            converted_channel_movies=result.channel_movies,
            channel_colors=tuple("gray" for _ in result.channel_movies),
            fs=result.fs,
            source_path=str(result.source_folder),
            import_bit_depth="16-bit",
            converted_color_avi_path=str(result.color_avi_path) if result.color_avi_path else "",
            converted_channel_avi_paths=tuple(str(path) for path in result.channel_avi_paths),
            converted_source_folder=str(result.source_folder),
        )
        self.mark_movie_changed()
        self.reset_loaded_movie_view(result.fs, preserve_view=False)
        self.show_frame(0)
        self.task_controller.reset_history_for_new_dataset()
        self.render_task_flow(force=True)
        channels = ", ".join(result.protocol.channels)
        self.log(
            f"已转换 {result.source_folder.name}：{result.frames} 帧，"
            f"{result.protocol.width}x{result.protocol.height}，{result.fs:.3g} Hz，通道={channels}。"
            "默认以灰度显示和保存；可在“视图”的通道色块中选择伪彩。"
        )
        if getattr(result, "interlacing_search_range", 0):
            self.log(
                f"双光子图像行偏移校正：估计偏移={int(result.interlacing_shift_px)} px "
                f"（搜索范围 +/-{int(result.interlacing_search_range)} px），已应用于全部通道。"
            )

    def open_stimulus(self):
        path = filedialog.askopenfilename(title="选择刺激数据", filetypes=[("刺激数据", "*.txt *.csv *.dat"), ("所有文件", "*.*")])
        if not path:
            return

        def finish(info):
            self.state.stimulus = info.signal
            if info.fs is not None and info.fs > 0:
                self.state.stimulus_fs = float(info.fs)
                self.stim_fs_var.set(f"{info.fs:.6g}")
            column = f"，列={info.column_name}" if info.column_name else ""
            fs_note = f"，刺激采样率={self.state.stimulus_fs:.6g} Hz" if self.state.stimulus_fs > 0 else ""
            self.log(f"已载入刺激数据 {Path(path).name}：{self.state.stimulus.size} 个采样点{column}{fs_note}")

        self.run_worker("载入刺激数据", lambda: core.read_stimulus_file_info(path), finish)

    def apply_protocol(self, update_baseline=True):
        try:
            old_baseline = (
                self.state.invalid_start_frames,
                self.state.baseline_start_frame,
                self.state.baseline_duration_frames,
            )
            self.state.fs = float(self.fs_var.get())
            self.state.stimulus_fs = float(self.stim_fs_var.get())
            invalid_start_frames = int(round(float(self.invalid_start_frames_var.get())))
            baseline_start_frame = int(round(float(self.baseline_start_var.get())))
            baseline_duration_frames = int(round(float(self.baseline_duration_var.get())))
            if invalid_start_frames < 0 or baseline_start_frame < 0 or baseline_duration_frames < 0:
                raise ValueError("无效起始帧数、基线起始帧和持续帧数必须大于或等于 0")
            if self.state.movie is not None and invalid_start_frames >= self.state.movie.shape[0]:
                raise ValueError(
                    f"无效起始帧数 {invalid_start_frames} 必须小于视频总帧数 {self.state.movie.shape[0]}"
                )
            self.state.invalid_start_frames = invalid_start_frames
            self.state.baseline_start_frame = baseline_start_frame
            self.state.baseline_duration_frames = baseline_duration_frames
            self.state.pre_trigger_s = float(self.pre_trigger_var.get())
            self.state.post_trigger_s = float(self.post_trigger_var.get())
            baseline_changed = old_baseline != (
                self.state.invalid_start_frames,
                self.state.baseline_start_frame,
                self.state.baseline_duration_frames,
            )
            if baseline_changed:
                self.state.baseline_image = None
                self.state.dff_movie = None
                self.state.traces = None
                self._converted_projection_cache = {}
            if old_baseline[0] != self.state.invalid_start_frames:
                self.clear_deepcad_cache()
            if update_baseline and self.state.movie is not None:
                self.queue_movie_view_refresh("应用实验协议", preserve_view=False)
            if self.state.baseline_duration_frames > 0:
                end_frame = None
                effective_baseline_start = max(
                    self.state.invalid_start_frames,
                    self.state.baseline_start_frame,
                )
                if self.state.movie is not None:
                    end_frame = min(
                        self.state.movie.shape[0],
                        effective_baseline_start + self.state.baseline_duration_frames,
                    ) - 1
                if end_frame is None:
                    self.log("实验协议已应用；dF/F 基线使用所选帧窗口的均值。")
                else:
                    self.log(
                        "实验协议已应用；"
                        f"dF/F 基线使用第 {effective_baseline_start}-{end_frame} 帧的均值。"
                    )
            else:
                valid_note = (
                    f"（已排除前 {self.state.invalid_start_frames} 个无效帧）"
                    if self.state.invalid_start_frames
                    else ""
                )
                self.log(f"实验协议已应用；dF/F 基线使用有效视频的第 25 百分位{valid_note}。")
        except Exception as exc:
            messagebox.showerror("应用实验协议失败", str(exc))

    def detect_triggers(self):
        if not self.require_movie():
            return
        self.apply_protocol(update_baseline=False)
        try:
            interval = float(self.trigger_interval_var.get())
            start = float(self.trigger_start_var.get())
            stimulus = None if self.state.stimulus is None else np.asarray(self.state.stimulus, dtype=np.float32).copy()
            if interval <= 0 and stimulus is None:
                self.log("未载入刺激数据，且触发间隔为 0。")
                return
            fs = float(self.state.fs)
            stimulus_fs = float(self.state.stimulus_fs)
            movie_frames = int(self.state.movie.shape[0])
            pre_trigger_s = float(self.state.pre_trigger_s)
            post_trigger_s = float(self.state.post_trigger_s)
            threshold = float(self.trigger_threshold_var.get())

            def worker(cancel_event):
                source_id = id(self.state.movie)
                if interval > 0:
                    frames = core.generate_interval_triggers(start, interval, fs, movie_frames, pre_trigger_s, post_trigger_s)
                else:
                    samples = core.detect_stimulus_triggers(stimulus, stimulus_fs, threshold=threshold)
                    frames = core.map_stimulus_triggers_to_frames(
                        samples, stimulus_fs, fs, movie_frames, pre_trigger_s, post_trigger_s
                    )
                if cancel_event.is_set():
                    raise TaskCancelled()
                return source_id, np.asarray(frames, dtype=int)

            def finish(result):
                source_id, frames = result
                if source_id != id(self.state.movie):
                    self.log("已忽略过期的刺激触发检测结果。")
                    return
                self.state.trigger_frames = frames
                self.redraw()
                self.log(f"检测到 {len(frames)} 个有效刺激触发。")

            self.enqueue_task("检测刺激触发", worker, finish)
        except Exception as exc:
            messagebox.showerror("刺激触发检测失败", str(exc))

    def refresh_projection(self, preserve_view=False):
        if not self.require_movie():
            return
        self.queue_movie_view_refresh("刷新投影视图", preserve_view=preserve_view)

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
        raw_img = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        img = self.display_image_for_render()
        if img is not None:
            h, w = img.shape[:2]
            if view_limits is None:
                view_limits = self._full_image_limits(img.shape)
                self._view_limits = view_limits
                self._view_is_fit = True
            overlay_source = raw_img if raw_img is not None else img
            if np.asarray(overlay_source).ndim == 3:
                overlay_source = np.mean(np.asarray(overlay_source), axis=2)
            overlay = core.draw_roi_overlay(
                overlay_source,
                self.state.roi_masks,
                self.state.roi_names,
                highlighted_index=self.highlighted_roi_index,
            )
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
        else:
            self.draw_empty_preview_background()
        if extra is not None:
            self.ax.imshow(extra, alpha=0.55, interpolation="nearest", origin="upper", aspect="auto")
        if self.current_polygon:
            xs, ys = zip(*self.current_polygon)
            self.ax.plot(xs, ys, color="cyan", linewidth=1.5)
            if len(self.current_polygon) >= 3 and not self.freehand_drawing:
                self.ax.plot([xs[-1], xs[0]], [ys[-1], ys[0]], color="cyan", linewidth=1.0, linestyle="--")
        self.canvas.draw_idle()

    def draw_empty_preview_background(self):
        path = ui_background.default_background_path()
        if path is None:
            return
        try:
            widget = self.canvas.get_tk_widget()
            width = max(2, int(widget.winfo_width()))
            height = max(2, int(widget.winfo_height()))
            if width <= 2 or height <= 2:
                width, height = 900, 650
            with Image.open(path) as src:
                fitted = ui_background.cover_crop_image(src, (width, height))
            fitted = ui_background.tint_image(fitted, THEME["bg"], 0.18)
            self.ax.set_position([0, 0, 1, 1])
            self.ax.imshow(np.asarray(fitted), origin="upper", aspect="auto")
            self.ax.set_xlim(-0.5, width - 0.5)
            self.ax.set_ylim(height - 0.5, -0.5)
        except Exception:
            pass

    def on_press(self, event):
        if event.inaxes == self.ax and event.xdata is not None and event.ydata is not None:
            self.last_cursor_image_xy = (float(event.xdata), float(event.ydata))
        if event.inaxes != self.ax or self.state.display_image is None:
            return
        if self.roi_view_refresh_pending and self.mode.get() in {"circle", "freehand", "delete_roi"}:
            self.log("正在切换 ROI 交互视图，请在预览刷新后绘制。")
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
                self.log("已开始自由绘制；移动鼠标绘制，再次点击确认。")
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
                self.add_roi(mask, "圆形")
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
            self.log("自由绘制 ROI 至少需要 3 个点。")
            return
        mask = core.polygon_mask(self.state.display_image.shape, self.current_polygon)
        self.current_polygon = []
        self.freehand_drawing = False
        self.add_roi(mask, "自由绘制")

    def cancel_freehand(self):
        self.current_polygon = []
        self.freehand_drawing = False
        self.redraw()
        self.log("已取消自由绘制 ROI。")

    def add_roi(self, mask, prefix):
        if mask is None or not np.any(mask):
            self.log("已忽略空 ROI。")
            return
        base_name = self.next_roi_base_name()
        self.state.roi_masks.append(mask.astype(bool))
        self.state.roi_metadata.append(
            {"source": "manual", "base_name": base_name}
        )
        self.mark_rois_changed()
        self.redraw()
        self.log(f"已添加 {base_name}；总数={len(self.state.roi_masks)}。")

    def delete_last_roi(self):
        if self.state.roi_masks:
            idx = len(self.state.roi_masks)
            self.state.roi_masks.pop()
            if self.state.roi_metadata:
                self.state.roi_metadata.pop()
            self.mark_rois_changed()
            self.redraw()
            self.log(f"已删除列表中的第 {idx} 个 ROI。")

    def delete_roi_at(self, x, y):
        if x is None or y is None or not self.state.roi_masks:
            self.log("点击位置没有 ROI。")
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
            self.log("点击位置没有 ROI。")
            return
        self.state.roi_masks.pop(hit)
        if hit < len(self.state.roi_metadata):
            self.state.roi_metadata.pop(hit)
        deleted = hit + 1
        self.mark_rois_changed()
        self.redraw()
        self.log(f"已点击删除列表中的第 {deleted} 个 ROI。")

    def clear_rois(self):
        self.state.roi_masks = []
        self.state.roi_names = []
        self.state.roi_metadata = []
        self.state.roi_revision += 1
        self.state.traces = None
        self.redraw()
        self.log("已清空全部 ROI。")
        self.refresh_roi_list_if_visible()

    def load_roi(self):
        if not self.require_movie():
            return
        path = filedialog.askopenfilename(
            filetypes=[
                ("ROI 或图谱", "*.npz *.json *.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("ROI npz", "*.npz"),
                ("Atlas JSON", "*.json"),
                ("图谱图像", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("所有文件", "*.*"),
            ]
        )
        if not path:
            return
        try:
            ext = Path(path).suffix.lower()
            if ext == ".npz":
                def load_npz():
                    with np.load(path, allow_pickle=True) as data:
                        masks = [m.astype(bool) for m in data["masks"]]
                        names = list(data["names"]) if "names" in data else None
                        metadata_json = data["metadata_json"] if "metadata_json" in data else None
                    metadata = roi_fit.deserialize_roi_metadata(
                        metadata_json,
                        count=len(masks),
                        names=names,
                        source="loaded",
                    )
                    return masks, names, metadata

                self.run_worker(
                    "载入 ROI 文件",
                    load_npz,
                    lambda result: self.set_rois(result[0], "ROI 文件", names=result[1], metadata=result[2]),
                )
            elif ext == ".json":
                vals = self.param_dialog("Atlas JSON 转 ROI", [("min_area", "最小面积", 50)])
                if not vals:
                    return
                shape = self.state.movie.shape[1:]
                self.run_worker(
                    "Atlas JSON 转 ROI",
                    lambda: core.process_atlas_json(path, shape, int(vals["min_area"])),
                    lambda result: self.set_rois(result[0], "Atlas JSON", names=result[1]),
                )
            elif ext in {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}:
                vals = self.param_dialog("图谱图像转 ROI", [("min_area", "最小面积", 50)])
                if not vals:
                    return
                shape = self.state.movie.shape[1:]
                self.run_worker(
                    "图谱图像转 ROI",
                    lambda: core.process_atlas_image(path, shape, int(vals["min_area"])),
                    lambda result: self.set_rois(result[0], "图谱图像", names=result[1]),
                )
            else:
                raise ValueError(f"不支持的 ROI 文件类型：{ext}")
        except Exception as exc:
            messagebox.showerror("载入 ROI 失败", str(exc))

    def atlas_roi(self):
        if not self.require_movie():
            return
        path = filedialog.askopenfilename(
            title="选择图谱图像",
            filetypes=[("图谱图像", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("所有文件", "*.*")]
        )
        if not path:
            return
        vals = self.param_dialog("图谱图像转 ROI", [("min_area", "最小面积", 50)])
        if not vals:
            return
        try:
            shape = self.state.movie.shape[1:]
            self.run_worker(
                "图谱图像转 ROI",
                lambda: core.process_atlas_image(path, shape, int(vals["min_area"])),
                lambda result: self.set_rois(result[0], "图谱 ROI", names=result[1]),
            )
        except Exception as exc:
            messagebox.showerror("图谱 ROI 生成失败", str(exc))

    def atlas_reference_builder(self):
        if not NEUROALIGN_DIR.exists():
            self.show_parameter_panel(
                "标准图谱构建",
                [{"type": "note", "text": f"未找到 NeuroAlign 文件夹：{NEUROALIGN_DIR}"}],
                cancel_command=self.clear_parameter_panel,
            )
            self.set_parameter_feedback("无法启动标准图谱构建。", error=True)
            return
        defaults = atlas_builder_defaults()
        saved = self.user_settings.get("atlas_reference_builder", {})
        self.show_parameter_panel(
            "Atlas Reference Builder",
            [
                {
                    "key": "image",
                    "label": "图谱线稿图像",
                    "default": saved.get("image", ""),
                    "type": "path",
                    "browse": {
                        "title": "选择图谱线稿图像",
                        "filetypes": [("图像文件", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"), ("所有文件", "*.*")],
                    },
                },
                {
                    "key": "outdir",
                    "label": "输出文件夹",
                    "default": saved.get("outdir") or default_neuroalign_outdir("atlas_reference"),
                    "type": "path",
                    "browse": {"title": "选择输出文件夹", "directory": True},
                },
                ("line_threshold", "线条阈值", saved.get("line_threshold", defaults["line_threshold"])),
                ("auto_gap_bridge_dist", "断点连接距离 (px)", saved.get("auto_gap_bridge_dist", defaults["auto_gap_bridge_dist"])),
                ("barrier_radius", "边界扩张半径", saved.get("barrier_radius", defaults["barrier_radius"])),
                ("min_region_area", "最小区域面积", saved.get("min_region_area", defaults["min_region_area"])),
                {"key": "detect_dark_lines", "label": "检测深色线条", "default": bool(saved.get("detect_dark_lines", defaults["detect_dark_lines"])), "type": "checkbox"},
            ],
            self._run_atlas_reference_builder_from_panel,
            description="从图谱线稿自动补全边界并生成可导入的 Atlas JSON。",
            apply_text="构建标准图谱",
            help_text=load_neuroalign_help_text(),
        )

    def _run_atlas_reference_builder_from_panel(self, values):
        try:
            image_text = str(values["image"]).strip()
            outdir_text = str(values["outdir"]).strip()
            if not image_text:
                raise ValueError("必须选择图谱线稿图像。")
            if not outdir_text:
                raise ValueError("必须选择输出文件夹。")
            image = Path(image_text)
            outdir = Path(outdir_text)
            if not image.is_file():
                raise ValueError("图谱线稿图像不存在。")
            vals = {
                "image": str(image),
                "outdir": str(outdir),
                "line_threshold": int(float(values["line_threshold"])),
                "auto_gap_bridge_dist": int(float(values["auto_gap_bridge_dist"])),
                "barrier_radius": int(float(values["barrier_radius"])),
                "min_region_area": int(float(values["min_region_area"])),
                "detect_dark_lines": bool(values.get("detect_dark_lines", True)),
            }
        except (KeyError, TypeError, ValueError) as exc:
            self.set_parameter_feedback(str(exc), error=True)
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
                raise RuntimeError("标准图谱构建已结束，但未生成 atlas_regions_raw.json")
            return {"atlas_json": str(atlas_json), "outdir": str(outdir), "log": log}

        self.run_worker("标准图谱构建", run, self._finish_atlas_reference_builder)
        self.set_parameter_feedback("已加入任务流，正在构建标准图谱。")

    def _finish_atlas_reference_builder(self, result):
        self.last_atlas_reference_json = result["atlas_json"]
        self.log(f"标准图谱已保存：{result['atlas_json']}")
        if self.state.movie is not None:
            shape = self.state.movie.shape[1:]
            self.run_worker(
                "载入标准图谱 ROI",
                lambda: core.process_atlas_json(result["atlas_json"], shape, 50),
                lambda value: self.set_rois(value[0], "标准图谱预览", names=value[1]),
                on_error=lambda exc: self.log(f"标准图谱已构建，但预览导入失败：{exc}"),
            )
        log = str(result.get("log", "")).strip()
        if log:
            self.log(log[-800:])

    def neuroalign(self):
        if not self.require_movie():
            return
        if not NEUROALIGN_DIR.exists():
            self.show_parameter_panel(
                "NeuroAlign 脑图谱配准",
                [{"type": "note", "text": f"未找到 NeuroAlign 文件夹：{NEUROALIGN_DIR}"}],
                cancel_command=self.clear_parameter_panel,
            )
            self.set_parameter_feedback("无法启动 NeuroAlign。", error=True)
            return
        default_video = self.state.source_path if self.state.source_path else ""
        default_atlas = self.last_atlas_reference_json
        if not default_atlas:
            candidate = NEUROALIGN_DIR / "atlas_regions_raw.json"
            default_atlas = str(candidate) if candidate.exists() else ""
        saved = self.user_settings.get("neuroalign", {})
        cfg = neuroalign_recommended_cfg()
        cfg.update(saved.get("cfg") or {})
        self._neuroalign_panel_state = {
            "stage": "outer",
            "result": None,
            "original_source": self.display_source,
            "values": {
                "video": saved.get("video") or default_video,
                "atlas_json": saved.get("atlas_json") or default_atlas,
                "outdir": saved.get("outdir") or default_neuroalign_outdir("neuroalign"),
                "cfg": {key: str(value) for key, value in cfg.items()},
            },
        }
        self._show_neuroalign_panel()

    @staticmethod
    def _neuroalign_stage_fields(stage):
        if stage == "outer":
            return (
                ("brain_mask_percentile", "脑区蒙版百分位"),
                ("mask_min_area_frac", "蒙版最小面积比例"),
                ("mask_max_area_frac", "蒙版最大面积比例"),
                ("mask_max_center_fill_frac", "中心最大填充比例"),
                ("outer_resample_n", "外轮廓重采样点数"),
                ("outer_anchor_count", "外轮廓锚点数量"),
                ("outer_anchor_weight", "外轮廓权重"),
            )
        if stage == "cluster":
            return (
                ("functional_unit_mm", "功能单元尺寸 (mm)"),
                ("resolution", "聚类分辨率"),
                ("compactness", "SLIC 紧凑度"),
                ("min_n_segments", "最少分割数"),
                ("max_n_segments", "最多分割数"),
                ("min_cluster_size_superpixels", "最小聚类大小"),
                ("sparsity_percentile", "稀疏度百分位"),
                ("symmetry_reward", "对称性奖励"),
                ("distance_decay_scale", "距离衰减尺度"),
                ("inner_max_pairs_per_hemi", "单侧最大内部配对"),
            )
        return (
            ("midline_anchor_count", "中线锚点数量"),
            ("midline_anchor_weight", "中线权重"),
            ("max_ctrl_shift_px", "最大控制点位移 (px)"),
            ("tps_smooth", "TPS 平滑度"),
            ("min_inner_ctrl_for_tps", "最少内部控制点"),
            ("adaptive_search_dist_min", "最小搜索距离"),
            ("adaptive_search_dist_max", "最大搜索距离"),
            ("adaptive_search_quantile_min", "最小搜索分位"),
            ("adaptive_search_quantile_max", "最大搜索分位"),
            ("auto_rerun_max_attempts", "自动重试次数"),
        )

    def _capture_neuroalign_panel_values(self):
        state = getattr(self, "_neuroalign_panel_state", None)
        if not state:
            return
        values = self.panel_parameter_values()
        saved = state["values"]
        for key in ("video", "atlas_json", "outdir"):
            if key in values:
                saved[key] = str(values[key]).strip()
        for key, _label in self._neuroalign_stage_fields(state["stage"]):
            if key in values:
                saved["cfg"][key] = str(values[key]).strip()

    def _show_neuroalign_panel(self):
        state = getattr(self, "_neuroalign_panel_state", None)
        if not state:
            return
        stage = state["stage"]
        values = state["values"]
        stage_title = {
            "outer": "第 1/3 步：外轮廓拟合",
            "cluster": "第 2/3 步：聚类预览",
            "final": "第 3/3 步：最终图谱预览",
        }[stage]
        fields = [
            {
                "key": "video",
                "label": "待配准视频",
                "default": values["video"],
                "type": "path",
                "browse": {"title": "选择待配准视频", "filetypes": [("视频文件", "*.avi *.mp4 *.mov *.mkv *.tif *.tiff"), ("所有文件", "*.*")]},
            },
            {
                "key": "atlas_json",
                "label": "Atlas JSON",
                "default": values["atlas_json"],
                "type": "path",
                "browse": {"title": "选择 Atlas JSON", "filetypes": [("Atlas JSON", "*.json"), ("所有文件", "*.*")]},
            },
            {
                "key": "outdir",
                "label": "输出文件夹",
                "default": values["outdir"],
                "type": "path",
                "browse": {"title": "选择输出文件夹", "directory": True},
            },
            {"type": "note", "text": stage_title},
        ]
        fields.extend((key, label, values["cfg"].get(key, "")) for key, label in self._neuroalign_stage_fields(stage))
        previous_action = ("上一步", self._neuroalign_previous_stage)
        next_action = ("使用最终结果", self._accept_neuroalign_result, "Accent.TButton") if stage == "final" else ("下一步", self._neuroalign_next_stage, "Accent.TButton")
        fields.append(
            {
                "type": "buttons",
                "columns": 2,
                "actions": (
                    ("重新构建", self._rebuild_neuroalign_from_panel, "Accent.TButton"),
                    next_action,
                    previous_action,
                ),
            }
        )
        self.show_parameter_panel(
            "NeuroAlign 脑图谱配准",
            fields,
            description="当前阶段的预览会显示在主图像区域。",
            cancel_command=self._close_neuroalign_panel,
            help_text=load_neuroalign_help_text(),
        )
        result = state.get("result")
        if result:
            self._display_neuroalign_preview(result, stage)

    def _close_neuroalign_panel(self):
        self._capture_neuroalign_panel_values()
        state = self._neuroalign_panel_state
        self._neuroalign_panel_state = None
        self.clear_parameter_panel()
        if state and getattr(self, "display_source", (None,))[0] == "neuroalign_preview":
            self._restore_movie_display_source(state.get("original_source"))

    def _collect_neuroalign_panel_values(self):
        self._capture_neuroalign_panel_values()
        state = self._neuroalign_panel_state
        saved = state["values"]
        video_text = str(saved["video"]).strip()
        atlas_text = str(saved["atlas_json"]).strip()
        outdir_text = str(saved["outdir"]).strip()
        if not video_text or not Path(video_text).exists():
            raise ValueError("待配准视频不存在。")
        if not atlas_text or not Path(atlas_text).exists():
            raise ValueError("Atlas JSON 不存在。")
        if not outdir_text:
            raise ValueError("必须选择输出文件夹。")
        integer_keys = {
            "outer_resample_n", "outer_anchor_count", "midline_anchor_count", "min_inner_ctrl_for_tps",
            "auto_rerun_max_attempts", "min_n_segments", "max_n_segments", "min_cluster_size_superpixels",
            "inner_max_pairs_per_hemi",
        }
        cfg = neuroalign_recommended_cfg()
        for key, raw in saved["cfg"].items():
            raw = str(raw).strip()
            if raw == "":
                continue
            cfg[key] = int(float(raw)) if key in integer_keys else float(raw)
        vals = {"video": video_text, "atlas_json": atlas_text, "outdir": outdir_text, "cfg": cfg}
        self.user_settings["neuroalign"] = vals
        save_user_settings(self.user_settings)
        return vals

    def _neuroalign_previous_stage(self):
        self._capture_neuroalign_panel_values()
        state = self._neuroalign_panel_state
        if state["stage"] == "final":
            state["stage"] = "cluster"
        elif state["stage"] == "cluster":
            state["stage"] = "outer"
        else:
            self.set_parameter_feedback("当前已是第 1 步。")
            return
        self._show_neuroalign_panel()

    def _neuroalign_next_stage(self):
        self._capture_neuroalign_panel_values()
        state = self._neuroalign_panel_state
        if state["stage"] == "outer":
            state["stage"] = "cluster"
        elif state["stage"] == "cluster":
            state["stage"] = "final"
        self._show_neuroalign_panel()

    def _rebuild_neuroalign_from_panel(self):
        try:
            vals = self._collect_neuroalign_panel_values()
        except (TypeError, ValueError) as exc:
            self.set_parameter_feedback(str(exc), error=True)
            return
        stage = self._neuroalign_panel_state["stage"]
        stage_name = {"outer": "外轮廓", "cluster": "聚类", "final": "最终图谱"}[stage]
        self.set_parameter_feedback(f"已加入任务流，正在运行 NeuroAlign {stage_name}阶段。")

        def finish(result):
            state = self._neuroalign_panel_state
            if state is None:
                return
            state["result"] = result
            self._display_neuroalign_preview(result, state["stage"])
            self.set_parameter_feedback(f"{stage_name}阶段完成，可调整参数后重新构建。")
            log = str(result.get("log", "")).strip()
            if log:
                self.log(log[-1200:])

        def fail(exc):
            self.set_parameter_feedback(self.worker_error_summary(str(exc)), error=True)

        self.run_worker(
            f"NeuroAlign {stage_name}阶段",
            lambda: self.run_neuroalign_backend(vals, stage=stage),
            finish,
            on_error=fail,
        )

    def _neuroalign_preview_path(self, result, stage):
        outdir = Path(result["outdir"])
        if stage == "outer":
            self._create_neuroalign_outer_preview(outdir)
            names = ("outer_fit_preview.png", "outer_registration_overlay.png", "subject_outer_mask.png", "midline_profile_overlay.png")
        elif stage == "cluster":
            self._create_neuroalign_cluster_preview(outdir)
            names = ("cluster_on_affine_preview.png", "outer_fit_preview.png", "outer_registration_overlay.png", "subject_outer_mask.png")
        else:
            self._create_neuroalign_cluster_preview(outdir)
            names = ("final_warp_overlay.png", "cluster_on_affine_preview.png", "outer_fit_preview.png", "outer_registration_overlay.png", "subject_outer_mask.png")
        return next((outdir / name for name in names if (outdir / name).exists()), None)

    def _display_neuroalign_preview(self, result, stage):
        path = self._neuroalign_preview_path(result, stage)
        if path is None:
            self.set_parameter_feedback("本阶段没有生成可用预览图，请查看运行日志。", error=True)
            return
        try:
            with Image.open(path) as image:
                preview = np.asarray(image.convert("RGB"))
            self.state.display_image = preview
            self.display_source = ("neuroalign_preview", stage)
            self.redraw(preserve_view=False)
            self.log(f"NeuroAlign {stage}阶段预览：{path}")
        except Exception as exc:
            self.set_parameter_feedback(f"预览加载失败：{exc}", error=True)

    def _neuroalign_preview_mean_image(self, shape_hw):
        image = self.state.baseline_image
        if image is None and self.state.movie is not None:
            image = np.mean(self.state.movie, axis=0)
        if image is None:
            return None
        image = np.asarray(image, dtype=np.float32)
        if image.ndim == 3:
            image = np.mean(image, axis=2)
        if tuple(image.shape[:2]) != tuple(shape_hw):
            image = core.cv2.resize(image, (int(shape_hw[1]), int(shape_hw[0])), interpolation=core.cv2.INTER_AREA)
        return image

    def _create_neuroalign_outer_preview(self, outdir):
        mask_path = outdir / "subject_mask.npy"
        affine_json_path = outdir / "affine_atlas_regions.json"
        if not mask_path.exists() or not affine_json_path.exists():
            return
        subject_mask = np.load(mask_path).astype(np.uint8)
        with open(affine_json_path, "r", encoding="utf-8") as handle:
            atlas = json.load(handle)
        mean_image = self._neuroalign_preview_mean_image(subject_mask.shape)
        fig = Figure(figsize=(8, 8), dpi=160)
        ax = fig.add_subplot(111)
        ax.set_facecolor("#020617")
        ax.set_axis_off()
        if mean_image is not None:
            vmin, vmax = np.percentile(mean_image, [2, 98])
            ax.imshow(mean_image, cmap="gray", vmin=vmin, vmax=vmax, alpha=0.30, interpolation="bilinear")
        contours, _ = core.cv2.findContours(subject_mask, core.cv2.RETR_EXTERNAL, core.cv2.CHAIN_APPROX_NONE)
        for contour in contours:
            points = contour[:, 0, :]
            ax.plot(points[:, 0], points[:, 1], color="#38bdf8", linewidth=1.0)
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

    @staticmethod
    def _create_neuroalign_cluster_preview(outdir):
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

    def _accept_neuroalign_result(self):
        state = getattr(self, "_neuroalign_panel_state", None)
        result = None if state is None else state.get("result")
        if not result or not result.get("warped_json"):
            self.set_parameter_feedback("请先在第 3 步完成重新构建，再使用配准结果。", error=True)
            return
        self._restore_movie_display_source(state.get("original_source"))
        state["original_source"] = None
        self._finish_neuroalign(result)
        self._close_neuroalign_panel()

    def run_neuroalign_backend(self, vals, stage="final"):
        script = APP_DIR / "neuroalign_step_worker.py"
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
            ["--stage", stage, "--config", str(cfg_path)],
            cwd=APP_DIR,
            timeout=None,
        )
        result = {"outdir": str(outdir), "config": str(cfg_path), "stage": stage, "log": log}
        warped_json = outdir / "warped_atlas_regions.json"
        if stage == "final" and not warped_json.exists():
            raise RuntimeError("NeuroAlign 已结束，但未生成 warped_atlas_regions.json")
        if warped_json.exists():
            result["warped_json"] = str(warped_json)
        return result

    def _finish_neuroalign(self, result):
        self.last_neuroalign_output_dir = result["outdir"]
        self.log(f"NeuroAlign 已载入变形图谱 ROI：{result['warped_json']}")
        shape = self.state.movie.shape[1:]
        self.run_worker(
            "载入 NeuroAlign 图谱 ROI",
            lambda: core.process_atlas_json(result["warped_json"], shape, 50),
            lambda value: self.set_rois(value[0], "NeuroAlign", names=value[1]),
        )
        log = str(result.get("log", "")).strip()
        if log:
            self.log(log[-800:])

    def save_roi(self):
        if not self.state.roi_masks:
            self.log("没有可保存的 ROI。")
            return
        if len(self.state.roi_names) != len(self.state.roi_masks):
            self.sync_roi_names()
        path = filedialog.asksaveasfilename(defaultextension=".npz", filetypes=[("ROI npz", "*.npz")])
        if not path:
            return
        masks = np.stack(self.state.roi_masks).astype(bool)
        names = np.array(self.state.roi_names)
        metadata_json = roi_fit.serialize_roi_metadata(self.state.roi_metadata)

        def save(cancel_event):
            np.savez_compressed(path, masks=masks, names=names, metadata_json=metadata_json)
            if cancel_event.is_set():
                raise TaskCancelled()
            return path

        self.enqueue_task("保存 ROI", save, lambda result: self.log(f"ROI 已保存：{result}"))

    def current_movie_result_defaults(self):
        if self.state.source_path:
            src = Path(self.state.source_path)
            initial_dir = src if src.is_dir() else src.parent
            return initial_dir, "result.avi", ".avi"
        return APP_DIR, "result.avi", ".avi"

    def ask_current_movie_save_path(self):
        initial_dir, initial_file, ext = self.current_movie_result_defaults()
        path = filedialog.asksaveasfilename(
            title="保存当前视频",
            initialdir=str(initial_dir),
            initialfile=initial_file,
            defaultextension=ext,
            filetypes=[("AVI 视频（显示效果）", "*.avi"), ("TIFF 堆栈（定量数据）", "*.tif *.tiff"), ("所有文件", "*.*")],
            confirmoverwrite=True,
        )
        if not path:
            return None
        path = Path(path)
        return path if path.suffix.lower() in {".avi", ".tif", ".tiff"} else path.with_suffix(".avi")

    def movie_output_bit_depth(self, path):
        if Path(path).suffix.lower() not in {".tif", ".tiff"}:
            return "auto"
        try:
            return core.normalized_movie_bit_depth(getattr(self.state, "import_bit_depth", "auto"))
        except ValueError:
            return "auto"

    def save_movie_to_path(self, movie, path, fs=None, bit_depth=None, display_settings=None):
        path = Path(path)
        fs = float(self.state.fs) if fs is None else float(fs)
        bit_depth = self.movie_output_bit_depth(path) if bit_depth is None else bit_depth
        if path.suffix.lower() == ".avi":
            if display_settings is None:
                display_settings = self.display_controls()
            shadows, highlights, brightness, contrast = display_settings
            limits = core.movie_display_limits(movie, shadows=shadows, highlights=highlights)
            core.save_movie(
                movie,
                str(path),
                fs=fs,
                bit_depth=bit_depth,
                display_limits=limits,
                brightness=brightness,
                contrast=contrast,
            )
            return
        core.save_movie(movie, str(path), fs=fs, bit_depth=bit_depth)

    def save_converted_channels_to_path(self, path):
        channel_movies = tuple(movie for movie in self.state.converted_channel_movies if movie is not None)
        if len(channel_movies) >= 2:
            saved = []
            for idx, movie in enumerate(channel_movies, start=1):
                channel_path = path.with_name(f"{path.stem}_ch{idx}{path.suffix}")
                self.save_movie_to_path(movie, channel_path)
                saved.append(channel_path)
            self.log("已分别保存各通道视频：" + ", ".join(str(p) for p in saved))
            return True
        if len(self.state.converted_channel_avi_paths) >= 2:
            saved = []
            for idx, raw_path in enumerate(self.state.converted_channel_avi_paths, start=1):
                src = Path(raw_path)
                if not src.exists():
                    return False
                channel_path = path.with_name(f"{path.stem}_ch{idx}{path.suffix}")
                shutil.copy2(src, channel_path)
                saved.append(channel_path)
            self.log("已分别保存各通道视频：" + ", ".join(str(p) for p in saved))
            return True
        return False

    def save_current_movie(self):
        if not self.require_movie():
            return
        path = self.ask_current_movie_save_path()
        if path is None:
            return
        movie = self.state.movie
        fs = float(self.state.fs)
        channel_movies = self.channel_movies()
        channel_colors = self.channel_colors()
        save_bit_depth = self.movie_output_bit_depth(path)
        deepcad_enabled = bool(self.deepcad_enabled_var.get())
        shadows, highlights, brightness, contrast = self.display_controls()

        if self.channel_pseudocolor_enabled():
            def save_pseudocolor(cancel_event):
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.suffix.lower() in {".tif", ".tiff"}:
                    core.save_channel_pseudocolor_tiff(
                        channel_movies,
                        channel_colors,
                        str(path),
                        shadows=shadows,
                        highlights=highlights,
                        brightness=brightness,
                        contrast=contrast,
                    )
                else:
                    core.save_channel_pseudocolor_avi(
                        channel_movies,
                        channel_colors,
                        str(path),
                        fs=fs,
                        shadows=shadows,
                        highlights=highlights,
                        brightness=brightness,
                        contrast=contrast,
                    )
                if cancel_event.is_set():
                    raise TaskCancelled()
                return path

            self.enqueue_task("保存伪彩视频", save_pseudocolor, lambda result: self.log(f"伪彩视频已保存：{result}"))
            return

        if len(channel_movies) >= 2:
            def save_channels(cancel_event):
                path.parent.mkdir(parents=True, exist_ok=True)
                saved = []
                for idx, channel_movie in enumerate(channel_movies, start=1):
                    if cancel_event.is_set():
                        raise TaskCancelled()
                    channel_path = path.with_name(f"{path.stem}_ch{idx}{path.suffix}")
                    self.save_movie_to_path(channel_movie, channel_path, fs=fs, bit_depth=save_bit_depth, display_settings=(shadows, highlights, brightness, contrast))
                    saved.append(channel_path)
                return saved

            self.enqueue_task(
                "保存各通道视频",
                save_channels,
                lambda saved: self.log("已分别保存各通道视频：" + ", ".join(str(item) for item in saved)),
            )
            return

        if not deepcad_enabled:
            def save_plain(cancel_event):
                path.parent.mkdir(parents=True, exist_ok=True)
                self.save_movie_to_path(movie, path, fs=fs, bit_depth=save_bit_depth, display_settings=(shadows, highlights, brightness, contrast))
                if cancel_event.is_set():
                    raise TaskCancelled()
                return path

            self.enqueue_task("保存当前视频", save_plain, lambda result: self.log(f"视频已保存：{result}"))
            return
        weight = self.deepcad_weight()
        if self.deepcad_cache_is_current():
            denoised = self.deepcad_denoised_movie

            def save_cached_denoise(cancel_event):
                path.parent.mkdir(parents=True, exist_ok=True)
                self.save_movie_to_path(
                    core.blend_movies(movie, denoised, weight),
                    path,
                    fs=fs,
                    bit_depth=save_bit_depth,
                    display_settings=(shadows, highlights, brightness, contrast),
                )
                if cancel_event.is_set():
                    raise TaskCancelled()
                return path

            self.enqueue_task(
                "保存 DeepCAD-RT 视频",
                save_cached_denoise,
                lambda result: self.log(f"DeepCAD-RT 混合视频已保存：{result}"),
            )
            return

        out_dir = self.deepcad_temp_dir()
        invalid_start_frames = int(self.state.invalid_start_frames)
        self.log("已加入任务流：保存前运行 DeepCAD-RT 深度学习降噪。")

        def save_with_denoise(cancel_event):
            payload = {"path": str(path), "movie": None, "log": "", "error": ""}
            try:
                denoised, log = core.run_deepcadrt_denoise(
                    movie,
                    str(out_dir),
                    invalid_start_frames=invalid_start_frames,
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                self.save_movie_to_path(
                    core.blend_movies(movie, denoised, weight),
                    path,
                    fs=fs,
                    bit_depth=save_bit_depth,
                    display_settings=(shadows, highlights, brightness, contrast),
                )
                payload.update({
                    "movie": denoised,
                    "log": log,
                    "invalid_start_frames": invalid_start_frames,
                })
            except Exception as exc:
                payload["error"] = str(exc)
            if cancel_event.is_set():
                raise TaskCancelled()
            return payload

        self.enqueue_task("DeepCAD-RT 降噪并保存", save_with_denoise, self._finish_deepcad_save)

    def _finish_deepcad_save(self, payload):
        if payload.get("error"):
            self.log(f"DeepCAD-RT 保存失败：{payload['error']}")
            messagebox.showerror("DeepCAD-RT 保存", self.worker_error_summary(payload["error"]))
            return
        if payload.get("movie") is not None and self.state.movie is not None:
            self.deepcad_denoised_movie = payload["movie"]
            self.deepcad_cache_movie_id = id(self.state.movie)
            self.deepcad_cache_invalid_start_frames = payload.get("invalid_start_frames")
            self.deepcad_projection_cache = {}
        self.log(f"DeepCAD-RT 混合视频已保存：{payload['path']}")
        log = str(payload.get("log", "")).strip()
        if log:
            self.log(log[-800:])

    def param_dialog(self, title, fields):
        if self.parameter_panel is not None:
            done = tk.BooleanVar(value=False)
            result = {"values": None}

            def apply(values):
                result["values"] = values
                done.set(True)

            def cancel():
                result["values"] = None
                done.set(True)
                self.clear_parameter_panel()

            self.show_parameter_panel(
                title,
                fields,
                apply,
                description="请在此调整参数，然后应用。",
                apply_text="应用",
                cancel_command=cancel,
            )
            self.root.wait_variable(done)
            return result["values"]
        dlg = ParameterDialog(self.root, title, fields)
        return dlg.values

    def apply_movie_operation(self, label, func, on_complete=None):
        if not self.require_movie():
            return
        try:
            self.apply_protocol(update_baseline=False)
            baseline_start = int(self.state.baseline_start_frame)
            baseline_duration = int(self.state.baseline_duration_frames)
            invalid_start_frames = int(self.state.invalid_start_frames)
            projection_mode = self.projection_mode.get()
            acceleration = self.acceleration()

            def worker(cancel_event):
                source_id = id(self.state.movie)
                channel_sources = tuple(self.channel_movies())
                if channel_sources:
                    processed_channels = []
                    for source in channel_sources:
                        if cancel_event.is_set():
                            raise TaskCancelled()
                        processed_channels.append(func(np.asarray(source, dtype=np.float32).copy()))
                    processed_movie = core.two_photon_analysis_movie(tuple(processed_channels))
                else:
                    processed_channels = ()
                    processed_movie = func(np.asarray(self.state.movie, dtype=np.float32).copy())
                if cancel_event.is_set():
                    raise TaskCancelled()
                baseline = core.baseline_from_frames(
                    processed_movie,
                    baseline_start,
                    baseline_duration,
                    invalid_start_frames=invalid_start_frames,
                )
                projection = core.compute_projection(
                    processed_movie,
                    projection_mode,
                    acceleration=acceleration,
                    mean_start_frame=baseline_start,
                    mean_duration_frames=baseline_duration,
                    invalid_start_frames=invalid_start_frames,
                )
                return {
                    "source_id": source_id,
                    "movie": processed_movie,
                    "channels": tuple(processed_channels),
                    "baseline": baseline,
                    "projection": projection,
                }

            def finish(result):
                if result["source_id"] != id(self.state.movie):
                    self.log(f"已忽略过期的处理结果：{label}")
                    return
                self.push_history(label)
                self.state.movie = result["movie"]
                self.mark_movie_changed()
                if result["channels"]:
                    self.state.converted_channel_movies = result["channels"]
                    self._converted_frame_cache = (None, None, None)
                    self._converted_projection_cache = {}
                self.state.baseline_image = result["baseline"]
                self.state.dff_movie = None
                self.state.traces = None
                self.state.display_image = result["projection"]
                self.display_source = ("projection", projection_mode)
                self.clear_deepcad_cache()
                self.update_frame_controls()
                self.update_channel_color_buttons()
                self.redraw(preserve_view=False)
                self.log(f"处理完成：{label}")
                if on_complete is not None:
                    on_complete()

            self.enqueue_task(label, worker, finish)
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror(label, str(exc))

    def show_preprocess_parameters(self, action_id):
        spec = PREPROCESS_PANEL_SPECS.get(action_id)
        if spec is None:
            return
        fields = spec.get("fields", [])
        if action_id == "display_adjustment":
            fields = [
                ("shadows", "阴影 (%)", self.display_shadows_var.get()),
                ("highlights", "高亮 (%)", self.display_highlights_var.get()),
                ("brightness", "亮度 (-100 至 100)", self.display_brightness_var.get()),
                ("contrast", "对比 (0 至 300)", self.display_contrast_var.get()),
            ]
        self.show_parameter_panel(
            spec["label"],
            fields,
            lambda values, key=action_id: self.run_preprocess_action(key, values),
            description=spec.get("description", ""),
            apply_text="运行",
        )

    def _param_float(self, values, key, default=0.0, min_value=None, max_value=None):
        raw = values.get(key, default)
        value = float(raw)
        if min_value is not None:
            value = max(float(min_value), value)
        if max_value is not None:
            value = min(float(max_value), value)
        return value

    def _param_int(self, values, key, default=0, min_value=None, max_value=None):
        value = int(round(self._param_float(values, key, default, min_value, max_value)))
        return value

    def run_preprocess_action(self, action_id, values):
        label = PREPROCESS_PANEL_SPECS.get(action_id, {}).get("label", action_id)
        try:
            if action_id == "display_adjustment":
                shadows, highlights, brightness, contrast = core.normalized_display_controls(
                    values.get("shadows", 1),
                    values.get("highlights", 99),
                    values.get("brightness", 0),
                    values.get("contrast", 100),
                )
                self.display_shadows_var.set(f"{shadows:.4g}")
                self.display_highlights_var.set(f"{highlights:.4g}")
                self.display_brightness_var.set(f"{brightness:.4g}")
                self.display_contrast_var.set(f"{contrast:.4g}")
                self._display_limits_cache = {}
                self.redraw(preserve_view=True)
                self.set_parameter_feedback("显示调节已应用；仅影响预览和 AVI 导出。")
                return
            if action_id == "caiman_motion":
                self.run_caiman_motion_from_values(values)
                return
            if action_id == "builtin_rigid_motion":
                reference_mode = str(values.get("reference_mode", "auto")).strip().lower()
                if reference_mode not in {"auto", "manual"}:
                    reference_mode = "auto"
                reference_start = self._param_int(values, "reference_start", 0, min_value=0)
                reference_frames = self._param_int(values, "reference_frames", 100, min_value=1)
                max_shift = self._param_float(values, "max_shift", 15.0, min_value=0.0)
                flexible_strength = self._param_float(values, "flexible_strength", 0.0, min_value=0.0, max_value=1.0)
                local_block_size = self._param_int(values, "local_block_size", 96, min_value=8)
                max_local_deformation = self._param_float(
                    values,
                    "max_local_deformation",
                    3.0,
                    min_value=0.0,
                )

                motion_details = {}

                def run(m):
                    corrected, shifts, info = core.fast_motion_correction(
                        m,
                        reference_mode=reference_mode,
                        reference_start=reference_start,
                        reference_frames=reference_frames,
                        max_shift=max_shift,
                        flexible_strength=flexible_strength,
                        local_block_size=local_block_size,
                        max_local_deformation=max_local_deformation,
                    )
                    shift_array = np.abs(np.asarray(shifts, dtype=np.float32))
                    motion_details["rigid"] = (
                        f"刚性参考区间：第 {info['reference_start']}-{info['reference_end'] - 1} 帧，"
                        f"锚定帧={info['anchor_frame']}；绝对位移中位数 dy/dx="
                        f"{np.median(shift_array, axis=0)}，最大值 dy/dx={np.max(shift_array, axis=0)}"
                    )
                    if info["local_applied"]:
                        motion_details["flexible"] = (
                            f"柔性矫正：强度={info['flexible_strength']:.2f}，"
                            f"有效块尺寸={info['local_block_size']} px，网格={info['local_grid_shape']}；"
                            f"局部绝对位移中位数 dy/dx={info['local_median_abs_shift']}，"
                            f"最大值 dy/dx={info['local_max_abs_shift_by_axis']}，"
                            f"触及形变上限比例={info['local_limit_hit_fraction']:.1%}"
                        )
                    elif info["local_skip_reason"] == "flexible_strength_zero":
                        motion_details["flexible"] = "柔性强度为 0，本次仅执行刚性矫正。"
                    else:
                        motion_details["flexible"] = f"柔性矫正未执行：{info['local_skip_reason']}"
                    return corrected

                def log_motion_details():
                    for line in motion_details.values():
                        self.log(line)

                self.apply_movie_operation(label, run, on_complete=log_motion_details)
                return
            if action_id == "image_shift":
                self.run_image_shift_from_values(values)
                return
            if action_id == "gaussian_smooth":
                sigma = self._param_float(values, "sigma", 1.0, min_value=0.0)
                acceleration = self.acceleration()
                self.apply_movie_operation(label, lambda m: core.gaussian_smooth_movie(m, sigma, acceleration=acceleration))
                return
            if action_id == "median_filter":
                size = self._param_int(values, "size", 3, min_value=1)
                self.apply_movie_operation(label, lambda m: core.median_filter_movie(m, size))
                return
            if action_id == "background_subtract":
                sigma = self._param_float(values, "sigma", 20.0, min_value=1.0)
                self.apply_movie_operation(label, lambda m: core.background_subtract(m, sigma))
                return
            if action_id == "bleach_correction":
                self.apply_movie_operation(label, core.bleach_correct)
                return
            if action_id == "enhance_contrast":
                clip_limit = self._param_float(values, "clip_limit", 0.02, min_value=0.001, max_value=1.0)
                self.apply_movie_operation(label, lambda m: core.enhance_contrast(m, clip_limit=clip_limit))
                return
            if action_id == "detect_vessels":
                self.run_detect_vessels_from_values(values)
                return
            if action_id == "remove_vessel_artifact":
                threshold = self._param_float(values, "threshold", 90.0, min_value=0.0, max_value=100.0)
                self.run_remove_vessels_from_values(label, threshold)
                return
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror(label, str(exc))

    def gaussian_smooth(self):
        self.show_preprocess_parameters("gaussian_smooth")

    def median_filter(self):
        self.show_preprocess_parameters("median_filter")

    def background_subtract(self):
        self.show_preprocess_parameters("background_subtract")

    def bleach_correct(self):
        self.show_preprocess_parameters("bleach_correction")

    def enhance_contrast(self):
        self.show_preprocess_parameters("enhance_contrast")

    def image_shift(self):
        self.show_preprocess_parameters("image_shift")

    def run_image_shift_from_values(self, values):
        search_range = self._param_int(values, "range", 10, min_value=0)
        row_parity = str(values.get("row_parity", "odd")).strip().lower()
        if row_parity not in {"odd", "even"}:
            row_parity = "odd"
        if search_range < 0:
            messagebox.showerror("图像行偏移校正", "搜索范围必须大于或等于 0。")
            return
        if not self.require_movie():
            return
        try:
            self.apply_protocol(update_baseline=False)
            baseline_start = int(self.state.baseline_start_frame)
            baseline_duration = int(self.state.baseline_duration_frames)
            invalid_start_frames = int(self.state.invalid_start_frames)
            projection_mode = self.projection_mode.get()
            acceleration = self.acceleration()

            def worker(cancel_event):
                source_id = id(self.state.movie)
                sources = tuple(self.channel_movies())
                source_movie = sources[0] if sources else self.state.movie
                shift = core.estimate_interlacing_shift_from_movie(source_movie, search_range=search_range, row_parity=row_parity)
                if cancel_event.is_set():
                    raise TaskCancelled()
                if shift == 0:
                    return {"source_id": source_id, "shift": 0}
                if sources:
                    processed_channels = tuple(np.asarray(movie, dtype=np.float32).copy() for movie in sources)
                    for movie in processed_channels:
                        core.apply_interlacing_shift_movie_inplace(movie, shift, row_parity=row_parity)
                    processed_movie = core.two_photon_analysis_movie(processed_channels)
                else:
                    processed_channels = ()
                    processed_movie = core.apply_interlacing_shift_movie(
                        np.asarray(self.state.movie, dtype=np.float32).copy(), shift, row_parity=row_parity
                    )
                if cancel_event.is_set():
                    raise TaskCancelled()
                return {
                    "source_id": source_id,
                    "shift": int(shift),
                    "movie": processed_movie,
                    "channels": processed_channels,
                    "baseline": core.baseline_from_frames(
                        processed_movie,
                        baseline_start,
                        baseline_duration,
                        invalid_start_frames=invalid_start_frames,
                    ),
                    "projection": core.compute_projection(
                        processed_movie,
                        projection_mode,
                        acceleration=acceleration,
                        mean_start_frame=baseline_start,
                        mean_duration_frames=baseline_duration,
                        invalid_start_frames=invalid_start_frames,
                    ),
                }

            def finish(result):
                if result["source_id"] != id(self.state.movie):
                    self.log("已忽略过期的图像行偏移校正结果。")
                    return
                if result["shift"] == 0:
                    self.log("图像行偏移校正：估计偏移=0 px，未应用校正。")
                    return
                self.push_history("图像行偏移校正")
                self.state.movie = result["movie"]
                self.mark_movie_changed()
                if result["channels"]:
                    self.state.converted_channel_movies = result["channels"]
                    self.clear_channel_render_cache()
                self.state.baseline_image = result["baseline"]
                self.state.dff_movie = None
                self.state.traces = None
                self.state.display_image = result["projection"]
                self.display_source = ("projection", projection_mode)
                self.clear_deepcad_cache()
                self.update_frame_controls()
                self.update_channel_color_buttons()
                self.redraw(preserve_view=False)
                row_name = "奇数行" if row_parity == "odd" else "偶数行"
                channel_note = "，已应用于全部通道" if result["channels"] else ""
                self.log(f"图像行偏移校正：估计偏移={result['shift']} px，移动{row_name}{channel_note}。")

            self.enqueue_task("图像行偏移校正", worker, finish)
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror("图像行偏移校正", str(exc))

    def builtin_motion(self):
        self.show_preprocess_parameters("builtin_rigid_motion")

    def detect_vessels(self):
        self.show_preprocess_parameters("detect_vessels")

    def run_detect_vessels_from_values(self, values):
        if not self.require_movie():
            return
        threshold = self._param_float(values, "threshold", 90.0, min_value=0.0, max_value=100.0)
        alpha = self._param_float(values, "alpha", 0.45, min_value=0.0, max_value=1.0)
        fs = float(self.state.fs)

        def worker(cancel_event):
            source_id = id(self.state.movie)
            mask, vesselness = core.detect_vessels(np.asarray(self.state.movie, dtype=np.float32), fs, threshold)
            if cancel_event.is_set():
                raise TaskCancelled()
            return source_id, mask, vesselness

        def finish(result):
            source_id, mask, _vesselness = result
            if source_id != id(self.state.movie):
                self.log("已忽略过期的血管检测结果。")
                return
            self.vessel_mask = mask
            extra = np.zeros(mask.shape + (4,), dtype=np.float32)
            extra[..., 0] = mask
            extra[..., 3] = mask * alpha
            self.redraw(extra=extra)
            self.log(f"检测到血管/伪影像素：{int(mask.sum())}")

        self.enqueue_task("血管/伪影检测", worker, finish)

    def run_remove_vessels_from_values(self, label, threshold):
        if not self.require_movie():
            return
        self.apply_protocol(update_baseline=False)
        baseline_start = int(self.state.baseline_start_frame)
        baseline_duration = int(self.state.baseline_duration_frames)
        invalid_start_frames = int(self.state.invalid_start_frames)
        projection_mode = self.projection_mode.get()
        acceleration = self.acceleration()
        fs = float(self.state.fs)

        def worker(cancel_event):
            source_id = id(self.state.movie)
            source_movie = np.asarray(self.state.movie, dtype=np.float32)
            mask, _vesselness = core.detect_vessels(source_movie, fs, threshold)
            if cancel_event.is_set():
                raise TaskCancelled()
            sources = tuple(self.channel_movies())
            if sources:
                channels = tuple(core.suppress_vessels(np.asarray(movie, dtype=np.float32).copy(), mask) for movie in sources)
                processed = core.two_photon_analysis_movie(channels)
            else:
                channels = ()
                processed = core.suppress_vessels(source_movie.copy(), mask)
            if cancel_event.is_set():
                raise TaskCancelled()
            return {
                "source_id": source_id,
                "mask": mask,
                "movie": processed,
                "channels": channels,
                "baseline": core.baseline_from_frames(
                    processed,
                    baseline_start,
                    baseline_duration,
                    invalid_start_frames=invalid_start_frames,
                ),
                "projection": core.compute_projection(
                    processed,
                    projection_mode,
                    acceleration=acceleration,
                    mean_start_frame=baseline_start,
                    mean_duration_frames=baseline_duration,
                    invalid_start_frames=invalid_start_frames,
                ),
            }

        def finish(result):
            if result["source_id"] != id(self.state.movie):
                self.log(f"已忽略过期的处理结果：{label}")
                return
            self.push_history(label)
            self.vessel_mask = result["mask"]
            self.state.movie = result["movie"]
            self.mark_movie_changed()
            if result["channels"]:
                self.state.converted_channel_movies = result["channels"]
                self.clear_channel_render_cache()
            self.state.baseline_image = result["baseline"]
            self.state.dff_movie = None
            self.state.traces = None
            self.state.display_image = result["projection"]
            self.display_source = ("projection", projection_mode)
            self.clear_deepcad_cache()
            self.update_frame_controls()
            self.update_channel_color_buttons()
            self.redraw(preserve_view=False)
            self.log(f"处理完成：{label}")

        self.enqueue_task(label, worker, finish)

    def remove_vessels(self):
        self.show_preprocess_parameters("remove_vessel_artifact")

    def show_dff_heatmap(self):
        if not self.require_movie():
            return
        acceleration = self.acceleration()

        def operation(movie, baseline, _traces, _masks, _names, _fs, _frames, _cancel_event):
            return np.mean(core.compute_dff(movie, baseline, acceleration=acceleration), axis=0)

        def finish(heatmap):
            self.state.display_image = heatmap
            self.display_source = ("custom", "dff_heatmap")
            self.redraw(preserve_view=False)
            self.log("正在显示均值 dF/F 热图。")

        self.queue_analysis_operation("计算均值 dF/F 热图", operation, finish)

    def heatmap_mask(self, use_roi=True):
        if use_roi and self.state.roi_masks:
            return np.any(np.stack(self.state.roi_masks).astype(bool), axis=0)
        return np.ones(self.state.movie.shape[1:], dtype=bool)

    def generate_heatmap_avi(self):
        if not self.require_movie():
            return
        acceleration = self.acceleration()

        def operation(movie, baseline, _traces, _masks, _names, _fs, _frames, _cancel_event):
            return core.compute_dff(movie, baseline, acceleration=acceleration)

        self.queue_analysis_operation("准备热图 AVI", operation, self._show_heatmap_video_panel)

    def _show_heatmap_video_panel(self, dff):
        saved = self.user_settings.get("heatmap_avi", {})
        self._heatmap_panel_state = {
            "dff": np.asarray(dff, dtype=np.float32),
            "task": None,
            "original_source": self.display_source,
        }
        self.show_parameter_panel(
            "生成热图 AVI",
            [
                ("alpha", "叠加透明度", saved.get("alpha", 0.55)),
                ("sigma", "平滑 sigma", saved.get("sigma", 1.2)),
                ("low", "低百分位", saved.get("low", 1)),
                ("high", "高百分位", saved.get("high", 99)),
                ("max_display", "最大显示强度", saved.get("max_display", "auto")),
                {"key": "show_colorbar", "label": "显示色条", "default": bool(saved.get("show_colorbar", True)), "type": "checkbox"},
                {"key": "heatmap_only", "label": "仅显示热图", "default": bool(saved.get("heatmap_only", False)), "type": "checkbox"},
                {"key": "roi_only", "label": "仅显示 ROI", "default": bool(saved.get("roi_only", True)), "type": "checkbox"},
                {"type": "note", "text": "预览使用底部时间条选择的当前帧，并显示在主图像区域。"},
                {
                    "type": "buttons",
                    "columns": 1,
                    "actions": (
                        ("刷新预览", self._update_heatmap_preview_from_panel),
                        ("保存 AVI", self._save_heatmap_video_from_panel, "Accent.TButton"),
                        ("取消当前生成", self.cancel_current_task),
                    ),
                },
            ],
            cancel_command=self._close_heatmap_video_panel,
        )
        self._update_heatmap_preview_from_panel()

    def _close_heatmap_video_panel(self):
        state = self._heatmap_panel_state
        self._heatmap_panel_state = None
        self.clear_parameter_panel()
        if state and getattr(self, "display_source", (None,))[0] == "heatmap_preview":
            self._restore_movie_display_source(state.get("original_source"))

    def _heatmap_panel_values(self):
        values = self.panel_parameter_values()
        low = float(values["low"])
        high = float(values["high"])
        if high <= low:
            high = low + 1.0
        return {
            "alpha": float(values["alpha"]),
            "sigma": float(values["sigma"]),
            "low": low,
            "high": high,
            "max_display": core.parse_optional_float(values.get("max_display", "auto")),
            "show_colorbar": bool(values.get("show_colorbar", True)),
            "heatmap_only": bool(values.get("heatmap_only", False)),
            "roi_only": bool(values.get("roi_only", True)),
        }

    def _update_heatmap_preview_from_panel(self):
        state = getattr(self, "_heatmap_panel_state", None)
        if not state or self.state.movie is None:
            return
        try:
            values = self._heatmap_panel_values()
            frame = min(max(0, int(self.current_frame.get())), self.state.movie.shape[0] - 1)
            mask = self.heatmap_mask(use_roi=values["roi_only"])
            vmin, vmax = core.heatmap_limits(
                state["dff"],
                values["low"],
                values["high"],
                max_display=values["max_display"],
            )
            preview = core.render_heatmap_frame_rgb(
                state["dff"][frame],
                self.state.movie[frame],
                mask,
                vmin,
                vmax,
                values["alpha"],
                values["sigma"],
                show_colorbar=values["show_colorbar"],
                heatmap_only=values["heatmap_only"],
            )
            self.state.display_image = preview
            self.display_source = ("heatmap_preview", frame)
            self.redraw(preserve_view=False)
            self.set_parameter_feedback(f"已更新第 {frame + 1}/{self.state.movie.shape[0]} 帧热图预览。")
        except Exception as exc:
            self.set_parameter_feedback(f"热图预览失败：{exc}", error=True)

    def _save_heatmap_video_from_panel(self):
        state = getattr(self, "_heatmap_panel_state", None)
        if not state or self.state.movie is None:
            return
        try:
            values = self._heatmap_panel_values()
        except (TypeError, ValueError) as exc:
            self.set_parameter_feedback(f"热图参数无效：{exc}", error=True)
            return
        path = filedialog.asksaveasfilename(
            title="保存热图 AVI",
            initialdir=str(self.analysis_default_dir()),
            initialfile=f"{self.analysis_name()}_heatmap.avi",
            defaultextension=".avi",
            filetypes=[("AVI 视频", "*.avi")],
            confirmoverwrite=True,
        )
        if not path:
            return
        self.user_settings["heatmap_avi"] = dict(values)
        self.user_settings["heatmap_avi"]["max_display"] = self.panel_parameter_values().get("max_display", "auto")
        save_user_settings(self.user_settings)
        mask = self.heatmap_mask(use_roi=values["roi_only"])
        movie = np.asarray(self.state.movie, dtype=np.float32).copy()
        dff = np.asarray(state["dff"], dtype=np.float32).copy()
        fs = float(self.state.fs)
        self.set_parameter_feedback("已加入任务流，等待生成热图 AVI。")

        def progress(done, total):
            self.post_ui_callback(self._update_heatmap_save_progress, done, total)

        def worker(cancel_event):
            completed = core.save_heatmap_video(
                path,
                dff,
                movie,
                mask,
                fs,
                alpha=values["alpha"],
                sigma=values["sigma"],
                low_percentile=values["low"],
                high_percentile=values["high"],
                max_display=values["max_display"],
                show_colorbar=values["show_colorbar"],
                heatmap_only=values["heatmap_only"],
                cancel_event=cancel_event,
                progress_callback=progress,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return path, completed

        state["task"] = self.enqueue_task(
            "生成热图 AVI",
            worker,
            self._finish_heatmap_video_save,
            on_cancel=lambda: self.set_parameter_feedback("已取消生成热图 AVI。"),
        )

    def _update_heatmap_save_progress(self, done, total):
        if self._heatmap_panel_state is not None:
            self.set_parameter_feedback(f"正在生成热图 AVI：{done}/{total}")

    def _finish_heatmap_video_save(self, result):
        path, completed = result
        if completed:
            self.set_parameter_feedback(f"热图 AVI 已保存：{path}")
            self.log(f"热图 AVI 已保存：{path}")
        else:
            self.set_parameter_feedback("已取消生成热图 AVI。")

    def analysis_default_dir(self):
        if self.state.source_path:
            return Path(self.state.source_path).parent
        return APP_DIR

    def analysis_name(self):
        if self.state.source_path:
            stem = Path(self.state.source_path).stem
            if stem:
                return stem
        return "NewLight"

    def ask_analysis_save_path(self, title, initialfile, defaultextension, filetypes):
        path = filedialog.asksaveasfilename(
            title=title,
            initialdir=str(self.analysis_default_dir()),
            initialfile=initialfile,
            defaultextension=defaultextension,
            filetypes=filetypes,
            confirmoverwrite=True,
        )
        return Path(path) if path else None

    def ensure_baseline_image(self):
        if self.state.movie is not None and self.state.baseline_image is None:
            self.recompute_baseline_image()
        return self.state.baseline_image

    def ensure_traces(self, show_window=False):
        if self.state.traces is None:
            self.extract_traces(show_window=show_window)
        return self.state.traces

    def queue_analysis_operation(self, label, operation, on_complete, *, need_traces=False, need_baseline=True):
        """Run an analysis/export from a coherent movie snapshot in the FIFO queue."""
        if not self.require_movie():
            return None
        self.apply_protocol(update_baseline=False)
        if need_traces and not self.state.roi_masks:
            self.ensure_global_roi()
        if len(self.state.roi_names) != len(self.state.roi_masks):
            self.sync_roi_names()
        baseline_start = int(self.state.baseline_start_frame)
        baseline_duration = int(self.state.baseline_duration_frames)
        invalid_start_frames = int(self.state.invalid_start_frames)
        roi_masks = [np.asarray(mask, dtype=bool).copy() for mask in self.state.roi_masks]
        roi_names = list(self.state.roi_names)
        fs = float(self.state.fs)
        trigger_frames = np.asarray(self.state.trigger_frames, dtype=int).copy()
        acceleration = self.acceleration()
        baseline_correct = bool(self.trace_baseline_correct_var.get())
        baseline_window = int(float(self.trace_baseline_window_var.get()))
        smooth_window = int(float(self.trace_smooth_window_var.get()))

        def worker(cancel_event):
            source_id = id(self.state.movie)
            movie = np.asarray(self.state.movie, dtype=np.float32).copy()
            baseline = None
            if need_baseline or need_traces:
                baseline = core.baseline_from_frames(
                    movie,
                    baseline_start,
                    baseline_duration,
                    invalid_start_frames=invalid_start_frames,
                )
            if cancel_event.is_set():
                raise TaskCancelled()
            traces = None
            if need_traces:
                traces = core.extract_traces(movie, roi_masks, "dff", baseline, acceleration=acceleration)
                traces = core.process_traces(
                    traces,
                    baseline_correct=baseline_correct,
                    baseline_window=baseline_window,
                    smooth_window=smooth_window,
                )
            if cancel_event.is_set():
                raise TaskCancelled()
            output = operation(movie, baseline, traces, roi_masks, roi_names, fs, trigger_frames, cancel_event)
            if cancel_event.is_set():
                raise TaskCancelled()
            return source_id, baseline, traces, output

        def finish(result):
            source_id, baseline, traces, output = result
            if source_id != id(self.state.movie):
                self.log(f"已忽略过期的分析结果：{label}")
                return
            if baseline is not None:
                self.state.baseline_image = baseline
                self.state.dff_movie = None
            if traces is not None:
                self.state.traces = traces
            on_complete(output)

        return self.enqueue_task(label, worker, finish)

    def event_trigger_frames(self, pre_s, post_s):
        if not self.require_movie():
            return np.array([], dtype=int)
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
                    pre_s,
                    post_s,
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
                    pre_s,
                    post_s,
                )
            elif self.state.trigger_frames.size:
                frames = self.state.trigger_frames.astype(int)
            else:
                frames = np.array([], dtype=int)
        except Exception as exc:
            messagebox.showerror("刺激触发", str(exc))
            return np.array([], dtype=int)
        return np.asarray(frames, dtype=int)

    def stimulus_event_average(self):
        if not self.require_movie():
            return
        default_pre = self.state.pre_trigger_s if self.state.pre_trigger_s > 0 else 1.0
        default_post = self.state.post_trigger_s if self.state.post_trigger_s > 0 else 5.0
        vals = self.param_dialog(
            "刺激事件对齐平均",
            [
                ("pre_s", "事件前时间 (s)", default_pre),
                ("post_s", "事件后时间 (s)", default_post),
                ("heatmap_start_s", "热图起始时间 (s)", 0.0),
                ("heatmap_end_s", "热图结束时间 (s)", default_post),
                ("top_percent", "最高荧光比例 (%)", 0),
            ],
        )
        if not vals:
            return
        try:
            pre_s = max(0.0, float(vals["pre_s"]))
            post_s = max(0.0, float(vals["post_s"]))
            heatmap_start_s = float(vals["heatmap_start_s"])
            heatmap_end_s = float(vals["heatmap_end_s"])
            top_percent = core.parse_optional_float(vals.get("top_percent", "0"))
            if top_percent is not None:
                top_percent = max(0.0, min(100.0, float(top_percent)))
        except Exception as exc:
            messagebox.showerror("刺激事件对齐平均", f"参数无效：{exc}")
            return
        out_dir = filedialog.askdirectory(title="选择刺激事件分析输出文件夹", initialdir=str(self.analysis_default_dir()))
        if not out_dir:
            return
        try:
            self.apply_protocol(update_baseline=False)
            if not self.state.roi_masks:
                self.ensure_global_roi()
            if len(self.state.roi_names) != len(self.state.roi_masks):
                self.sync_roi_names()
            frames = np.asarray(self.state.trigger_frames, dtype=int).copy()
            interval = float(self.trigger_interval_var.get())
            stimulus = None if self.state.stimulus is None else np.asarray(self.state.stimulus, dtype=np.float32).copy()
            if frames.size == 0 and interval <= 0 and stimulus is None:
                self.log("刺激事件对齐平均需要已检测的触发事件或有效的间隔触发设置。")
                return
            baseline_start = int(self.state.baseline_start_frame)
            baseline_duration = int(self.state.baseline_duration_frames)
            invalid_start_frames = int(self.state.invalid_start_frames)
            roi_masks = [np.asarray(mask, dtype=bool).copy() for mask in self.state.roi_masks]
            roi_names = list(self.state.roi_names)
            fs = float(self.state.fs)
            stimulus_fs = float(self.state.stimulus_fs)
            trigger_start = float(self.trigger_start_var.get())
            trigger_threshold = float(self.trigger_threshold_var.get())
            movie_frames = int(self.state.movie.shape[0])
            name = self.analysis_name()
            acceleration = self.acceleration()
            baseline_correct = bool(self.trace_baseline_correct_var.get())
            baseline_window = int(float(self.trace_baseline_window_var.get()))
            smooth_window = int(float(self.trace_smooth_window_var.get()))

            def worker(cancel_event):
                source_id = id(self.state.movie)
                event_frames = frames
                if event_frames.size == 0:
                    if interval > 0:
                        event_frames = core.generate_interval_triggers(
                            trigger_start, interval, fs, movie_frames, pre_s, post_s
                        )
                    else:
                        samples = core.detect_stimulus_triggers(stimulus, stimulus_fs, threshold=trigger_threshold)
                        event_frames = core.map_stimulus_triggers_to_frames(
                            samples, stimulus_fs, fs, movie_frames, pre_s, post_s
                        )
                event_frames = np.asarray(event_frames, dtype=int)
                if event_frames.size == 0:
                    raise ValueError("未检测到可用于事件对齐的有效刺激触发。")
                movie = np.asarray(self.state.movie, dtype=np.float32).copy()
                baseline = core.baseline_from_frames(
                    movie,
                    baseline_start,
                    baseline_duration,
                    invalid_start_frames=invalid_start_frames,
                )
                traces = core.extract_traces(movie, roi_masks, "dff", baseline, acceleration=acceleration)
                traces = core.process_traces(
                    traces,
                    baseline_correct=baseline_correct,
                    baseline_window=baseline_window,
                    smooth_window=smooth_window,
                )
                if cancel_event.is_set():
                    raise TaskCancelled()
                paths = core.export_event_aligned_response(
                    out_dir,
                    name,
                    movie,
                    baseline,
                    roi_masks,
                    roi_names,
                    traces,
                    event_frames,
                    fs,
                    pre_s,
                    post_s,
                    heatmap_start_s=heatmap_start_s,
                    heatmap_end_s=heatmap_end_s,
                    top_percent=top_percent,
                    acceleration=acceleration,
                )
                if cancel_event.is_set():
                    raise TaskCancelled()
                return source_id, baseline, traces, event_frames, paths

            def finish(result):
                source_id, baseline, traces, event_frames, paths = result
                if source_id == id(self.state.movie):
                    self.state.baseline_image = baseline
                    self.state.dff_movie = None
                    self.state.traces = traces
                    self.state.trigger_frames = event_frames
                    self.redraw()
                self.log(f"刺激事件对齐平均已导出 {len(paths)} 个文件到 {out_dir}")
                messagebox.showinfo("刺激事件对齐平均", f"刺激事件分析已保存到：\n{out_dir}")

            self.enqueue_task("刺激事件对齐平均", worker, finish)
        except Exception as exc:
            traceback.print_exc()
            messagebox.showerror("刺激事件对齐平均失败", str(exc))

    def export_traces_csv(self):
        if not self.require_movie():
            return
        path = self.ask_analysis_save_path(
            "导出曲线 CSV",
            f"{self.analysis_name()}_deltaF_F_multiROI.csv",
            ".csv",
            [("CSV", "*.csv"), ("所有文件", "*.*")],
        )
        if path is None:
            return

        def operation(_movie, _baseline, traces, _masks, names, fs, _frames, _cancel_event):
            core.save_traces_csv(str(path), traces, names, fs)
            return path

        self.queue_analysis_operation("导出曲线 CSV", operation, lambda result: self.log(f"曲线 CSV 已导出：{result}"), need_traces=True)

    def export_trace_plot_png(self):
        if not self.require_movie():
            return
        path = self.ask_analysis_save_path(
            "导出曲线图 PNG",
            f"{self.analysis_name()}_traces.png",
            ".png",
            [("PNG 图像", "*.png"), ("所有文件", "*.*")],
        )
        if path is None:
            return

        def operation(_movie, _baseline, traces, _masks, names, fs, frames, _cancel_event):
            t = np.arange(traces.shape[0]) / fs
            core.plot_traces(str(path), t, traces, names, frames, fs)
            return path

        self.queue_analysis_operation("导出曲线图 PNG", operation, lambda result: self.log(f"曲线图 PNG 已导出：{result}"), need_traces=True)

    def export_roi_statistics_table(self):
        if not self.require_movie():
            return
        path = self.ask_analysis_save_path(
            "导出 ROI 统计",
            f"{self.analysis_name()}_ROI_statistics.xlsx",
            ".xlsx",
            [("Excel 工作簿", "*.xlsx"), ("CSV", "*.csv"), ("所有文件", "*.*")],
        )
        if path is None:
            return
        pre_trigger_s = float(self.state.pre_trigger_s)
        post_trigger_s = float(self.state.post_trigger_s)

        def operation(movie, _baseline, traces, masks, names, fs, frames, _cancel_event):
            stats = core.roi_statistics(traces, names, fs, frames)
            core.save_roi_statistics_table(
                str(path),
                stats,
                movie=movie,
                fs=fs,
                roi_count=len(masks),
                trigger_count=len(frames),
                pre_trigger_s=pre_trigger_s,
                post_trigger_s=post_trigger_s,
            )
            return path

        self.queue_analysis_operation("导出 ROI 统计", operation, lambda result: self.log(f"ROI 统计已导出：{result}"), need_traces=True)

    def export_correlation_outputs(self):
        if not self.require_movie():
            return
        out_dir = filedialog.askdirectory(title="选择相关性结果输出文件夹", initialdir=str(self.analysis_default_dir()))
        if not out_dir:
            return
        name = self.analysis_name()

        def operation(_movie, _baseline, traces, _masks, names, _fs, _frames, _cancel_event):
            if traces.shape[1] < 2:
                raise ValueError("导出相关性至少需要两条 ROI 曲线。")
            return core.save_correlation_outputs(out_dir, name, traces, names)

        self.queue_analysis_operation(
            "导出 ROI 相关性",
            operation,
            lambda paths: self.log(f"相关性结果已导出：{len(paths)} 个文件，位置为 {out_dir}"),
            need_traces=True,
        )

    def export_heatmap_png(self):
        if not self.require_movie():
            return
        path = self.ask_analysis_save_path(
            "导出均值 dF/F 热图",
            f"{self.analysis_name()}_diff_heatmap.png",
            ".png",
            [("PNG 图像", "*.png"), ("所有文件", "*.*")],
        )
        if path is None:
            return
        acceleration = self.acceleration()

        def operation(movie, baseline, _traces, masks, _names, _fs, _frames, _cancel_event):
            combined = np.any(np.stack(masks).astype(bool), axis=0) if masks else np.ones_like(baseline, dtype=bool)
            dff = core.compute_dff(movie, baseline, acceleration=acceleration)
            core.save_heatmap(str(path), np.mean(dff, axis=0), combined)
            return path

        self.queue_analysis_operation("导出 dF/F 热图", operation, lambda result: self.log(f"dF/F 热图 PNG 已导出：{result}"))

    def export_roi_snapshot(self):
        if not self.require_movie():
            return
        if len(self.state.roi_names) != len(self.state.roi_masks):
            self.sync_roi_names()
        out_dir = filedialog.askdirectory(title="选择 ROI 快照输出文件夹", initialdir=str(self.analysis_default_dir()))
        if not out_dir:
            return
        name = self.analysis_name()

        def operation(_movie, baseline, _traces, masks, names, _fs, _frames, _cancel_event):
            return core.save_roi_snapshot_outputs(out_dir, name, baseline, masks, names)

        self.queue_analysis_operation(
            "导出 ROI 快照",
            operation,
            lambda paths: self.log(f"ROI 快照已导出：{len(paths)} 个文件，位置为 {out_dir}"),
        )

    def export_summary_json(self):
        if not self.require_movie():
            return
        path = self.ask_analysis_save_path(
            "导出摘要 JSON",
            f"{self.analysis_name()}_summary.json",
            ".json",
            [("JSON", "*.json"), ("所有文件", "*.*")],
        )
        if path is None:
            return
        name = self.analysis_name()

        def operation(movie, _baseline, _traces, masks, _names, fs, frames, _cancel_event):
            return core.save_summary_json(str(path), name, movie, fs, masks, frames)

        self.queue_analysis_operation("导出摘要 JSON", operation, lambda result: self.log(f"摘要 JSON 已导出：{result}"), need_baseline=False)

    @staticmethod
    def _roi_preset_updates(engine, preset_name):
        if preset_name == "custom":
            return {}
        preset = roi_fit.QUALITY_PRESETS.get(preset_name, roi_fit.QUALITY_PRESETS["balanced"])
        updates = {"similarity_limit": preset.similarity_limit}
        if engine == "fast":
            updates["confidence"] = preset.fast_confidence
        else:
            updates.update(
                min_snr=preset.caiman_min_snr,
                rval_threshold=preset.caiman_rval,
                min_cnn_threshold=preset.caiman_cnn,
            )
        return updates

    def _apply_roi_quality_preset(self, engine):
        values = self.panel_parameter_values()
        preset_name = str(values.get("quality_preset", "balanced"))
        updates = self._roi_preset_updates(engine, preset_name)
        if not updates:
            self.set_parameter_feedback("自定义预设保留当前高级参数。")
            return
        for key, value in updates.items():
            variable = self.parameter_vars.get(key)
            if variable is not None:
                variable.set(f"{float(value):.6g}")
        self.set_parameter_feedback("质量预设已应用到可见参数；模型权重未改变。")

    def _fill_fast_area_from_current_rois(self):
        try:
            current_min = self._param_int(self.panel_parameter_values(), "min_area", 20, min_value=1)
            current_max = self._param_int(self.panel_parameter_values(), "max_area", 4000, min_value=1)
        except (TypeError, ValueError) as exc:
            self.set_parameter_feedback(f"面积参数无效：{exc}", error=True)
            return
        suggested_min, suggested_max = roi_fit.suggest_area_range(
            self.state.roi_masks,
            current_min,
            current_max,
        )
        if not self.state.roi_masks:
            self.set_parameter_feedback("当前没有 ROI，面积范围保持不变。")
            return
        self.parameter_vars["min_area"].set(str(suggested_min))
        self.parameter_vars["max_area"].set(str(suggested_max))
        if len(self.state.roi_masks) == 1:
            self.set_parameter_feedback(f"已按 1 个 ROI 填入最大面积 {suggested_max}；最小面积保持不变。")
        else:
            self.set_parameter_feedback(f"已按当前 ROI 填入面积范围 {suggested_min}-{suggested_max} px^2。")

    def _run_adaptive_roi_from_panel(self, engine):
        values = self.panel_parameter_values()
        if engine == "fast":
            self._run_fast_roi_from_panel(values, adaptive=True)
        else:
            self._run_caiman_roi_from_panel(values, adaptive=True)

    def caiman_roi(self):
        if not self.require_movie():
            return
        saved = self.user_settings.get("caiman_roi", {})
        self.show_parameter_panel(
            MODEL_NAMES["caiman_roi"],
            [
                {
                    "key": "quality_preset",
                    "label": "质量预设",
                    "default": saved.get("quality_preset", "balanced"),
                    "choices": (("recall", "高召回"), ("balanced", "均衡"), ("precision", "高精度"), ("custom", "自定义")),
                    "on_change": lambda: self._apply_roi_quality_preset("caiman"),
                },
                ("mode", "成像模式", saved.get("mode", "two_photon"), (("two_photon", "双光子 CNMF"), ("one_photon", "一光子 CNMF-E"))),
                ("cell_diameter", "细胞直径 (px)", saved.get("cell_diameter", 12)),
                ("components_per_patch", "每 Patch 初始成分数", saved.get("components_per_patch", 4)),
                ("background_components", "背景成分数", saved.get("background_components", 2)),
                ("spatial_subsample", "空间降采样", saved.get("spatial_subsample", 2)),
                ("temporal_subsample", "时间降采样", saved.get("temporal_subsample", 2)),
                ("ar_order", "钙信号 AR 阶数", saved.get("ar_order", 1)),
                ("merge_threshold", "成分合并阈值", saved.get("merge_threshold", 0.85)),
                ("min_snr", "最小时间 SNR", saved.get("min_snr", 2.0)),
                ("rval_threshold", "最小空间相关", saved.get("rval_threshold", 0.80)),
                {"key": "use_cnn", "label": "启用 CaImAn CNN 质量筛选", "default": bool(saved.get("use_cnn", True)), "type": "checkbox"},
                ("min_cnn_threshold", "最小 CNN 分数", saved.get("min_cnn_threshold", 0.90)),
                ("cnn_lowest", "CNN 最低拒绝界限", saved.get("cnn_lowest", 0.1)),
                ("footprint_threshold", "空间轮廓阈值", saved.get("footprint_threshold", 0.20)),
                ("similarity_limit", "自适应相似距离", saved.get("similarity_limit", 2.3)),
                {
                    "type": "buttons",
                    "columns": 1,
                    "actions": (("根据当前 ROI 自适应拟合并运行", lambda: self._run_adaptive_roi_from_panel("caiman"), "Accent.TButton"),),
                },
            ],
            self._run_caiman_roi_from_panel,
            description="在当前已预处理视频上进行钙源分解，输出相互独立的任意形状 ROI。运行时间通常长于快速分割。",
            apply_text="运行 CaImAn 分割",
            help_text=(
                "细胞直径用于估计 gSig，换算为 gSig = max(1, round(直径/4))。"
                "每 Patch 成分数控制局部初始化密度；SNR、空间相关和 CNN 分数越高，筛选越严格。"
                "空间轮廓阈值是每个 footprint 相对峰值阈值，降低可扩大轮廓，提高会收紧轮廓。"
                "一光子 CNMF-E 使用环形背景模型；双光子数据通常保持默认 CNMF。"
                "自适应拟合只校准轮廓、质量和相似度阈值，不训练或修改模型权重。"
            ),
        )

    def _run_caiman_roi_from_panel(self, values, adaptive=False):
        try:
            values = dict(values)
            quality_preset = str(values.get("quality_preset", "balanced"))
            if quality_preset not in {"recall", "balanced", "precision", "custom"}:
                raise ValueError("质量预设无效")
            values.update(self._roi_preset_updates("caiman", quality_preset))
            if adaptive and self.state.roi_masks:
                fitted_diameter = roi_fit.suggest_cell_diameter(
                    self.state.roi_masks,
                    values.get("cell_diameter", 12),
                )
                values["cell_diameter"] = fitted_diameter
                self.parameter_vars["cell_diameter"].set(f"{fitted_diameter:.4g}")
                self.set_parameter_feedback(f"当前 ROI 建议细胞直径 {fitted_diameter:.3g} px；已加入自适应任务。")
            mode = str(values.get("mode", "two_photon"))
            if mode not in {"two_photon", "one_photon"}:
                raise ValueError("成像模式无效")
            settings = {
                "quality_preset": quality_preset,
                "mode": mode,
                "cell_diameter": self._param_float(values, "cell_diameter", 12, min_value=1),
                "components_per_patch": self._param_int(values, "components_per_patch", 4, min_value=1),
                "background_components": self._param_int(values, "background_components", 2, min_value=0),
                "spatial_subsample": self._param_int(values, "spatial_subsample", 2, min_value=1),
                "temporal_subsample": self._param_int(values, "temporal_subsample", 2, min_value=1),
                "ar_order": self._param_int(values, "ar_order", 1, min_value=0, max_value=2),
                "merge_threshold": self._param_float(values, "merge_threshold", 0.85, min_value=0, max_value=1),
                "min_snr": self._param_float(values, "min_snr", 2.0, min_value=0),
                "rval_threshold": self._param_float(values, "rval_threshold", 0.85, min_value=-1, max_value=1),
                "use_cnn": bool(values.get("use_cnn", True)),
                "min_cnn_threshold": self._param_float(values, "min_cnn_threshold", 0.99, min_value=0, max_value=1),
                "cnn_lowest": self._param_float(values, "cnn_lowest", 0.1, min_value=0, max_value=1),
                "footprint_threshold": self._param_float(values, "footprint_threshold", 0.20, min_value=0.01, max_value=1),
                "similarity_limit": self._param_float(values, "similarity_limit", 2.3, min_value=0.1, max_value=10),
            }
        except (TypeError, ValueError) as exc:
            self.set_parameter_feedback(f"CaImAn 参数无效：{exc}", error=True)
            return
        self.apply_protocol(update_baseline=False)
        self.user_settings["caiman_roi"] = dict(settings)
        save_user_settings(self.user_settings)
        movie_source = self.state.movie
        source_id = id(movie_source)
        frame_rate = float(self.state.fs)
        invalid_start_frames = int(self.state.invalid_start_frames)

        if adaptive:
            self._enqueue_adaptive_roi("caiman", settings)
            return

        backend_settings = {
            key: value
            for key, value in settings.items()
            if key not in {"quality_preset", "similarity_limit"}
        }

        def worker(cancel_event):
            movie_snapshot = np.array(movie_source, copy=True)
            if cancel_event.is_set():
                raise TaskCancelled()
            result = core.run_caiman_roi_segmentation(
                movie_snapshot,
                session_dir=str(self.session_temp_dir),
                frame_rate=frame_rate,
                invalid_start_frames=invalid_start_frames,
                **backend_settings,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return source_id, result

        def finish(payload):
            result_source_id, result = payload
            if result_source_id != id(self.state.movie):
                self.log("已忽略过期的 CaImAn ROI 分割结果。")
                return
            self._finish_caiman_roi(result)

        self.enqueue_task(MODEL_NAMES["caiman_roi"], worker, finish)
        self.set_parameter_feedback("已加入任务流；CaImAn 将在后台执行，界面可继续操作。")

    def _finish_caiman_roi(self, result):
        if result.masks.shape[0] == 0:
            self.log("CaImAn 未筛选出有效成分；已保留当前 ROI，请降低质量阈值或检查细胞直径。")
            self.set_parameter_feedback("未检测到 ROI，现有 ROI 未改变。", error=True)
            return
        self.last_roi_backend_result = result
        self.set_rois(result.masks, MODEL_NAMES["caiman_roi"], names=result.names)
        quality = []
        for key, label in (("snr", "SNR"), ("r_values", "空间相关"), ("cnn_scores", "CNN")):
            values = np.asarray(result.arrays.get(key, []), dtype=np.float32)
            finite = values[np.isfinite(values)]
            if finite.size:
                quality.append(f"{label}均值={float(np.mean(finite)):.3g}")
        if quality:
            self.log("CaImAn 成分质量：" + "，".join(quality))
        if result.log:
            self.log(clean_backend_log(result.log)[-1200:])
        self.log(f"CaImAn ROI 摘要：{result.summary_path}")
        self.set_parameter_feedback(f"完成：检测到 {result.masks.shape[0]} 个 ROI。")

    def fast_roi(self):
        if not self.require_movie():
            return
        saved = self.user_settings.get("fast_roi", {})
        default_projection = saved.get("projection_mode", self.projection_mode.get())
        self.show_parameter_panel(
            MODEL_NAMES["fast_roi"],
            [
                {
                    "key": "quality_preset",
                    "label": "质量预设",
                    "default": saved.get("quality_preset", "balanced"),
                    "choices": (("recall", "高召回"), ("balanced", "均衡"), ("precision", "高精度"), ("custom", "自定义")),
                    "on_change": lambda: self._apply_roi_quality_preset("fast"),
                },
                ("projection_mode", "输入投影视图", default_projection, (("mean", "均值"), ("max", "最大值"), ("std", "标准差"), ("p25", "25% 分位"))),
                ("confidence", "检测置信度", saved.get("confidence", 0.25)),
                ("iou", "实例 IoU 阈值", saved.get("iou", 0.70)),
                ("image_size", "模型输入尺寸", saved.get("image_size", 960)),
                ("min_area", "最小面积 (px^2)", saved.get("min_area", 20)),
                ("max_area", "最大面积 (px^2)", saved.get("max_area", 4000)),
                ("device", "运行设备", saved.get("device", "auto"), (("auto", "自动"), ("cpu", "CPU"), ("0", "CUDA 0"))),
                ("similarity_limit", "自适应相似距离", saved.get("similarity_limit", 2.3)),
                {
                    "type": "buttons",
                    "columns": 1,
                    "actions": (
                        ("从当前 ROI 填入面积", self._fill_fast_area_from_current_rois),
                        ("根据当前 ROI 自适应拟合并运行", lambda: self._run_adaptive_roi_from_panel("fast"), "Accent.TButton"),
                    ),
                },
            ],
            self._run_fast_roi_from_panel,
            description="使用已授权的 NeuSuite 神经结构实例模型处理所选科学灰度投影；不使用伪彩或显示对比度。",
            apply_text="运行快速分割",
            help_text=(
                "置信度越低召回越高，也会增加假阳性；建议从 0.25 开始。IoU 控制重叠实例的抑制，"
                "较高值更容易保留邻近结构。模型输入尺寸越大越利于小结构，但显存占用和耗时增加。"
                "面积范围按恢复到原始分辨率后的实际像素计算。"
                "自适应拟合只校准轮廓、质量和相似度阈值，不训练或修改模型权重。"
            ),
        )

    def _run_fast_roi_from_panel(self, values, adaptive=False):
        try:
            values = dict(values)
            quality_preset = str(values.get("quality_preset", "balanced"))
            if quality_preset not in {"recall", "balanced", "precision", "custom"}:
                raise ValueError("质量预设无效")
            values.update(self._roi_preset_updates("fast", quality_preset))
            projection_mode = str(values.get("projection_mode", "mean"))
            if projection_mode not in {"mean", "max", "std", "p25"}:
                raise ValueError("投影视图无效")
            settings = {
                "quality_preset": quality_preset,
                "projection_mode": projection_mode,
                "confidence": self._param_float(values, "confidence", 0.25, min_value=0, max_value=1),
                "iou": self._param_float(values, "iou", 0.70, min_value=0, max_value=1),
                "image_size": self._param_int(values, "image_size", 960, min_value=320, max_value=1920),
                "min_area": self._param_int(values, "min_area", 20, min_value=1),
                "max_area": self._param_int(values, "max_area", 4000, min_value=1),
                "device": str(values.get("device", "auto")),
                "similarity_limit": self._param_float(values, "similarity_limit", 2.3, min_value=0.1, max_value=10),
            }
            if settings["max_area"] < settings["min_area"]:
                raise ValueError("最大面积必须大于或等于最小面积")
        except (TypeError, ValueError) as exc:
            self.set_parameter_feedback(f"快速 ROI 参数无效：{exc}", error=True)
            return
        self.apply_protocol(update_baseline=False)
        self.user_settings["fast_roi"] = dict(settings)
        save_user_settings(self.user_settings)
        movie_source = self.state.movie
        source_id = id(movie_source)
        baseline_start = int(self.state.baseline_start_frame)
        baseline_duration = int(self.state.baseline_duration_frames)
        invalid_start_frames = int(self.state.invalid_start_frames)
        acceleration = self.acceleration()

        if adaptive:
            self._enqueue_adaptive_roi("fast", settings)
            return

        backend_settings = {
            key: value
            for key, value in settings.items()
            if key not in {"quality_preset", "similarity_limit"}
        }

        def worker(cancel_event):
            projection = core.compute_projection(
                np.asarray(movie_source, dtype=np.float32),
                projection_mode,
                acceleration=acceleration,
                mean_start_frame=baseline_start,
                mean_duration_frames=baseline_duration,
                invalid_start_frames=invalid_start_frames,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            result = core.run_fast_roi_segmentation(
                projection,
                session_dir=str(self.session_temp_dir),
                **backend_settings,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return source_id, result

        def finish(payload):
            result_source_id, result = payload
            if result_source_id != id(self.state.movie):
                self.log("已忽略过期的快速 ROI 分割结果。")
                return
            self._finish_fast_roi(result)

        self.enqueue_task(MODEL_NAMES["fast_roi"], worker, finish)
        self.set_parameter_feedback("已加入任务流；快速分割将在后台执行。")

    def _finish_fast_roi(self, result):
        if result.masks.shape[0] == 0:
            self.log("快速 ROI 分割未检测到实例；已保留当前 ROI。")
            self.set_parameter_feedback("未检测到 ROI，现有 ROI 未改变。", error=True)
            return
        self.last_roi_backend_result = result
        self.set_rois(result.masks, MODEL_NAMES["fast_roi"], names=result.names)
        scores = np.asarray(result.arrays.get("scores", []), dtype=np.float32)
        if scores.size:
            self.log(f"快速 ROI 置信度：均值={float(np.mean(scores)):.3g}，最低={float(np.min(scores)):.3g}")
        if result.log:
            self.log(clean_backend_log(result.log)[-1200:])
        self.log(f"快速 ROI 摘要：{result.summary_path}")
        self.set_parameter_feedback(f"完成：检测到 {result.masks.shape[0]} 个 ROI。")

    @staticmethod
    def _roi_backend_settings(engine, settings):
        excluded = {"quality_preset", "similarity_limit"}
        values = {key: value for key, value in settings.items() if key not in excluded}
        if engine == "fast":
            return values
        values.pop("projection_mode", None)
        return values

    @staticmethod
    def _roi_generation_parameters(engine, settings, frame_rate):
        if engine == "fast":
            keys = ("image_size", "iou", "min_area", "max_area", "device")
            values = {key: settings[key] for key in keys}
            values["candidate_confidence"] = 0.05
            return values
        keys = (
            "mode",
            "cell_diameter",
            "components_per_patch",
            "background_components",
            "spatial_subsample",
            "temporal_subsample",
            "ar_order",
            "merge_threshold",
            "use_cnn",
            "footprint_threshold",
        )
        values = {key: settings[key] for key in keys}
        values["frame_rate"] = float(frame_rate)
        return values

    @staticmethod
    def _roi_path_identity(path):
        path = Path(path).resolve()
        try:
            if path.is_file():
                stat = path.stat()
                return (str(path), 1, int(stat.st_size), int(stat.st_mtime_ns))
            if path.is_dir():
                entries = []
                for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
                    stat = item.stat()
                    entries.append((str(item.relative_to(path)), int(stat.st_size), int(stat.st_mtime_ns)))
                return (str(path), len(entries), tuple(entries))
        except OSError:
            pass
        return (str(path), 0)

    @staticmethod
    def _roi_model_identity(engine):
        if engine != "fast":
            environment = core.caiman_worker_environment()
            prefix = core.resolve_conda_environment_prefix(environment)
            runtime = Path(environment) if prefix is None else prefix / "conda-meta"
            return (
                str(environment),
                NewLightApp._roi_path_identity(runtime),
                NewLightApp._roi_path_identity(core.CAIMAN_RESOURCE_DIR),
            )
        return (
            NewLightApp._roi_path_identity(core.NEUSUITE_DEFAULT_WEIGHTS),
            NewLightApp._roi_path_identity(core.NEUSUITE_RUNTIME_ROOT),
            NewLightApp._roi_path_identity(core.PROJECT_DIR / "NeuSuite_RuntimeDeps"),
        )

    @staticmethod
    def _candidate_bank_from_result(engine, result, signature, generation_parameters):
        quality_keys = (
            ("scores", "source_indices")
            if engine == "fast"
            else ("snr", "r_values", "cnn_scores", "component_indices", "preset_accepted")
        )
        quality = {
            key: np.asarray(result.arrays[key]).copy()
            for key in quality_keys
            if key in result.arrays
        }
        return roi_fit.CandidateBank(
            engine=engine,
            masks=np.asarray(result.masks, dtype=bool).copy(),
            names=tuple(result.names),
            model_quality=quality,
            source_signature=signature,
            generation_parameters=dict(generation_parameters),
        )

    @staticmethod
    def _adaptive_quality_preset(engine, settings):
        preset_name = str(settings.get("quality_preset", "balanced"))
        if preset_name != "custom":
            return preset_name
        balanced = roi_fit.QUALITY_PRESETS["balanced"]
        return roi_fit.QualityPreset(
            fast_confidence=float(settings.get("confidence", balanced.fast_confidence)),
            caiman_min_snr=float(settings.get("min_snr", balanced.caiman_min_snr)),
            caiman_rval=float(settings.get("rval_threshold", balanced.caiman_rval)),
            caiman_cnn=float(settings.get("min_cnn_threshold", balanced.caiman_cnn)),
            similarity_limit=float(settings.get("similarity_limit", balanced.similarity_limit)),
        )

    def _enqueue_adaptive_roi(self, engine, settings):
        movie_source = self.state.movie
        source_id = id(movie_source)
        source_generation = int(self.movie_generation)
        source_roi_revision = int(self.state.roi_revision)
        reference_masks = tuple(np.asarray(mask, dtype=bool).copy() for mask in self.state.roi_masks)
        reference_metadata = tuple(dict(item) for item in self.state.roi_metadata)
        frame_rate = float(self.state.fs)
        invalid_start_frames = int(self.state.invalid_start_frames)
        baseline_window = (
            int(self.state.baseline_start_frame),
            int(self.state.baseline_duration_frames),
        )
        projection_mode = str(settings.get("projection_mode", "mean")) if engine == "fast" else "mean"
        generation_parameters = self._roi_generation_parameters(engine, settings, frame_rate)
        signature = roi_fit.candidate_source_signature(
            engine,
            source_generation,
            tuple(movie_source.shape[1:]),
            invalid_start_frames,
            projection_mode,
            baseline_window if engine == "fast" else (0, 0),
            self._roi_model_identity(engine),
            generation_parameters,
        )
        cached_bank = self.roi_candidate_banks[engine]
        quality_preset = self._adaptive_quality_preset(engine, settings)
        backend_settings = self._roi_backend_settings(engine, settings)
        acceleration = self.acceleration()

        def worker(cancel_event):
            movie_snapshot = np.asarray(movie_source, dtype=np.float32).copy()
            valid_movie = movie_snapshot[invalid_start_frames:]
            if cancel_event.is_set():
                raise TaskCancelled()
            if engine == "fast":
                projection = core.compute_projection(
                    movie_snapshot,
                    projection_mode,
                    acceleration=acceleration,
                    mean_start_frame=baseline_window[0],
                    mean_duration_frames=baseline_window[1],
                    invalid_start_frames=invalid_start_frames,
                )
            else:
                projection = core.compute_projection(
                    movie_snapshot,
                    "mean",
                    acceleration=acceleration,
                    invalid_start_frames=invalid_start_frames,
                )
            bank = cached_bank
            reused = bank is not None and bank.source_signature == signature
            backend_result = None
            if not reused:
                if engine == "fast":
                    backend_result = core.run_fast_roi_segmentation(
                        projection,
                        session_dir=str(self.session_temp_dir),
                        candidate_mode=True,
                        candidate_confidence=0.05,
                        **backend_settings,
                    )
                else:
                    backend_result = core.run_caiman_roi_segmentation(
                        movie_snapshot,
                        session_dir=str(self.session_temp_dir),
                        frame_rate=frame_rate,
                        invalid_start_frames=invalid_start_frames,
                        candidate_mode=True,
                        **backend_settings,
                    )
                bank = self._candidate_bank_from_result(
                    engine,
                    backend_result,
                    signature,
                    generation_parameters,
                )
            if cancel_event.is_set():
                raise TaskCancelled()
            fitted = roi_fit.adapt_candidate_bank(
                valid_movie,
                projection,
                reference_masks,
                reference_metadata,
                bank,
                quality_preset,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return {
                "source_id": source_id,
                "source_generation": source_generation,
                "source_roi_revision": source_roi_revision,
                "bank": bank,
                "reused": reused,
                "backend_result": backend_result,
                "fitted": fitted,
            }

        def finish(payload):
            if (
                payload["source_id"] != id(self.state.movie)
                or payload["source_generation"] != self.movie_generation
            ):
                self.log("视频已变化，已忽略过期的自适应 ROI 结果。")
                return
            self.roi_candidate_banks[engine] = payload["bank"]
            if not roi_fit.adaptive_result_is_current(
                payload["source_generation"],
                payload["source_roi_revision"],
                current_generation=self.movie_generation,
                current_roi_revision=self.state.roi_revision,
            ):
                self.log("ROI 列表已变化；候选缓存已保留，请重新运行自适应拟合。")
                self.set_parameter_feedback("ROI 已在任务期间变化，未覆盖当前列表；请重新运行。", error=True)
                return
            fitted = payload["fitted"]
            if not fitted.masks:
                self.log("自适应候选为空；当前 ROI 列表保持不变。")
                self.set_parameter_feedback("未找到可用候选，当前 ROI 未改变。", error=True)
                return
            names = [item["base_name"] for item in fitted.metadata]
            self.set_rois(
                fitted.masks,
                f"{MODEL_NAMES['fast_roi'] if engine == 'fast' else MODEL_NAMES['caiman_roi']} 自适应",
                names=names,
                metadata=fitted.metadata,
            )
            cache_text = "复用候选缓存" if payload["reused"] else "新建候选缓存"
            if payload["backend_result"] is not None:
                self.last_roi_backend_result = payload["backend_result"]
            summary = (
                f"{cache_text}；保护 {fitted.protected_count} 个，新增 {fitted.selected_count} 个，"
                f"低质量保留 {fitted.low_quality_count} 个。"
            )
            self.log(f"自适应 ROI 完成：{summary}")
            self.set_parameter_feedback(summary)

        label = f"{MODEL_NAMES['fast_roi'] if engine == 'fast' else MODEL_NAMES['caiman_roi']} 自适应拟合"
        self.enqueue_task(label, worker, finish)
        reference_text = f"参考 ROI={len(reference_masks)}" if reference_masks else "无参考 ROI，将按质量预设筛选"
        self.set_parameter_feedback(f"已加入任务流；{reference_text}。拟合只校准参数，不训练模型权重。")

    def auto_roi(self):
        if not self.require_movie():
            return
        image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        if image is not None and np.asarray(image).ndim != 2:
            image = self.state.baseline_image
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
                    f"内置自动 ROI 种子点 ({x:.1f}, {y:.1f}) 建议面积范围 {min_area_default}-{max_area_default} px^2 "
                    f"（估计面积约 {cell_area_est:.0f} px^2，直径约 {cell_diameter_est:.1f} px）。"
                )
        self.show_parameter_panel(
            "内置自动 ROI",
            [
                ("min_area", "最小面积 (px^2)", min_area_default),
                ("max_area", "最大面积 (px^2)", max_area_default),
                {
                    "type": "action",
                    "text": "使用最后 2 个 ROI 估算面积范围",
                    "command": self._auto_roi_use_current_samples,
                },
            ],
            self._run_auto_roi_from_panel,
            description="可先绘制最小和最大的示例 ROI，再自动填入面积范围。",
            apply_text="运行自动 ROI",
        )

    def _auto_roi_use_current_samples(self):
        masks = list(getattr(self.state, "roi_masks", []))
        if len(masks) < 2:
            self.set_parameter_feedback("请先绘制至少两个示例 ROI。", error=True)
            return
        areas = [int(np.count_nonzero(np.asarray(mask, dtype=bool))) for mask in masks[-2:]]
        areas = [area for area in areas if area > 0]
        if len(areas) < 2:
            self.set_parameter_feedback("最后两个 ROI 的面积必须大于 0。", error=True)
            return
        sample_min = max(3, int(round(min(areas) * 0.9)))
        sample_max = max(sample_min + 1, int(round(max(areas) * 1.1)))
        self.parameter_vars["min_area"].set(str(sample_min))
        self.parameter_vars["max_area"].set(str(sample_max))
        self.set_parameter_feedback(f"已根据示例 ROI 填入：{areas[0]}、{areas[1]} px^2。")
        self.log(f"内置自动 ROI 已根据最后两个 ROI 填入面积范围：{areas[0]}、{areas[1]} px^2 -> {sample_min}-{sample_max} px^2。")

    def _run_auto_roi_from_panel(self, values):
        try:
            min_area = max(3, int(float(values["min_area"])))
            max_area = max(min_area + 1, int(float(values["max_area"])))
        except (KeyError, TypeError, ValueError):
            self.set_parameter_feedback("请输入有效的数字面积范围。", error=True)
            return
        image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        if image is not None and np.asarray(image).ndim != 2:
            image = self.state.baseline_image
        if image is None:
            self.set_parameter_feedback("没有可用于自动 ROI 的图像。", error=True)
            return
        image_snapshot = np.asarray(image, dtype=np.float32).copy()
        self.run_worker(
            "内置自动 ROI",
            lambda: core.auto_roi_from_image(image_snapshot, min_area, max_area),
            lambda rois: self.set_rois(rois, "内置自动 ROI"),
        )
        self.set_parameter_feedback("已加入任务流，正在运行自动 ROI。")

    def neuroseg3_roi(self):
        if not self.require_movie():
            return
        weights = core.available_neuroseg3_weights()
        saved = self.user_settings.get("neuroseg3", {})
        default_weight = saved.get("weights") if saved.get("weights") in weights else (weights[0] if weights else "")
        for path in weights:
            if not saved.get("weights") and "segmentation" in path.lower():
                default_weight = path
                break
        choices = tuple((path, Path(path).name) for path in weights)
        self.show_parameter_panel(
            MODEL_NAMES["neuroseg3"],
            [
                ("conf", "检测置信度", saved.get("conf", 0.002)),
                {"key": "mask_threshold", "label": "蒙版像素阈值", "default": "固定为 0.50", "type": "readonly"},
                {
                    "key": "weights",
                    "label": "模型权重 (.pt)",
                    "default": default_weight,
                    "type": "path",
                    "choices": choices,
                    "browse": {
                        "title": "选择 NeuroSeg3 模型权重",
                        "filetypes": [("PyTorch 权重", "*.pt"), ("所有文件", "*.*")],
                        "initialdir": str(core.NEUROSEG3_DIR / "weights") if (core.NEUROSEG3_DIR / "weights").exists() else str(APP_DIR),
                    },
                },
                {"key": "fallback", "label": "未检测到蒙版时使用内置方法", "default": bool(saved.get("fallback", True)), "type": "checkbox"},
            ],
            self._run_neuroseg3_from_panel,
            description="检测置信度通常需要很低的值；0.002 是当前数据的推荐起点。",
            apply_text="运行 NeuroSeg3",
        )

    def _run_neuroseg3_from_panel(self, values):
        try:
            conf = float(values["conf"])
        except (KeyError, TypeError, ValueError):
            self.set_parameter_feedback("检测置信度必须是数字。", error=True)
            return
        if not 0.0 <= conf <= 1.0:
            self.set_parameter_feedback("检测置信度必须位于 0 到 1 之间。", error=True)
            return
        weights_path = str(values.get("weights", "")).strip() or None
        fallback = bool(values.get("fallback", True))
        self.user_settings["neuroseg3"] = {"conf": round(conf, 6), "weights": weights_path or "", "fallback": fallback}
        save_user_settings(self.user_settings)
        image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
        if image is not None and np.asarray(image).ndim != 2:
            image = self.state.baseline_image
        if image is None:
            self.set_parameter_feedback("没有可用于分割的图像。", error=True)
            return
        out_dir = self.temp_work_dir("NeuroSeg3")
        mask_threshold = 0.5
        image_snapshot = np.asarray(image, dtype=np.float32).copy()
        self.run_worker(
            MODEL_NAMES["neuroseg3"],
            lambda: core.run_neuroseg3(image_snapshot, str(out_dir), weights=weights_path, conf=conf, mask_threshold=mask_threshold),
            lambda result: self._finish_neuroseg3(result, fallback=fallback),
        )
        self.set_parameter_feedback("已加入任务流，正在运行 NeuroSeg3 自动 ROI 分割。")

    def _finish_neuroseg3(self, result, fallback=True):
        masks, log = result
        if not masks and fallback:
            image = self.state.display_image if self.state.display_image is not None else self.state.baseline_image
            masks = core.auto_roi_from_image(image, 20, 4000)
            self.set_rois(masks, "NeuroSeg3 未检测到 ROI，已使用内置方法")
        else:
            self.set_rois(masks, MODEL_NAMES["neuroseg3"])
        if log.strip():
            self.log(log.strip()[-800:])

    def caiman_motion(self):
        self.show_preprocess_parameters("caiman_motion")

    def run_caiman_motion_from_values(self, values):
        if not self.require_movie():
            return
        mode = str(values.get("mode", "piecewise")).strip().lower()
        if mode not in {"rigid", "piecewise"}:
            mode = "piecewise"
        max_shift = self._param_int(values, "max_shift", 12, min_value=1)
        stride = self._param_int(values, "stride", 48, min_value=1)
        overlap = self._param_int(values, "overlap", 24, min_value=0)
        max_deviation = self._param_int(values, "max_deviation", 5, min_value=0)
        out_dir = self.temp_work_dir("CaImAn")
        previous_source = self.display_source
        def worker(cancel_event):
            source_id = id(self.state.movie)
            movie = np.asarray(self.state.movie, dtype=np.float32).copy()
            result = core.run_caiman_motion(
                movie,
                str(out_dir),
                mode=mode,
                max_shift=max_shift,
                stride=stride,
                overlap=overlap,
                max_deviation=max_deviation,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return source_id, result

        def finish(payload):
            source_id, result = payload
            if source_id != id(self.state.movie):
                self.log("已忽略过期的 CaImAn 运动矫正结果。")
                return
            self.push_history(MODEL_NAMES["caiman"])
            self._finish_caiman_motion(result, previous_source=previous_source)

        self.enqueue_task(
            MODEL_NAMES["caiman"],
            worker,
            finish,
        )

    def _finish_caiman_motion(self, result, previous_source=("projection", "mean")):
        movie, log, preview_path = result
        self.state.movie = movie
        self.mark_movie_changed()
        self.clear_converted_color_source()
        self.state.converted_channel_movies = (movie,)
        self.state.channel_colors = ("gray",)
        self.update_channel_color_buttons()
        self.clear_deepcad_cache()
        self.state.baseline_image = None
        self.state.dff_movie = None
        self.state.traces = None
        self.update_frame_controls()
        if previous_source[0] == "frame":
            self.show_frame(previous_source[1])
        else:
            self.state.display_image = movie[0]
            self.display_source = ("frame", 0)
            self.redraw(preserve_view=False)
        self.queue_movie_view_refresh("生成 CaImAn 结果预览")
        self.log("CaImAn 结果已载入当前临时预览；请使用“保存当前视频”永久保存。")
        self.log(f"CaImAn 临时预览文件：{preview_path}")
        log = clean_backend_log(log)
        if log:
            self.log(log[-800:])

    def enqueue_task(self, label, worker, callback, on_error=None, on_cancel=None, cancellable=True):
        """Queue a cancellable worker that never accesses Tk directly."""
        def handle_error(exc):
            if on_error is not None:
                on_error(exc)
                return
            self.log(f"后台处理失败：{exc}")
            messagebox.showerror("后台处理失败", self.worker_error_summary(str(exc)))

        def handle_cancel():
            if on_cancel is not None:
                on_cancel()
            else:
                self.log(f"已取消：{label}")

        task = self.task_controller.enqueue_task(
            label,
            worker,
            callback,
            handle_error,
            handle_cancel,
            cancellable=cancellable,
        )
        self.log(f"已加入任务流：{label}")
        self.render_task_flow(force=True)
        return task

    def run_worker(self, label, func, callback, on_error=None, on_cancel=None, cancellable=True):
        """Queue a legacy zero-argument worker through the global FIFO controller."""
        def worker(cancel_event):
            if cancel_event.is_set():
                raise TaskCancelled()
            result = func()
            if cancel_event.is_set():
                raise TaskCancelled()
            return result

        return self.enqueue_task(label, worker, callback, on_error, on_cancel, cancellable)

    def _poll_worker(self):
        try:
            while True:
                callback, args = self.ui_callback_queue.get_nowait()
                callback(*args)
        except queue.Empty:
            pass
        self.task_controller.drain_results()
        self.render_task_flow()
        self.root.after(100, self._poll_worker)

    def queue_trace_extraction(self, label="提取 dF/F 曲线", show_window=True, on_ready=None):
        if not self.require_movie():
            return None
        if not self.state.roi_masks:
            self.ensure_global_roi()
        self.apply_protocol(update_baseline=False)
        if len(self.state.roi_names) != len(self.state.roi_masks):
            self.sync_roi_names()
        baseline_start = int(self.state.baseline_start_frame)
        baseline_duration = int(self.state.baseline_duration_frames)
        invalid_start_frames = int(self.state.invalid_start_frames)
        roi_masks = [np.asarray(mask, dtype=bool).copy() for mask in self.state.roi_masks]
        baseline_correct = bool(self.trace_baseline_correct_var.get())
        baseline_window = int(float(self.trace_baseline_window_var.get()))
        smooth_window = int(float(self.trace_smooth_window_var.get()))
        acceleration = self.acceleration()

        def worker(cancel_event):
            source_id = id(self.state.movie)
            movie = np.asarray(self.state.movie, dtype=np.float32).copy()
            baseline = core.baseline_from_frames(
                movie,
                baseline_start,
                baseline_duration,
                invalid_start_frames=invalid_start_frames,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            traces = core.extract_traces(movie, roi_masks, "dff", baseline, acceleration=acceleration)
            traces = core.process_traces(
                traces,
                baseline_correct=baseline_correct,
                baseline_window=baseline_window,
                smooth_window=smooth_window,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            return source_id, baseline, traces

        def finish(result):
            source_id, baseline, traces = result
            if source_id != id(self.state.movie):
                self.log(f"已忽略过期的曲线提取结果：{label}")
                return
            self.state.baseline_image = baseline
            self.state.dff_movie = None
            self.state.traces = traces
            correction = "开启" if baseline_correct else "关闭"
            self.log(f"已提取曲线：{traces.shape}，基线校正={correction}，平滑窗口={smooth_window}")
            if on_ready is not None:
                on_ready(traces, baseline)
            if show_window:
                self.show_trace_window(traces)

        return self.enqueue_task(label, worker, finish)

    def extract_traces(self, show_window=True):
        self.queue_trace_extraction(show_window=show_window)

    def show_trace_window(self, traces):
        win = tk.Toplevel(self.root)
        win.title("ROI dF/F 曲线")
        win.configure(bg=THEME["bg"])
        fig = Figure(figsize=(9, 5), dpi=100)
        fig.patch.set_facecolor(THEME["bg"])
        ax = fig.add_subplot(111)
        ax.set_facecolor("#06101f")
        t = np.arange(traces.shape[0]) / self.state.fs
        offsets = np.arange(traces.shape[1]) * (np.nanstd(traces) * 4 + 0.1)
        for i in range(traces.shape[1]):
            ax.plot(t, traces[:, i] + offsets[i], color=core.roi_color_hex(i), lw=0.9)
        for frame in self.state.trigger_frames:
            if 0 <= frame < traces.shape[0]:
                ax.axvline(frame / self.state.fs, color="red", linestyle="--", linewidth=0.8, alpha=0.55)
        ax.set_yticks(offsets)
        ax.set_yticklabels(self.state.roi_names)
        ax.set_xlabel("时间 (s)")
        ax.set_title("ROI dF/F 曲线")
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
        def operation(_movie, _baseline, traces, _masks, names, fs, frames, _cancel_event):
            return core.roi_statistics(traces, names, fs, frames)

        def finish(stats):
            win = tk.Toplevel(self.root)
            win.title("ROI 统计")
            win.configure(bg=THEME["bg"])
            table = ttk.Treeview(win, columns=list(stats.columns), show="headings", height=min(18, max(4, len(stats))))
            for col in stats.columns:
                table.heading(col, text=ROI_STAT_COLUMN_LABELS.get(col, col))
                table.column(col, width=110, anchor="center")
            for _, row in stats.iterrows():
                values = [f"{value:.5g}" if isinstance(value, float) else str(value) for value in row]
                table.insert("", "end", values=values)
            table.pack(fill="both", expand=True)

        self.queue_analysis_operation("计算 ROI 统计", operation, finish, need_traces=True)

    def show_trial_average(self):
        if not self.require_movie():
            return
        self.apply_protocol(update_baseline=False)
        if not self.state.roi_masks:
            self.ensure_global_roi()
        if len(self.state.roi_names) != len(self.state.roi_masks):
            self.sync_roi_names()

        trigger_frames = np.asarray(self.state.trigger_frames, dtype=int).copy()
        try:
            interval = float(self.trigger_interval_var.get())
            trigger_start = float(self.trigger_start_var.get())
            trigger_threshold = float(self.trigger_threshold_var.get())
        except ValueError as exc:
            messagebox.showerror("试次平均", f"刺激触发参数无效：{exc}")
            return
        stimulus = None if self.state.stimulus is None else np.asarray(self.state.stimulus, dtype=np.float32).copy()
        if trigger_frames.size == 0 and interval <= 0 and stimulus is None:
            self.log("试次平均需要已检测的触发事件、有效的触发间隔或刺激输入数据。")
            return

        baseline_start = int(self.state.baseline_start_frame)
        baseline_duration = int(self.state.baseline_duration_frames)
        invalid_start_frames = int(self.state.invalid_start_frames)
        roi_masks = [np.asarray(mask, dtype=bool).copy() for mask in self.state.roi_masks]
        roi_names = list(self.state.roi_names)
        fs = float(self.state.fs)
        stimulus_fs = float(self.state.stimulus_fs)
        pre_trigger_s = float(self.state.pre_trigger_s)
        post_trigger_s = float(self.state.post_trigger_s)
        acceleration = self.acceleration()
        baseline_correct = bool(self.trace_baseline_correct_var.get())
        baseline_window = int(float(self.trace_baseline_window_var.get()))
        smooth_window = int(float(self.trace_smooth_window_var.get()))

        def worker(cancel_event):
            source_id = id(self.state.movie)
            movie = np.asarray(self.state.movie, dtype=np.float32).copy()
            event_frames = trigger_frames
            if event_frames.size == 0:
                if interval > 0:
                    event_frames = core.generate_interval_triggers(
                        trigger_start,
                        interval,
                        fs,
                        movie.shape[0],
                        pre_trigger_s,
                        post_trigger_s,
                    )
                else:
                    samples = core.detect_stimulus_triggers(
                        stimulus,
                        stimulus_fs,
                        threshold=trigger_threshold,
                    )
                    event_frames = core.map_stimulus_triggers_to_frames(
                        samples,
                        stimulus_fs,
                        fs,
                        movie.shape[0],
                        pre_trigger_s,
                        post_trigger_s,
                    )
            event_frames = np.asarray(event_frames, dtype=int)
            if event_frames.size == 0:
                raise ValueError("未检测到可用于试次平均的有效刺激触发。")
            if cancel_event.is_set():
                raise TaskCancelled()
            baseline = core.baseline_from_frames(
                movie,
                baseline_start,
                baseline_duration,
                invalid_start_frames=invalid_start_frames,
            )
            traces = core.extract_traces(movie, roi_masks, "dff", baseline, acceleration=acceleration)
            traces = core.process_traces(
                traces,
                baseline_correct=baseline_correct,
                baseline_window=baseline_window,
                smooth_window=smooth_window,
            )
            if cancel_event.is_set():
                raise TaskCancelled()
            trials, trial_t = core.trial_average(traces, event_frames, fs, pre_trigger_s, post_trigger_s)
            if trials.size == 0:
                raise ValueError("所选事件前后窗口内没有完整试次。")
            return source_id, baseline, traces, event_frames, trials, trial_t

        def finish(result):
            source_id, baseline, traces, event_frames, trials, trial_t = result
            if source_id != id(self.state.movie):
                self.log("已忽略过期的试次平均结果。")
                return
            self.state.baseline_image = baseline
            self.state.dff_movie = None
            self.state.traces = traces
            self.state.trigger_frames = event_frames
            self._show_trial_average_window(trials, trial_t, roi_names)
            self.log(f"已显示试次平均，n={trials.shape[0]}。")

        self.enqueue_task("计算试次平均", worker, finish)

    def _show_trial_average_window(self, trials, trial_t, roi_names):
        mean_trial = np.nanmean(trials, axis=0)
        win = tk.Toplevel(self.root)
        win.title("试次平均")
        win.configure(bg=THEME["bg"])
        fig = Figure(figsize=(9, 5), dpi=100)
        fig.patch.set_facecolor(THEME["bg"])
        ax = fig.add_subplot(111)
        ax.set_facecolor("#06101f")
        offsets = np.arange(mean_trial.shape[1]) * (np.nanstd(mean_trial) * 4 + 0.1)
        for i in range(mean_trial.shape[1]):
            ax.plot(trial_t, mean_trial[:, i] + offsets[i], color=core.roi_color_hex(i), lw=1.0)
        ax.axvline(0, color="red", linestyle="--", linewidth=1.0)
        ax.set_yticks(offsets)
        ax.set_yticklabels(roi_names)
        ax.set_xlabel("相对触发时间 (s)")
        ax.set_title(f"试次平均，n={trials.shape[0]}")
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

    def peak_detection(self):
        def operation(_movie, _baseline, traces, _masks, names, fs, _frames, _cancel_event):
            return [(names[i], len(core.detect_trace_peaks(traces[:, i], fs))) for i in range(traces.shape[1])]

        def finish(counts):
            messagebox.showinfo("峰值检测", "\n".join(f"{name}：{count} 个峰值" for name, count in counts))
            self.log("峰值检测完成。")

        self.queue_analysis_operation("峰值检测", operation, finish, need_traces=True)

    def roi_correlation(self):
        def operation(_movie, _baseline, traces, _masks, names, _fs, _frames, _cancel_event):
            if traces.shape[1] < 2:
                raise ValueError("ROI 相关性至少需要两条 ROI 曲线。")
            return np.corrcoef(traces.T), names

        def finish(result):
            corr, names = result
            win = tk.Toplevel(self.root)
            win.title("ROI 相关性")
            win.configure(bg=THEME["bg"])
            fig = Figure(figsize=(6, 5), dpi=100)
            fig.patch.set_facecolor(THEME["bg"])
            ax = fig.add_subplot(111)
            ax.set_facecolor("#06101f")
            im = ax.imshow(corr, cmap="hot", vmin=-1, vmax=1)
            ax.set_xticks(np.arange(len(names)))
            ax.set_yticks(np.arange(len(names)))
            ax.set_xticklabels(names, rotation=45, ha="right")
            ax.set_yticklabels(names)
            ax.tick_params(colors=THEME["muted"])
            for spine in ax.spines.values():
                spine.set_color(THEME["border"])
            cbar = fig.colorbar(im, ax=ax)
            cbar.ax.tick_params(colors=THEME["muted"])
            canvas = FigureCanvasTkAgg(fig, master=win)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

        self.queue_analysis_operation("计算 ROI 相关性", operation, finish, need_traces=True)

    def export_analysis(self):
        if not self.require_movie():
            return
        out_dir = filedialog.askdirectory()
        if not out_dir:
            return
        name = Path(self.state.source_path).stem or "NewLight"
        pre_trigger_s = float(self.state.pre_trigger_s)
        post_trigger_s = float(self.state.post_trigger_s)

        def operation(movie, baseline, traces, masks, names, fs, frames, _cancel_event):
            return core.export_results(
                out_dir,
                name,
                movie,
                baseline,
                masks,
                names,
                traces,
                fs,
                frames,
                pre_trigger_s,
                post_trigger_s,
            )

        def finish(paths):
            self.log(f"已导出 {len(paths)} 个文件到 {out_dir}")
            messagebox.showinfo("导出完成", f"结果已导出到：\n{out_dir}")

        self.queue_analysis_operation("导出完整分析", operation, finish, need_traces=True)


def main():
    root = tk.Tk()
    apply_dark_theme(root)
    NewLightApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
