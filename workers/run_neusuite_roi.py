"""Isolated authorized NeuSuite instance-segmentation worker."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def ensure_shared_module_path() -> None:
    """Locate core-side shared modules when this script runs in GPU Addon."""
    candidates = [
        ROOT,
        Path(os.environ.get("NEWLIGHT_RESOURCE_DIR", "")),
        Path(sys.executable).resolve().parent,
        Path(sys.executable).resolve().parent.parent,
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "roi_engines.py").is_file():
            path = str(candidate)
            if path not in sys.path:
                sys.path.insert(0, path)
            return


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NeuSuite fast ROI worker for NewLight Analysis")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--image-size", type=int, default=960)
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--candidate-mode", action="store_true")
    parser.add_argument("--candidate-confidence", type=float, default=0.05)
    parser.add_argument("--iou", type=float, default=0.70)
    parser.add_argument("--min-area", type=int, default=20)
    parser.add_argument("--max-area", type=int, default=4000)
    parser.add_argument("--device", default="auto")
    return parser


def inference_confidence(args) -> float:
    return float(args.candidate_confidence if args.candidate_mode else args.confidence)


def resize_instance_masks(masks, output_shape, threshold=0.5):
    import cv2
    import numpy as np

    array = np.asarray(masks)
    if array.ndim == 2:
        array = array[np.newaxis, ...]
    height, width = int(output_shape[0]), int(output_shape[1])
    if array.shape[0] == 0:
        return np.zeros((0, height, width), dtype=bool)
    restored = [
        cv2.resize(np.asarray(mask, dtype=np.float32), (width, height), interpolation=cv2.INTER_NEAREST)
        >= float(threshold)
        for mask in array
    ]
    return np.stack(restored).astype(bool, copy=False)


def filter_masks_by_area(masks, scores, min_area, max_area):
    import numpy as np

    array = np.asarray(masks, dtype=bool)
    score_values = [float(score) for score in scores]
    if array.shape[0] != len(score_values):
        raise ValueError("Mask and score counts do not match")
    areas = array.reshape(array.shape[0], -1).sum(axis=1)
    selected = [
        index
        for index, area in enumerate(areas)
        if int(area) >= int(min_area) and (int(max_area) <= 0 or int(area) <= int(max_area))
    ]
    if selected:
        filtered = np.stack([array[index] for index in selected])
    else:
        filtered = np.zeros((0,) + tuple(array.shape[1:]), dtype=bool)
    return filtered, [score_values[index] for index in selected], selected


def import_neusuite_yolo(runtime_root):
    method_root = Path(runtime_root).resolve()
    suite_root = method_root.parent
    if str(suite_root) not in sys.path:
        sys.path.insert(0, str(suite_root))
    bundled_dependencies = suite_root / "NeuSuite_RuntimeDeps"
    if not bundled_dependencies.is_dir():
        bundled_dependencies = ROOT / "NeuSuite_RuntimeDeps"
    if bundled_dependencies.is_dir() and str(bundled_dependencies) not in sys.path:
        sys.path.append(str(bundled_dependencies))
    from method.ultralytics import YOLO

    sys.modules["ultralytics"] = sys.modules["method.ultralytics"]

    return YOLO


def _scientific_gray_to_model_rgb(image):
    import numpy as np

    gray = np.asarray(image)
    finite = np.isfinite(gray)
    if not np.any(finite):
        scaled = np.zeros(gray.shape, dtype=np.uint8)
    else:
        values = gray[finite].astype(np.float32)
        low, high = np.percentile(values, (0.5, 99.5))
        if high <= low:
            low, high = float(np.min(values)), float(np.max(values))
        if high <= low:
            scaled = np.zeros(gray.shape, dtype=np.uint8)
        else:
            clipped = np.clip(gray.astype(np.float32), low, high)
            scaled = np.rint((clipped - low) * (255.0 / (high - low))).astype(np.uint8)
    return np.repeat(scaled[..., np.newaxis], 3, axis=2)


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def run(args) -> int:
    import numpy as np
    import tifffile
    ensure_shared_module_path()
    from roi_engines import save_roi_artifact

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    summary_path = Path(args.summary).resolve()
    weights = Path(args.weights).resolve()
    runtime_root = Path(args.runtime_root).resolve()
    if not weights.is_file():
        raise FileNotFoundError(f"NeuSuite model weights not found: {weights}")
    if not (runtime_root / "ultralytics").is_dir():
        raise FileNotFoundError(f"NeuSuite custom Ultralytics runtime not found: {runtime_root}")
    for stale in (output_path, summary_path):
        if stale.exists():
            stale.unlink()

    image = np.asarray(tifffile.imread(input_path))
    if image.ndim != 2:
        raise ValueError(f"Fast ROI input must be a 2D grayscale projection, got {image.shape}")
    model_input = _scientific_gray_to_model_rgb(image)

    YOLO = import_neusuite_yolo(runtime_root)
    model = YOLO(str(weights), task="segment")
    predict_options = {
        "source": model_input,
        "imgsz": int(args.image_size),
        "conf": inference_confidence(args),
        "iou": float(args.iou),
        "retina_masks": True,
        "verbose": False,
    }
    if args.device != "auto":
        predict_options["device"] = args.device
    results = model.predict(**predict_options)
    result = results[0]
    if result.masks is None:
        raw_masks = np.zeros((0,) + image.shape, dtype=np.float32)
    else:
        raw_masks = result.masks.data.detach().float().cpu().numpy()
    masks = resize_instance_masks(raw_masks, image.shape)
    if result.boxes is None or result.boxes.conf is None:
        scores = [1.0] * masks.shape[0]
    else:
        scores = result.boxes.conf.detach().float().cpu().numpy().tolist()
    masks, scores, source_indices = filter_masks_by_area(
        masks,
        scores,
        min_area=args.min_area,
        max_area=args.max_area,
    )

    parameters = {
        "image_size": int(args.image_size),
        "confidence": float(args.confidence),
        "candidate_mode": bool(args.candidate_mode),
        "candidate_confidence": float(args.candidate_confidence),
        "inference_confidence": inference_confidence(args),
        "iou": float(args.iou),
        "min_area": int(args.min_area),
        "max_area": int(args.max_area),
        "device": args.device,
    }
    metadata = {
        "engine": "neusuite_fast",
        "roi_count": int(masks.shape[0]),
        "raw_instance_count": int(raw_masks.shape[0]),
        "image_shape": list(image.shape),
        "parameters": parameters,
    }
    names = [f"Fast_ROI{index + 1}" for index in range(masks.shape[0])]
    save_roi_artifact(
        output_path,
        masks,
        image_shape=image.shape,
        names=names,
        metadata=metadata,
        extra_arrays={
            "scores": np.asarray(scores, dtype=np.float32),
            "source_indices": np.asarray(source_indices, dtype=np.int32),
        },
    )
    _write_json(summary_path, metadata)
    print(f"NeuSuite fast ROI extraction complete: {masks.shape[0]} instances")
    print(f"ROI artifact: {output_path}")
    print(f"Summary: {summary_path}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
