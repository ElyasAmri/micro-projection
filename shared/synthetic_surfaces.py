from __future__ import annotations

import math

SURFACE_KINDS: tuple[str, ...] = (
    "dome-ridge",
    "twin-hills",
    "saddle-ripple",
    "terrace",
    "ring-crater",
    "folded-sheet",
    "cross-groove",
)


def height_field_depth_m(
    u: float,
    v: float,
    patch_width: float,
    patch_height: float,
    *,
    surface_kind: str,
) -> float:
    x_norm = u / (patch_width * 0.5)
    y_norm = v / (patch_height * 0.5)
    if surface_kind == "dome-ridge":
        dome_cm = 1.35 * math.exp(-2.5 * (x_norm * x_norm + y_norm * y_norm))
        ridge_cm = 0.55 * math.exp(-22.0 * (y_norm + 0.16) ** 2) * math.exp(-1.1 * x_norm * x_norm)
        ripple_cm = (
            0.18
            * math.sin(2.2 * math.pi * x_norm)
            * math.cos(1.4 * math.pi * y_norm)
            * math.exp(-1.6 * (x_norm * x_norm + y_norm * y_norm))
        )
        depth_cm = 0.16 + dome_cm + ridge_cm + ripple_cm
    elif surface_kind == "twin-hills":
        hill_left_cm = 1.05 * math.exp(-7.5 * ((x_norm + 0.42) ** 2 + 1.3 * (y_norm + 0.05) ** 2))
        hill_right_cm = 0.92 * math.exp(-8.8 * ((x_norm - 0.28) ** 2 + 0.9 * (y_norm - 0.18) ** 2))
        valley_cm = -0.22 * math.exp(-10.0 * ((x_norm + 0.02) ** 2 + 2.5 * (y_norm - 0.02) ** 2))
        shoulder_cm = 0.18 * math.exp(-2.2 * ((x_norm * 0.9) ** 2 + (y_norm * 1.3) ** 2))
        depth_cm = 0.18 + hill_left_cm + hill_right_cm + valley_cm + shoulder_cm
    elif surface_kind == "saddle-ripple":
        saddle_cm = 0.72 * (0.9 * x_norm * x_norm - 0.65 * y_norm * y_norm + 0.4)
        diagonal_cm = 0.24 * x_norm * y_norm
        ripple_cm = 0.12 * math.sin(2.8 * math.pi * x_norm + 0.45) * math.sin(1.8 * math.pi * y_norm)
        taper = math.exp(-1.3 * (x_norm * x_norm + y_norm * y_norm))
        depth_cm = 0.18 + (saddle_cm + diagonal_cm + ripple_cm) * taper
    elif surface_kind == "terrace":
        radial = math.sqrt((0.95 * x_norm) ** 2 + (1.15 * y_norm) ** 2)
        dome_cm = 1.55 * max(0.0, 1.0 - radial**1.6)
        terrace_cm = 0.18 * round(dome_cm / 0.18)
        trench_cm = -0.18 * math.exp(-18.0 * ((x_norm - 0.22) ** 2 + (y_norm + 0.28) ** 2))
        lip_cm = 0.14 * math.exp(-35.0 * (y_norm - 0.08) ** 2) * math.exp(-3.0 * x_norm * x_norm)
        depth_cm = 0.14 + terrace_cm + trench_cm + lip_cm
    elif surface_kind == "ring-crater":
        radial = math.sqrt((1.05 * x_norm) ** 2 + (0.92 * y_norm) ** 2)
        ring_cm = 1.10 * math.exp(-42.0 * (radial - 0.48) ** 2)
        crater_cm = -0.72 * math.exp(-11.5 * radial * radial)
        skew_cm = 0.22 * math.exp(-9.5 * ((x_norm + 0.18) ** 2 + (y_norm - 0.16) ** 2))
        ripple_cm = 0.10 * math.sin(5.0 * math.pi * radial) * math.exp(-3.2 * radial * radial)
        depth_cm = 0.22 + ring_cm + crater_cm + skew_cm + ripple_cm
    elif surface_kind == "folded-sheet":
        base_cm = 0.42 + 0.24 * x_norm - 0.11 * y_norm
        fold_a_cm = 0.34 * math.sin(3.8 * math.pi * x_norm + 0.35) * math.exp(-0.7 * y_norm * y_norm)
        fold_b_cm = 0.26 * math.sin(2.6 * math.pi * (x_norm + 0.55 * y_norm) - 0.2)
        fold_c_cm = 0.18 * math.cos(4.6 * math.pi * y_norm + 0.3) * math.exp(-0.9 * x_norm * x_norm)
        pinch_cm = -0.20 * math.exp(-20.0 * ((x_norm - 0.12) ** 2 + (y_norm + 0.10) ** 2))
        depth_cm = base_cm + fold_a_cm + fold_b_cm + fold_c_cm + pinch_cm
    elif surface_kind == "cross-groove":
        broad_cm = 1.05 * math.exp(-1.7 * (x_norm * x_norm + 0.7 * y_norm * y_norm))
        groove_x_cm = -0.44 * math.exp(-60.0 * x_norm * x_norm)
        groove_y_cm = -0.36 * math.exp(-52.0 * y_norm * y_norm)
        corner_peaks_cm = 0.26 * (
            math.exp(-16.0 * ((x_norm - 0.42) ** 2 + (y_norm - 0.42) ** 2))
            + math.exp(-16.0 * ((x_norm + 0.40) ** 2 + (y_norm + 0.38) ** 2))
        )
        step_cm = 0.10 * round((broad_cm + corner_peaks_cm) / 0.10)
        depth_cm = 0.16 + step_cm + groove_x_cm + groove_y_cm
    else:
        raise ValueError(f"Unsupported surface kind: {surface_kind}")
    return max(0.08, depth_cm) / 100.0
