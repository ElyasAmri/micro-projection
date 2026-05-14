"""scene_compose.py — Pose-composition layer for the Stage 4b unified scene.

Mesh builders in `scene.py` produce primitives in their own local frames
(boxes centered on origin; cylinders along local +Z). This module builds
the 4x4 transformation matrices that place those primitives into the
world / lab frame.

World frame
-----------
Origin at the test surface center. +Z is the surface normal (up). +X
is the horizontal axis that the arms swing through when their tilt
angles become non-zero (sign convention from PROJECT_CONTEXT.md Sec 9:
+theta tilts toward +X, -theta toward -X). +Y is out of the page from
the standard side-view orientation.

Arm frame and lens-local +Z
---------------------------
Each arm (camera, projector) is parameterized by (theta_deg, distance_mm).
The arm transform places the *body+lens assembly* such that:

  - Assembly's local origin lands at world position
    `(d * sin(theta), 0, d * cos(theta))`.
  - Assembly's local +Z axis points from the assembly back at the
    world origin (i.e., the lens optical axis aims at the surface
    center). At theta=0 this means local +Z = world -Z.

Construction (right-handed, column-vector convention,
matrix applied right-to-left to a column vector v):

    M = T_translation(d*sin theta, 0, d*cos theta) @ R_y(theta) @ R_x(pi)

R_x(pi) flips the assembly so local +Z faces world -Z at theta=0.
R_y(theta) tilts the assembly through the XZ plane.
T translates to the final arm-end position.

Returned matrices are 4x4 float32 NumPy arrays in row-major form.
pyqtgraph's `Transform3D` constructor accepts the row-major form
directly (it copies into Qt's internally column-major storage).

Pico Genie lens off-center offset (deferred to sub-task 3)
----------------------------------------------------------
The Pico Genie's measured lens position in body-corner frame is
(X = 21, Y ~= 1-2, Z = 45) mm (PROJECT_CONTEXT Sec 2). In the
body-centered frame this becomes X = -6.5 mm (off-center horizontally
on the cube's front face). `body_lens_offset(body_size_mm, lens_length_mm)`
returns a PURE-Z translation that meets the body's front face — it
does NOT add this -6.5 mm horizontal offset. Sub-task 3 (GUI
composition) is responsible for left-multiplying an additional
horizontal translation when composing the projector's lens transform.
This keeps `body_lens_offset` reusable for both lenses and isolates the
Pico-Genie-specific quirk in one place at composition time.

Module scope
------------
No pyqtgraph imports, no Qt imports. Pure NumPy. The GUI layer
constructs `pg.Transform3D(matrix)` from these arrays when wiring
each mesh item.
"""
from __future__ import annotations

import numpy as np


def _rotation_x(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0,   c,  -s, 0.0],
            [0.0,   s,   c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def _rotation_y(angle_rad: float) -> np.ndarray:
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    return np.array(
        [
            [  c, 0.0,   s, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [ -s, 0.0,   c, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def _translation(tx: float, ty: float, tz: float) -> np.ndarray:
    return np.array(
        [
            [1.0, 0.0, 0.0, float(tx)],
            [0.0, 1.0, 0.0, float(ty)],
            [0.0, 0.0, 1.0, float(tz)],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float32,
    )


def _arm_transform(theta_deg: float, distance_mm: float) -> np.ndarray:
    """Shared math for camera_arm_transform and projector_arm_transform.

    Both arms apply the same construction; the two named functions are
    public wrappers so GUI call sites read naturally as
    `camera_arm_transform(...)` vs `projector_arm_transform(...)`.
    """
    theta = float(np.deg2rad(theta_deg))
    d = float(distance_mm)
    t = _translation(d * np.sin(theta), 0.0, d * np.cos(theta))
    r_y = _rotation_y(theta)
    r_x = _rotation_x(np.pi)
    return (t @ r_y @ r_x).astype(np.float32, copy=False)


def camera_arm_transform(theta_cam_deg: float, distance_mm: float) -> np.ndarray:
    """4x4 transform placing the camera body+lens assembly along its arm.

    See module docstring for the construction. The returned matrix
    transforms a point in the assembly's local frame (where the body
    sits at origin and the lens runs along local +Z) into the world
    frame (where the surface center is at origin).

    Parameters
    ----------
    theta_cam_deg : float
        Arm tilt angle from the +Z world axis (surface normal), in
        degrees. +theta tilts the arm toward +X, -theta toward -X.
    distance_mm : float
        Distance from world origin to the assembly's local origin,
        along the arm.

    Returns
    -------
    (4, 4) float32, row-major.
    """
    return _arm_transform(theta_cam_deg, distance_mm)


def projector_arm_transform(theta_proj_deg: float, distance_mm: float) -> np.ndarray:
    """4x4 transform placing the projector body+lens assembly along its arm.

    See `camera_arm_transform` and the module docstring; the math is
    identical. The two are named separately so GUI wiring code reads
    naturally and so any future arm-specific behavior (different
    rotation axes, mounting offsets) has a clear extension point.

    Parameters
    ----------
    theta_proj_deg : float
        Arm tilt angle in degrees. Sign convention matches the camera arm.
    distance_mm : float
        Distance from world origin to the assembly's local origin.

    Returns
    -------
    (4, 4) float32, row-major.
    """
    return _arm_transform(theta_proj_deg, distance_mm)


def body_lens_offset(body_size_mm: float, lens_length_mm: float) -> np.ndarray:
    """Pure-Z translation placing a lens in front of a body face.

    Composes with an arm transform so the lens sits on the body's
    front face (the face that points toward the world origin) instead
    of being centered on the body. The lens's local frame is
    centered on its own geometric center, so the +Z offset is:

        tz = body_size_mm / 2 + lens_length_mm / 2

    For the camera assembly (body 30 mm deep, lens 200 mm long):
        tz = 30/2 + 200/2 = 115 mm

    For the projector assembly (body 55 mm deep, lens 5 mm long):
        tz = 55/2 + 5/2  = 30 mm

    The Pico Genie's horizontal lens offset (X = -6.5 mm in
    body-centered frame) is NOT included here — see the module
    docstring. Caller (sub-task 3 GUI composition) is responsible
    for left-multiplying that horizontal translation when needed.

    Parameters
    ----------
    body_size_mm : float
        Body depth along local +Z (the dimension perpendicular to
        the front face). Camera: 30 mm; projector: 55 mm.
    lens_length_mm : float
        Lens length along its own local +Z.

    Returns
    -------
    (4, 4) float32, row-major. Pure translation along +Z.
    """
    tz = float(body_size_mm) / 2.0 + float(lens_length_mm) / 2.0
    return _translation(0.0, 0.0, tz)
