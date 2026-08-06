import argparse
import gc
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import tifffile

from caiman_headless import install_caiman_headless_compat


warnings.filterwarnings(
    "ignore",
    message="In setting CNMFParams, non-pathed parameters were used; this is deprecated.*",
)


def prepare_opencl_vendor_file() -> None:
    vendor_dir = Path(sys.prefix) / "Library" / "etc" / "OpenCL" / "vendors"
    try:
        vendor_dir.mkdir(parents=True, exist_ok=True)
        (vendor_dir / "temp.txt").touch(exist_ok=True)
    except Exception:
        pass


def prepare_caiman_temp_dir() -> Path:
    configured = os.environ.get("CAIMAN_TEMP", "").strip()
    temp_dir = (
        Path(configured).expanduser()
        if configured
        else Path(tempfile.gettempdir()) / "NewLight_Analysis" / "caiman"
    )
    temp_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CAIMAN_TEMP"] = str(temp_dir)
    return temp_dir


def print_shift_statistics(label: str, y_values, x_values, limit: float | None = None) -> None:
    y = np.asarray(y_values, dtype=np.float64).reshape(-1)
    x = np.asarray(x_values, dtype=np.float64).reshape(-1)
    valid = np.isfinite(y) & np.isfinite(x)
    if not np.any(valid):
        print(f"{label}: unavailable")
        return
    absolute = np.column_stack((np.abs(y[valid]), np.abs(x[valid])))
    message = (
        f"{label}: median_abs_yx={np.median(absolute, axis=0).tolist()}, "
        f"max_abs_yx={np.max(absolute, axis=0).tolist()}"
    )
    if limit is not None and limit > 0:
        saturation = float(np.mean(np.any(absolute >= float(limit) - 0.25, axis=1)))
        message += f", at_limit_fraction={saturation:.4f}"
    print(message)


def flattened_shift_values(values) -> np.ndarray:
    parts = [np.asarray(value, dtype=np.float64).reshape(-1) for value in values]
    return np.concatenate(parts) if parts else np.empty(0, dtype=np.float64)


def motion(args) -> int:
    try:
        prepare_caiman_temp_dir()
        prepare_opencl_vendor_file()
        install_caiman_headless_compat()
        import caiman as cm
        from caiman.motion_correction import MotionCorrect
        from caiman.source_extraction.cnmf import params as params

        input_path = str(Path(args.input).resolve())
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(
            "CaImAn parameters: "
            f"mode={args.mode}, max_shift={args.max_shift}, stride={args.stride}, "
            f"overlap={args.overlap}, max_deviation={args.max_deviation}"
        )
        with tempfile.TemporaryDirectory(prefix="newlight_caiman_") as tmpdir:
            tmpdir = Path(tmpdir)
            work_input = tmpdir / Path(input_path).name
            shutil.copy2(input_path, work_input)
            opts = params.CNMFParams(params_dict={
                "data": {
                    "fnames": [str(work_input)],
                },
                "motion": {
                    "pw_rigid": args.mode == "piecewise",
                    "max_shifts": (args.max_shift, args.max_shift),
                    "strides": (args.stride, args.stride),
                    "overlaps": (args.overlap, args.overlap),
                    "max_deviation_rigid": args.max_deviation,
                    "border_nan": "copy",
                },
            })
            mc = MotionCorrect([str(work_input)], dview=None, **opts.get_group("motion"))
            mc.motion_correct(save_movie=True)
            rigid_shifts = np.asarray(getattr(mc, "shifts_rig", []), dtype=np.float64)
            if rigid_shifts.ndim == 2 and rigid_shifts.shape[1] >= 2:
                print_shift_statistics(
                    "CaImAn rigid shift statistics",
                    rigid_shifts[:, 0],
                    rigid_shifts[:, 1],
                    limit=args.max_shift,
                )
            else:
                print("CaImAn rigid shift statistics: unavailable")
            if args.mode == "piecewise":
                local_x = flattened_shift_values(getattr(mc, "x_shifts_els", []))
                local_y = flattened_shift_values(getattr(mc, "y_shifts_els", []))
                print_shift_statistics(
                    "CaImAn local shift statistics",
                    local_y,
                    local_x,
                    limit=args.max_shift + args.max_deviation,
                )
            else:
                print("CaImAn local shift statistics: not used in rigid mode")
            corrected_file = mc.mmap_file[0] if isinstance(mc.mmap_file, list) else mc.mmap_file
            movie = cm.load(corrected_file)
            arr = np.array(movie, dtype=np.float32, copy=True)
            work_output = tmpdir / "caiman_corrected.tif"
            tifffile.imwrite(work_output, arr, photometric="minisblack")
            del movie
            del mc
            gc.collect()
            shutil.copy2(work_output, output_path)
        print("CaImAn motion correction complete.")
    except Exception as exc:
        print(f"CaImAn unavailable or failed: {exc}")
        raise
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CaImAn worker for NewLight Analysis.")
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("motion")
    m.add_argument("--input", required=True)
    m.add_argument("--output", required=True)
    m.add_argument("--mode", choices=["rigid", "piecewise"], default="piecewise")
    m.add_argument("--max-shift", type=int, default=12)
    m.add_argument("--stride", type=int, default=48)
    m.add_argument("--overlap", type=int, default=24)
    m.add_argument("--max-deviation", type=int, default=5)
    args = parser.parse_args()
    if args.command == "motion":
        return motion(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
