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
from phase_shifting import extract_phase
from reconstruction import recover_object_height
from synthetic_fringes import synthesize_psi_stack
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
