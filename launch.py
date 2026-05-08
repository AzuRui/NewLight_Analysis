import importlib.util
import sys
import tkinter as tk
from tkinter import messagebox


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
    missing = [name for name in REQUIRED if importlib.util.find_spec(name) is None]
    if missing:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "NewLight_Analysis cannot start",
            "Missing Python packages:\n\n"
            + "\n".join(missing)
            + "\n\nInstall them in the Python used by run_NewLight_Analysis.bat, then launch again.",
        )
        return 1
    import NewLight_Analysis

    NewLight_Analysis.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
