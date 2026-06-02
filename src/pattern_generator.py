"""pattern_generator.py — Inverse-grating projection patterns (Stage 6 A.1).

The projector-side entry point for the inverse-FPP loop. Given a reference
measurement's phase, it emits the pre-distorted ("inverse") grating phase that,
when projected and re-warped by a matching surface, lands on the camera as a
clean carrier — the projector bias and the reference's curvature cancel
(Ch.4 §4.3.1).

Single source of truth
----------------------
The inverse operation IS the tilt-flip already implemented and fixture-locked in
`calibration.compute_inverse_phase`:

    phi_inverse = 2 * P - phi_ref,   P = fit_tilt_plane(phi_ref)

i.e. keep the linear carrier/tilt `P`, negate the curvature. This module reuses
that function rather than reimplementing the flip, so there is one definition of
the inverse phase. `pattern_generator` adds the projector-side framing and is the
seam where later pattern concerns (wrapping to [0, 2*pi), clamping to the
projector's dynamic range, phase -> intensity) will attach.

Seam discipline
---------------
A.1 makes the pattern only. It does NOT synthesize frames or run recovery — the
loop (reference -> inverse grating -> project -> recover) is closed in A.2. Pure
NumPy, headless, geometry-free (matches `calibration.py`'s no-Geometry
constraint).

Known item for B.2
------------------
`fit_tilt_plane` is the correct linear detrend for the general reference (it
admits a genuine y-tilt). Whether reflecting an arbitrary *2D-curved* golden part
about that linear plane correctly nulls a matching part is not yet validated —
that is the B.2 golden-part claim. A.1's tests stay in the y-invariant regime,
where the 2D plane fit and the 1D row-mean fit provably agree.
"""
from __future__ import annotations

import numpy as np

from calibration import compute_inverse_phase


def inverse_grating_phase(reference_phase: np.ndarray) -> np.ndarray:
    """Inverse-grating phase to project, from a reference measurement's phase.

    Delegates the tilt-flip to `calibration.compute_inverse_phase` (single
    source of truth); see the module docstring for the formula and rationale.

    Parameters
    ----------
    reference_phase : ndarray, shape (H, W)
        The reference measurement's phase, in radians. Provenance is the
        caller's choice — a flat calibration capture (cancels projector bias
        only) or a golden-part capture (cancels bias + part shape, the B.2
        nulling case). For a flat/linear reference the result reduces to the
        plain carrier (no pre-distortion needed).

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        The inverse-grating phase, in radians, ready to be projected. Same
        (H, W) grid as the input.
    """
    return compute_inverse_phase(reference_phase)
