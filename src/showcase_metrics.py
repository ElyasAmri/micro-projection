"""showcase_metrics.py — beyond-Nyquist steep-region headline metrics.

GUI-agnostic core for the Stage 6 B.3a "dynamic-range" headline. Lifted verbatim
from the GUI readout (``MainWindow._update_dynamic_range_readout``) so the live
readout and the B.4 reference artifact compute the SAME numbers from the SAME
code — single source of truth, no drift.

Imports only the math layer (never gui.*). The caller owns presentation: this
module returns raw floats; the ``:.0f`` display rounding lives at the GUI label.
"""
from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from calibration import fit_tilt_plane
from pattern_generator import inverse_grating_phase
from pipeline import run_inverse_fpp, run_straight_fringe
from synthetic_fringes import project


def steep_region_ratios(
    golden: np.ndarray,
    geometry,
    deltas,
    noise_kwargs: Callable[[], dict],
    with_error_ratio: bool,
) -> dict:
    """Beyond-Nyquist steep-region ratios over the matching golden.

    Two convention-agnostic ratios over the steep (observed f > 0.5) region:

    - ``decoupling`` = mean f_straight / mean f_inverse — how far the inverse
      grating pulls the observed fringe frequency below the sampling wall.
      Phase-only and cheap; reported whenever a steep region exists.
    - ``error_ratio`` = steep-region RMS recovery error, straight / inverse-FPP
      — needs both recoveries, so it is computed only when ``with_error_ratio``
      is True (the GUI gates it to the steep-dome showcase). Uses the MATCHING
      shape (golden vs golden), so it reports steep-SHAPE recovery, independent
      of any demo defect.

    Parameters
    ----------
    golden, geometry, deltas
        The showcase golden surface, the ``HybridGeometry``, and the PSI phase
        shifts.
    noise_kwargs
        A ZERO-ARG FACTORY returning fresh sensor-noise kwargs (a fresh seeded
        RNG per call). It is invoked ONCE PER PRODUCER in the dual-run, so the
        straight and inverse recoveries see identical, independent draws — the
        load-bearing detail that makes the before/after comparison fair. (Pass a
        factory, not a pre-built dict: a shared RNG would advance between the two
        producer calls and change the second recovery's noise.)
    with_error_ratio
        When True, run the dual recovery and return ``error_ratio``; when False,
        skip it (decoupling only).

    Returns
    -------
    dict
        ``{"has_steep": bool, "decoupling": float | None,
           "error_ratio": float | None}``. Raw floats — the caller rounds for
        display. ``error_ratio`` is ``float('inf')`` if the inverse-FPP RMS is
        zero, and ``None`` when not computed.
    """
    H, W = golden.shape
    X = np.tile(np.arange(W, dtype=np.float64), (H, 1))
    carrier = (2.0 * np.pi / geometry.p) * X
    h_g = geometry.height_to_phase(golden)
    cam_straight = project(carrier, geometry) + h_g

    def _lf(phase):
        gy, gx = np.gradient(phase)
        return np.hypot(gx, gy) / (2.0 * np.pi)

    f_straight = _lf(cam_straight)
    steep = f_straight > 0.5
    if not steep.any():
        return {"has_steep": False, "decoupling": None, "error_ratio": None}

    cam_inverse = project(
        inverse_grating_phase(project(carrier, geometry) + h_g), geometry
    ) + h_g
    f_inverse = _lf(cam_inverse)
    decoupling = float(f_straight[steep].mean() / f_inverse[steep].mean())

    if not with_error_ratio:
        return {"has_steep": True, "decoupling": decoupling, "error_ratio": None}

    # Dual-run (gated to the steep-dome showcase): matching-shape recovery.
    rec_s = run_straight_fringe(
        golden, geometry, deltas, selfcal_fit=fit_tilt_plane,
        **noise_kwargs(),
    )
    dev_i = run_inverse_fpp(
        golden, golden, geometry, deltas, selfcal_fit=fit_tilt_plane,
        **noise_kwargs(),
    )
    rec_i = golden + (dev_i - dev_i.mean())

    def _rms(a):
        v = a[steep]
        return float(np.sqrt(((v - v.mean()) ** 2).mean()))

    rms_s, rms_i = _rms(rec_s - golden), _rms(rec_i - golden)
    ratio: Optional[float] = rms_s / rms_i if rms_i > 0 else float("inf")
    return {"has_steep": True, "decoupling": decoupling, "error_ratio": ratio}
