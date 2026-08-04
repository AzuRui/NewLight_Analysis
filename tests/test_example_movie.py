from __future__ import annotations

import hashlib
from pathlib import Path

import analysis_core as core


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "example" / "twophone.avi"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def test_retained_twophone_sample_is_read_only_movie_smoke():
    before = file_sha256(SAMPLE)

    movie, fps = core.load_movie(str(SAMPLE), max_preview_frames=3)

    assert movie.shape[0] == 3
    assert movie.ndim == 3
    assert movie.shape[1] > 0 and movie.shape[2] > 0
    assert fps > 0
    assert file_sha256(SAMPLE) == before
