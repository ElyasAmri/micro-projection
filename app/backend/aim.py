"""Camera-aim measurement: where does the camera actually look?

The reconstruction assumes the camera views the center of the projected field.
This module measures the pointing error so the mount can be adjusted against
numbers instead of by eye:

* Marker method (fast, one frame): project a small bright disc at the projector
  field center and find its centroid in the camera frame. The offset from the
  camera's center pixel is the aim error, reported in camera px and (via the
  design telecentric scale) in mm.
* Absolute-phase method (fallback, 2 x N frames): when the marker is not in the
  camera's view at all, single-period fringes give an unambiguous projector
  coordinate for every camera pixel; the coordinate imaged at the camera center
  says where the camera looks and hence which way to move.

Both assume the camera sees the specimen plane; the mm figures use the design
telecentric scale (geometry_constants), so along the tilt axis true plane
distances are ~1/cos(theta) larger. The guide converges regardless.

Qt-free, like backend.calibrate, so the maths runs headless and under test.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.base import fringe_pattern, sim_dir
from backend.calibrate import _shift_fringe_h, psa_phase

MARKER_RADIUS_PX = 20  # ~1.4mm on the plane at the design 68um projector px


def marker_pattern(proj_w: int, proj_h: int,
                   radius_px: int = MARKER_RADIUS_PX, level: int = 255) -> np.ndarray:
    """A black field with a bright disc at the projector center."""
    y, x = np.ogrid[:proj_h, :proj_w]
    cx, cy = (proj_w - 1) / 2.0, (proj_h - 1) / 2.0
    disc = (x - cx) ** 2 + (y - cy) ** 2 <= float(radius_px) ** 2
    image = np.zeros((proj_h, proj_w), dtype=np.uint8)
    image[disc] = level
    return image


def locate_patterns(proj_w: int, proj_h: int, n_steps: int = 8) -> list:
    """Single-period (absolute, wrap-free) fringe stacks, vertical then
    horizontal, for the phase-based fallback."""
    vertical = [
        fringe_pattern(1.0, phase=k / n_steps, width=proj_w, height=proj_h)
        for k in range(n_steps)
    ]
    horizontal = [
        _shift_fringe_h(1.0, k / n_steps, proj_w, proj_h)
        for k in range(n_steps)
    ]
    return vertical + horizontal


def find_marker(frame: np.ndarray, bright_fraction: float = 0.5,
                min_area_px: int = 30, max_area_fraction: float = 0.05) -> dict:
    """Centroid of the projected marker in a camera frame. Raises ValueError
    when no plausible blob is visible (the caller falls back to the phase
    method). `touches_border` flags a clipped blob whose centroid is biased."""
    import cv2

    image = np.asarray(frame, dtype=np.float64)
    if image.ndim == 3:
        image = image.mean(axis=2)
    peak = float(image.max())
    if peak < 20.0:
        raise ValueError("frame is dark; the marker is not in view")
    mask = (image >= bright_fraction * peak).astype(np.uint8)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        raise ValueError("no bright blob found")
    areas = stats[1:, cv2.CC_STAT_AREA]
    best = int(np.argmax(areas)) + 1
    if int(areas[best - 1]) < min_area_px:
        raise ValueError("no blob large enough to be the marker")
    # A marker-sized disc covers well under a percent of the camera frame. A
    # huge "blob" means the threshold caught the ambient-lit scene instead
    # (auto-exposure flooding a mostly-dark projection), not the marker.
    frame_area = float(mask.shape[0] * mask.shape[1])
    if float(areas[best - 1]) > max_area_fraction * frame_area:
        raise ValueError(
            f"brightest region covers {100.0 * areas[best - 1] / frame_area:.0f}% "
            "of the frame; ambient light or auto-exposure flooding, not the marker")
    cx, cy = (float(centroids[best][0]), float(centroids[best][1]))
    x0 = int(stats[best, cv2.CC_STAT_LEFT])
    y0 = int(stats[best, cv2.CC_STAT_TOP])
    x1 = x0 + int(stats[best, cv2.CC_STAT_WIDTH])
    y1 = y0 + int(stats[best, cv2.CC_STAT_HEIGHT])
    h, w = mask.shape
    touches = x0 <= 0 or y0 <= 0 or x1 >= w or y1 >= h
    return {"centroid": (cx, cy), "area_px": int(areas[best - 1]),
            "touches_border": touches}


def center_projector_coord(stack_v: np.ndarray, stack_h: np.ndarray,
                           proj_w: int, proj_h: int,
                           modulation_dn: float = 5.0,
                           window: int = 15) -> tuple:
    """The projector pixel imaged at the camera frame center, from absolute
    (single-period) phase stacks. Raises ValueError when the center of the
    camera frame sees no modulated light at all."""
    phase_v, mod_v = psa_phase(stack_v)
    phase_h, mod_h = psa_phase(stack_h)
    h, w = phase_v.shape
    half = max(1, window // 2)
    ys = slice(h // 2 - half, h // 2 + half + 1)
    xs = slice(w // 2 - half, w // 2 + half + 1)
    mask = (mod_v[ys, xs] >= modulation_dn) & (mod_h[ys, xs] >= modulation_dn)
    if mask.sum() < 5:
        raise ValueError("the camera center sees no projected light; aim the "
                         "camera roughly at the projection first")
    # Median of the wrapped phase over the window, through the wrap. With one
    # period across the field, phase maps 1:1 onto the projector coordinate.
    pv = _circular_median(phase_v[ys, xs][mask])
    ph = _circular_median(phase_h[ys, xs][mask])
    u = (pv % (2.0 * np.pi)) / (2.0 * np.pi)
    v = (ph % (2.0 * np.pi)) / (2.0 * np.pi)
    return (u * proj_w - 0.5, v * proj_h - 0.5)


def _circular_median(phase: np.ndarray) -> float:
    """Median direction of wrapped phases (safe near the +/-pi seam)."""
    z = np.exp(1j * phase)
    return float(np.angle(np.median(z.real) + 1j * np.median(z.imag)))


def design_geometry() -> dict:
    """The rig design constants the aim report is scored against: camera mm
    per px and the design tilt. Falls back to px-only reporting when the
    simulation package is unavailable."""
    try:
        import sys

        d = str(sim_dir())
        if d not in sys.path:
            sys.path.insert(0, d)
        import geometry_constants as g  # noqa: E402  (sibling sim package)

        return {
            "cam_mm_per_px_x": g.W0_MM / g.CAM_PIXELS[0],
            "cam_mm_per_px_y": g.H0_MM / g.CAM_PIXELS[1],
            "design_theta_deg": g.THETA_DEG,
        }
    except Exception:  # noqa: BLE001 - design constants are optional
        return {"cam_mm_per_px_x": None, "cam_mm_per_px_y": None,
                "design_theta_deg": None}


def offset_metrics(dx_px: float, dy_px: float, method: str,
                   geometry: dict | None = None) -> dict:
    """Aim-error metrics from a camera-px offset of the projected field center
    relative to the camera center. Positive dx = the field center appears to
    the right of where the camera looks (pan the camera right), positive dy =
    it appears below (pan down)."""
    g = geometry or design_geometry()
    mx, my = g.get("cam_mm_per_px_x"), g.get("cam_mm_per_px_y")
    dx_mm = dx_px * mx if mx else None
    dy_mm = dy_px * my if my else None
    distance_mm = (float(np.hypot(dx_mm, dy_mm))
                   if dx_mm is not None and dy_mm is not None else None)
    return {
        "method": method,
        "offset_cam_px": (float(dx_px), float(dy_px)),
        "offset_mm": (dx_mm, dy_mm),
        "distance_mm": distance_mm,
        "pan": ("right" if dx_px > 0 else "left",
                "down" if dy_px > 0 else "up"),
        "design_theta_deg": g.get("design_theta_deg"),
    }


def measure_from_marker(frame: np.ndarray, geometry: dict | None = None) -> dict:
    """Aim error from one marker frame (raises ValueError if not visible)."""
    marker = find_marker(frame)
    h, w = np.asarray(frame).shape[:2]
    cx, cy = marker["centroid"]
    metrics = offset_metrics(cx - w / 2.0, cy - h / 2.0, "marker", geometry)
    metrics["marker_area_px"] = marker["area_px"]
    metrics["marker_touches_border"] = marker["touches_border"]
    return metrics


def measure_from_phase(frames: list, proj_w: int, proj_h: int, n_steps: int = 8,
                       geometry: dict | None = None) -> dict:
    """Aim error from the absolute-phase stacks (2 x n_steps camera frames).
    Works however far off the camera points, as long as it sees fringes."""
    stack_v = np.stack([np.asarray(f, dtype=np.float64) for f in frames[:n_steps]])
    stack_h = np.stack([np.asarray(f, dtype=np.float64) for f in frames[n_steps:]])
    u0, v0 = center_projector_coord(stack_v, stack_h, proj_w, proj_h)
    # The camera looks at (u0, v0); the target is the field center. The pan
    # direction is toward the center, i.e. the sign of (center - look-at) in
    # projector coords, which matches the camera-frame sign convention because
    # the projector-to-camera map preserves orientation on this rig.
    du = proj_w / 2.0 - u0
    dv = proj_h / 2.0 - v0
    metrics = offset_metrics(du, dv, "absolute_phase", geometry)
    # Projector px offsets are exact here; mm via the camera scale is only an
    # approximation (it treats projector px as camera px), so replace it with
    # the projector-space numbers and drop the mm figures.
    metrics["cam_center_proj_px"] = (float(u0), float(v0))
    metrics["offset_proj_px"] = (float(du), float(dv))
    metrics["offset_mm"] = (None, None)
    metrics["distance_mm"] = None
    metrics["offset_cam_px"] = (None, None)
    return metrics


def load_frames(capture_dir: Path) -> list:
    """The frame_*.png stack of a capture directory, as grayscale ndarrays."""
    import cv2

    frames = []
    for path in sorted(Path(capture_dir).glob("frame_*.png")):
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"could not read {path}")
        frames.append(image)
    return frames


def write_report(path: Path, metrics: dict) -> None:
    lines = ["Camera aim measurement", f"method: {metrics['method']}"]
    dx_px, dy_px = metrics.get("offset_cam_px", (None, None))
    dx_mm, dy_mm = metrics.get("offset_mm", (None, None))
    if dx_px is not None:
        lines.append(f"projected center vs camera center: "
                     f"({dx_px:+.1f}, {dy_px:+.1f}) camera px")
    if dx_mm is not None:
        lines.append(f"  = ({dx_mm:+.2f}, {dy_mm:+.2f}) mm on the plane, "
                     f"{metrics['distance_mm']:.2f} mm total")
    if metrics.get("offset_proj_px") is not None:
        du, dv = metrics["offset_proj_px"]
        u0, v0 = metrics["cam_center_proj_px"]
        lines.append(f"camera looks at projector px ({u0:.0f}, {v0:.0f}); "
                     f"field center offset ({du:+.0f}, {dv:+.0f}) projector px")
    pan_x, pan_y = metrics["pan"]
    lines.append(f"adjust: pan the camera {pan_x} and {pan_y}")
    if metrics.get("marker_touches_border"):
        lines.append("warning: the marker blob touches the camera frame "
                     "border; the centroid (and this offset) is biased")
    if metrics.get("design_theta_deg") is not None:
        lines.append(f"design camera tilt: {metrics['design_theta_deg']:.1f} deg "
                     "(compare via Calibrate Camera Angle)")
    with open(path, "w", encoding="ascii") as handle:
        handle.write("\n".join(lines) + "\n")
