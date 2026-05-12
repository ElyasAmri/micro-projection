"""Regression tests for reconstruction.phase_to_height and recover_object_height.

Three checks:

a. phase_to_height is a true dispatcher — its result is bit-identical to
   calling geometry.phase_to_height directly (atol=0).

b. recover_object_height reproduces the notebook's H_rec0 to ATOL_PIPELINE
   when fed:
     - a synthesized PSI stack from phi3 = carrier + height_to_phase(H_obj)
     - phi_calibration = inline 1D polyfit on phi3_unwrapped.mean(axis=0),
       tiled to (H, W), bit-for-bit matching notebook cell 18.
     - the canonical 4-step deltas
     - SymmetricGeometry() (matches the fixture's provenance)
   The cell-20 DC alignment to H_obj.mean() is applied in the test, not
   inside the function, because it requires ground truth.

   Why not use calibration.fit_tilt_plane here: that function does a 2D
   lstsq fit, while the notebook does a 1D polyfit on the row-mean. For
   phi3_unwrapped (which contains a centered Gaussian bump whose center
   sits ~0.5 px off the grid centroid), the two fits diverge by enough
   to produce a ~4e-5 difference in H_rec — far above ATOL_PIPELINE.
   calibration.fit_tilt_plane's correctness is verified independently
   in test_calibration.py; this test exercises recover_object_height as
   a pipeline with notebook-faithful inputs.

c. HybridGeometry round-trip identity check:
   h -> height_to_phase -> phase_to_height -> h, to ATOL_ANALYTICAL.
   Exercises HybridGeometry's lambda_eq path independently of the
   fixture (which was built under the symmetric formula).
"""
from __future__ import annotations

import numpy as np

from conftest import ATOL_ANALYTICAL, ATOL_PIPELINE
import reconstruction
from geometry import HybridGeometry, SymmetricGeometry
from synthetic_fringes import synthesize_psi_stack


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

    # Match notebook cell 18 bit-for-bit: 1D polyfit on phi3_unwrapped's
    # row-mean, then np.tile to (H, W). Not via calibration.fit_tilt_plane
    # (which is 2D lstsq) — see module docstring for the divergence.
    phi3_profile = regression_data["phi3_unwrapped"].mean(axis=0)
    m3, c3 = np.polyfit(x, phi3_profile, 1)
    phi_calibration = np.tile(m3 * x + c3, (H, 1))

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
