from __future__ import annotations

import numpy as np


def normalize(x, pmin=2, pmax=99.8, axis=None, clip=False, eps=1e-20, dtype=np.float32):
    """Small compatible subset of csbdeep.utils.normalize.

    DeepCAD-RT imports this for display helpers. Keeping the implementation here
    avoids pulling the full csbdeep/TensorFlow dependency chain into the app.
    """
    arr = np.asarray(x)
    lo = np.percentile(arr, pmin, axis=axis, keepdims=True)
    hi = np.percentile(arr, pmax, axis=axis, keepdims=True)
    out = (arr - lo) / (hi - lo + eps)
    if clip:
        out = np.clip(out, 0, 1)
    if dtype is not None:
        out = out.astype(dtype, copy=False)
    return out

