import argparse
import os
import sys
import warnings
from pathlib import Path

import cv2
import numpy as np

resource_dir = Path(os.environ.get("NEWLIGHT_RESOURCE_DIR", Path(__file__).resolve().parents[1]))
workspace = Path(__file__).resolve().parents[2]
neuroseg3_dir = resource_dir / "NeuroSeg3"
if not neuroseg3_dir.exists():
    neuroseg3_dir = workspace / "NeuroSeg3"
if neuroseg3_dir.exists():
    sys.path.insert(0, str(neuroseg3_dir))

warnings.filterwarnings(
    "ignore",
    message="Importing from timm.models.layers is deprecated, please import via timm.layers",
    category=FutureWarning,
)

from ultralytics import YOLO


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NeuroSeg3 ROI segmentation and export masks.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--mask-threshold", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=640)
    args = parser.parse_args()

    image = cv2.imread(args.input, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(args.input)
    h, w = image.shape[:2]

    print(f"NeuroSeg3 weights: {args.weights}")
    print(f"NeuroSeg3 detection confidence cutoff: {args.conf}")
    print(f"NeuroSeg3 mask pixel cutoff: {args.mask_threshold}")
    model = YOLO(args.weights)
    results = model.predict(
        source=args.input,
        conf=args.conf,
        imgsz=args.imgsz,
        retina_masks=True,
        save=False,
        verbose=False,
    )
    masks = []
    if results and results[0].masks is not None:
        data = results[0].masks.data.cpu().numpy()
        for m in data:
            if m.shape != (h, w):
                m = cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)
            mask = m > args.mask_threshold
            if mask.any():
                masks.append(mask)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    if masks:
        arr = np.stack(masks).astype(bool)
    else:
        arr = np.zeros((0, h, w), dtype=bool)
    names = np.array([f"NS3_ROI{i + 1}" for i in range(arr.shape[0])])
    np.savez_compressed(out, masks=arr, names=names)
    print(f"NeuroSeg3 exported {arr.shape[0]} masks to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
