"""reconstruction.py — Object phase to height map (user-facing pipeline).

Composes phase_shifting + unwrapping + geometry to recover an object's
height from a phase-shifted intensity stack. The lambda_eq formula and
the height-phase boundary live in geometry.py; this module only
dispatches.

Architectural constraints
-------------------------
- `phase_to_height` is a thin dispatcher. No lambda_eq arithmetic here.
- `recover_object_height` composes lower-level modules; no duplicated
  logic.
- Pure NumPy + intra-package imports. No scipy, no skimage.

What the notebook subtracts from the object's unwrapped phase
-------------------------------------------------------------
Grep of notebook cells 14-20 confirms the variable subtracted at cell 18
is `tilt3_2d`, NOT `phi1_unwrapped`, `phi2`, or `bias_2d`. `tilt3_2d` is
computed inside cell 18 as

    phi3_profile = phi3_unwrapped.mean(axis=0)
    m3, c3       = np.polyfit(x, phi3_profile, 1)
    tilt3_2d     = np.tile(m3*x + c3, (H, 1))
    phi_height   = phi3_unwrapped - tilt3_2d
    phi_height  -= phi_height.mean()

i.e., a 1D tilt fit of the OBJECT'S own row-mean phase, tiled to 2D,
then subtracted. This is **self-calibration**, not cross-calibration
from a separate flat reference. Neither phi1_unwrapped nor phi2 would
work as the subtracted operand — both would leave the bias term sitting
on the residual.

`recover_object_height` takes the operand-to-subtract as the
`phi_calibration` argument, so the caller chooses the strategy: pass a
self-fitted tilt for the notebook's behavior, pass a flat-reference
tilt for an operational cross-calibration pipeline, or eventually pass
a calibration-file plane. The function does not care about provenance.
"""
from __future__ import annotations

import numpy as np

from phase_shifting import extract_phase
from unwrapping import unwrap_2d


def phase_to_height(phase: np.ndarray, geometry) -> np.ndarray:
    """Dispatch to `geometry.phase_to_height(phase)`.

    Thin user-facing wrapper. The lambda_eq formula and the
    height-phase boundary live in geometry.py; this module is the
    pipeline-layer entry point that other code calls.

    Parameters
    ----------
    phase : ndarray, shape (H, W)
        Phase in radians (typically the height-induced component after
        carrier and tilt removal).
    geometry : Geometry
        Concrete geometry (Hybrid, Symmetric, ...) implementing
        `phase_to_height`.

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Height in the geometry's native length units (pixels by
        convention here).
    """
    return geometry.phase_to_height(phase)


def recover_object_height(
    stack: np.ndarray,
    phi_calibration: np.ndarray,
    deltas,
    geometry,
) -> np.ndarray:
    """End-to-end height recovery from a phase-shifted intensity stack.

    Lifts notebook cells 14-20 steps 1-5; the cell-20 DC alignment to
    ground truth is not part of this function — see Notes.

    Pipeline:
        1. wrapped = extract_phase(stack, deltas)         (cell 17)
        2. unwrapped = unwrap_2d(wrapped)                 (cell 17)
        3. phi_height = unwrapped - phi_calibration       (cell 18, head)
        4. phi_height -= phi_height.mean()                (cell 18, tail)
        5. height = geometry.phase_to_height(phi_height)  (cell 19)

    Parameters
    ----------
    stack : ndarray, shape (H, W, N)
        Phase-shifted intensity frames captured of the object.
    phi_calibration : ndarray, shape (H, W)
        The reference phase to subtract from the recovered unwrapped
        phase. In the notebook this is `tilt3_2d` — a tilt-plane fit of
        the OBJECT'S own unwrapped phase (self-cal). A future operational
        pipeline could instead pass a tilt fit of a flat-reference
        measurement; the function is agnostic to provenance. See the
        module docstring.
    deltas : sequence of float, shape (N,)
        Phase shifts in radians, in the same order as `stack`'s last
        axis.
    geometry : Geometry
        Provides `phase_to_height` via lambda_eq.

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Recovered height map, mean-centered (the notebook's `H_rec`,
        cell 19). For DC-aligned recovery against a known reference
        (the notebook's `H_rec0`, cell 20), apply

            H_rec0 = h_rec - h_rec.mean() + h_target.mean()

        outside this function. The DC step requires ground truth (or an
        independently measured DC) and is a synthetic-test convenience,
        not part of the operational pipeline.
    """
    stack_arr = np.asarray(stack, dtype=np.float64)
    phi_cal = np.asarray(phi_calibration, dtype=np.float64)

    wrapped = extract_phase(stack_arr, deltas)
    unwrapped = unwrap_2d(wrapped)
    phi_height = unwrapped - phi_cal
    phi_height -= phi_height.mean()
    return phase_to_height(phi_height, geometry)
