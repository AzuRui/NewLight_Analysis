import importlib.util
import multiprocessing
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import machine_setup
from initialization_splash import SplashUnavailableError, run_with_initialization_splash


REQUIRED = [
    "cv2",
    "matplotlib",
    "numpy",
    "openpyxl",
    "pandas",
    "PIL",
    "scipy",
    "skimage",
    "tifffile",
]


def main():
    if Path(sys.executable).stem.lower() == "newlight_worker" or (len(sys.argv) > 1 and sys.argv[1] == "--worker"):
        if len(sys.argv) > 1 and sys.argv[1] == "--worker":
            del sys.argv[1]
        import worker_launcher

        return worker_launcher.main()

    frozen = bool(getattr(sys, "frozen", False))
    application_dir = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent
    setup_complete = machine_setup.setup_is_complete(machine_setup.default_state_path())
    if frozen and not setup_complete:
        try:
            setup_ok = run_with_initialization_splash(
                application_dir,
                lambda progress, dialog_visibility: machine_setup.ensure_application_setup(
                    application_dir,
                    progress=progress,
                    dialog_visibility=dialog_visibility,
                ),
            )
        except SplashUnavailableError:
            setup_ok = machine_setup.ensure_application_setup(application_dir)
    else:
        setup_ok = machine_setup.ensure_application_setup(application_dir)
    if not setup_ok:
        return 0

    # PyInstaller already carries the application runtime inside _internal.
    # importlib.find_spec() is not a valid dependency check in a frozen app:
    # packages may live in the archive or use a loader without a filesystem
    # spec, which previously produced a false "openpyxl is missing" dialog.
    if not frozen:
        missing = [name for name in REQUIRED if importlib.util.find_spec(name) is None]
        if missing:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "NewLight_Analysis 无法启动",
                "源码运行环境缺少 Python 包：\n\n"
                + "\n".join(missing)
                + "\n\n请使用项目环境启动，或运行开发者环境配置脚本后重试。",
            )
            return 1
    import NewLight_Analysis

    NewLight_Analysis.main()
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
