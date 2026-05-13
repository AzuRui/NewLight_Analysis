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

    return na


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
