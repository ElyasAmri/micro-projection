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

from sampling import contrast_envelope


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
        - 'exact': full Ch.2 Eq. 2-44 form (notebook cell 25),

              phi_exact(x) = (2 * pi / p) * x / (1 + 2 * x * tan(theta) / a),

          replacing `input_phase`'s carrier. The bias is exact (no truncation
          remainder). Reads only the same (p, theta_projector, a) attributes
          as the Taylor branch, preserving lambda_eq-independence. Raises
          ValueError if the denominator is non-positive anywhere on the grid
          (small-angle assumption violated).

    Returns
    -------
    ndarray, shape (H, W), dtype float64
        Biased phase: `input_phase - bias`, in radians.

    Notes
    -----
    The bias is column-only (independent of row) because the projector's
    perspective effect is horizontal-only under the chapter's geometry.
    The output has the same shape as `input_phase`.

    Sign convention for the 'exact' branch: the +u denominator
    (`1 + 2*x*tan(theta)/a`) matches the existing Taylor branch (which
    subtracts a positive bias). Ch.4 Eq. 4-6 as printed in the thesis has
    -u; the notebook (cell 25) treats this as a sign typo akin to the
    missing 2*pi in Eq. 4-2. With -u, the Taylor expansion would carry a
    + bias and disagree with this module's Taylor branch at the leading
    order.
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
        phase = np.asarray(input_phase, dtype=np.float64)
        H, W = phase.shape
        x = np.arange(W, dtype=np.float64)
        X = np.tile(x, (H, 1))
        denom = 1.0 + 2.0 * X * np.tan(geometry.theta_projector) / geometry.a
        denom_min = float(denom.min())
        if denom_min <= 0.0:
            raise ValueError(
                "project(model='exact'): denominator "
                "1 + 2*x*tan(theta_projector)/a is non-positive on the grid "
                f"(min={denom_min:.6e}). The small-angle/short-throw assumption "
                f"is violated. Parameters: p={geometry.p}, "
                f"theta_projector={geometry.theta_projector} rad, "
                f"a={geometry.a}, x_range=[0, {W - 1}]."
            )
        carrier_exact = (2.0 * np.pi / geometry.p) * X / denom
        # Substitute the exact-bias carrier for the carrier in `input_phase`.
        # The carrier the caller passed in is (2*pi/p)*X (the unbiased term
        # the Taylor branch is parameterized around); replacing it with
        # `carrier_exact` preserves any height/object phase the caller layered
        # on top, exactly as the Taylor branch's `phase - bias` does.
        carrier_input = (2.0 * np.pi / geometry.p) * X
        return phase - carrier_input + carrier_exact
    raise ValueError(f"unknown model {model!r}; expected 'taylor' or 'exact'")


def synthesize_psi_stack(
    phase: np.ndarray,
    deltas,
    A: float = 1.0,
    B: float = 0.9,
    fill_factor: float | None = None,
    noise_sigma: float = 0.0,
    rng=None,
) -> np.ndarray:
    """Synthesize an N-step phase-shifted intensity stack.

    Reproduces notebook cells 4 and 16: for each phase shift `delta_k` in
    `deltas`,

        I_k(x, y) = A + B * cos(phase(x, y) + delta_k),

    and stacks the frames along the last axis.

    With `fill_factor` set, a pixel-area sampling envelope locally attenuates
    the fringe contrast where the LOCAL phase gradient pushes the observed
    fringe frequency toward the sampling limit (Stage 6 A.0.2):

        I_k(x, y) = A + B * env(x, y) * cos(phase(x, y) + delta_k),

    where `env = sampling.contrast_envelope(phase, fill_factor)` keys off
    `|grad(phase)| / (2*pi)` in cycles/pixel. Steep/tall object regions fade;
    flat regions stay full-contrast.

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
    fill_factor : float or None, default None
        Pixel-area sampling model. `None` (default) reproduces the original
        point-sampled, un-attenuated synthesis byte-for-byte — the sealed-core
        regression path. A positive float enables the sampling envelope with
        that fill factor (1.0 -> first contrast null at a 1-px fringe period).
    noise_sigma : float, default 0.0
        Additive Gaussian read-noise standard deviation, in INTENSITY units
        (same scale as `A`, `B`). `0.0` (default) adds no noise and returns the
        clean stack byte-for-byte. A positive value adds sensor noise at the
        intensity stage, AFTER the envelope (Stage 6 A.4): because the noise is
        independent per frame while the `B*env` contrast is common to all
        frames, it does NOT cancel in `extract_phase`'s arctan2 — so low
        contrast (faded region) + fixed sigma = low SNR = phase error. This is
        what turns the sampling fade into a gradual beyond-Nyquist wall. Read
        noise only; shot noise (sigma ~ sqrt(I)) would attach at this same
        post-envelope site if added later.
    rng : numpy.random.Generator or None, default None
        Generator for the noise draw. Required when `noise_sigma > 0` (raises
        ValueError otherwise) so the noise is reproducible from a recorded
        seed — `np.random.default_rng(seed)`; the caller serializes `seed`, not
        the generator. Untouched (never constructed or sampled) when
        `noise_sigma <= 0`.

    Returns
    -------
    ndarray, shape (H, W, N), dtype float64
        Intensity stack. `out[..., k]` is the k-th phase-shifted frame.
    """
    phase_arr = np.asarray(phase, dtype=np.float64)
    deltas_arr = np.asarray(deltas, dtype=np.float64)
    # Broadcast: (H, W, 1) + (N,) -> (H, W, N)
    if fill_factor is None:
        signal = A + B * np.cos(phase_arr[..., None] + deltas_arr)
    else:
        env = contrast_envelope(phase_arr, fill_factor)
        signal = A + B * env[..., None] * np.cos(phase_arr[..., None] + deltas_arr)

    # Additive read noise at the sensor stage, AFTER the envelope. Gated off
    # (sigma <= 0) -> the clean signal above is returned unchanged, so the
    # no-noise path is byte-identical and no RNG state is touched.
    if noise_sigma <= 0.0:
        return signal
    if rng is None:
        raise ValueError(
            "noise_sigma > 0 requires an explicit np.random.Generator `rng` "
            "so the noise is reproducible from a recorded seed (B4 reference "
            "requirement); refusing to silently default-seed."
        )
    # size=signal.shape -> (H, W, N): INDEPENDENT per frame. An (H, W) map
    # broadcast across the N shifts would cancel in extract_phase like the
    # common B*env factor does, silently defeating the SNR mechanism.
    return signal + rng.normal(loc=0.0, scale=noise_sigma, size=signal.shape)
