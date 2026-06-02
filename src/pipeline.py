"""pipeline.py — End-to-end forward + inverse fringe projection pipeline.

`run_pipeline()` chains the existing math modules into a single call that
takes a ground-truth heightmap and returns the recovered heightmap. It is
a refactor of the object leg of `tests/test_pipeline_synthetic.py`, not a
redesign:

    1. Build object phase: carrier + geometry.height_to_phase(heightmap)
    2. Synthesize a phase-shifted intensity stack
    3. Extract wrapped phase + unwrap
    4. Self-calibrate via fit_tilt_line_1d on the unwrapped phase
    5. Recover height via recover_object_height
    6. DC-align the recovered height to heightmap.mean()

The pipeline is self-calibrating (cell-18 tilt-fit on the object's own
unwrapped phase). It does NOT use a separate flat-reference stack or
`compute_inverse_phase` — the integration test's calibration leg
computes those but does not feed them into the object recovery, so
they're dead code in the operational pipeline.

Architectural notes
-------------------
- Units are caller-controlled. `geometry.p`, `geometry.a`, and the
  heightmap are expected to share a common unit (the math layer's
  X grid is `np.arange(W)`, pixel indices). The fixture tests use
  pixel units throughout; the GUI passes mm-valued p/a/heightmap and
  inherits dimensional inconsistency from the spec — see commit 4/N
  message for the open issue.
- `model` parameter is accepted for API completeness but is currently
  a no-op: the object leg synthesizes from `carrier + height_phase`
  directly without `project()`, matching the integration test's
  deliberate omission of the projector-bias step (see that test's
  module docstring for the rationale).
"""
from __future__ import annotations

from typing import Union

import numpy as np

from calibration import fit_tilt_line_1d
from pattern_generator import inverse_grating_phase
from phase_shifting import extract_phase
from reconstruction import recover_object_height
from synthetic_fringes import project, synthesize_psi_stack
from unwrapping import unwrap_2d


def run_pipeline(
    heightmap: np.ndarray,
    geometry,
    n_psi_steps: int,
    model: str = "taylor",
    return_stages: bool = False,
) -> Union[np.ndarray, tuple[np.ndarray, dict[str, np.ndarray]]]:
    """Run the full forward + inverse fringe projection pipeline.

    Takes a ground-truth heightmap and returns the recovered heightmap.

    Parameters
    ----------
    heightmap : (H, W) ndarray, float64
        Ground-truth surface. Units must match `geometry.p`,
        `geometry.a`, and the geometry's `lambda_eq` output (caller-
        controlled — see module docstring).
    geometry : Geometry protocol
        `HybridGeometry` or `SymmetricGeometry`. Provides `p`,
        `theta_projector`, `a`, and the `height_to_phase` /
        `phase_to_height` boundary via `lambda_eq`.
    n_psi_steps : int
        Number of phase-shifted frames synthesized in the PSI stack.
        Typically 4 or 8. Deltas are evenly spaced over [0, 2*pi).
    model : {'taylor', 'exact'}, default 'taylor'
        Forward-model choice. Currently a no-op in the object leg of
        the pipeline (see module docstring); reserved for future
        calibration-leg integration.
    return_stages : bool, default False
        If False, return only the recovered heightmap (backwards
        compatible). If True, return a 2-tuple
        `(recovered, stages_dict)` where stages_dict exposes the
        pipeline's intermediate arrays for visualization:

            'ground_truth'    : the input heightmap (float64-cast)
            'fringe_frame'    : object_stack[..., 0], the first PSI
                                phase-shift frame (the "camera view")
            'wrapped_phase'   : output of extract_phase (range [-pi, pi])
            'unwrapped_phase' : output of unwrap_2d

        The dict values are references (not copies) to the pipeline's
        intermediate arrays. The caller should not mutate them; if
        mutation is needed, np.array(value) explicitly.

    Returns
    -------
    recovered : (H, W) ndarray, float64
        Reconstructed height, DC-aligned to `heightmap.mean()` so the
        output is element-wise comparable to the input on absolute
        magnitude.
    stages : dict[str, ndarray] (only if `return_stages=True`)
        See description above.
    """
    heightmap = np.asarray(heightmap, dtype=np.float64)
    H, W = heightmap.shape

    # Evenly-spaced PSI deltas over [0, 2*pi). For n=4 this is the
    # notebook's [0, pi/2, pi, 3*pi/2].
    deltas = [2.0 * np.pi * k / n_psi_steps for k in range(n_psi_steps)]

    # Object phase: carrier + height-induced phase shift. Matches
    # tests/test_pipeline_synthetic.py object leg lines 117-118.
    x = np.arange(W, dtype=np.float64)
    X = np.tile(x, (H, 1))
    carrier = (2.0 * np.pi / geometry.p) * X
    phi_object = carrier + geometry.height_to_phase(heightmap)

    # Synthesize phase-shifted intensity stack.
    object_stack = synthesize_psi_stack(phi_object, deltas)

    # Self-calibration: tilt-fit the object's own unwrapped phase.
    object_wrapped = extract_phase(object_stack, deltas)
    phi_unwrapped = unwrap_2d(object_wrapped)
    phi_calibration, _ = fit_tilt_line_1d(phi_unwrapped)

    # Recover height. Note: recover_object_height re-runs extract+unwrap
    # internally on the stack — `phi_unwrapped` above is consumed only
    # by fit_tilt_line_1d for the self-cal step.
    h_rec = recover_object_height(object_stack, phi_calibration, deltas, geometry)

    # DC alignment to input heightmap mean. Matches notebook cell 20.
    recovered = h_rec - h_rec.mean() + heightmap.mean()

    if return_stages:
        stages: dict[str, np.ndarray] = {
            "ground_truth": heightmap,
            "fringe_frame": object_stack[..., 0],
            "wrapped_phase": object_wrapped,
            "unwrapped_phase": phi_unwrapped,
        }
        return recovered, stages
    return recovered


def run_inverse_fpp(
    reference_heightmap: np.ndarray,
    object_heightmap: np.ndarray,
    geometry,
    deltas,
    fill_factor: Union[float, None] = None,
) -> np.ndarray:
    """One closed inverse-FPP pass: reference -> inverse grating -> project -> recover.

    The single callable step of the inverse-FPP loop (Stage 6 A.2). Unlike
    `run_pipeline` — which synthesizes the object directly from
    `carrier + height_to_phase` with NO projector bias — this routes the
    capture through the non-telecentric projector's perspective bias
    (`synthetic_fringes.project`) and pre-corrects it with an inverse grating
    derived from the reference (`pattern_generator.inverse_grating_phase`):

        1. ref_phase  = project(carrier, geom) + height_to_phase(reference)
        2. phi_proj   = inverse_grating_phase(ref_phase)        # = 2P - ref_phase
        3. obj_phase  = project(phi_proj, geom) + height_to_phase(object)
        4. recover obj_phase via the existing PSI + self-cal path
        5. DC-align to object.mean()

    Because `project` is affine in its phase argument (the bias is independent
    of the phase, `synthetic_fringes.project`), step 3 cancels the bias
    EXACTLY: `project(phi_proj) = 2P - carrier`, a purely linear term the
    self-calibration removes. The inverse grating is therefore what makes
    `project()`-on-the-object safe — without it, the quadratic bias residual
    blows recovery up by ~6 orders (see tests/test_pipeline_synthetic.py
    module docstring). The inverse grating is NON-identity whenever the
    projector is biased; it reduces to the plain carrier only in the
    telecentric (bias-free) limit.

    Loop-wrappable by construction: height in, height out. A convergence loop
    can feed the previous recovered height back as `reference_heightmap`
    without any adapter — the closed-loop seam (deferred) wraps this step,
    it does not rewrite it.

    Parameters
    ----------
    reference_heightmap : (H, W) ndarray
        Known reference surface. Flat (zeros) for A.2; a measured golden-part
        heightmap later (B.2). Must match `object_heightmap`'s shape.
    object_heightmap : (H, W) ndarray
        Object surface to measure.
    geometry : Geometry protocol
        Provides `p`, the `project` bias params, and `height_to_phase` /
        `phase_to_height` via `lambda_eq`.
    deltas : sequence of float, shape (N,)
        PSI phase shifts (same contract as `recover_object_height`).
    fill_factor : float or None, default None
        Pixel-area sampling model for the OBJECT capture. `None` (default)
        keeps point sampling — the existing behavior, byte-identical. A
        positive float enables the contrast-fade envelope (A.2b only flips
        this default; the structure is unchanged).

    Returns
    -------
    (H, W) ndarray, float64
        Recovered object height, DC-aligned to `object_heightmap.mean()`.

    Notes
    -----
    Tautology caveat: the same affine `project` model creates the capture and
    is inverted by the inverse grating, so a passing closure proves CONSISTENCY
    (composition, sign, unwrap, self-cal wired correctly), NOT physics. Physics
    validation is D.3-vs-B.4 (a real projector whose bias is not the analytic
    Taylor model).
    """
    reference_heightmap = np.asarray(reference_heightmap, dtype=np.float64)
    object_heightmap = np.asarray(object_heightmap, dtype=np.float64)
    H, W = object_heightmap.shape

    x = np.arange(W, dtype=np.float64)
    X = np.tile(x, (H, 1))
    carrier = (2.0 * np.pi / geometry.p) * X

    # 1-2. Reference capture (biased) -> inverse grating (non-identity).
    ref_phase = project(carrier, geometry) + geometry.height_to_phase(
        reference_heightmap
    )
    phi_projected = inverse_grating_phase(ref_phase)

    # 3. Project the inverse pattern onto the object; the bias cancels exactly.
    obj_phase = project(phi_projected, geometry) + geometry.height_to_phase(
        object_heightmap
    )

    # 4. Existing PSI + self-cal recovery path (envelope off by default).
    object_stack = synthesize_psi_stack(obj_phase, deltas, fill_factor=fill_factor)
    object_wrapped = extract_phase(object_stack, deltas)
    phi_unwrapped = unwrap_2d(object_wrapped)
    phi_calibration, _ = fit_tilt_line_1d(phi_unwrapped)
    h_rec = recover_object_height(object_stack, phi_calibration, deltas, geometry)

    # 5. DC alignment to the object mean.
    return h_rec - h_rec.mean() + object_heightmap.mean()
