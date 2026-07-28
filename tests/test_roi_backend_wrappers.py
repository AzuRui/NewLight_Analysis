from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile

import analysis_core as core
from roi_engines import ROIArtifactError, save_roi_artifact


def arg_value(args, name):
    return args[args.index(name) + 1]


def test_caiman_environment_resolves_named_fallback_prefix(tmp_path, monkeypatch):
    local_prefix = tmp_path / "missing-local"
    named_prefix = tmp_path / "caiman_latest"
    (named_prefix / "conda-meta").mkdir(parents=True)
    monkeypatch.setattr(core, "NEWLIGHT_CAIMAN_PREFIX", local_prefix)
    monkeypatch.setenv("CONDA_PREFIX", str(named_prefix))

    assert core.caiman_worker_environment() == "caiman_latest"
    assert core.resolve_conda_environment_prefix("caiman_latest") == named_prefix.resolve()


def test_caiman_wrapper_preserves_movie_dtype_and_forwards_all_controls(tmp_path, monkeypatch):
    movie = (np.arange(12 * 7 * 9).reshape(12, 7, 9) * 17).astype(np.uint16)
    observed = {}

    def fake_run(environment, script, args, cwd=None, timeout=None):
        observed.update(environment=environment, script=script, args=list(args), cwd=cwd, timeout=timeout)
        worker_input = Path(arg_value(args, "--input"))
        loaded = tifffile.imread(worker_input)
        observed["input_dtype"] = loaded.dtype
        observed["input_shape"] = loaded.shape
        output = Path(arg_value(args, "--output"))
        summary = Path(arg_value(args, "--summary"))
        masks = np.zeros((2, 7, 9), dtype=bool)
        masks[0, 1:4, 2] = True
        masks[1, 3:6, 4:8] = True
        save_roi_artifact(
            output,
            masks,
            image_shape=(7, 9),
            names=["caiman-a", "caiman-b"],
            metadata={"engine": "caiman"},
            extra_arrays={
                "traces": np.ones((2, 9), dtype=np.float32),
                "snr": np.ones(2, dtype=np.float32),
                "r_values": np.ones(2, dtype=np.float32),
                "cnn_scores": np.ones(2, dtype=np.float32),
                "component_indices": np.arange(2, dtype=np.int32),
                "preset_accepted": np.ones(2, dtype=bool),
            },
        )
        summary.write_text('{"engine":"caiman"}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="done", stderr="")

    monkeypatch.setattr(core, "run_conda_worker", fake_run)
    result = core.run_caiman_roi_segmentation(
        movie,
        session_dir=str(tmp_path),
        frame_rate=13.5,
        invalid_start_frames=3,
        mode="one_photon",
        cell_diameter=18,
        components_per_patch=6,
        background_components=1,
        spatial_subsample=1,
        temporal_subsample=2,
        ar_order=2,
        merge_threshold=0.8,
        min_snr=1.5,
        rval_threshold=0.7,
        use_cnn=False,
        min_cnn_threshold=0.9,
        cnn_lowest=0.2,
        footprint_threshold=0.3,
        candidate_mode=True,
    )

    args = observed["args"]
    assert observed["input_dtype"] == np.uint16
    assert observed["input_shape"] == movie.shape
    assert arg_value(args, "--frame-rate") == "13.5"
    assert arg_value(args, "--invalid-start-frames") == "3"
    assert arg_value(args, "--mode") == "one_photon"
    assert arg_value(args, "--cell-diameter") == "18.0"
    assert "--no-cnn" in args
    assert "--candidate-mode" in args
    assert result.masks.shape == (2, 7, 9)
    assert result.names == ["caiman-a", "caiman-b"]
    assert result.arrays["traces"].shape == (2, 9)
    assert not Path(arg_value(args, "--input")).exists()
    assert result.artifact_path.is_file()
    assert result.summary_path.is_file()


def test_fast_wrapper_preserves_scientific_projection_and_authorized_paths(tmp_path, monkeypatch):
    projection = np.linspace(0, 65535, 5 * 8, dtype=np.uint16).reshape(5, 8)
    weights = tmp_path / "segment_model.pt"
    runtime = tmp_path / "method"
    weights.write_bytes(b"model")
    (runtime / "ultralytics").mkdir(parents=True)
    observed = {}

    def fake_run(environment, script, args, cwd=None, timeout=None):
        observed.update(environment=environment, script=script, args=list(args), cwd=cwd, timeout=timeout)
        worker_input = Path(arg_value(args, "--input"))
        loaded = tifffile.imread(worker_input)
        observed["input_dtype"] = loaded.dtype
        observed["input_values"] = loaded.copy()
        output = Path(arg_value(args, "--output"))
        summary = Path(arg_value(args, "--summary"))
        mask = np.zeros((1, 5, 8), dtype=bool)
        mask[0, 1:4, 2:6] = True
        save_roi_artifact(
            output,
            mask,
            image_shape=(5, 8),
            metadata={"engine": "neusuite_fast"},
            extra_arrays={
                "scores": np.array([0.88], dtype=np.float32),
                "source_indices": np.array([0], dtype=np.int32),
            },
        )
        summary.write_text('{"engine":"neusuite_fast"}', encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="fast done", stderr="")

    monkeypatch.setattr(core, "run_conda_worker", fake_run)
    result = core.run_fast_roi_segmentation(
        projection,
        session_dir=str(tmp_path),
        projection_mode="p25",
        weights=str(weights),
        runtime_root=str(runtime),
        image_size=768,
        confidence=0.35,
        iou=0.65,
        min_area=12,
        max_area=900,
        device="cpu",
        candidate_mode=True,
        candidate_confidence=0.05,
    )

    args = observed["args"]
    assert observed["input_dtype"] == np.uint16
    np.testing.assert_array_equal(observed["input_values"], projection)
    assert arg_value(args, "--weights") == str(weights.resolve())
    assert arg_value(args, "--runtime-root") == str(runtime.resolve())
    assert arg_value(args, "--image-size") == "768"
    assert arg_value(args, "--confidence") == "0.35"
    assert arg_value(args, "--candidate-confidence") == "0.05"
    assert "--candidate-mode" in args
    assert result.metadata["projection_mode"] == "p25"
    assert result.masks.shape == (1, 5, 8)
    assert not Path(arg_value(args, "--input")).exists()


def test_wrapper_rejects_worker_artifact_with_wrong_spatial_shape(tmp_path, monkeypatch):
    def fake_run(environment, script, args, cwd=None, timeout=None):
        output = Path(arg_value(args, "--output"))
        save_roi_artifact(output, np.ones((1, 3, 4), dtype=bool), image_shape=(3, 4))
        Path(arg_value(args, "--summary")).write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(core, "run_conda_worker", fake_run)
    with pytest.raises(ROIArtifactError, match="spatial shape"):
        core.run_fast_roi_segmentation(
            np.ones((4, 3), dtype=np.float32),
            session_dir=str(tmp_path),
            weights=str(tmp_path / "weights.pt"),
            runtime_root=str(tmp_path / "method"),
        )


@pytest.mark.parametrize(
    "backend,array_name,bad_array",
    [
        ("fast", "scores", np.ones(1, dtype=np.float32)),
        ("fast", "source_indices", np.ones(1, dtype=np.int32)),
        ("caiman", "traces", np.ones((1, 8), dtype=np.float32)),
        ("caiman", "snr", np.ones(1, dtype=np.float32)),
        ("caiman", "r_values", np.ones(1, dtype=np.float32)),
        ("caiman", "cnn_scores", np.ones(1, dtype=np.float32)),
        ("caiman", "component_indices", np.ones(1, dtype=np.int32)),
        ("caiman", "preset_accepted", np.ones(1, dtype=bool)),
    ],
)
def test_wrapper_rejects_misaligned_candidate_quality_arrays(
    tmp_path, monkeypatch, backend, array_name, bad_array
):
    def fake_run(environment, script, args, cwd=None, timeout=None):
        output = Path(arg_value(args, "--output"))
        summary = Path(arg_value(args, "--summary"))
        arrays = {array_name: bad_array}
        save_roi_artifact(
            output,
            np.ones((2, 4, 6), dtype=bool),
            image_shape=(4, 6),
            extra_arrays=arrays,
        )
        summary.write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(core, "run_conda_worker", fake_run)
    with pytest.raises(ROIArtifactError, match=array_name):
        if backend == "fast":
            core.run_fast_roi_segmentation(
                np.ones((4, 6), dtype=np.float32),
                session_dir=str(tmp_path),
                weights=str(tmp_path / "weights.pt"),
                runtime_root=str(tmp_path / "method"),
                candidate_mode=True,
            )
        else:
            core.run_caiman_roi_segmentation(
                np.ones((12, 4, 6), dtype=np.float32),
                session_dir=str(tmp_path),
                candidate_mode=True,
            )


@pytest.mark.parametrize("backend", ["fast", "caiman"])
def test_candidate_wrapper_rejects_missing_required_quality_arrays(tmp_path, monkeypatch, backend):
    def fake_run(environment, script, args, cwd=None, timeout=None):
        output = Path(arg_value(args, "--output"))
        summary = Path(arg_value(args, "--summary"))
        save_roi_artifact(
            output,
            np.ones((1, 4, 6), dtype=bool),
            image_shape=(4, 6),
            extra_arrays={},
        )
        summary.write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(core, "run_conda_worker", fake_run)
    with pytest.raises(ROIArtifactError, match="missing required"):
        if backend == "fast":
            core.run_fast_roi_segmentation(
                np.ones((4, 6), dtype=np.float32),
                session_dir=str(tmp_path),
                weights=str(tmp_path / "weights.pt"),
                runtime_root=str(tmp_path / "method"),
                candidate_mode=True,
            )
        else:
            core.run_caiman_roi_segmentation(
                np.ones((12, 4, 6), dtype=np.float32),
                session_dir=str(tmp_path),
                candidate_mode=True,
            )


def test_zero_roi_artifact_is_returned_without_inventing_global_roi(tmp_path, monkeypatch):
    def fake_run(environment, script, args, cwd=None, timeout=None):
        output = Path(arg_value(args, "--output"))
        save_roi_artifact(output, np.zeros((0, 4, 6), dtype=bool), image_shape=(4, 6))
        Path(arg_value(args, "--summary")).write_text("{}", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="no detections", stderr="")

    monkeypatch.setattr(core, "run_conda_worker", fake_run)
    result = core.run_fast_roi_segmentation(
        np.ones((4, 6), dtype=np.float32),
        session_dir=str(tmp_path),
        weights=str(tmp_path / "weights.pt"),
        runtime_root=str(tmp_path / "method"),
    )

    assert result.masks.shape == (0, 4, 6)
    assert result.names == []


def test_failed_worker_removes_only_its_session_job_directory(tmp_path, monkeypatch):
    protected = tmp_path / "validation_sample.txt"
    protected.write_text("keep", encoding="utf-8")

    def fake_run(environment, script, args, cwd=None, timeout=None):
        return SimpleNamespace(returncode=2, stdout="", stderr="backend failed")

    monkeypatch.setattr(core, "run_conda_worker", fake_run)
    with pytest.raises(RuntimeError, match="backend failed"):
        core.run_fast_roi_segmentation(
            np.ones((4, 6), dtype=np.float32),
            session_dir=str(tmp_path),
            weights=str(tmp_path / "weights.pt"),
            runtime_root=str(tmp_path / "method"),
        )

    assert protected.read_text(encoding="utf-8") == "keep"
    assert list(tmp_path.glob("fast_roi_*")) == []
