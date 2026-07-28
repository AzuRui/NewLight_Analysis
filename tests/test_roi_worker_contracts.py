import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_worker(name):
    path = ROOT / "workers" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def option_destinations(parser):
    return {action.dest for action in parser._actions}


def test_caiman_worker_import_sets_native_environment_before_backend_use(monkeypatch):
    monkeypatch.delenv("MKL_THREADING_LAYER", raising=False)
    monkeypatch.delenv("KERAS_BACKEND", raising=False)

    worker = load_worker("run_caiman_roi.py")

    assert os.environ["MKL_THREADING_LAYER"] == "SEQUENTIAL"
    assert os.environ["KERAS_BACKEND"] == "torch"
    assert "numpy" not in worker.__dict__
    assert "caiman" not in worker.__dict__


def test_caiman_worker_parser_exposes_source_extraction_and_quality_controls():
    worker = load_worker("run_caiman_roi.py")
    parser = worker.build_parser()
    destinations = option_destinations(parser)

    assert {
        "input",
        "output",
        "summary",
        "session_dir",
        "caiman_data",
        "mode",
        "frame_rate",
        "invalid_start_frames",
        "cell_diameter",
        "components_per_patch",
        "background_components",
        "spatial_subsample",
        "temporal_subsample",
        "ar_order",
        "merge_threshold",
        "min_snr",
        "rval_threshold",
        "use_cnn",
        "min_cnn_threshold",
        "cnn_lowest",
        "footprint_threshold",
        "candidate_mode",
    }.issubset(destinations)

    args = parser.parse_args(
        [
            "--input",
            "movie.tif",
            "--output",
            "rois.npz",
            "--summary",
            "summary.json",
            "--session-dir",
            "session",
        ]
    )
    assert args.mode == "two_photon"
    assert args.cell_diameter == 12.0
    assert args.footprint_threshold == 0.2
    assert args.use_cnn is True
    assert args.candidate_mode is False


def test_caiman_candidate_mode_selects_every_component_before_empty_filtering():
    worker = load_worker("run_caiman_roi.py")

    standard = worker.selected_component_indices(5, [1, 3], candidate_mode=False)
    candidates = worker.selected_component_indices(5, [1, 3], candidate_mode=True)

    assert standard.tolist() == [1, 3]
    assert candidates.tolist() == [0, 1, 2, 3, 4]


def test_caiman_candidate_arrays_remain_aligned_after_empty_filtering():
    worker = load_worker("run_caiman_roi.py")
    masks = np.zeros((4, 3, 3), dtype=bool)
    masks[0, 0, 0] = True
    masks[2, 1, 1] = True
    masks[3, 2, 2] = True
    selected = worker.selected_component_indices(4, [0, 3], candidate_mode=True)

    masks, selected = worker.filter_empty_footprints(masks, selected)
    traces = np.arange(4 * 6, dtype=np.float32).reshape(4, 6)[selected]
    snr = worker._quality_values([1.0, 2.0, 3.0, 4.0], selected, np.nan)
    r_values = worker._quality_values([0.1, 0.2, 0.3, 0.4], selected, np.nan)
    cnn_scores = worker._quality_values([0.5, 0.6, 0.7, 0.8], selected, np.nan)
    preset_accepted = np.isin(selected, np.asarray([0, 3], dtype=int))

    assert masks.shape[0] == 3
    assert selected.tolist() == [0, 2, 3]
    assert traces.shape == (3, 6)
    assert snr.tolist() == [1.0, 3.0, 4.0]
    np.testing.assert_allclose(r_values, [0.1, 0.3, 0.4])
    np.testing.assert_allclose(cnn_scores, [0.5, 0.7, 0.8])
    assert preset_accepted.tolist() == [True, False, True]


@pytest.mark.parametrize(
    "diameter,expected",
    [(1.0, (1, 1)), (12.0, (3, 3)), (20.0, (5, 5))],
)
def test_cell_diameter_converts_to_caiman_gaussian_sigma(diameter, expected):
    worker = load_worker("run_caiman_roi.py")
    assert worker.cell_diameter_to_gsig(diameter) == expected


def test_caiman_footprints_use_fortran_order_and_keep_accepted_instances():
    scipy_sparse = pytest.importorskip("scipy.sparse")
    worker = load_worker("run_caiman_roi.py")
    first = np.zeros((3, 4), dtype=np.float32)
    first[0:2, 1] = 1
    second = np.zeros((3, 4), dtype=np.float32)
    second[1:3, 2:4] = 1
    dense = np.column_stack(
        [first.reshape(-1, order="F"), second.reshape(-1, order="F")]
    )

    masks = worker.spatial_footprints_to_masks(
        scipy_sparse.csc_matrix(dense),
        dims=(3, 4),
        accepted_indices=[1, 0],
    )

    assert masks.shape == (2, 3, 4)
    np.testing.assert_array_equal(masks[0], second.astype(bool))
    np.testing.assert_array_equal(masks[1], first.astype(bool))


def test_caiman_empty_thresholded_footprint_is_removed_with_its_component_index():
    worker = load_worker("run_caiman_roi.py")
    masks = np.zeros((3, 4, 5), dtype=bool)
    masks[0, 1, 1] = True
    masks[2, 2:4, 3] = True

    filtered, accepted = worker.filter_empty_footprints(masks, [8, 13, 21])

    assert filtered.shape == (2, 4, 5)
    assert accepted.tolist() == [8, 21]
    np.testing.assert_array_equal(filtered[0], masks[0])
    np.testing.assert_array_equal(filtered[1], masks[2])


def test_caiman_worker_uses_a_session_memmap_for_patch_cnmf():
    source = (ROOT / "workers" / "run_caiman_roi.py").read_text(encoding="utf-8")

    assert "cm.save_memmap(" in source
    assert "cm.load_memmap(" in source
    assert 'order="F"' in source
    assert "memmap_path.unlink" in source


def test_fast_worker_parser_exposes_authorized_model_and_instance_controls():
    worker = load_worker("run_neusuite_roi.py")
    parser = worker.build_parser()
    destinations = option_destinations(parser)

    assert {
        "input",
        "output",
        "summary",
        "weights",
        "runtime_root",
        "image_size",
        "confidence",
        "iou",
        "min_area",
        "max_area",
        "device",
        "candidate_mode",
        "candidate_confidence",
    }.issubset(destinations)

    args = parser.parse_args(
        [
            "--input",
            "projection.tif",
            "--output",
            "rois.npz",
            "--summary",
            "summary.json",
            "--weights",
            "segment_model.pt",
            "--runtime-root",
            "method",
        ]
    )
    assert args.image_size == 960
    assert args.confidence == 0.25
    assert args.iou == 0.70
    assert args.min_area == 20
    assert args.max_area == 4000
    assert args.candidate_mode is False
    assert args.candidate_confidence == 0.05


def test_fast_worker_uses_separate_confidence_only_for_candidate_mode():
    worker = load_worker("run_neusuite_roi.py")
    parser = worker.build_parser()
    base = [
        "--input", "projection.tif",
        "--output", "rois.npz",
        "--summary", "summary.json",
        "--weights", "segment_model.pt",
        "--runtime-root", "method",
        "--confidence", "0.42",
        "--candidate-confidence", "0.03",
    ]

    standard = parser.parse_args(base)
    candidate = parser.parse_args(base + ["--candidate-mode"])

    assert worker.inference_confidence(standard) == 0.42
    assert worker.inference_confidence(candidate) == 0.03


def test_fast_worker_resizes_each_mask_independently_with_nearest_neighbor():
    worker = load_worker("run_neusuite_roi.py")
    masks = np.zeros((2, 2, 3), dtype=np.float32)
    masks[0, 0, 0] = 1.0
    masks[1, 1, 2] = 1.0

    restored = worker.resize_instance_masks(masks, output_shape=(4, 6), threshold=0.5)

    assert restored.shape == (2, 4, 6)
    assert restored.dtype == np.bool_
    assert restored[0, :2, :2].all()
    assert not restored[0, 2:, 2:].any()
    assert restored[1, 2:, 4:].all()
    assert not restored[1, :2, :4].any()


def test_fast_worker_area_filter_keeps_scores_aligned_with_instances():
    worker = load_worker("run_neusuite_roi.py")
    masks = np.zeros((3, 5, 6), dtype=bool)
    masks[0, 0, 0] = True
    masks[1, 1:3, 1:4] = True
    masks[2, 1:5, 1:6] = True

    filtered, scores, source_indices = worker.filter_masks_by_area(
        masks,
        scores=[0.2, 0.8, 0.9],
        min_area=3,
        max_area=10,
    )

    assert filtered.shape == (1, 5, 6)
    assert scores == [0.8]
    assert source_indices == [1]


def test_fast_worker_imports_custom_runtime_through_method_package(tmp_path):
    worker = load_worker("run_neusuite_roi.py")
    method = tmp_path / "method"
    ultralytics = method / "ultralytics"
    internal = tmp_path / "NeuSuite_RuntimeDeps"
    ultralytics.mkdir(parents=True)
    internal.mkdir()
    (method / "__init__.py").write_text("", encoding="utf-8")
    (method / "marker.py").write_text("VALUE = 'custom-runtime'\n", encoding="utf-8")
    (internal / "runtime_dependency.py").write_text("VALUE = 'bundled-dependency'\n", encoding="utf-8")
    (ultralytics / "__init__.py").write_text(
        "from method.marker import VALUE\n"
        "from runtime_dependency import VALUE as DEP_VALUE\n"
        "class YOLO:\n"
        "    runtime = VALUE + '+' + DEP_VALUE\n",
        encoding="utf-8",
    )
    try:
        yolo = worker.import_neusuite_yolo(method)
        assert yolo.runtime == "custom-runtime+bundled-dependency"
        assert sys.modules["ultralytics"] is sys.modules["method.ultralytics"]
    finally:
        for name in list(sys.modules):
            if name == "method" or name.startswith("method.") or name == "ultralytics" or name.startswith("ultralytics."):
                sys.modules.pop(name, None)
        sys.modules.pop("runtime_dependency", None)
