from __future__ import annotations

import argparse
import json
import sys
import warnings
from argparse import Namespace
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)

APP_DIR = Path(__file__).resolve().parent
WORKSPACE = APP_DIR.parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
NEUROALIGN_DIR = RESOURCE_DIR / "NeuroAlign"
if not NEUROALIGN_DIR.exists():
    NEUROALIGN_DIR = WORKSPACE / "2cafe_analysis" / "NeuroAlign"

CLUSTER_OUTPUTS = [
    "leiden_label_map.npy",
    "subject_inner_boundaries.png",
    "cluster_on_affine_preview.png",
    "stage_cluster_result.json",
]

FINAL_OUTPUTS = [
    "attempt_results.json",
    "control_points_all.csv",
    "control_points_inner.csv",
    "control_points_outer.csv",
    "control_points_overlay.png",
    "final_warp_overlay.png",
    "final_warp_segmentation_overlay.png",
    "registration_summary.json",
    "report.html",
    "score_components.json",
    "score_triangle.png",
    "selected_attempt_config.json",
    "stage_final_result.json",
    "subject_midline_profile.json",
    "warped_atlas_bundle.npz",
    "warped_atlas_label_map.npy",
    "warped_atlas_mask.png",
    "warped_atlas_pretty_boundaries.png",
    "warped_atlas_regions.json",
]


def load_neuroalign_module():
    sys.path.insert(0, str(NEUROALIGN_DIR))
    import atlas_registration_merged_bilateral_midline as na

    install_midline_locked_outer_affine(na)
    return na


def install_midline_locked_outer_affine(na) -> None:
    """Keep the detected fissure center active during the outer affine fit."""
    if getattr(na, "_NEWLIGHT_MIDLINE_LOCKED_OUTER_AFFINE", False):
        return

    defaults = {
        "outer_affine_midline_anchor_count": 12,
        "outer_affine_midline_weight": 7.0,
        "outer_affine_contour_weight": 1.0,
        "outer_affine_landmark_weight": 2.0,
        "outer_affine_refine_iter": 5,
        "outer_affine_midline_score_weight": 1.8,
        "outer_affine_rotation_limit_deg": 5.0,
        "outer_affine_rotation_penalty": 0.35,
        "outer_affine_midline_min_reliability": 0.10,
        "outer_affine_midline_band_frac": 0.18,
        "outer_affine_midline_band_px_min": 16,
        "outer_affine_midline_y_window": 4,
        "outer_affine_subject_midline_y_window": 5,
        "outer_affine_allow_shear": True,
        "outer_affine_shear_limit": 0.08,
        "outer_affine_shear_penalty": 8.0,
    }
    for key, value in defaults.items():
        na.DEFAULT_CFG.setdefault(key, value)
        if hasattr(na, "CFG_CLI_KEYS") and key not in na.CFG_CLI_KEYS:
            na.CFG_CLI_KEYS.append(key)

    original_estimate = na.estimate_outer_affine

    def cfg_value(key: str, fallback):
        cfg = getattr(na, "_CURRENT_RUNTIME_CFG", None) or getattr(na, "DEFAULT_CFG", {})
        return cfg.get(key, fallback)

    def apply_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
        if points.size == 0:
            return points.copy()
        return na.cv2.transform(np.asarray(points, dtype=np.float32)[None, :, :], matrix)[0].astype(np.float32)

    def weighted_similarity(src: np.ndarray, dst: np.ndarray, weights: np.ndarray):
        src = np.asarray(src, dtype=np.float64)
        dst = np.asarray(dst, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)
        if len(src) < 2 or len(dst) != len(src):
            return None
        weights = np.maximum(weights, 1e-6)
        rows = []
        rhs = []
        row_weights = []
        for (x, y), (xp, yp), weight in zip(src, dst, weights):
            rows.append([x, -y, 1.0, 0.0])
            rhs.append(xp)
            row_weights.append(weight)
            rows.append([y, x, 0.0, 1.0])
            rhs.append(yp)
            row_weights.append(weight)
        a_mat = np.asarray(rows, dtype=np.float64)
        b_vec = np.asarray(rhs, dtype=np.float64)
        sqrt_w = np.sqrt(np.asarray(row_weights, dtype=np.float64))
        try:
            sol, *_ = np.linalg.lstsq(a_mat * sqrt_w[:, None], b_vec * sqrt_w, rcond=None)
        except np.linalg.LinAlgError:
            return None
        a, b, tx, ty = sol
        scale = float(np.hypot(a, b))
        if not np.isfinite(scale) or scale < 1e-6:
            return None
        return np.asarray([[a, -b, tx], [b, a, ty]], dtype=np.float32)

    def weighted_affine(src: np.ndarray, dst: np.ndarray, weights: np.ndarray):
        src = np.asarray(src, dtype=np.float64)
        dst = np.asarray(dst, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)
        if len(src) < 3 or len(dst) != len(src):
            return None
        weights = np.maximum(weights, 1e-6)
        rows = []
        rhs = []
        row_weights = []
        for (x, y), (xp, yp), weight in zip(src, dst, weights):
            rows.append([x, y, 1.0, 0.0, 0.0, 0.0])
            rhs.append(xp)
            row_weights.append(weight)
            rows.append([0.0, 0.0, 0.0, x, y, 1.0])
            rhs.append(yp)
            row_weights.append(weight)
        a_mat = np.asarray(rows, dtype=np.float64)
        b_vec = np.asarray(rhs, dtype=np.float64)
        sqrt_w = np.sqrt(np.asarray(row_weights, dtype=np.float64))
        try:
            sol, *_ = np.linalg.lstsq(a_mat * sqrt_w[:, None], b_vec * sqrt_w, rcond=None)
        except np.linalg.LinAlgError:
            return None
        matrix = np.asarray([[sol[0], sol[1], sol[2]], [sol[3], sol[4], sol[5]]], dtype=np.float32)
        if not np.all(np.isfinite(matrix)):
            return None
        if abs(float(np.linalg.det(matrix[:, :2]))) < 1e-6:
            return None
        return matrix

    def rotation_degrees(matrix: np.ndarray) -> float:
        return float(np.degrees(np.arctan2(float(matrix[1, 0]), float(matrix[0, 0]))))

    def shear_amount(matrix: np.ndarray) -> float:
        linear = np.asarray(matrix[:, :2], dtype=np.float64)
        c0 = linear[:, 0]
        c1 = linear[:, 1]
        denom = float(np.linalg.norm(c0) * np.linalg.norm(c1))
        if denom <= 1e-9:
            return 0.0
        return float(abs(np.dot(c0, c1)) / denom)

    def profile_curve_value(profile: dict, key: str, y: float, fallback: float) -> float:
        curve = profile.get(key)
        if curve is None:
            return float(fallback)
        curve = np.asarray(curve, dtype=np.float32)
        if curve.size == 0:
            return float(fallback)
        yi = int(np.clip(round(float(y)), 0, len(curve) - 1))
        val = float(curve[yi])
        return val if np.isfinite(val) else float(fallback)

    def sample_atlas_medial_edge(
        atlas_outer: np.ndarray,
        atlas_midline_x: float,
        y_values: np.ndarray,
        side: str,
        y_window_override: float = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        atlas_outer = np.asarray(atlas_outer, dtype=np.float32)
        brain_width = float(np.max(atlas_outer[:, 0]) - np.min(atlas_outer[:, 0]))
        band = max(
            float(cfg_value("outer_affine_midline_band_px_min", 16)),
            brain_width * float(cfg_value("outer_affine_midline_band_frac", 0.18)),
        )
        y_window = float(cfg_value("outer_affine_midline_y_window", 32)) if y_window_override is None else float(y_window_override)
        pts = []
        keep = []
        for idx, y in enumerate(np.asarray(y_values, dtype=np.float32)):
            cand = atlas_outer[np.abs(atlas_outer[:, 1] - float(y)) <= y_window]
            if len(cand) == 0:
                continue
            if side == "left":
                cand = cand[(cand[:, 0] < atlas_midline_x) & ((atlas_midline_x - cand[:, 0]) <= band)]
                if len(cand) == 0:
                    continue
                x = float(np.max(cand[:, 0]))
            else:
                cand = cand[(cand[:, 0] > atlas_midline_x) & ((cand[:, 0] - atlas_midline_x) <= band)]
                if len(cand) == 0:
                    continue
                x = float(np.min(cand[:, 0]))
            pts.append([x, float(y)])
            keep.append(idx)
        if not pts:
            return np.zeros((0, 2), dtype=np.float32), np.zeros((0,), dtype=np.int32)
        return np.asarray(pts, dtype=np.float32), np.asarray(keep, dtype=np.int32)

    def align_indexed_points(
        src_pts: np.ndarray,
        src_keep: np.ndarray,
        dst_pts: np.ndarray,
        dst_keep: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        if len(src_pts) == 0 or len(dst_pts) == 0:
            return np.zeros((0, 2), dtype=np.float32), np.zeros((0, 2), dtype=np.float32)
        src_by_idx = {int(idx): src_pts[i] for i, idx in enumerate(src_keep)}
        dst_by_idx = {int(idx): dst_pts[i] for i, idx in enumerate(dst_keep)}
        common = [idx for idx in src_by_idx if idx in dst_by_idx]
        if not common:
            return np.zeros((0, 2), dtype=np.float32), np.zeros((0, 2), dtype=np.float32)
        return (
            np.asarray([src_by_idx[idx] for idx in common], dtype=np.float32),
            np.asarray([dst_by_idx[idx] for idx in common], dtype=np.float32),
        )

    def build_midline_pairs(
        atlas_outer_xy: np.ndarray,
        subject_outer_xy: np.ndarray,
        atlas_midline_x: float,
        subject_midline_x: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        profile = getattr(na, "_CURRENT_SUBJECT_MIDLINE_PROFILE", None) or {}
        reliability = float(profile.get("reliability", 0.0) or 0.0)
        min_reliability = float(cfg_value("outer_affine_midline_min_reliability", 0.10))
        if reliability < min_reliability:
            return np.zeros((0, 2), dtype=np.float32), np.zeros((0, 2), dtype=np.float32)

        n_points = int(max(4, round(float(cfg_value("outer_affine_midline_anchor_count", 12)))))
        atlas_outer = np.asarray(atlas_outer_xy, dtype=np.float32)
        subject_outer = np.asarray(subject_outer_xy, dtype=np.float32)
        atlas_y0 = float(np.min(atlas_outer[:, 1]))
        atlas_y1 = float(np.max(atlas_outer[:, 1]))
        subject_y0 = float(profile.get("y_min", np.min(subject_outer[:, 1])))
        subject_y1 = float(profile.get("y_max", np.max(subject_outer[:, 1])))
        if subject_y1 <= subject_y0 + 3:
            subject_y0 = float(np.min(subject_outer[:, 1]))
            subject_y1 = float(np.max(subject_outer[:, 1]))

        ts = np.linspace(0.06, 0.94, n_points, dtype=np.float32)
        atlas_y = atlas_y0 + ts * (atlas_y1 - atlas_y0)
        subject_y = subject_y0 + ts * (subject_y1 - subject_y0)
        subject_x = [
            profile_curve_value(profile, "center_curve", y, subject_midline_x)
            for y in subject_y
        ]
        src_parts = [
            np.column_stack([np.full(n_points, atlas_midline_x, dtype=np.float32), atlas_y]).astype(np.float32)
        ]
        dst_parts = [
            np.column_stack([np.asarray(subject_x, dtype=np.float32), subject_y]).astype(np.float32)
        ]

        left_src, left_keep = sample_atlas_medial_edge(atlas_outer, atlas_midline_x, atlas_y, "left")
        right_src, right_keep = sample_atlas_medial_edge(atlas_outer, atlas_midline_x, atlas_y, "right")
        subject_y_window = float(cfg_value("outer_affine_subject_midline_y_window", 5))
        left_dst_edge, left_dst_keep = sample_atlas_medial_edge(
            subject_outer, subject_midline_x, subject_y, "left", y_window_override=subject_y_window
        )
        right_dst_edge, right_dst_keep = sample_atlas_medial_edge(
            subject_outer, subject_midline_x, subject_y, "right", y_window_override=subject_y_window
        )
        left_src_edge, left_dst_edge = align_indexed_points(left_src, left_keep, left_dst_edge, left_dst_keep)
        right_src_edge, right_dst_edge = align_indexed_points(right_src, right_keep, right_dst_edge, right_dst_keep)
        if len(left_src_edge) >= 3:
            src_parts.append(left_src_edge)
            dst_parts.append(left_dst_edge)
        elif len(left_src) >= 3:
            left_dst_x = [
                profile_curve_value(profile, "left_curve", subject_y[idx], subject_midline_x)
                for idx in left_keep
            ]
            src_parts.append(left_src)
            dst_parts.append(np.column_stack([np.asarray(left_dst_x, dtype=np.float32), subject_y[left_keep]]).astype(np.float32))
        if len(right_src_edge) >= 3:
            src_parts.append(right_src_edge)
            dst_parts.append(right_dst_edge)
        elif len(right_src) >= 3:
            right_dst_x = [
                profile_curve_value(profile, "right_curve", subject_y[idx], subject_midline_x)
                for idx in right_keep
            ]
            src_parts.append(right_src)
            dst_parts.append(np.column_stack([np.asarray(right_dst_x, dtype=np.float32), subject_y[right_keep]]).astype(np.float32))

        src = np.vstack(src_parts).astype(np.float32)
        dst = np.vstack(dst_parts).astype(np.float32)
        return src, dst

    def alignment_score(
        matrix: np.ndarray,
        src_dense: np.ndarray,
        dst_dense: np.ndarray,
        mid_src: np.ndarray,
        mid_dst: np.ndarray,
    ) -> tuple[float, float, float]:
        pred = apply_points(src_dense, matrix)
        contour_err = float(np.mean(np.min(na.cdist(pred, dst_dense), axis=1)))
        mid_err = 0.0
        if len(mid_src) > 0:
            mid_pred = apply_points(mid_src, matrix)
            mid_err = float(np.mean(np.linalg.norm(mid_pred - mid_dst, axis=1)))
        rot = abs(rotation_degrees(matrix))
        rot_limit = float(cfg_value("outer_affine_rotation_limit_deg", 5.0))
        rot_penalty = max(0.0, rot - rot_limit) * float(cfg_value("outer_affine_rotation_penalty", 0.35))
        shear = shear_amount(matrix)
        shear_limit = float(cfg_value("outer_affine_shear_limit", 0.08))
        shear_penalty = max(0.0, shear - shear_limit) * float(cfg_value("outer_affine_shear_penalty", 8.0))
        score = (
            contour_err
            + float(cfg_value("outer_affine_midline_score_weight", 1.8)) * mid_err
            + rot_penalty
            + shear_penalty
        )
        return float(score), contour_err, mid_err

    def estimate_outer_affine_midline_locked(
        atlas_outer_xy: np.ndarray,
        subject_outer_xy: np.ndarray,
        n_resample: int = 256,
        atlas_midline_x: float = None,
        subject_midline_x: float = None,
    ) -> np.ndarray:
        atlas_outer = np.asarray(atlas_outer_xy, dtype=np.float32)
        subject_outer = np.asarray(subject_outer_xy, dtype=np.float32)
        atlas_midline_x = float(np.mean(atlas_outer[:, 0])) if atlas_midline_x is None else float(atlas_midline_x)
        subject_midline_x = float(np.mean(subject_outer[:, 0])) if subject_midline_x is None else float(subject_midline_x)

        src_lm = na.contour_landmarks(atlas_outer, atlas_midline_x)
        dst_lm = na.contour_landmarks(subject_outer, subject_midline_x)
        n_lm = min(len(src_lm), len(dst_lm))
        src_lm = src_lm[:n_lm]
        dst_lm = dst_lm[:n_lm]
        mid_src, mid_dst = build_midline_pairs(atlas_outer, subject_outer, atlas_midline_x, subject_midline_x)

        landmark_weight = float(cfg_value("outer_affine_landmark_weight", 2.0))
        midline_weight = float(cfg_value("outer_affine_midline_weight", cfg_value("midline_anchor_weight", 7.0)))
        contour_weight = float(cfg_value("outer_affine_contour_weight", 1.0))

        init_src = [src_lm]
        init_dst = [dst_lm]
        init_w = [np.full(len(src_lm), landmark_weight, dtype=np.float32)]
        if len(mid_src) > 0:
            init_src.append(mid_src)
            init_dst.append(mid_dst)
            init_w.append(np.full(len(mid_src), midline_weight, dtype=np.float32))
        src_init = np.vstack(init_src)
        dst_init = np.vstack(init_dst)
        w_init = np.concatenate(init_w)
        initial_candidates = [weighted_similarity(src_init, dst_init, w_init)]
        if bool(cfg_value("outer_affine_allow_shear", True)):
            initial_candidates.append(weighted_affine(src_init, dst_init, w_init))
        initial_candidates = [m for m in initial_candidates if m is not None]
        best_m = initial_candidates[0] if initial_candidates else None
        if best_m is None:
            return original_estimate(atlas_outer, subject_outer, n_resample, atlas_midline_x, subject_midline_x)

        src_dense = na.resample_closed_curve(atlas_outer, n_resample)
        dst_dense = na.resample_closed_curve(subject_outer, n_resample)
        best_score, best_contour_err, best_midline_err = alignment_score(best_m, src_dense, dst_dense, mid_src, mid_dst)
        for candidate in initial_candidates[1:]:
            cand_score, cand_contour_err, cand_midline_err = alignment_score(candidate, src_dense, dst_dense, mid_src, mid_dst)
            if cand_score < best_score:
                best_m = candidate
                best_score = cand_score
                best_contour_err = cand_contour_err
                best_midline_err = cand_midline_err
        n_iter = int(max(1, round(float(cfg_value("outer_affine_refine_iter", 5)))))
        for _ in range(n_iter):
            src_w = apply_points(src_dense, best_m)
            idx = np.argmin(na.cdist(src_w, dst_dense), axis=1)
            matched = dst_dense[idx]
            src_parts = [src_dense, src_lm]
            dst_parts = [matched, dst_lm]
            w_parts = [
                np.full(len(src_dense), contour_weight, dtype=np.float32),
                np.full(len(src_lm), landmark_weight, dtype=np.float32),
            ]
            if len(mid_src) > 0:
                src_parts.append(mid_src)
                dst_parts.append(mid_dst)
                w_parts.append(np.full(len(mid_src), midline_weight, dtype=np.float32))
            src_all = np.vstack(src_parts)
            dst_all = np.vstack(dst_parts)
            w_all = np.concatenate(w_parts)
            candidates = [weighted_similarity(src_all, dst_all, w_all)]
            if bool(cfg_value("outer_affine_allow_shear", True)):
                candidates.append(weighted_affine(src_all, dst_all, w_all))
            candidates = [m for m in candidates if m is not None]
            if not candidates:
                break
            improved = False
            for candidate in candidates:
                cand_score, cand_contour_err, cand_midline_err = alignment_score(candidate, src_dense, dst_dense, mid_src, mid_dst)
                if cand_score <= best_score:
                    best_m = candidate
                    best_score = cand_score
                    best_contour_err = cand_contour_err
                    best_midline_err = cand_midline_err
                    improved = True
            if not improved:
                break

        print(
            "Outer affine estimated, "
            f"mean contour error = {best_contour_err:.3f} px, "
            f"midline error = {best_midline_err:.3f} px, "
            f"rotation = {rotation_degrees(best_m):.2f} deg, "
            f"shear = {shear_amount(best_m):.3f}, "
            f"midline anchors = {len(mid_src)}"
        )
        return best_m.astype(np.float32)

    na.estimate_outer_affine = estimate_outer_affine_midline_locked
    na._NEWLIGHT_MIDLINE_LOCKED_OUTER_AFFINE = True


def load_bundle(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        bundle = json.load(f)
    if not isinstance(bundle, dict):
        raise ValueError("Config bundle must be a JSON object.")
    return bundle


def jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def save_json(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jsonable(obj), f, ensure_ascii=False, indent=2)


def resolve_cfg(na, bundle: dict) -> dict:
    preset = bundle.get("preset") or "balanced"
    cfg = na.apply_preset(dict(na.DEFAULT_CFG), preset)
    cfg.update(bundle.get("cfg", {}))
    return cfg


def resolve_paths(bundle: dict) -> tuple[Path, Path, Path]:
    video = Path(str(bundle.get("video") or ""))
    atlas_json = Path(str(bundle.get("atlas_json") or ""))
    outdir = Path(str(bundle.get("outdir") or ""))
    if not video.exists():
        raise FileNotFoundError(f"Video path does not exist: {video}")
    if not atlas_json.exists():
        raise FileNotFoundError(f"Atlas JSON does not exist: {atlas_json}")
    if not str(outdir):
        raise ValueError("Output dir is required.")
    outdir.mkdir(parents=True, exist_ok=True)
    return video, atlas_json, outdir


def save_stage_status(outdir: Path, stage: str, cfg: dict, extra: dict | None = None) -> None:
    payload = {"stage": stage, "cfg": cfg}
    if extra:
        payload.update(extra)
    save_json(payload, outdir / "stage_status.json")


def cleanup_outputs(outdir: Path, names: list[str]) -> None:
    for name in names:
        path = outdir / name
        try:
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass


def load_stage_arrays(outdir: Path):
    mean_path = outdir / "mean_img.npy"
    mask_path = outdir / "subject_mask.npy"
    label_path = outdir / "leiden_label_map.npy"
    if not mean_path.exists():
        raise FileNotFoundError("Missing mean_img.npy. Run Step 1 / outer contour first.")
    if not mask_path.exists():
        raise FileNotFoundError("Missing subject_mask.npy. Run Step 1 / outer contour first.")
    mean_img = np.load(mean_path)
    subject_mask = np.load(mask_path).astype(bool)
    label_map = np.load(label_path).astype(np.int32) if label_path.exists() else None
    return mean_img, subject_mask, label_map


def run_outer(na, bundle: dict, cfg: dict, video_path: Path, atlas_json: Path, outdir: Path) -> dict:
    cleanup_outputs(outdir, CLUSTER_OUTPUTS + FINAL_OUTPUTS)
    atlas = na.load_atlas_json(str(atlas_json))
    video, diagnostics = na.preprocess_video(str(video_path), cfg)
    mean_img = diagnostics["mean_img"].astype(np.float32)
    raw_mean = diagnostics.get("raw_mean_image", mean_img).astype(np.float32)
    subject_mask = diagnostics["auto_mask"].astype(bool)

    np.save(outdir / "preprocessed_video.npy", video.astype(np.float32))
    np.save(outdir / "mean_img.npy", mean_img.astype(np.float32))
    np.save(outdir / "raw_mean_image.npy", raw_mean.astype(np.float32))
    np.save(outdir / "subject_mask.npy", subject_mask.astype(np.uint8))
    np.save(outdir / "vessel_mask.npy", diagnostics.get("vessel_mask", np.zeros_like(subject_mask)).astype(np.uint8))

    na._CURRENT_RUNTIME_CFG = cfg
    na._CURRENT_SUBJECT_REF_IMG = mean_img
    na._CURRENT_SUBJECT_MIDLINE_PROFILE = na.estimate_subject_midline_profile(subject_mask, mean_img, cfg)

    subject_outer = na.largest_contour_from_mask(subject_mask)
    atlas_outer = np.asarray(atlas["brain_outer_polygon"], dtype=np.float32)
    subject_midline_x = na.estimate_subject_midline_x(subject_mask)
    outer_affine = na.estimate_outer_affine(
        atlas_outer_xy=atlas_outer,
        subject_outer_xy=subject_outer,
        n_resample=int(cfg["outer_resample_n"]),
        atlas_midline_x=float(atlas.get("midline_x", np.mean(atlas_outer[:, 0]))),
        subject_midline_x=subject_midline_x,
    )
    atlas_affine = na.transform_atlas_polygons_affine(atlas, outer_affine, subject_mask.shape)
    affine_label_map = na.rasterize_atlas_regions(atlas_affine, shape_hw=subject_mask.shape)
    affine_label_map[~subject_mask] = 0
    affine_eval = na.evaluate_outer_alignment(np.asarray(atlas_affine["brain_outer_polygon"], dtype=np.float32), subject_outer, subject_mask.shape)

    na.save_json(atlas_affine, str(outdir / "affine_atlas_regions.json"))
    np.save(outdir / "affine_atlas_label_map.npy", affine_label_map.astype(np.int32))
    na.save_mask_png(subject_mask.astype(np.uint8) * 255, str(outdir / "subject_outer_mask.png"), "Subject outer mask", dpi=cfg["mask_png_dpi"])
    na.draw_polygon_overlay(mean_img, atlas_affine, str(outdir / "outer_registration_overlay.png"), title="Outer registration (affine atlas)", boundary_color=(0.0, 1.0, 1.0), with_ids=False, dpi=cfg["overlay_dpi"], line_width=cfg["overlay_linewidth"])
    na.draw_midline_profile_overlay(mean_img, subject_mask, na._CURRENT_SUBJECT_MIDLINE_PROFILE, str(outdir / "midline_profile_overlay.png"))

    runtime = {
        "label_map_source": "not_computed_outer_stage",
        "video_shape": [int(x) for x in video.shape],
        "mask_pixels": int(np.sum(subject_mask)),
        "subject_midline_profile": na._serialize_midline_profile(na._CURRENT_SUBJECT_MIDLINE_PROFILE),
        "affine_outer_eval": affine_eval,
    }
    save_json(runtime, outdir / "runtime_stats.json")
    save_run_config(na, bundle, cfg, outdir, config_source=bundle.get("config_source"))
    save_stage_status(outdir, "outer", cfg, {"runtime_stats": runtime})
    print("Step outer finished.")
    print(f"Outputs saved to: {outdir}")
    return {"outdir": str(outdir), "stage": "outer"}


def run_cluster(na, bundle: dict, cfg: dict, video_path: Path, atlas_json: Path, outdir: Path) -> dict:
    cleanup_outputs(outdir, FINAL_OUTPUTS)
    _mean_img, subject_mask, _label_map = load_stage_arrays(outdir)
    video_path_npy = outdir / "preprocessed_video.npy"
    if not video_path_npy.exists():
        raise FileNotFoundError("Missing preprocessed_video.npy. Run Step 1 / outer contour first.")
    video = np.load(video_path_npy, mmap_mode="r")
    label_map, leiden_stats = na.compute_leiden_label_map(video, subject_mask, cfg)
    np.save(outdir / "leiden_label_map.npy", label_map.astype(np.int32))
    na.save_mask_png(na.extract_subject_boundaries(label_map).astype(np.uint8) * 255, str(outdir / "subject_inner_boundaries.png"), "Leiden inner boundaries", dpi=cfg["mask_png_dpi"])
    runtime_path = outdir / "runtime_stats.json"
    runtime = {}
    if runtime_path.exists():
        with open(runtime_path, "r", encoding="utf-8") as f:
            runtime = json.load(f)
    runtime.update({"label_map_source": "computed_from_cached_preprocessed_video", **leiden_stats})
    save_json(runtime, runtime_path)
    save_run_config(na, bundle, cfg, outdir, config_source=bundle.get("config_source"))
    save_stage_status(outdir, "cluster", cfg, {"runtime_stats": runtime})
    print("Step cluster finished.")
    print(f"Labels: {leiden_stats.get('label_count')}")
    print(f"Outputs saved to: {outdir}")
    return {"outdir": str(outdir), "stage": "cluster"}


def run_final(na, bundle: dict, cfg: dict, video_path: Path, atlas_json: Path, outdir: Path, config_path: str) -> dict:
    atlas = na.load_atlas_json(str(atlas_json))
    mean_img, subject_mask, label_map = load_stage_arrays(outdir)
    if label_map is None:
        raise FileNotFoundError("Missing leiden_label_map.npy. Run Step 2 / clustering first.")

    na._CURRENT_RUNTIME_CFG = cfg
    na._CURRENT_SUBJECT_REF_IMG = mean_img.astype(np.float32)
    na._CURRENT_SUBJECT_MIDLINE_PROFILE = na.estimate_subject_midline_profile(subject_mask, mean_img, cfg)

    summary, extra = na.register_atlas_to_subject_auto(atlas=atlas, label_map=label_map, subject_mask=subject_mask, cfg=cfg)
    atlas_affine = extra["atlas_affine"]
    atlas_affine_map = extra["atlas_affine_map"]
    atlas_final = extra["atlas_final"]
    atlas_final_map = extra["atlas_final_map"]

    runtime_path = outdir / "runtime_stats.json"
    runtime_stats = {}
    if runtime_path.exists():
        with open(runtime_path, "r", encoding="utf-8") as f:
            runtime_stats = json.load(f)
    runtime_stats.update({"final_stage": "computed_from_cached_label_map"})

    args = Namespace(video=str(video_path), label_map_npy=None, subject_mask_npy=None, atlas_json=str(atlas_json), outdir=str(outdir))
    na.save_run_bundle(args, bundle.get("preset") or "balanced", cfg, runtime_stats, str(outdir), config_path)
    np.save(outdir / "affine_atlas_label_map.npy", atlas_affine_map.astype(np.int32))
    na.save_json(atlas_affine, str(outdir / "affine_atlas_regions.json"))
    np.save(outdir / "warped_atlas_label_map.npy", atlas_final_map.astype(np.int32))
    na.save_json(atlas_final, str(outdir / "warped_atlas_regions.json"))
    na.save_json(summary, str(outdir / "registration_summary.json"))
    na.save_json(runtime_stats, str(outdir / "runtime_stats.json"))
    na.save_json(na._serialize_midline_profile(na._CURRENT_SUBJECT_MIDLINE_PROFILE), str(outdir / "subject_midline_profile.json"))
    if "selected_cfg" in extra:
        na.save_json(extra["selected_cfg"], str(outdir / "selected_attempt_config.json"))
    if "attempt_records" in extra:
        na.save_json([rec["digest"] for rec in extra["attempt_records"]], str(outdir / "attempt_results.json"))
    np.save(outdir / "subject_mask.npy", subject_mask.astype(np.uint8))
    na.write_points_csv(str(outdir / "control_points_outer.csv"), extra["outer_src"], extra["outer_dst"], tags=["outer"] * len(extra["outer_src"]))
    na.write_points_csv(str(outdir / "control_points_inner.csv"), extra["inner_src"], extra["inner_dst"], tags=["inner"] * len(extra["inner_src"]))
    na.write_points_csv(str(outdir / "control_points_all.csv"), extra["src_ctrl"], extra["dst_ctrl"], tags=extra["ctrl_tags"])
    na.save_mask_png(subject_mask.astype(np.uint8) * 255, str(outdir / "subject_outer_mask.png"), "Subject outer mask", dpi=cfg["mask_png_dpi"])
    na.save_mask_png(na.extract_subject_boundaries(label_map).astype(np.uint8) * 255, str(outdir / "subject_inner_boundaries.png"), "Leiden inner boundaries", dpi=cfg["mask_png_dpi"])
    na.draw_polygon_overlay(mean_img, atlas_affine, str(outdir / "outer_registration_overlay.png"), title="Outer registration (affine atlas)", boundary_color=(0.0, 1.0, 1.0), with_ids=False, dpi=cfg["overlay_dpi"], line_width=cfg["overlay_linewidth"])
    na.draw_polygon_overlay(mean_img, atlas_final, str(outdir / "final_warp_overlay.png"), title="Final warped atlas polygons", boundary_color=(1.0, 1.0, 0.0), with_ids=True, dpi=cfg["overlay_dpi"], line_width=cfg["overlay_linewidth"])
    na.save_segmentation_overlay(mean_img, atlas_final_map, str(outdir / "final_warp_segmentation_overlay.png"), title="Final warped atlas segmentation", alpha=cfg["overlay_alpha"], dpi=cfg["overlay_dpi"])
    na.draw_control_points_overlay(mean_img, extra["src_ctrl"], extra["dst_ctrl"], str(outdir / "control_points_overlay.png"), title="Selected control points")
    na.draw_midline_profile_overlay(mean_img, subject_mask, na._CURRENT_SUBJECT_MIDLINE_PROFILE, str(outdir / "midline_profile_overlay.png"))
    na.save_npz_bundle(str(outdir), atlas_final_map, subject_mask, atlas_final)
    na.save_binary_mask_png(atlas_final_map > 0, str(outdir / "warped_atlas_mask.png"))
    na.save_pretty_region_boundaries_png(atlas_final_map, str(outdir / "warped_atlas_pretty_boundaries.png"), scale=cfg["pretty_png_scale"], fill_value=cfg["pretty_fill_value"], line_value=cfg["pretty_line_value"], close_radius=cfg["pretty_boundary_close_radius"], line_thickness=cfg["pretty_boundary_thickness"])
    na.generate_html_report(str(outdir), summary, runtime_stats, cfg)
    save_stage_status(outdir, "final", cfg, {"registration_summary": summary})
    print("Step final finished.")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Outputs saved to: {outdir}")
    return {"outdir": str(outdir), "stage": "final", "warped_json": str(outdir / "warped_atlas_regions.json")}


def save_run_config(na, bundle: dict, cfg: dict, outdir: Path, config_source: str | None = None) -> None:
    args = Namespace(
        video=bundle.get("video"),
        label_map_npy=None,
        subject_mask_npy=None,
        atlas_json=bundle.get("atlas_json"),
        outdir=str(outdir),
    )
    runtime_stats = {}
    runtime_path = outdir / "runtime_stats.json"
    if runtime_path.exists():
        try:
            with open(runtime_path, "r", encoding="utf-8") as f:
                runtime_stats = json.load(f)
        except Exception:
            runtime_stats = {}
    na.save_run_bundle(args, bundle.get("preset") or "balanced", cfg, runtime_stats, str(outdir), config_source)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage-aware NeuroAlign worker for NewLight_Analysis.")
    parser.add_argument("--stage", choices=["outer", "cluster", "final"], required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    na = load_neuroalign_module()
    bundle = load_bundle(args.config)
    bundle["config_source"] = args.config
    cfg = resolve_cfg(na, bundle)
    video_path, atlas_json, outdir = resolve_paths(bundle)

    try:
        if args.stage == "outer":
            result = run_outer(na, bundle, cfg, video_path, atlas_json, outdir)
        elif args.stage == "cluster":
            result = run_cluster(na, bundle, cfg, video_path, atlas_json, outdir)
        else:
            result = run_final(na, bundle, cfg, video_path, atlas_json, outdir, args.config)
        save_json(result, outdir / f"stage_{args.stage}_result.json")
    finally:
        na.close_hidden_tk_root()


if __name__ == "__main__":
    main()
