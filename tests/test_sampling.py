"""Tests for the pixel-area sampling model (Stage 6 A.0.2).

The binding gate (Part 3) proves the envelope keys off the LOCAL phase
gradient, not the scalar carrier period:

  (a) a uniform coarse carrier barely fades (envelope ~ 1 everywhere),
  (b) a STEEP feature collapses contrast in the steep region while flat
      regions stay full-contrast (relative assertion — the carrier's constant
      gradient keeps flat regions ~0.999, never exactly 1.0),
  (c) the wall is honest: substantial contrast (~0.637) still survives at the
      2-px Nyquist period, with monotone suppression toward the 1-px first null
      — not a hard cliff.

Plus: the envelope is OFF by default in synthesize_psi_stack so the sealed-core
regression path stays byte-identical.
"""
from __future__ import annotations

import numpy as np

from sampling import contrast_envelope
from synthetic_fringes import synthesize_psi_stack


def _uniform_x_ramp(f_cyc_px: float, shape=(16, 16)) -> np.ndarray:
    """Phase varying only along columns at a uniform f cycles/pixel."""
    H, W = shape
    slope = f_cyc_px * 2.0 * np.pi  # rad/pixel
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    return slope * X


# ----------------------------------------------------------------------
# Part 3(a) — uniform coarse carrier: no meaningful fade.
# ----------------------------------------------------------------------
def test_coarse_uniform_carrier_no_fade():
    H, W = 32, 64
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    phase = (2.0 * np.pi / 40.0) * X  # p = 40 px -> f ~ 0.025 cyc/px
    env = contrast_envelope(phase, fill_factor=1.0)
    # Relative, not exact: carrier's constant gradient keeps flat ~0.999.
    assert env.min() > 0.99
    assert env.max() <= 1.0


# ----------------------------------------------------------------------
# Part 3(b) — STEEP feature: contrast collapses where local |grad phi| is high.
# ----------------------------------------------------------------------
def test_steep_region_fades_relative_to_flat():
    H, W = 32, 80
    # Left half: coarse carrier (f ~ 0.025). Right half: steep (f ~ 0.9),
    # via a per-column slope that is small then large; phase = cumsum(slope).
    cols = np.arange(W)
    slope = np.where(cols < W // 2, 2.0 * np.pi / 40.0, 0.9 * 2.0 * np.pi)
    phase_row = np.cumsum(slope)
    phase = np.tile(phase_row, (H, 1))

    env = contrast_envelope(phase, fill_factor=1.0)

    # Exclude the 2-column boundary band where the central-difference gradient
    # straddles the slope jump.
    flat = env[:, : W // 2 - 2]
    steep = env[:, W // 2 + 2 :]

    assert flat.mean() > 0.9          # flat region full-contrast
    assert steep.mean() < 0.3         # steep region collapsed
    assert steep.mean() < 0.5 * flat.mean()   # the relative pin


# ----------------------------------------------------------------------
# Part 3(c) — honest wall: substantial at Nyquist, monotone, null at 1 px.
# ----------------------------------------------------------------------
def test_nyquist_period_keeps_substantial_contrast():
    # 2-px period == f = 0.5 cyc/px. |sinc(0.5)| = 2/pi ~ 0.6366.
    env = contrast_envelope(_uniform_x_ramp(0.5), fill_factor=1.0)
    np.testing.assert_allclose(env, 2.0 / np.pi, atol=1e-6)
    assert env.mean() > 0.6  # substantial — NOT a hard cliff at Nyquist


def test_envelope_monotone_decreasing_toward_one_pixel_limit():
    fs = np.linspace(0.05, 0.99, 20)
    vals = np.array([contrast_envelope(_uniform_x_ramp(f)).mean() for f in fs])
    assert np.all(np.diff(vals) < 0.0)  # strictly decreasing, not a step


def test_first_null_at_one_pixel_period():
    # f = 1.0 cyc/px (1-px period) -> |sinc(1.0)| ~ 0.
    env = contrast_envelope(_uniform_x_ramp(1.0), fill_factor=1.0)
    assert env.max() < 1e-2


# ----------------------------------------------------------------------
# Envelope range, fill-factor behavior, input guards.
# ----------------------------------------------------------------------
def test_envelope_in_unit_interval():
    rng = np.random.RandomState(0)
    phase = rng.standard_normal((20, 24)) * 5.0
    env = contrast_envelope(phase, fill_factor=1.0)
    assert env.shape == (20, 24)
    assert np.all(env >= 0.0) and np.all(env <= 1.0)


def test_smaller_fill_factor_fades_less():
    # A narrower photosensitive box averages over less of a cycle -> less fade.
    ramp = _uniform_x_ramp(0.5)
    full = contrast_envelope(ramp, fill_factor=1.0).mean()
    narrow = contrast_envelope(ramp, fill_factor=0.5).mean()
    assert narrow > full


def test_invalid_fill_factor_raises():
    phase = np.zeros((4, 4))
    for bad in (0.0, -1.0):
        try:
            contrast_envelope(phase, fill_factor=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"fill_factor={bad} should raise ValueError")


def test_non_2d_phase_raises():
    try:
        contrast_envelope(np.zeros((2, 3, 4)), fill_factor=1.0)
    except ValueError:
        pass
    else:
        raise AssertionError("3D phase should raise ValueError")


# ----------------------------------------------------------------------
# OFF-by-default: synthesize_psi_stack stays byte-identical without the flag.
# ----------------------------------------------------------------------
def test_synthesize_off_by_default_is_byte_identical():
    H, W = 24, 32
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    phase = (2.0 * np.pi / 12.0) * X
    deltas = [0.0, np.pi / 2.0, np.pi, 3.0 * np.pi / 2.0]

    got = synthesize_psi_stack(phase, deltas)
    expected = 1.0 + 0.9 * np.cos(phase[..., None] + np.asarray(deltas))
    np.testing.assert_array_equal(got, expected)


def test_synthesize_with_fill_factor_attenuates():
    H, W = 24, 32
    # Fine carrier so the envelope bites.
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    phase = (2.0 * np.pi / 3.0) * X  # p = 3 px -> f ~ 0.33 cyc/px
    deltas = [0.0, np.pi / 2.0, np.pi, 3.0 * np.pi / 2.0]

    off = synthesize_psi_stack(phase, deltas)
    on = synthesize_psi_stack(phase, deltas, fill_factor=1.0)

    # AC amplitude (peak-to-peak across the 4 shifts) shrinks under sampling.
    assert (on.max(axis=-1) - on.min(axis=-1)).mean() < (
        off.max(axis=-1) - off.min(axis=-1)
    ).mean()
