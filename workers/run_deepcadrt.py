from __future__ import annotations

import argparse
import os
import sys
import tempfile
import types
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import tifffile

warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API.*", category=UserWarning)

DEEPCAD_DOWNLOAD_FOLDER = Path("ModelForPytorch") / "DownloadedModel"


def model_download_hint(deepcad_dir: Path) -> str:
    return str(deepcad_dir / "pth" / DEEPCAD_DOWNLOAD_FOLDER)


def validate_model_dir(model_dir: Path, deepcad_dir: Path) -> tuple[Path, str, Path]:
    if model_dir.is_file():
        raise FileNotFoundError(
            "DeepCAD-RT model path is a file, but it must be a folder containing .pth files:\n"
            f"{model_dir}\n"
            "Replace it with a folder and download/copy the .pth model files there."
        )
    if not model_dir.exists():
        raise FileNotFoundError(
            "No DeepCAD-RT model folder was found.\n"
            f"Download/copy .pth model files into:\n{model_download_hint(deepcad_dir)}"
        )
    if not model_dir.is_dir() or not list(model_dir.glob("*.pth")):
        raise FileNotFoundError(
            "No DeepCAD-RT .pth model file was found in:\n"
            f"{model_dir}\n"
            f"Download/copy the .pth model files into:\n{model_download_hint(deepcad_dir)}"
        )
    return model_dir.parent, model_dir.name, model_dir


def resolve_model_location(deepcad_dir: Path, model: Optional[str]) -> tuple[Path, str, Path]:
    pth_dir = deepcad_dir / "pth"
    if model:
        model_path = Path(model)
        if model_path.is_absolute():
            if model_path.is_file() and model_path.suffix.lower() == ".pth":
                return validate_model_dir(model_path.parent, deepcad_dir)
            if model_path.is_dir():
                return validate_model_dir(model_path, deepcad_dir)
        candidates = [
            pth_dir / model_path,
            pth_dir / "ModelForPytorch" / model_path,
        ]
        for candidate in candidates:
            if candidate.exists():
                if candidate.is_file() and candidate.suffix.lower() == ".pth":
                    return validate_model_dir(candidate.parent, deepcad_dir)
                return validate_model_dir(candidate, deepcad_dir)
        raise FileNotFoundError(
            f"Could not resolve DeepCAD-RT model '{model}'.\n"
            f"Default expected download folder:\n{model_download_hint(deepcad_dir)}"
        )

    model_files = []
    if pth_dir.exists():
        model_files = sorted(p for p in pth_dir.rglob("*.pth") if p.is_file())
    if model_files:
        return validate_model_dir(model_files[0].parent, deepcad_dir)
    raise FileNotFoundError(
        "No DeepCAD-RT .pth model file was found.\n"
        f"Pass --model explicitly, or download/copy a .pth model under:\n{pth_dir}"
    )


def infer_required_fmap(model_dir: Path) -> int | None:
    model_files = sorted(model_dir.glob("*.pth"))
    if not model_files:
        return None
    try:
        import torch

        state = torch.load(model_files[-1], map_location="cpu")
        first = state.get("Generator.encoders.0.basic_module.SingleConv1.conv.weight")
        if first is None and isinstance(state, dict) and "state_dict" in state:
            first = state["state_dict"].get("Generator.encoders.0.basic_module.SingleConv1.conv.weight")
        if first is None or len(first.shape) < 1:
            return None
        # DeepCAD-RT's DoubleConv halves the first encoder channel count,
        # so a checkpoint with first conv out_channels=16 needs f_maps=32.
        return max(1, int(first.shape[0]) * 2)
    except Exception:
        return None


def pad_short_movie_for_temporal_stitching(
    movie: np.ndarray,
    patch_t: int,
    overlap: float,
) -> tuple[np.ndarray, int]:
    """Pad short inputs so DeepCAD-RT's temporal stitcher covers every frame.

    The upstream stitcher writes only the leading half of a single temporal
    patch.  A movie no longer than one patch therefore leaves its trailing
    frames as zeros.  Extending it to one patch plus one stride makes the
    stitcher emit a leading and a trailing patch; the caller crops the result
    back to the original frame count.
    """
    source = np.asarray(movie)
    if source.ndim != 3 or source.shape[0] < 1:
        raise ValueError(f"DeepCAD-RT expects a nonempty 3D movie stack, got shape {source.shape}.")
    patch_t = max(4, int(patch_t))
    gap_t = max(1, int(patch_t * (1.0 - float(overlap))))
    minimum_frames = patch_t + gap_t
    if source.shape[0] > patch_t:
        return source, int(source.shape[0])
    padded = np.pad(source, ((0, minimum_frames - source.shape[0]), (0, 0), (0, 0)), mode="edge")
    return padded, int(source.shape[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run DeepCAD-RT denoising for NewLight Analysis.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--deepcad-dir", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--gpu", default="0")
    parser.add_argument("--patch-xy", type=int, default=150)
    parser.add_argument("--patch-t", type=int, default=150)
    parser.add_argument("--overlap", type=float, default=0.6)
    parser.add_argument("--fmap", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=0)
    args = parser.parse_args()

    deepcad_dir = Path(args.deepcad_dir).resolve()
    if not deepcad_dir.exists():
        raise FileNotFoundError(f"DeepCAD-RT pytorch folder not found: {deepcad_dir}")
    sys.path.insert(0, str(deepcad_dir))
    if "gdown" not in sys.modules:
        gdown_stub = types.ModuleType("gdown")

        def _download_stub(*_args, **_kwargs):
            raise RuntimeError("gdown is not bundled; NewLight uses local DeepCAD-RT model files only.")

        gdown_stub.download = _download_stub
        sys.modules["gdown"] = gdown_stub

    import torch
    from deepcad.test_collection import testing_class

    if not torch.cuda.is_available():
        raise RuntimeError("DeepCAD-RT worker requires CUDA, but torch.cuda.is_available() is False.")

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    movie = tifffile.imread(input_path)
    movie = np.asarray(movie)
    if movie.ndim == 2:
        movie = movie[None, :, :]
    if movie.ndim != 3:
        raise ValueError(f"DeepCAD-RT expects a 3D movie stack, got shape {movie.shape}.")
    original_frames, h, w = movie.shape
    patch_xy = max(8, min(int(args.patch_xy), int(h), int(w)))
    patch_t = max(4, int(args.patch_t))
    work_movie, original_frames = pad_short_movie_for_temporal_stitching(movie, patch_t, args.overlap)

    pth_dir, model_name, model_dir = resolve_model_location(deepcad_dir, args.model.strip() or None)
    inferred_fmap = infer_required_fmap(model_dir)
    fmap = inferred_fmap if inferred_fmap else int(args.fmap)

    with tempfile.TemporaryDirectory(prefix="newlight_deepcadrt_worker_") as tmp:
        tmp_dir = Path(tmp)
        datasets_dir = tmp_dir / "datasets"
        results_dir = tmp_dir / "results"
        datasets_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)
        work_input = datasets_dir / "input.tif"
        tifffile.imwrite(work_input, work_movie, photometric="minisblack")

        test_dict = {
            "patch_x": patch_xy,
            "patch_y": patch_xy,
            "patch_t": patch_t,
            "overlap_factor": float(args.overlap),
            "scale_factor": 1,
            "test_datasize": int(work_movie.shape[0]),
            "datasets_path": "datasets",
            "pth_dir": str(pth_dir),
            "denoise_model": model_name,
            "output_dir": "results",
            "fmap": int(fmap),
            "GPU": str(args.gpu),
            "num_workers": int(args.num_workers),
            "visualize_images_per_epoch": False,
        }
        print(f"DeepCAD-RT model: {model_name}")
        print(f"DeepCAD-RT model folder: {model_dir}")
        print(f"DeepCAD-RT input shape: {movie.shape}")
        if work_movie.shape[0] != original_frames:
            print(
                "DeepCAD-RT temporal padding: "
                f"{original_frames} -> {work_movie.shape[0]} frames (edge replication); "
                "the result will be cropped to the original length."
            )
        print(f"DeepCAD-RT patch_xy={patch_xy}, patch_t={patch_t}, overlap={args.overlap}, fmap={fmap}")
        old_cwd = Path.cwd()
        os.chdir(tmp_dir)
        try:
            testing_class(test_dict).run()
        finally:
            os.chdir(old_cwd)

        outputs = sorted(results_dir.rglob("*_output.tif"), key=lambda p: p.stat().st_mtime)
        if not outputs:
            raise RuntimeError("DeepCAD-RT finished but no *_output.tif result was found.")
        denoised = tifffile.imread(outputs[-1])
        denoised = np.asarray(denoised)
        if denoised.ndim == 2:
            denoised = denoised[None, :, :]
        if denoised.ndim != 3 or denoised.shape[1:] != movie.shape[1:] or denoised.shape[0] < original_frames:
            raise RuntimeError(
                f"DeepCAD-RT output shape {denoised.shape} does not match padded input {work_movie.shape}."
            )
        denoised = denoised[:original_frames]
        tifffile.imwrite(output_path, denoised.astype(movie.dtype, copy=False), photometric="minisblack")

    print(f"DeepCAD-RT denoised movie saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
