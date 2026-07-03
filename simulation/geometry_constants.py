"""Rig geometry constants, shared by rig.py (Blender scene-building) and
reconstruct.py (plain-Python phase/height reconstruction). No bpy import,
so reconstruct.py can run outside Blender.

Numbers are the results derived in report/math.tex.
"""
from __future__ import annotations

MM = 1e-3

# --- Camera: fixed telecentric FOV (report/math.tex sec. 3) -----------------
H0_MM = 54.67
W0_MM = 68.22
CAM_PIXELS = (1280, 1024)
CAM_WORKING_DISTANCE_MM = 160.0  # chosen within the GoldTL lens's 132-182mm range

# --- Projector: PRO4500, 460nm LED, 184mm-WD 3D-measurement lens -------------
# The 460nm module ships with 92 / 184 / 700mm lens options; we run the 184mm
# lens (131.2x82mm rated FOV, 100um pixel) at ~123mm -- inside its rated range,
# closer than nominal -- to shrink the image onto the camera's footprint. The
# 92mm lens is the same throw ratio at half the distance/FOV (50um pixel). Throw
# ratio = working distance / image dimension (report/math.tex sec. 4).
THROW_RATIO_W = 92.0 / 65.6   # = 184/131.2 = 1.402
THROW_RATIO_H = 92.0 / 41.0   # = 184/82    = 2.244
D_PROJ_MM = 122.7   # H0 * THROW_RATIO_H: distance for a 54.67mm-tall image (report/math.tex sec. 5)
W_PROJ_MM = 87.47   # image width there (= H0 * 1.6); unchanged from the earlier design
SPOT_CONE_DEG = 50.0  # full angle; wide enough to cover the footprint's corners at ~123mm

# --- Camera tilt (report/math.tex sec. 7) -----------------------------------
THETA_DEG = 38.7

SURFACE_SIZE_M = 0.30  # flat surface, generous margin around the ~90x55mm footprint
SURFACE_GRID_SUBDIVISIONS = 180  # ~1.7mm vertex spacing: >8 verts across BUMP_SIGMA_MM
