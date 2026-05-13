"""Regression tests for reconstruction.phase_to_height and recover_object_height.

Three checks:

a. phase_to_height is a true dispatcher — its result is bit-identical to
   calling geometry.phase_to_height directly (atol=0).

b. recover_object_height reproduces the notebook's H_rec0 to ATOL_PIPELINE
   when fed:
     - a synthesized PSI stack from phi3 = carrier + height_to_phase(H_obj)
     - phi_calibration = calibration.fit_tilt_line_1d(phi3_unwrapped)[0]
       where phi3_unwrapped is derived from the same stack via the PSI
       extract + unwrap path. Stage 3.5 note: this used to read
       phi3_unwrapped directly from the fixture, but the fixture was
       generated against the OLD λ_eq (Eq. 4-11 sin form). After Stage
       3.5 (Eq. 2-51 / Eq. 2-52 tan form), the fixture's phi3_unwrapped
       carries a slightly different linear coefficient than the new
       geometry's stack produces, and the cross-mixed wiring leaks a
       ~1e-6 residual into H_rec0 — two orders over ATOL_PIPELINE.
       Deriving phi3_unwrapped internally (as the integration test
       already does) keeps everything on the same λ_eq.
     - the canonical 4-step deltas
     - SymmetricGeometry() (matches the fixture's provenance)
   The cell-20 DC alignment to H_obj.mean() is applied in the test, not
   inside the function, because it requires ground truth.

   Why fit_tilt_line_1d and not fit_tilt_plane here: see the calibration
   module docstring for the use-case split. The 2D plane fit diverges
   from the 1D row-mean fit by ~4e-5 in H_rec on this fixture (Gaussian
   bump center sits ~0.5 px off the grid centroid), exceeding
   ATOL_PIPELINE.

c. HybridGeometry round-trip identity check:
   h -> height_to_phase -> phase_to_height -> h, to ATOL_ANALYTICAL.
   Exercises HybridGeometry's lambda_eq path independently of the
   fixture (which was built under the symmetric formula).
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_ANALYTICAL, ATOL_PIPELINE
import reconstruction
from calibration import fit_tilt_line_1d
from geometry import HybridGeometry, SymmetricGeometry
from phase_shifting import extract_phase
from synthetic_fringes import synthesize_psi_stack
from unwrapping import unwrap_2d


def test_phase_to_height_dispatches_to_geometry(regression_data):
    geom = SymmetricGeometry()
    phase = regression_data["phi3_unwrapped"]

    direct = geom.phase_to_height(phase)
    via_dispatcher = reconstruction.phase_to_height(phase, geom)

    np.testing.assert_array_equal(
        direct,
        via_dispatcher,
        err_msg="reconstruction.phase_to_height must be a pure pass-through",
    )


def test_recover_object_height_matches_fixture(regression_data):
    geom = SymmetricGeometry()
    H, W = geom.H, geom.W
    assert regression_data["H_obj"].shape == (H, W)

    # Rebuild the analytical phi3 the notebook used in cell 14 to drive
    # cell 16's frame synthesis: phi3 = (2*pi/p)*X + K*H_obj, where
    # K = 1/lambda_eq. Use geometry.height_to_phase to wire the same
    # lambda_eq path the fixture was generated with.
    x = np.arange(W, dtype=np.float64)
    y = np.arange(H, dtype=np.float64)
    X, _ = np.meshgrid(x, y)
    carrier = (2.0 * np.pi / geom.p) * X
    phi3 = carrier + geom.height_to_phase(regression_data["H_obj"])

    deltas = [0.0, np.pi / 2.0, np.pi, 3.0 * np.pi / 2.0]
    stack = synthesize_psi_stack(phi3, deltas)

    # Derive phi3_unwrapped from the same stack (PSI extract + unwrap), so
    # phi_calibration's linear coefficient matches the stack's λ_eq. The
    # fixture's phi3_unwrapped is on the OLD λ_eq and would leak ~1e-6 of
    # residual into H_rec0 — see module docstring (Stage 3.5 note).
    wrapped = extract_phase(stack, deltas)
    phi3_unwrapped = unwrap_2d(wrapped)

    # Match notebook cell 18 via calibration.fit_tilt_line_1d (1D polyfit
    # on row-mean, tiled). NOT fit_tilt_plane — see the calibration module
    # docstring for why the 2D fit diverges here.
    phi_calibration, _ = fit_tilt_line_1d(phi3_unwrapped)

    h_rec = reconstruction.recover_object_height(
        stack, phi_calibration, deltas, geom
    )

    # DC alignment to ground truth (notebook cell 20). Done in the test
    # because it requires H_obj.mean(); the recovery function itself
    # returns the mean-centered height map.
    h_rec0 = h_rec - h_rec.mean() + regression_data["H_obj"].mean()

    np.testing.assert_allclose(
        h_rec0,
        regression_data["H_rec0"],
        atol=ATOL_PIPELINE,
        err_msg=(
            "recover_object_height + DC alignment must reproduce the "
            "notebook's H_rec0"
        ),
    )


def test_hybrid_geometry_round_trip():
    geom = HybridGeometry()
    H, W = geom.H, geom.W

    rng = np.random.RandomState(0)
    h_true = rng.standard_normal((H, W))

    phase = geom.height_to_phase(h_true)
    h_rec = reconstruction.phase_to_height(phase, geom)

    np.testing.assert_allclose(
        h_rec,
        h_true,
        atol=ATOL_ANALYTICAL,
        err_msg=(
            "HybridGeometry round-trip height -> phase -> height must "
            "recover the input"
        ),
    )
