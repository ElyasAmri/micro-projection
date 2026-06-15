"""Paper-spec-derived prior calibration parameters (solver warm-start + UI demo)."""
from __future__ import annotations

import math

from microprojection.core import paper_specs


def prior_calibration() -> dict[str, float]:
    """Calibration parameter dict consistent with the paper specs.

    Derivations:
      - Pixel pitch on the measurement plane (mm/px): a telecentric lens maps
        the imaged field onto the sensor 1:1 up to a magnification factor that
        depends on the chosen lens. As a prior we use the largest field the
        telecentric front element can cover (= lens diameter) divided by the
        capture grid width. Calibration will refine this.
      - fringe_pitch_mm: physical pitch of one fringe on the plane =
        fringe_period_px * the PRO4500 projected pixel size (305 um at the
        700 mm measurement-lens working distance, from the brochure).
      - lambda_eq_mm: equivalent (triangulation) wavelength relating phase to
        height, h = (lambda_eq / 2*pi) * d_phi. For a fringe of pitch p on the
        plane viewed with angle theta between the projection and viewing axes,
        lambda_eq = p / tan(theta). Calibration ties it to the actual rig.
      - baseline_mm: nominal projector-camera spacing from paper specs.
      - Incidence angles: paper specs place both at ~41 degrees from normal.
    """
    field_mm = 10.0 * paper_specs.MAX_TELECENTRIC_FIELD_WIDTH_CM  # cm -> mm
    pixel_pitch_mm = field_mm / paper_specs.SURFACE_CAMERA_CAPTURE_WIDTH_PX
    # Physical fringe pitch on the plane from the real projector pixel size.
    fringe_period_px = 48.0
    fringe_pitch_mm = fringe_period_px * paper_specs.PROJECTOR_PIXEL_SIZE_MM
    baseline_mm = 10.0 * paper_specs.DEFAULT_DEVICE_SPACING_CM
    # Symmetric rig prior: camera and projector at the same incidence from
    # normal (derived from the simulation geometry; calibration will refine).
    incidence_deg = math.degrees(math.atan2(baseline_mm,
                                            2.0 * 10.0 * paper_specs.OPTICAL_AXIS_HEIGHT_CM))
    # Angle between the projection and viewing axes (symmetric rig).
    theta_rad = 2.0 * math.radians(incidence_deg)
    lambda_eq_mm = fringe_pitch_mm / math.tan(theta_rad)
    field_h_mm = field_mm * (paper_specs.SURFACE_CAMERA_CAPTURE_HEIGHT_PX
                             / paper_specs.SURFACE_CAMERA_CAPTURE_WIDTH_PX)
    return {
        "pixel_pitch_mm": pixel_pitch_mm,
        "projector_pixel_size_mm": paper_specs.PROJECTOR_PIXEL_SIZE_MM,
        "fringe_pitch_mm": fringe_pitch_mm,
        "lambda_eq_mm": lambda_eq_mm,
        "baseline_mm": baseline_mm,
        "camera_angle_deg": incidence_deg,
        "projector_angle_deg": incidence_deg,
        "field_mm": (field_mm, field_h_mm),
        "calibration_rms_px": float("nan"),
    }
