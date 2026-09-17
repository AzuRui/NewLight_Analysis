import numpy as np
import pytest

import analysis_core as core


def test_manual_bandpass_keeps_signal_and_reduces_high_frequency_noise():
    fs = 100.0
    t = np.arange(1000) / fs
    clean = np.sin(2 * np.pi * 2.0 * t)
    noisy = clean + 0.7 * np.sin(2 * np.pi * 30.0 * t)
    traces = noisy[:, None].astype(np.float32)
    filtered, info = core.filter_trace_signals(traces, fs, mode="manual", low_hz=1.0, high_hz=5.0)
    assert info["mode"] == "manual"
    assert info["low_hz"] == pytest.approx(1.0)
    assert info["high_hz"] == pytest.approx(5.0)
    assert np.std(filtered[:, 0] - clean) < np.std(noisy - clean)


def test_adaptive_band_estimation_finds_dominant_signal_band():
    fs = 40.0
    t = np.arange(800) / fs
    traces = np.stack([
        np.sin(2 * np.pi * 2.0 * t),
        0.8 * np.sin(2 * np.pi * 2.0 * t + 0.3),
    ], axis=1).astype(np.float32)
    low, high = core.estimate_trace_band(traces, fs)
    assert 0.5 <= low < 2.1
    assert 2.0 < high <= 5.0
    filtered, info = core.filter_trace_signals(traces, fs, mode="adaptive", low_hz=0.1, high_hz=10.0)
    assert filtered.shape == traces.shape
    assert info["mode"] == "adaptive"
    assert info["high_hz"] > info["low_hz"]


def test_spectrum_suppresses_common_mains_frequency_bins():
    fs = 200.0
    t = np.arange(1000) / fs
    traces = (np.sin(2 * np.pi * 3.0 * t) + np.sin(2 * np.pi * 50.0 * t))[:, None]
    freqs, power = core.trace_spectrum(traces, fs)
    mains = int(np.argmin(np.abs(freqs - 50.0)))
    signal = int(np.argmin(np.abs(freqs - 3.0)))
    assert power[mains, 0] == 0
    assert power[signal, 0] > 0


def test_manual_bandpass_rejects_invalid_nyquist_range():
    with pytest.raises(ValueError, match="带通范围无效"):
        core.filter_trace_signals(np.ones((100, 1), dtype=np.float32), 10.0, mode="manual", low_hz=6.0, high_hz=8.0)


def test_process_traces_requires_sampling_rate_when_filtering():
    with pytest.raises(ValueError, match="采样率"):
        core.process_traces(np.ones((20, 1), dtype=np.float32), filter_mode="manual")


def test_background_subtract_estimates_diffuse_fluorescence_background():
    movie = np.full((12, 16, 16), 20.0, dtype=np.float32)
    movie[6, 7:9, 7:9] += 40.0
    result = core.background_subtract(
        movie,
        sigma=2.0,
        background_percentile=20.0,
        subtraction_strength=1.0,
    )
    assert float(np.median(result)) == pytest.approx(0.0, abs=0.5)
    assert float(result[6, 7:9, 7:9].mean()) > 20.0
    assert float(result.min()) >= 0.0


def test_background_subtract_strength_is_bounded_and_preserves_scale():
    movie = np.full((8, 10, 10), 12.0, dtype=np.float32)
    result = core.background_subtract(
        movie,
        sigma=1.0,
        background_percentile=20.0,
        subtraction_strength=0.5,
    )
    assert float(result.mean()) == pytest.approx(6.0, abs=0.2)


def test_adaptive_band_expands_estimated_limits():
    fs = 40.0
    t = np.arange(800) / fs
    traces = np.stack([np.sin(2 * np.pi * 2.0 * t)], axis=1).astype(np.float32)
    estimated = core.estimate_trace_band(traces, fs)
    expanded = core.adaptive_trace_band(traces, fs)
    _, info = core.filter_trace_signals(traces, fs, mode="adaptive")
    assert expanded == pytest.approx((info["low_hz"], info["high_hz"]))
    assert info["low_hz"] == pytest.approx(estimated[0] / 4.0)
    assert info["high_hz"] == pytest.approx(fs / 2.0 - fs / len(traces))
