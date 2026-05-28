"""Surface-metrology processing steps.

Real implementations of the fringe-projection pipeline algorithms used by the
app, ported from the simulation line (`simulation/reconstruction.py`):

    extract_phase    N-step PSA (works on a phase-shifted sequence; on a single
                     frame it returns a zero placeholder for the live preview)
    unwrap_phase     2D phase unwrap (separable np.unwrap baseline)
    compute_height   phase -> height for a triangulation rig (calibration-dependent)
    filter_surface   Gaussian S-filter (ISO 16610-21): roughness / form split
    compute_roughness  ISO 25178 areal parameters: Sa, Sq, Sz, Ssk, Sku
    temporal_unwrap_ladder  multi-frequency coarse-to-fine temporal unwrap

The capture-acquisition step that feeds these (projector phase-shift sweep +
camera triggering) is handled by `acquisition/sequence_capture.py`.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


# ---------------------------------------------------------------------------
# N-step phase-shifting algorithm (PSA)
# ---------------------------------------------------------------------------

def extract_phase(
    image: np.ndarray,
    n_steps: int = 4,
    algorithm: str = "n-step",
) -> np.ndarray:
    """Wrapped phase from a phase-shifted sequence (or a placeholder for a
    single live frame).

    Args:
        image: either (H, W) - a single live frame - or (N, H, W) a stack of
            N >= 3 phase-shifted captures.
        n_steps: ignored when `image` already encodes the sequence; the stack
            length is authoritative.
        algorithm: only "n-step" is implemented at present.

    Returns:
        wrapped phase map (H, W) float64, in [-pi, +pi]. The N-step PSA result
        equals -phi_true (downstream code carries that sign convention).
    """
    arr = np.asarray(image, dtype=np.float64)
    if arr.ndim == 2:
        # Single-frame live preview: PSA needs a sequence. Return zeros so the
        # live UI keeps animating without claiming a phase result it cannot
        # compute. The real reconstruction lives in the sequence pipeline.
        return np.zeros(arr.shape, dtype=np.float64)
    if arr.ndim != 3 or arr.shape[0] < 3:
        raise ValueError("Image stack must have shape (N>=3, H, W) for N-step PSA.")
    if algorithm != "n-step":
        raise NotImplementedError(f"Unsupported PSA algorithm: {algorithm!r}")
    n = arr.shape[0]
    delta = np.arange(n, dtype=np.float64) * (2.0 * np.pi / n)
    sin_d = np.sin(delta)[:, None, None]
    cos_d = np.cos(delta)[:, None, None]
    s = (2.0 / n) * np.sum(arr * sin_d, axis=0)
    c = (2.0 / n) * np.sum(arr * cos_d, axis=0)
    return np.arctan2(s, c)


def compute_modulation(image: np.ndarray) -> np.ndarray:
    """Per-pixel modulation sqrt(S^2 + C^2) of a phase-shifted sequence.

    Low values mark untrusted pixels (low SNR / saturation). Returns zeros for a
    single-frame input.
    """
    arr = np.asarray(image, dtype=np.float64)
    if arr.ndim == 2:
        return np.zeros(arr.shape, dtype=np.float64)
    n = arr.shape[0]
    delta = np.arange(n, dtype=np.float64) * (2.0 * np.pi / n)
    sin_d = np.sin(delta)[:, None, None]
    cos_d = np.cos(delta)[:, None, None]
    s = (2.0 / n) * np.sum(arr * sin_d, axis=0)
    c = (2.0 / n) * np.sum(arr * cos_d, axis=0)
    return np.hypot(s, c)


# ---------------------------------------------------------------------------
# 2D phase unwrap
# ---------------------------------------------------------------------------

def unwrap_phase(wrapped: np.ndarray, method: str = "temporal") -> np.ndarray:
    """Continuous phase from a wrapped phase map.

    `method == "temporal"` is the default but for a single-frequency wrapped
    map we fall back to the separable spatial unwrap (np.unwrap on both axes).
    True temporal unwrap requires a multi-frequency ladder - see
    `temporal_unwrap_ladder`.
    """
    if method not in ("temporal", "spatial", "auto"):
        raise NotImplementedError(f"Unsupported unwrap method: {method!r}")
    return np.unwrap(np.unwrap(np.asarray(wrapped, dtype=np.float64), axis=1), axis=0)


def wrapped_phase_delta(phase: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Difference of two phase maps wrapped into [-pi, +pi]."""
    return np.angle(np.exp(1j * (phase - reference)))


def temporal_unwrap_ladder(
    wrapped_phases: Sequence[np.ndarray],
    fringe_periods_px: Sequence[float],
) -> np.ndarray:
    """Multi-frequency temporal unwrap (coarse disambiguates fine, geometric ladder)."""
    if len(wrapped_phases) != len(fringe_periods_px):
        raise ValueError("phases and periods must have the same length.")
    order = sorted(range(len(fringe_periods_px)),
                   key=lambda i: -float(fringe_periods_px[i]))
    coarse = np.unwrap(np.unwrap(np.asarray(wrapped_phases[order[0]]), axis=1), axis=0)
    coarse_period = float(fringe_periods_px[order[0]])
    for i in order[1:]:
        ratio = coarse_period / float(fringe_periods_px[i])
        expected = coarse * ratio
        fine_wrapped = np.asarray(wrapped_phases[i], dtype=np.float64)
        k = np.round((expected - fine_wrapped) / (2.0 * np.pi))
        coarse = fine_wrapped + 2.0 * np.pi * k
        coarse_period = float(fringe_periods_px[i])
    return coarse


# ---------------------------------------------------------------------------
# Phase -> height
# ---------------------------------------------------------------------------

def compute_height(phase: np.ndarray, lambda_eq: float = 0.32) -> np.ndarray:
    """height = phase * lambda_eq / (2 * pi).

    `lambda_eq` is the equivalent wavelength of the chosen fringe period for
    the rig's triangulation geometry; its value is set by the calibration step.
    Units of the returned height match `lambda_eq`.
    """
    return np.asarray(phase, dtype=np.float64) * (float(lambda_eq) / (2.0 * np.pi))


# ---------------------------------------------------------------------------
# Form / roughness separation (ISO 16610-21 Gaussian S-filter)
# ---------------------------------------------------------------------------

def _sigma_pixels_for_cutoff(cutoff_wavelength_mm: float, pixel_pitch_mm: float) -> float:
    """sigma (px) for a Gaussian low-pass at 50% transmission at lambda_c."""
    sigma_phys_mm = float(np.sqrt(np.log(2.0) / (2.0 * np.pi ** 2))) * float(cutoff_wavelength_mm)
    return sigma_phys_mm / float(pixel_pitch_mm)


def filter_surface(
    height: np.ndarray,
    cutoff: float = 15.0,
    method: str = "gaussian",
    *,
    mask: np.ndarray | None = None,
    pixel_pitch_mm: float = 0.214,
) -> tuple[np.ndarray, np.ndarray]:
    """Normalized Gaussian S-filter separating form from roughness.

    Returns (roughness, form), to match the call sites in `pipeline.py`. The
    filter uses normalized convolution so masked-out pixels do not bias the
    form estimate near boundaries.

    Args:
        height: HxW height map (same units throughout).
        cutoff: cutoff wavelength lambda_c (mm). 50% transmission point.
        method: only "gaussian" is implemented.
        mask: optional bool array of valid pixels.
        pixel_pitch_mm: physical pixel pitch in millimetres on the measured
            plane (depends on the calibrated optics).
    """
    if method != "gaussian":
        raise NotImplementedError(f"Unsupported filter method: {method!r}")
    if cv2 is None:
        raise RuntimeError("opencv-python is required for filter_surface.")
    z = np.asarray(height, dtype=np.float64)
    if mask is None:
        mask_b = np.ones_like(z, dtype=bool)
    else:
        mask_b = np.asarray(mask, dtype=bool)
    sigma_pix = _sigma_pixels_for_cutoff(float(cutoff), float(pixel_pitch_mm))
    z_masked = np.where(mask_b, z, 0.0)
    w = mask_b.astype(np.float64)
    z_blur = cv2.GaussianBlur(z_masked, ksize=(0, 0), sigmaX=sigma_pix, sigmaY=sigma_pix)
    w_blur = cv2.GaussianBlur(w, ksize=(0, 0), sigmaX=sigma_pix, sigmaY=sigma_pix)
    form = np.where(w_blur > 1e-6, z_blur / w_blur, 0.0)
    roughness = np.where(mask_b, z - form, 0.0)
    return roughness, form


# ---------------------------------------------------------------------------
# Areal roughness parameters (ISO 25178)
# ---------------------------------------------------------------------------

def compute_roughness(roughness: np.ndarray, mask: np.ndarray | None = None) -> dict[str, float]:
    """Sa, Sq, Sz, Ssk, Sku on the masked roughness residual.

    Roughness is the (height - form) residual on the same units as the height
    map. All five parameters are returned in those units (Ssk and Sku are
    dimensionless).
    """
    r = np.asarray(roughness, dtype=np.float64)
    valid = (np.isfinite(r) if mask is None
             else (np.asarray(mask, dtype=bool) & np.isfinite(r)))
    if not np.any(valid):
        return {"Sa": float("nan"), "Sq": float("nan"), "Sz": float("nan"),
                "Ssk": float("nan"), "Sku": float("nan")}
    v = r[valid]
    sa = float(np.mean(np.abs(v)))
    sq = float(np.sqrt(np.mean(v * v)))
    sz = float(v.max() - v.min())
    if sq > 1e-30:
        ssk = float(np.mean(v ** 3) / (sq ** 3))
        sku = float(np.mean(v ** 4) / (sq ** 4))
    else:
        ssk = float("nan")
        sku = float("nan")
    return {"Sa": sa, "Sq": sq, "Sz": sz, "Ssk": ssk, "Sku": sku}
