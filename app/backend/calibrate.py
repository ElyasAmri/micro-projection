"""Camera-angle calibration from projected patterns.

The camera is telecentric (orthographic), so viewing the specimen plane at an
angle theta from its normal foreshortens the image by cos(theta) along the tilt
axis only. A pattern of known geometry projected onto the plane therefore
images with a measurable anisotropy, and the anisotropy hands back the angle.
Two independent estimates are produced so they can be compared:

* Box aspect: a centered square box images as a rectangle whose bounding-box
  aspect is cos(theta). One frame, edge-based, assumes the tilt is aligned with
  a camera image axis and that the whole box is inside the camera frame.
* Phase gradients: an N-step phase-shift stack is captured for vertical and for
  horizontal fringes. The two wrapped-phase gradients give the full 2x2 linear
  map between projector and camera pixels; its SVD yields cos(theta) as the
  singular-value ratio plus the tilt-axis direction, using every well-modulated
  pixel (subpixel, no edge detection, no axis-alignment assumption).

Both treat the projector as normal to the plane with square pixels. If the
projector is itself oblique, the reported angle is the combined
projector/camera obliquity, not the camera's alone.

The capture is a single sequence of 1 + 2N patterns (box, vertical fringe
steps, horizontal fringe steps) produced by `calibration_patterns`, so one
camera session grabs everything; `run` then evaluates the frame stack. This
module stays Qt-free so the maths can run headless and under test.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from backend.base import fringe_pattern
from backend.patterns import _fringe_h


@dataclass(frozen=True)
class CalibrationSpec:
    """The pattern sequence of one calibration run and the geometry needed to
    evaluate its frames."""

    patterns: list
    n_steps: int
    n_periods: float
    proj_w: int
    proj_h: int
    box_rect: tuple  # (x0, y0, x1, y1) of the projected square, projector px


def calibration_patterns(
    proj_w: int,
    proj_h: int,
    n_steps: int = 8,
    n_periods: float = 8.0,
    box_fraction: float = 0.6,
) -> CalibrationSpec:
    """The projector sequence for one calibration run: a centered square box,
    then N vertical-fringe phase steps, then N horizontal-fringe phase steps."""
    side = box_fraction * min(proj_w, proj_h)
    half = side / 2.0
    cx, cy = proj_w / 2.0, proj_h / 2.0
    x0, y0 = int(round(cx - half)), int(round(cy - half))
    x1, y1 = int(round(cx + half)), int(round(cy + half))
    box = np.zeros((proj_h, proj_w), dtype=np.uint8)
    box[y0:y1, x0:x1] = 255

    vertical = [
        fringe_pattern(n_periods, phase=k / n_steps, width=proj_w, height=proj_h)
        for k in range(n_steps)
    ]
    # _fringe_h phase-steps the sinusoid down the height the same way.
    horizontal = [
        _shift_fringe_h(n_periods, k / n_steps, proj_w, proj_h)
        for k in range(n_steps)
    ]
    return CalibrationSpec(
        patterns=[box] + vertical + horizontal,
        n_steps=n_steps,
        n_periods=n_periods,
        proj_w=proj_w,
        proj_h=proj_h,
        box_rect=(x0, y0, x1, y1),
    )


def _shift_fringe_h(n_periods: float, phase: float, width: int, height: int) -> np.ndarray:
    """A horizontal fringe (sinusoid down the height) at the given phase step.
    patterns._fringe_h fixes phase=0, so the stepped variant lives here, built
    the same way: the vertical generator across the height, broadcast wide."""
    column = fringe_pattern(n_periods, phase=phase, width=height, height=1)[0]
    return np.broadcast_to(column[:, None], (height, width)).copy()


# -- phase-shift analysis ------------------------------------------------------

def psa_phase(stack: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """N-step phase-shift analysis of a (N, H, W) stack imaged from patterns
    I_k = A + B*sin(psi + 2*pi*k/N). Returns (wrapped phase psi, modulation B
    in the stack's intensity units)."""
    n = stack.shape[0]
    delta = 2.0 * np.pi * np.arange(n) / n
    s = np.tensordot(np.sin(delta), stack, axes=(0, 0))
    c = np.tensordot(np.cos(delta), stack, axes=(0, 0))
    # I_k*cos sums to B*sin(psi)*N/2 and I_k*sin to B*cos(psi)*N/2.
    psi = np.arctan2(c, s)
    modulation = 2.0 / n * np.sqrt(s * s + c * c)
    return psi, modulation


def _wrapped_gradient(phase: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    """Median (d/dx, d/dy) of a wrapped phase map over `mask`, differencing
    through the wrap (valid while the true per-pixel step stays under pi)."""
    dx = np.angle(np.exp(1j * (phase[:, 1:] - phase[:, :-1])))
    dy = np.angle(np.exp(1j * (phase[1:, :] - phase[:-1, :])))
    mx = mask[:, 1:] & mask[:, :-1]
    my = mask[1:, :] & mask[:-1, :]
    if mx.sum() < 100 or my.sum() < 100:
        raise ValueError("too few well-modulated pixels to estimate the phase gradient")
    return float(np.median(dx[mx])), float(np.median(dy[my]))


def phase_gradient_angle(
    phase_v: np.ndarray,
    phase_h: np.ndarray,
    mask: np.ndarray,
    n_periods: float,
    proj_w: int,
    proj_h: int,
) -> dict:
    """The camera angle from the two wrapped-phase gradients.

    With projector coords p and camera coords q related by q = A p + t, the
    vertical-fringe phase is (2*pi*n/W)*u so its camera-space gradient is
    (2*pi*n/W) times the first row of A^-1 (and the horizontal fringe gives the
    second row via H). Stacking both rows yields B = A^-1, the camera->projector
    linear map. Its singular values are projector px per camera px along the
    principal axes: the tilt compresses the camera image, inflating one of
    them, so cos(theta) = sigma_min / sigma_max and the tilt axis is the right
    singular vector paired with sigma_max."""
    gvx, gvy = _wrapped_gradient(phase_v, mask)
    ghx, ghy = _wrapped_gradient(phase_h, mask)
    b = np.array([
        [gvx * proj_w, gvy * proj_w],
        [ghx * proj_h, ghy * proj_h],
    ]) / (2.0 * np.pi * n_periods)
    _u, sigma, vt = np.linalg.svd(b)
    ratio = float(sigma[1] / sigma[0]) if sigma[0] > 0 else 0.0
    ratio = min(max(ratio, 1e-3), 1.0)
    axis = vt[0]  # camera-space direction of the compression (tilt) axis
    axis_deg = float(np.degrees(np.arctan2(axis[1], axis[0]))) % 180.0
    return {
        "theta_deg": float(np.degrees(np.arccos(ratio))),
        "tilt_axis_deg": axis_deg,
        # camera px per projector px, along the tilt axis and perpendicular
        "scale_tilt": float(1.0 / sigma[0]),
        "scale_perp": float(1.0 / sigma[1]),
    }


# -- box-aspect analysis -------------------------------------------------------

def box_aspect_angle(frame: np.ndarray, bright_fraction: float = 0.4) -> dict:
    """The camera angle from one frame of the projected square box: bounding
    box of the bright region, aspect = w/h = cos(theta). Assumes the tilt is
    horizontal in the camera image; `touches_border` flags a box that spills
    past the camera frame (its full extent is unknown, so the aspect and the
    angle derived from it are unreliable)."""
    image = np.asarray(frame, dtype=np.float64)
    if image.ndim == 3:
        image = image.mean(axis=2)
    peak = float(image.max())
    if peak <= 0:
        raise ValueError("box frame is entirely dark")
    mask = image >= bright_fraction * peak
    ys, xs = np.where(mask)
    if xs.size < 100:
        raise ValueError("no projected box found in the camera frame")
    w_box = float(xs.max() - xs.min() + 1)
    h_box = float(ys.max() - ys.min() + 1)
    h_img, w_img = mask.shape
    edge = max(2, min(h_img, w_img) // 200)
    touches = bool(
        mask[:, :edge].any() or mask[:, -edge:].any()
        or mask[:edge, :].any() or mask[-edge:, :].any()
    )
    # Aspect > 1 would mean vertical compression; fold it so theta stays real
    # and report the raw aspect for inspection.
    aspect = w_box / h_box if h_box else 1.0
    ratio = min(aspect, 1.0 / aspect) if aspect > 0 else 1e-3
    ratio = min(max(ratio, 1e-3), 1.0)
    return {
        "theta_deg": float(np.degrees(np.arccos(ratio))),
        "aspect": float(aspect),
        "touches_border": touches,
        "box_px": (w_box, h_box),
    }


# -- orchestration -------------------------------------------------------------

def run(
    capture_dir: Path,
    out_dir: Path,
    spec: CalibrationSpec,
    modulation_dn: float = 5.0,
) -> dict:
    """Evaluate a calibration frame stack: frame 0 is the box, then N vertical
    and N horizontal fringe steps. Writes phase/modulation maps and a text
    report to `out_dir`; returns the combined metrics."""
    import cv2

    frames = sorted(Path(capture_dir).glob("frame_*.png"))
    expected = 1 + 2 * spec.n_steps
    if len(frames) != expected:
        raise ValueError(f"expected {expected} calibration frames, found {len(frames)}")
    stack = []
    for path in frames:
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError(f"could not read {path}")
        stack.append(image.astype(np.float64))
    box_frame = stack[0]
    stack_v = np.stack(stack[1:1 + spec.n_steps])
    stack_h = np.stack(stack[1 + spec.n_steps:])

    phase_v, mod_v = psa_phase(stack_v)
    phase_h, mod_h = psa_phase(stack_h)
    mask = (mod_v >= modulation_dn) & (mod_h >= modulation_dn)
    valid_fraction = float(mask.mean())

    phase = phase_gradient_angle(
        phase_v, phase_h, mask, spec.n_periods, spec.proj_w, spec.proj_h
    )
    try:
        box = box_aspect_angle(box_frame)
    except ValueError as exc:
        box = {"error": str(exc)}

    metrics = {
        "theta_phase_deg": phase["theta_deg"],
        "tilt_axis_deg": phase["tilt_axis_deg"],
        "scale_tilt": phase["scale_tilt"],
        "scale_perp": phase["scale_perp"],
        "valid_fraction": valid_fraction,
        "theta_box_deg": box.get("theta_deg"),
        "box_aspect": box.get("aspect"),
        "box_touches_border": box.get("touches_border"),
        "box_error": box.get("error"),
    }
    if metrics["theta_box_deg"] is not None:
        metrics["delta_deg"] = abs(metrics["theta_phase_deg"] - metrics["theta_box_deg"])
    else:
        metrics["delta_deg"] = None

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_map(out_dir / "calibration_phase_v.png", phase_v, mask)
    _write_map(out_dir / "calibration_phase_h.png", phase_h, mask)
    cv2.imwrite(str(out_dir / "calibration_modulation.png"),
                np.clip(np.minimum(mod_v, mod_h), 0, 255).astype(np.uint8))
    _write_report(out_dir / "calibration.txt", spec, metrics)
    return metrics


def _write_map(path: Path, phase: np.ndarray, mask: np.ndarray) -> None:
    """A wrapped phase map as an 8-bit PNG, masked pixels black."""
    import cv2

    scaled = ((phase + np.pi) / (2.0 * np.pi) * 255.0).astype(np.uint8)
    scaled[~mask] = 0
    cv2.imwrite(str(path), scaled)


def _write_report(path: Path, spec: CalibrationSpec, m: dict) -> None:
    lines = [
        "Camera-angle calibration",
        f"projector: {spec.proj_w} x {spec.proj_h} px, "
        f"{spec.n_steps}-step, {spec.n_periods:g} periods",
        "",
        "Phase-gradient method (whole-field, subpixel):",
        f"  camera angle: {m['theta_phase_deg']:.2f} deg",
        f"  tilt axis: {m['tilt_axis_deg']:.1f} deg from camera x-axis",
        f"  scale (camera px per projector px): {m['scale_tilt']:.4f} along tilt, "
        f"{m['scale_perp']:.4f} perpendicular",
        f"  well-modulated pixels: {100.0 * m['valid_fraction']:.1f}%",
        "",
        "Box-aspect method (single frame, edge-based):",
    ]
    if m.get("box_error"):
        lines.append(f"  failed: {m['box_error']}")
    else:
        lines.append(f"  camera angle: {m['theta_box_deg']:.2f} deg "
                     f"(aspect {m['box_aspect']:.4f})")
        if m.get("box_touches_border"):
            lines.append("  warning: box touches the camera frame border; "
                         "its full extent is not visible, angle unreliable")
        lines.append("")
        lines.append(f"Difference between methods: {m['delta_deg']:.2f} deg")
    lines += [
        "",
        "Assumes the projector is normal to the plane with square pixels; an",
        "oblique projector folds its own angle into the numbers above.",
    ]
    with open(path, "w", encoding="ascii") as handle:
        handle.write("\n".join(lines) + "\n")
