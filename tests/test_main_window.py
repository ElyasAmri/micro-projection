"""MainWindow-level invariants that don't need GUI construction.

These tests assert on module-level constants exported from
`gui.main_window`. No QApplication needed — pure import-and-check.

Path setup: conftest.py adds `src/` to sys.path; that lets the
`from gui.main_window import ...` form resolve.
"""
from __future__ import annotations

from gui.main_window import (
    HARDWARE_INFO_ROWS,
    SURFACE_PIXEL_SIZE_MM,
    SURFACE_SHAPE,
)


def _parse_fov_mm() -> tuple[float, float]:
    """Return the advertised FOV (width_mm, height_mm) from HARDWARE_INFO_ROWS.

    Format expected: ("FOV", "<width> × <height> mm") with the Unicode
    multiplication sign U+00D7. Raises if the row is missing so a
    HARDWARE_INFO_ROWS rename can't silently coexist with a stale grid.
    """
    for name, value in HARDWARE_INFO_ROWS:
        if name == "FOV":
            stripped = value.replace("mm", "").strip()
            parts = [p.strip() for p in stripped.split("×")]
            return float(parts[0]), float(parts[1])
    raise AssertionError("HARDWARE_INFO_ROWS has no 'FOV' entry")


def test_surface_grid_matches_camera_fov():
    """SURFACE_SHAPE * SURFACE_PIXEL_SIZE_MM must equal the advertised FOV.

    Locks the math grid to the camera spec. If future grid bumps (Stage
    5/6 hardware reconciliation) change one without the other, this
    test fails and forces the divergence to be confronted.
    """
    fov_w_mm, fov_h_mm = _parse_fov_mm()
    actual_w_mm = SURFACE_SHAPE[1] * SURFACE_PIXEL_SIZE_MM
    actual_h_mm = SURFACE_SHAPE[0] * SURFACE_PIXEL_SIZE_MM
    assert actual_w_mm == fov_w_mm, (
        f"grid width {actual_w_mm} mm != FOV width {fov_w_mm} mm"
    )
    assert actual_h_mm == fov_h_mm, (
        f"grid height {actual_h_mm} mm != FOV height {fov_h_mm} mm"
    )
