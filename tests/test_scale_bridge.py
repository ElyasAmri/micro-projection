"""Tests for the object-space scale bridge (Stage 6 A.0.1).

The scale bridge is a LABELING-ONLY layer: three named constants that
convert pixel counts to physical microns for human display, with a single
canonical source so the number cannot drift. These tests pin:

- the derived relationship OBJECT_SPACE_UM_PER_PIXEL == pitch / magnification,
- that the (formerly dead, hardcoded-53.0) `pixel_pitch_um` field on both
  geometries now resolves to the one canonical constant.

They do NOT assert anything about the math path — by design the bridge is
never read by the carrier, lambda_eq, project(), or synthesize_psi_stack().
"""
from __future__ import annotations

from geometry import (
    CAMERA_MAGNIFICATION,
    CAMERA_PIXEL_PITCH_UM,
    OBJECT_SPACE_UM_PER_PIXEL,
    HybridGeometry,
    SymmetricGeometry,
)


def test_object_space_pixel_size_is_derived():
    """OBJECT_SPACE_UM_PER_PIXEL is pitch / magnification, not a 2nd literal."""
    assert CAMERA_PIXEL_PITCH_UM == 4.8
    assert CAMERA_MAGNIFICATION == 0.09
    assert OBJECT_SPACE_UM_PER_PIXEL == CAMERA_PIXEL_PITCH_UM / CAMERA_MAGNIFICATION


def test_geometry_pixel_pitch_redirects_to_canonical():
    """Both geometries' pixel_pitch_um now sources the one canonical value."""
    assert HybridGeometry().pixel_pitch_um == OBJECT_SPACE_UM_PER_PIXEL
    assert SymmetricGeometry().pixel_pitch_um == OBJECT_SPACE_UM_PER_PIXEL
