"""Regression tests for geometry.equivalent_wavelength() — Stage 3.5.

Verifies the two-angle Eq. 2-51 form
    lambda_eq = M * p / (2*pi * (tan(theta_projector) + tan(theta_camera)))
in `HybridGeometry` and `SymmetricGeometry`.

Three checks:

1. test_equivalent_wavelength_two_angle_general — asymmetric arm angles
   match the closed-form Eq. 2-51 to ATOL_ANALYTICAL.

2. test_equivalent_wavelength_symmetric_case — at theta_cam = theta_proj,
   the two-angle form collapses to Eq. 2-52's M*p / (4*pi*tan theta).

3. test_equivalent_wavelength_degenerate — at theta_proj + theta_cam tangent
   sum = 0 (both zero, or equal-and-opposite), returns float('inf') via
   IEEE-clean semantics (no exception). See module docstring "Degenerate
   case" for the design rationale.
"""
from __future__ import annotations

import numpy as np
import pytest

from conftest import ATOL_ANALYTICAL
from geometry import HybridGeometry, SymmetricGeometry


@pytest.mark.parametrize(
    "geom_cls",
    [HybridGeometry, SymmetricGeometry],
    ids=["hybrid", "symmetric"],
)
def test_equivalent_wavelength_two_angle_general(geom_cls):
    """Asymmetric (theta_proj=15 deg, theta_cam=5 deg) matches Eq. 2-51.

    The two classes implement the same formula (Eq. 2-51); only their
    default M differs. This test is parametrized over both so a future
    drift in one implementation is caught immediately.
    """
    theta_proj = np.deg2rad(15.0)
    theta_cam = np.deg2rad(5.0)
    geom = geom_cls(theta_camera=theta_cam)
    # SymmetricGeometry uses `theta`; HybridGeometry uses `theta_projector`.
    # Both classes default these to 15 deg, so we don't need to touch them
    # to hit theta_proj=15 deg — but we set explicitly for documentation.
    if isinstance(geom, SymmetricGeometry):
        geom.theta = theta_proj
    else:
        geom.theta_projector = theta_proj

    expected = geom.M * geom.p / (
        2.0 * np.pi * (np.tan(theta_proj) + np.tan(theta_cam))
    )
    np.testing.assert_allclose(
        geom.equivalent_wavelength(),
        expected,
        atol=ATOL_ANALYTICAL,
        err_msg=(
            f"{geom_cls.__name__}.equivalent_wavelength() must match the "
            f"closed-form Eq. 2-51 at asymmetric angles"
        ),
    )


@pytest.mark.parametrize(
    "geom_cls",
    [HybridGeometry, SymmetricGeometry],
    ids=["hybrid", "symmetric"],
)
def test_equivalent_wavelength_symmetric_case(geom_cls):
    """At theta_cam = theta_proj, Eq. 2-51 collapses to Eq. 2-52.

    Eq. 2-52 (symmetric special case): lambda_eq = M*p / (2*pi * 2*tan(theta))
    = M*p / (4*pi*tan(theta)).
    """
    theta = np.deg2rad(15.0)
    # Default constructor sets theta_camera = theta_projector via __post_init__.
    geom = geom_cls()
    # Both classes default theta_projector / theta to 15 deg, but assert
    # the symmetric setup is in place for the test's documentation.
    assert geom.theta_projector == pytest.approx(theta)
    assert geom.theta_camera == pytest.approx(theta)

    expected_eq_2_52 = geom.M * geom.p / (4.0 * np.pi * np.tan(theta))
    np.testing.assert_allclose(
        geom.equivalent_wavelength(),
        expected_eq_2_52,
        atol=ATOL_ANALYTICAL,
        err_msg=(
            f"{geom_cls.__name__}: symmetric case (theta_cam=theta_proj) "
            f"must match Eq. 2-52's M*p / (4*pi*tan theta)"
        ),
    )


@pytest.mark.parametrize(
    "geom_cls",
    [HybridGeometry, SymmetricGeometry],
    ids=["hybrid", "symmetric"],
)
@pytest.mark.parametrize(
    "theta_proj_deg, theta_cam_deg, label",
    [
        (0.0, 0.0, "both_zero"),
        (15.0, -15.0, "equal_opposite_15"),
        (30.0, -30.0, "equal_opposite_30"),
    ],
)
def test_equivalent_wavelength_degenerate(
    geom_cls, theta_proj_deg, theta_cam_deg, label
):
    """tan(theta_proj) + tan(theta_cam) == 0 returns float('inf').

    Physically: triangulation needs angular separation between the
    projector beam and camera view. When the angles sum to zero in tan,
    both arms effectively look from the same direction — no height
    sensitivity. The implementation returns float('inf') so downstream
    callers (Stage 4 GUI) can check with math.isinf() without try/except.
    """
    theta_proj = np.deg2rad(theta_proj_deg)
    theta_cam = np.deg2rad(theta_cam_deg)
    geom = geom_cls(theta_camera=theta_cam)
    if isinstance(geom, SymmetricGeometry):
        geom.theta = theta_proj
    else:
        geom.theta_projector = theta_proj

    result = geom.equivalent_wavelength()

    assert np.isinf(result), (
        f"{geom_cls.__name__} [{label}] expected inf at degenerate "
        f"theta_proj={theta_proj_deg} deg, theta_cam={theta_cam_deg} deg; "
        f"got {result!r}"
    )
    # Specifically positive infinity — the formula's numerator is positive
    # (M, p > 0), so the limit is +inf, not -inf.
    assert result == float("inf"), (
        f"{geom_cls.__name__} [{label}] expected +inf, got {result!r}"
    )
