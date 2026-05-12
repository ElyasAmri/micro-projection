"""synthetic_fringes.py — Forward model: phase to captured intensity frames.

This module provides the simulation-side forward model:

- `project()` applies the projector's perspective bias to a phase map. It is
  the Taylor-approximation of Eq. 2-44 from the Samara thesis, lifted out of
  notebook cell 2.

- `synthesize_psi_stack()` produces an N-step phase-shifted intensity
  stack from a phase map. Lifted out of notebook cells 4 and 16.

Architectural constraint
------------------------
`project()` is a pure phase-domain forward model. It reads ONLY the bias
parameters (`p`, `theta_projector`, `a`) from the Geometry. It deliberately
does NOT read `lambda_eq` — the equivalent wavelength is a reconstruction-
stage concept (phase to height conversion) and belongs in `reconstruction.py`.

A consequence: `HybridGeometry` and `SymmetricGeometry` produce bit-identical
`project()` output when their `p`, `theta_projector`, and `a` agree, even
though their `lambda_eq` differs. The asymmetry between the two geometries
lives entirely at the height-phase boundary, not at the projector bias.

This invariant is locked by `tests/test_synthetic_fringes.py`.
"""
from __future__ import annotations

import numpy as np


def project(
    input_phase: np.ndarray,
    geometry,
    model: str = "taylor",
) -> np.ndarray:
    """Apply the projector's perspective bias to a phase map.

    Notebook cell 2's bias-subtraction forward model, parameterized by a
    Geometry. Reads only `geometry.p`, `geometry.theta_projector`, and
    `geometry.a` (see module docstring for the lambda_eq-independence
    constraint).

    Parameters
    ----------
    input_phase : ndarray, shape (H, W)
        The phase map the projector is asked to display, in radians.
    geometry : Geometry
        Must expose attributes `p` (fringe period, pixels),
        `theta_projector` (projection angle, radians), and `a` (perspective
        distance parameter, pixels).
    model : {'taylor', 'exact'}, default 'taylor'
        - 'taylor': first-order Taylor approximation from Ch.4 Eq. 4-7,

              bias(x) = (4 * pi / p) * x^2 * tan(theta_projector) / a,

          subtracted from `input_phase`. `x` is the column index in pixels.
        - 'exact': Stage 3 work; raises NotImplementedError today.

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Biased phase: `input_phase - bias`, in radians.

    Notes
    -----
    The bias is column-only (independent of row) because the projector's
    perspective effect is horizontal-only under the chapter's geometry.
    The output has the same shape as `input_phase`.
    """
    if model == "taylor":
        phase = np.asarray(input_phase, dtype=np.float64)
        H, W = phase.shape
        x = np.arange(W, dtype=np.float64)
        X = np.tile(x, (H, 1))
        bias = (4.0 * np.pi / geometry.p) * (
            X ** 2 * np.tan(geometry.theta_projector) / geometry.a
        )
        return phase - bias
    if model == "exact":
        raise NotImplementedError(
            "model='exact' (full Eq. 2-44 forward model) is Stage 3 work. "
            "Use model='taylor' until then."
        )
    raise ValueError(f"unknown model {model!r}; expected 'taylor' or 'exact'")


def synthesize_psi_stack(
    phase: np.ndarray,
    deltas,
    A: float = 1.0,
    B: float = 0.9,
) -> np.ndarray:
    """Synthesize an N-step phase-shifted intensity stack.

    Reproduces notebook cells 4 and 16: for each phase shift `delta_k` in
    `deltas`,

        I_k(x, y) = A + B * cos(phase(x, y) + delta_k),

    and stacks the frames along the last axis.

    Parameters
    ----------
    phase : ndarray, shape (H, W)
        Phase map in radians. This is the phase that would be measured at
        the camera (already includes any projector bias from `project()`).
    deltas : sequence of float, length N
        Phase shifts in radians. The notebook uses
        [0, pi/2, pi, 3*pi/2] for a 4-step PSI scan.
    A : float, default 1.0
        Average intensity (notebook default).
    B : float, default 0.9
        Fringe modulation amplitude (notebook default).

    Returns
    -------
    ndarray, shape (H, W, N), dtype float64
        Intensity stack. `out[..., k]` is the k-th phase-shifted frame.
    """
    phase_arr = np.asarray(phase, dtype=np.float64)
    deltas_arr = np.asarray(deltas, dtype=np.float64)
    # Broadcast: (H, W, 1) + (N,) -> (H, W, N)
    return A + B * np.cos(phase_arr[..., None] + deltas_arr)
