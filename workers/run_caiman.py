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


def motion(args) -> int:
    try:
        prepare_opencl_vendor_file()
        import caiman as cm
        from caiman.motion_correction import MotionCorrect
        from caiman.source_extraction.cnmf import params as params

        input_path = str(Path(args.input).resolve())
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
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
            corrected_file = mc.mmap_file[0] if isinstance(mc.mmap_file, list) else mc.mmap_file
            movie = cm.load(corrected_file)
            arr = np.array(movie, dtype=np.float32, copy=True)
            work_output = tmpdir / "caiman_corrected.tif"
            tifffile.imwrite(work_output, arr, photometric="minisblack")
            del movie
            del mc
            gc.collect()
            shutil.copy2(work_output, output_path)
        print(f"CaImAn motion correction saved {output_path}")
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
    m.add_argument("--mode", choices=["rigid", "piecewise"], default="rigid")
    m.add_argument("--max-shift", type=int, default=6)
    m.add_argument("--stride", type=int, default=48)
    m.add_argument("--overlap", type=int, default=24)
    m.add_argument("--max-deviation", type=int, default=3)
    args = parser.parse_args()
    if args.command == "motion":
        return motion(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
