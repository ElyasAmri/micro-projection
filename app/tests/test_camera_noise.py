"""Camera noise qualification: Welford correctness, Mono8/Mono16 threshold
comparability, the three-check evaluation, and report writing."""
import numpy as np
import pytest

from backend.camera_noise import (NoiseThresholds, WelfordStats, evaluate,
                                  full_scale_for, write_outputs)


def _stack(rng, n=60, shape=(24, 32), mean=128.0, sigma=1.0, dtype=np.uint8):
    full = full_scale_for(dtype)
    scale = full / 255.0  # same *relative* noise at either bit depth
    frames = rng.normal(mean * scale, sigma * scale, size=(n, *shape))
    return np.clip(frames, 0, full).astype(dtype)


def test_welford_matches_numpy():
    rng = np.random.default_rng(7)
    frames = _stack(rng)
    stats = WelfordStats()
    for f in frames:
        stats.update(f)
    expected = frames.astype(np.float64).std(axis=0, ddof=1)
    np.testing.assert_allclose(stats.std(), expected, rtol=1e-10)
    assert stats.count == len(frames)
    assert stats.full_scale == 255.0


def test_mono16_normalises_to_mono8_scale():
    rng = np.random.default_rng(7)
    s8, s16 = WelfordStats(), WelfordStats()
    for f in _stack(rng, dtype=np.uint8):
        s8.update(f)
    rng = np.random.default_rng(7)
    for f in _stack(rng, dtype=np.uint16):
        s16.update(f)
    assert s16.full_scale == 65535.0
    # Same relative noise -> same 8-bit-equivalent std (clipping/rounding
    # differ slightly between depths, so compare loosely).
    assert abs(float(s16.std_8bit().mean()) - float(s8.std_8bit().mean())) < 0.1
    t = NoiseThresholds()
    assert evaluate(s8.std_8bit(), t)["overall_pass"] == \
        evaluate(s16.std_8bit(), t)["overall_pass"]


def test_evaluate_checks():
    t = NoiseThresholds(std_dn=2.0, max_fail_fraction=0.01,
                        percentile=99.0, percentile_limit=3.0, mean_ceiling=1.5)
    quiet = np.full((50, 50), 0.5)
    assert evaluate(quiet, t)["overall_pass"]

    hot_tail = quiet.copy()
    hot_tail.flat[:100] = 5.0  # 4% of pixels over the per-pixel limit
    c = evaluate(hot_tail, t)
    assert not c["per_pixel_pass"] and not c["overall_pass"]

    loud = np.full((50, 50), 1.8)  # mean over ceiling, no per-pixel failures
    c = evaluate(loud, t)
    assert c["per_pixel_pass"] and not c["mean_pass"] and not c["overall_pass"]


def test_write_outputs(tmp_path):
    pytest.importorskip("cv2")
    rng = np.random.default_rng(3)
    stats = WelfordStats()
    for f in _stack(rng):
        stats.update(f)
    report, passed = write_outputs(tmp_path, stats, NoiseThresholds(),
                                   "pattern: flat field (level 128)")
    text = report.read_text(encoding="utf-8")
    assert "overall: pass" in text and passed
    for name in ("variance_map.npy", "std_heatmap.png",
                 "over_threshold_mask.png"):
        assert (tmp_path / name).exists()
