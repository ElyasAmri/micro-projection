"""Auto-exposure brightness swing: model, detect, correct.

The N-step PSA assumes every frame in the stack shares one DC level and one
modulation -- i.e. the camera responds identically across the whole phase
sequence. Auto-exposure breaks that. It re-meters between frames, and because
the fringe pattern shifts from frame to frame the metered brightness swings, so
frame k is effectively scaled by an unknown gain g_k:

    I_k = g_k * (a + b*cos(phi + 2*pi*k/N)).

That per-frame gain is NOT random noise -- it's a systematic weighting. In the
PSA sums (Sum I_k cos, Sum I_k sin) it acts like a low-frequency amplitude
modulation across k, which biases the recovered phase and prints a periodic
ripple into the height map. Averaging more pixels doesn't help (it's coherent
across the field); more phase steps barely helps.

The real fix is a *fixed* exposure (set MP_CAM_EXPOSURE_US, which turns
ExposureAuto off). When that's not possible, estimate the residual gain and
divide it out before reconstruction:

Estimator. For an ideal stack the spatial mean of every frame is identical --
the cos term averages to ~0 over a field spanning many fringe periods -- so a
frame's brightness *relative to the sequence average* is its gain. Projecting
each frame onto the per-pixel DC image (a least-squares gain) refines that and
is robust to the projection mask and vignetting.
"""
from __future__ import annotations

import numpy as np


def frame_gains(frames: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Per-frame gain g_k (normalized to mean 1) for an (N, H, W) stack. g_k > 1
    means frame k came out brighter than the sequence average."""
    n = frames.shape[0]
    flat = np.ascontiguousarray(frames.reshape(n, -1))
    if mask is not None:
        flat = flat[:, mask.reshape(-1)]
    dc = flat.mean(axis=0)  # per-pixel DC (the mean gain folds in and cancels below)
    denom = float(np.sum(dc * dc))
    if denom <= 0.0:
        gains = flat.mean(axis=1)  # degenerate (black frame): fall back to the mean
    else:
        gains = np.einsum("nk,k->n", flat, dc) / denom  # each frame projected onto DC
    mean = float(gains.mean())
    return gains / mean if mean != 0.0 else np.ones(n)


def brightness_swing_pct(frames: np.ndarray, mask: np.ndarray | None = None) -> float:
    """How much the per-frame brightness swings across the scan, as a percent
    (std of the mean-1 gains x 100). A steady exposure is ~0; auto-exposure
    chasing a shifting fringe shows up here."""
    return float(100.0 * frame_gains(frames, mask).std())


def normalize_frame_gains(
    frames: np.ndarray, mask: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Divide out the estimated per-frame gain, so every frame sits at the same
    effective exposure before the PSA. Returns (corrected_stack, gains)."""
    gains = frame_gains(frames, mask)
    corrected = frames / gains[:, None, None]
    return corrected, gains
