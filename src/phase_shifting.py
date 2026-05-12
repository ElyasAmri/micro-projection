"""phase_shifting.py — N-step phase-shifting interferometry wrapped-phase extraction.

Lifts the wrapped-phase recovery step out of notebook cells 6 and 17 into a
single generalized function. Pure array op — no Geometry dependency.
"""
from __future__ import annotations

import numpy as np


def extract_phase(stack: np.ndarray, deltas) -> np.ndarray:
    """Generalized N-step phase-shifting interferometry wrapped-phase recovery.

    Computes the wrapped phase from N phase-shifted intensity frames via the
    closed-form least-squares solution:

        phi_wrapped = arctan2(-sum_k I_k * sin(delta_k),
                              +sum_k I_k * cos(delta_k))

    This is equivalent to a least-squares fit of A + B*cos(phi + delta_k)
    when the delta_k are uniformly distributed around 2*pi, which is the
    standard case (e.g., 4-step: [0, pi/2, pi, 3*pi/2]).

    Parameters
    ----------
    stack : ndarray, shape (H, W, N)
        Phase-shifted intensity frames.
    deltas : sequence of float, shape (N,)
        Phase shifts in radians, in the same order as the last axis of `stack`.
        N >= 3 is required (3 is the minimum to determine A, B, phi).

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Wrapped phase in radians, principal value in (-pi, pi].

    Notes
    -----
    For the canonical 4-step case [0, pi/2, pi, 3*pi/2], this reduces
    algebraically to `arctan2(I_4 - I_2, I_1 - I_3)`, the form used in
    notebook cells 6 and 17. The generalized form differs from that one
    by ULP-scale floating-point noise (sin(pi) is not exactly zero in
    float64) but is mathematically identical.
    """
    stack_arr = np.asarray(stack, dtype=np.float64)
    deltas_arr = np.asarray(deltas, dtype=np.float64)

    if stack_arr.ndim != 3:
        raise ValueError(
            f"stack must be 3D with shape (H, W, N); got {stack_arr.shape}"
        )
    if deltas_arr.ndim != 1 or deltas_arr.shape[0] != stack_arr.shape[2]:
        raise ValueError(
            f"deltas must be 1D with length matching stack's last axis; "
            f"got deltas shape {deltas_arr.shape}, stack shape {stack_arr.shape}"
        )
    if deltas_arr.shape[0] < 3:
        raise ValueError(
            f"N-step PSI requires N >= 3; got N = {deltas_arr.shape[0]}"
        )

    sin_d = np.sin(deltas_arr)
    cos_d = np.cos(deltas_arr)
    num = -np.sum(stack_arr * sin_d, axis=-1)
    den = np.sum(stack_arr * cos_d, axis=-1)
    return np.arctan2(num, den)
