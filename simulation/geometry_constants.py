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

# --- Projector: PRO4500, 460nm/700mm 3D-measurement lens --------------------
THROW_RATIO_W = 700.0 / 400.0
THROW_RATIO_H = 700.0 / 250.0
D_PROJ_MM = 153.1   # matches the camera's H0 (report/math.tex sec. 5)
W_PROJ_MM = 87.47
SPOT_CONE_DEG = 40.0  # full angle; wide enough to cover the footprint's corners

# --- Camera tilt (report/math.tex sec. 7) -----------------------------------
THETA_DEG = 38.7

SURFACE_SIZE_M = 0.30  # flat surface, generous margin around the ~90x55mm footprint
SURFACE_GRID_SUBDIVISIONS = 180  # ~1.7mm vertex spacing: >8 verts across BUMP_SIGMA_MM
