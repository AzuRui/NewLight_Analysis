from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: NewLight_Worker.exe <script.py> [args...]")
        return 2
    resource_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    os.environ.setdefault("NEWLIGHT_RESOURCE_DIR", str(resource_dir))
    if sys.argv[1] == "-c":
        if len(sys.argv) < 3:
            print("Usage: NewLight_Worker.exe -c <code>")
            return 2
        code = sys.argv[2]
        sys.argv = ["-c"] + sys.argv[3:]
        exec(code, {"__name__": "__main__"})
        return 0
    script = Path(sys.argv[1])
    if not script.is_absolute():
        candidate = resource_dir / script
        script = candidate if candidate.exists() else Path.cwd() / script
    if not script.exists():
        print(f"Worker script not found: {script}")
        return 2
    sys.argv = [str(script)] + sys.argv[2:]
    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
