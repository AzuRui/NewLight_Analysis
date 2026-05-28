"""Patch OpenCV loader configs inside a PyInstaller onedir build.

Conda's OpenCV package writes build-environment absolute paths into
cv2/config.py and cv2/config-3.x.py. Those paths work on the build machine, but
they make a frozen app non-portable and can trigger OpenCV's recursive import
guard on target machines.
"""

from __future__ import annotations

from pathlib import Path
import sys


CONFIG_PY = """import os

LOADER_DIR = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))

BINARIES_PATHS = [
    os.path.dirname(LOADER_DIR),
    LOADER_DIR,
] + BINARIES_PATHS
"""

CONFIG_VERSION_PY = """import os
import sys

LOADER_DIR = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))

PYTHON_EXTENSIONS_PATHS = [
    os.path.join(LOADER_DIR, "python-{}.{}".format(sys.version_info[0], sys.version_info[1])),
] + PYTHON_EXTENSIONS_PATHS
"""


def _find_cv2_dir(target: Path) -> Path:
    candidates = [
        target / "_internal" / "cv2",
        target / "cv2",
        target,
    ]
    for candidate in candidates:
        if (candidate / "__init__.py").exists() and (candidate / "load_config_py3.py").exists():
            return candidate
    raise FileNotFoundError(f"Could not find frozen cv2 package under: {target}")


def patch_frozen_cv2_config(target: str | Path) -> list[Path]:
    """Rewrite frozen cv2 config files and return the patched paths."""

    cv2_dir = _find_cv2_dir(Path(target).resolve())
    py_tag = f"python-{sys.version_info[0]}.{sys.version_info[1]}"
    pyds = list((cv2_dir / py_tag).glob("cv2*.pyd"))
    if not pyds:
        raise FileNotFoundError(f"Missing OpenCV native extension under: {cv2_dir / py_tag}")

    patched: list[Path] = []
    config_py = cv2_dir / "config.py"
    config_py.write_text(CONFIG_PY, encoding="utf-8", newline="\n")
    patched.append(config_py)

    version_configs = sorted(cv2_dir.glob("config-[0-9]*.py"))
    if not version_configs:
        raise FileNotFoundError(f"Missing OpenCV version config under: {cv2_dir}")
    for config_path in version_configs:
        config_path.write_text(CONFIG_VERSION_PY, encoding="utf-8", newline="\n")
        patched.append(config_path)

    return patched


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        argv = ["dist/NewLight_Analysis"]

    for raw_target in argv:
        patched = patch_frozen_cv2_config(raw_target)
        for path in patched:
            print(f"patched {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
