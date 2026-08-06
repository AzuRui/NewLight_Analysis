"""Isolated CaImAn CNMF/CNMF-E ROI extraction worker."""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
from pathlib import Path

from caiman_headless import install_caiman_headless_compat


def configure_backend_environment(caiman_data: str | None = None, session_dir: str | None = None) -> None:
    os.environ["MKL_THREADING_LAYER"] = "SEQUENTIAL"
    os.environ["KERAS_BACKEND"] = "torch"
    if caiman_data:
        os.environ["CAIMAN_DATA"] = str(Path(caiman_data).resolve())
    if session_dir:
        os.environ["CAIMAN_TEMP"] = str(Path(session_dir).resolve())


configure_backend_environment()


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CaImAn ROI extraction worker for NewLight Analysis")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--session-dir", required=True)
    parser.add_argument("--caiman-data", default="")
    parser.add_argument("--mode", choices=("two_photon", "one_photon"), default="two_photon")
    parser.add_argument("--frame-rate", type=float, default=10.0)
    parser.add_argument("--invalid-start-frames", type=int, default=0)
    parser.add_argument("--cell-diameter", type=float, default=12.0)
    parser.add_argument("--components-per-patch", type=int, default=4)
    parser.add_argument("--background-components", type=int, default=2)
    parser.add_argument("--spatial-subsample", type=int, default=2)
    parser.add_argument("--temporal-subsample", type=int, default=2)
    parser.add_argument("--ar-order", type=int, default=1)
    parser.add_argument("--merge-threshold", type=float, default=0.85)
    parser.add_argument("--min-snr", type=float, default=2.0)
    parser.add_argument("--rval-threshold", type=float, default=0.85)
    cnn = parser.add_mutually_exclusive_group()
    cnn.add_argument("--use-cnn", dest="use_cnn", action="store_true")
    cnn.add_argument("--no-cnn", dest="use_cnn", action="store_false")
    parser.set_defaults(use_cnn=True)
    parser.add_argument("--min-cnn-threshold", type=float, default=0.99)
    parser.add_argument("--cnn-lowest", type=float, default=0.1)
    parser.add_argument("--footprint-threshold", type=float, default=0.20)
    parser.add_argument("--candidate-mode", action="store_true")
    return parser


def cell_diameter_to_gsig(cell_diameter: float) -> tuple[int, int]:
    sigma = max(1, int(round(float(cell_diameter) / 4.0)))
    return sigma, sigma


def selected_component_indices(component_count, accepted_indices, candidate_mode):
    import numpy as np

    if candidate_mode:
        return np.arange(int(component_count), dtype=int)
    return np.asarray(accepted_indices, dtype=int).reshape(-1)


def spatial_footprints_to_masks(spatial, dims, accepted_indices):
    import numpy as np

    height, width = (int(dims[0]), int(dims[1]))
    accepted = [int(index) for index in accepted_indices]
    if not accepted:
        return np.zeros((0, height, width), dtype=bool)
    selected = spatial[:, accepted]
    dense = selected.toarray() if hasattr(selected, "toarray") else np.asarray(selected)
    return np.stack(
        [np.asarray(dense[:, column]).reshape((height, width), order="F") > 0 for column in range(dense.shape[1])]
    )


def filter_empty_footprints(masks, accepted_indices):
    import numpy as np

    array = np.asarray(masks, dtype=bool)
    accepted = np.asarray(accepted_indices, dtype=int).reshape(-1)
    if array.shape[0] != accepted.size:
        raise RuntimeError("CaImAn footprint and component-index counts do not match")
    keep = np.any(array.reshape(array.shape[0], -1), axis=1)
    return array[keep], accepted[keep]


def _quality_values(values, accepted_indices, default_value):
    import numpy as np

    accepted = np.asarray(accepted_indices, dtype=int)
    if values is None:
        return np.full(accepted.shape, default_value, dtype=np.float32)
    array = np.asarray(values).reshape(-1)
    if array.size == 0:
        return np.full(accepted.shape, default_value, dtype=np.float32)
    if accepted.size and int(np.max(accepted)) >= array.size:
        raise RuntimeError("CaImAn quality array is not aligned with spatial components")
    return np.asarray(array[accepted], dtype=np.float32)


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _build_cnmf_params(args, dims):
    from caiman.source_extraction.cnmf.params import CNMFParams

    gsig = list(cell_diameter_to_gsig(args.cell_diameter))
    patch_radius = max(16, int(round(args.cell_diameter * 2.0)))
    patch_stride = max(4, patch_radius // 2)
    one_photon = args.mode == "one_photon"
    return CNMFParams(
        params_dict={
            "data": {
                "dims": tuple(int(value) for value in dims),
                "fr": float(args.frame_rate),
                "decay_time": 0.4,
            },
            "patch": {
                "rf": patch_radius,
                "stride": patch_stride,
                "only_init": True,
            },
            "init": {
                "K": int(args.components_per_patch),
                "gSig": gsig,
                "gSiz": [2 * value + 1 for value in gsig],
                "method_init": "corr_pnr" if one_photon else "greedy_roi",
                "nb": 0 if one_photon else int(args.background_components),
                "ssub": int(args.spatial_subsample),
                "tsub": int(args.temporal_subsample),
                "center_psf": one_photon,
                "min_corr": 0.8,
                "min_pnr": 10.0,
                "ring_size_factor": 1.4,
            },
            "temporal": {"p": int(args.ar_order)},
            "merging": {"merge_thr": float(args.merge_threshold)},
            "quality": {
                "min_SNR": float(args.min_snr),
                "rval_thr": float(args.rval_threshold),
                "use_cnn": bool(args.use_cnn),
                "min_cnn_thr": float(args.min_cnn_threshold),
                "cnn_lowest": float(args.cnn_lowest),
            },
        }
    )


def run(args) -> int:
    configure_backend_environment(args.caiman_data or None, args.session_dir)
    install_caiman_headless_compat()

    import numpy as np
    import tifffile
    import caiman as cm
    from caiman.source_extraction.cnmf.cnmf import CNMF
    from roi_engines import save_roi_artifact

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    summary_path = Path(args.summary).resolve()
    session_dir = Path(args.session_dir).resolve()
    session_dir.mkdir(parents=True, exist_ok=True)
    for stale in (output_path, summary_path):
        if stale.exists():
            stale.unlink()

    images = np.asarray(tifffile.imread(input_path), dtype=np.float32)
    if images.ndim == 2:
        images = images[np.newaxis, ...]
    if images.ndim != 3:
        raise ValueError(f"CaImAn input must have shape (frames, height, width), got {images.shape}")
    invalid = max(0, int(args.invalid_start_frames))
    if invalid >= images.shape[0]:
        raise ValueError("Invalid start frames remove the entire movie")
    images = np.ascontiguousarray(images[invalid:])
    if images.shape[0] < 10:
        raise ValueError("CaImAn ROI extraction requires at least 10 valid frames")
    finite = np.isfinite(images)
    if not np.all(finite):
        images = np.where(finite, images, 0.0)
    minimum = float(np.min(images))
    if minimum < 0:
        images = images - minimum

    valid_input_path = session_dir / "caiman_valid_frames.tif"
    tifffile.imwrite(valid_input_path, images, photometric="minisblack")
    memmap_name = cm.save_memmap(
        [str(valid_input_path)],
        base_name=str(session_dir / "cnmf_memmap_"),
        order="C",
        border_to_0=0,
    )
    memmap_path = Path(memmap_name)
    temporal_pixels, dims, frame_count = cm.load_memmap(str(memmap_path))
    images = np.reshape(temporal_pixels.T, (frame_count,) + tuple(dims), order="F")

    params = _build_cnmf_params(args, dims)
    model = CNMF(n_processes=1, params=params, dview=None)
    model.fit(images)
    model.estimates.evaluate_components(images, model.params, dview=None)
    preset_accepted = np.asarray(model.estimates.idx_components, dtype=int).reshape(-1)
    component_count = int(np.asarray(model.estimates.C).shape[0])
    accepted = selected_component_indices(component_count, preset_accepted, args.candidate_mode)
    model.estimates.A_thr = None
    model.estimates.threshold_spatial_components(maxthr=float(args.footprint_threshold), dview=None)
    masks = spatial_footprints_to_masks(model.estimates.A_thr, images.shape[1:], accepted)
    masks, accepted = filter_empty_footprints(masks, accepted)

    traces_all = np.asarray(model.estimates.C, dtype=np.float32)
    residual = getattr(model.estimates, "YrA", None)
    if residual is not None and np.asarray(residual).shape == traces_all.shape:
        traces_all = traces_all + np.asarray(residual, dtype=np.float32)
    traces = traces_all[accepted] if accepted.size else np.zeros((0, images.shape[0]), dtype=np.float32)
    snr = _quality_values(getattr(model.estimates, "SNR_comp", None), accepted, np.nan)
    r_values = _quality_values(getattr(model.estimates, "r_values", None), accepted, np.nan)
    cnn_scores = _quality_values(getattr(model.estimates, "cnn_preds", None), accepted, np.nan)
    accepted_by_preset = np.isin(accepted, preset_accepted)

    parameters = {
        "mode": args.mode,
        "frame_rate": float(args.frame_rate),
        "invalid_start_frames": invalid,
        "valid_frames": int(images.shape[0]),
        "cell_diameter": float(args.cell_diameter),
        "gSig": list(cell_diameter_to_gsig(args.cell_diameter)),
        "components_per_patch": int(args.components_per_patch),
        "background_components": int(args.background_components),
        "spatial_subsample": int(args.spatial_subsample),
        "temporal_subsample": int(args.temporal_subsample),
        "ar_order": int(args.ar_order),
        "merge_threshold": float(args.merge_threshold),
        "min_snr": float(args.min_snr),
        "rval_threshold": float(args.rval_threshold),
        "use_cnn": bool(args.use_cnn),
        "min_cnn_threshold": float(args.min_cnn_threshold),
        "cnn_lowest": float(args.cnn_lowest),
        "footprint_threshold": float(args.footprint_threshold),
        "candidate_mode": bool(args.candidate_mode),
    }
    metadata = {
        "engine": "caiman",
        "roi_count": int(masks.shape[0]),
        "image_shape": list(images.shape[1:]),
        "parameters": parameters,
    }
    names = [f"CaImAn_ROI{index + 1}" for index in range(masks.shape[0])]
    save_roi_artifact(
        output_path,
        masks,
        image_shape=images.shape[1:],
        names=names,
        metadata=metadata,
        extra_arrays={
            "component_indices": accepted.astype(np.int32),
            "traces": traces,
            "snr": snr,
            "r_values": r_values,
            "cnn_scores": cnn_scores,
            "preset_accepted": accepted_by_preset,
        },
    )
    _write_json(summary_path, metadata)
    del model
    del images
    del temporal_pixels
    gc.collect()
    valid_input_path.unlink(missing_ok=True)
    memmap_path.unlink(missing_ok=True)
    print(f"CaImAn ROI extraction complete: {masks.shape[0]} accepted components")
    print(f"ROI artifact: {output_path}")
    print(f"Summary: {summary_path}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
