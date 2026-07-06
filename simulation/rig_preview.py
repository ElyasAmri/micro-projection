"""Annotated overview render of the rig: the PRO4500 projector, the telecentric
camera, and the fringe-lit surface, with device bodies, frustum/ray lines, and
labels so the geometry is readable at a glance. Feeds the app's "Rig" view.

Builds the scene with rig.py (so the preview is exactly the simulated
geometry), then adds emissive visualization aids on top. All aids are marked
shadow-invisible: the drawn lens barrel encloses the spot light's emission
point, so without that it would occlude the projector's own light.

The viewpoint is an orbit around the scene: `--azimuth`/`--elevation` (degrees)
and `--distance` (meters) place the overview camera on a sphere around AIM,
always looking at it. Defaults reproduce the original hand-picked framing.

Run:
    blender -b -P simulation/rig_preview.py -- \
        --out out/rig_model/overview_annotated.png --samples 32
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402
from geometry_constants import (  # noqa: E402
    CAM_PIXELS,
    CAM_WORKING_DISTANCE_MM,
    D_PROJ_MM,
    H0_MM,
    MM,
    SURFACE_SIZE_M,
    THETA_DEG,
    W0_MM,
    W_PROJ_MM,
)

PROJ_COLOR = (0.25, 0.45, 1.0)
CAM_COLOR = (1.0, 0.38, 0.18)
EDGE_COLOR = (0.55, 0.55, 0.55)
LABEL_COLOR = (0.9, 0.9, 0.9)

# Orbit center: between the surface center and the devices, so the whole rig
# stays framed as the viewpoint moves. The default orbit reproduces the
# original fixed vantage point (0.40, -0.44, 0.31).
AIM = (0.02, 0.0, 0.065)
DEFAULT_AZIMUTH_DEG = -49.2
DEFAULT_ELEVATION_DEG = 22.9
DEFAULT_DISTANCE_M = 0.631

_materials: dict[tuple, bpy.types.Material] = {}


def _emissive(color, strength):
    key = (tuple(color), strength)
    if key not in _materials:
        mat = bpy.data.materials.new(f"Viz{len(_materials)}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*color, 1.0)
        em.inputs["Strength"].default_value = strength
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        _materials[key] = mat
    return _materials[key]


def _set_mat(obj, color, strength):
    obj.data.materials.clear()
    obj.data.materials.append(_emissive(color, strength))
    # Viz-only geometry must not shadow the rig's projector (see module docstring).
    obj.visible_shadow = False


def _add_line(p1: Vector, p2: Vector, radius: float, color, strength=1.0):
    d = p2 - p1
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=d.length,
                                        location=(p1 + p2) / 2, vertices=8)
    obj = bpy.context.active_object
    obj.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    _set_mat(obj, color, strength)
    return obj


def _add_box(location: Vector, dims, color, strength, rotation=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.scale = dims
    if rotation is not None:
        obj.rotation_euler = rotation
    _set_mat(obj, color, strength)
    return obj


def _add_barrel(center: Vector, axis: Vector, radius, depth, color, strength):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=center)
    obj = bpy.context.active_object
    obj.rotation_euler = axis.to_track_quat("Z", "Y").to_euler()
    _set_mat(obj, color, strength)
    return obj


def _add_label(text: str, location: Vector, size: float, cam_obj):
    bpy.ops.object.text_add(location=location)
    obj = bpy.context.active_object
    obj.data.body = text
    obj.data.size = size
    obj.data.align_x = "CENTER"
    obj.rotation_euler = cam_obj.rotation_euler  # billboard toward overview cam
    _set_mat(obj, LABEL_COLOR, 1.0)
    return obj


def build_scene(azimuth_deg: float = DEFAULT_AZIMUTH_DEG,
                elevation_deg: float = DEFAULT_ELEVATION_DEG,
                distance_m: float = DEFAULT_DISTANCE_M):
    """The rig scene plus annotation; returns the overview camera, placed on
    the (azimuth, elevation, distance) orbit sphere around AIM."""
    rig.clear_scene()
    projector = rig.add_projector()
    rig.add_surface(projector)
    telecentric_cam = rig.add_telecentric_camera()
    bpy.context.view_layer.update()

    # Overview camera: frames the devices and the full plate. Elevation is
    # clamped short of the pole, where look_at's roll becomes degenerate.
    az = math.radians(azimuth_deg)
    el = math.radians(min(88.0, max(2.0, elevation_deg)))
    dist = max(0.2, distance_m)
    aim = Vector(AIM)
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.type = "PERSP"
    cam_data.lens = 31.0
    overview = bpy.data.objects.new("Camera_Preview", cam_data)
    bpy.context.collection.objects.link(overview)
    overview.location = aim + dist * Vector(
        (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    rig.look_at(overview, aim)
    bpy.context.view_layer.update()

    # Projector body (looks straight down from D_PROJ).
    p_loc = Vector(projector.location)
    _add_box(p_loc + Vector((0, 0, 0.028)), (0.052, 0.034, 0.024), PROJ_COLOR, 0.35)
    _add_barrel(p_loc + Vector((0, 0, 0.009)), Vector((0, 0, 1)), 0.008, 0.018,
                PROJ_COLOR, 0.8)

    # Projection cone edges + illuminated footprint rectangle on z=0.
    fw, fh = W_PROJ_MM * MM / 2, H0_MM * MM / 2
    corners = [Vector((sx * fw, sy * fh, 0)) for sx, sy in
               ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for c in corners:
        _add_line(p_loc, c, 0.0005, PROJ_COLOR, 0.6)
    for a, b in zip(corners, corners[1:] + corners[:1]):
        _add_line(a, b, 0.0006, PROJ_COLOR, 1.0)

    # Telecentric camera body (tilted; orthographic -> parallel rays).
    c_loc = Vector(telecentric_cam.location)
    view_dir = -c_loc.normalized()  # looks at the origin
    _add_barrel(c_loc - view_dir * 0.030, view_dir, 0.013, 0.060, CAM_COLOR, 0.5)
    _add_box(c_loc - view_dir * 0.075, (0.030, 0.030, 0.032), CAM_COLOR, 0.35,
             rotation=view_dir.to_track_quat("Z", "Y").to_euler())

    # Parallel ortho rays from the sensor rectangle corners down to z=0.
    w = W0_MM * MM
    h = w * CAM_PIXELS[1] / CAM_PIXELS[0]
    mw = telecentric_cam.matrix_world
    hits = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        o = mw @ Vector((sx * w / 2, sy * h / 2, 0))
        d = (mw.to_3x3() @ Vector((0, 0, -1))).normalized()
        hit = o + (-o.z / d.z) * d
        hits.append(hit)
        _add_line(o, hit, 0.0005, CAM_COLOR, 0.6)
    for a, b in zip(hits, hits[1:] + hits[:1]):
        _add_line(a, b, 0.0006, CAM_COLOR, 1.0)

    # Surface plate outline.
    s = SURFACE_SIZE_M / 2
    plate = [Vector((sx * s, sy * s, 0)) for sx, sy in
             ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for a, b in zip(plate, plate[1:] + plate[:1]):
        _add_line(a, b, 0.0008, EDGE_COLOR, 0.5)

    _add_label(f"PRO4500 projector\n({D_PROJ_MM:.0f} mm WD)",
               p_loc + Vector((0, 0, 0.055)), 0.016, overview)
    _add_label(f"Telecentric camera\n({CAM_WORKING_DISTANCE_MM:.0f} mm WD, "
               f"{THETA_DEG:.1f}° tilt)",
               c_loc - view_dir * 0.075 + Vector((0, 0, 0.045)), 0.016, overview)
    _add_label("Surface (300 mm, fringe-lit footprint)",
               Vector((0.0, -s - 0.012, 0.002)), 0.016, overview)
    return overview


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="out/rig_model/overview_annotated.png")
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument("--azimuth", type=float, default=DEFAULT_AZIMUTH_DEG)
    parser.add_argument("--elevation", type=float, default=DEFAULT_ELEVATION_DEG)
    parser.add_argument("--distance", type=float, default=DEFAULT_DISTANCE_M)
    args = parser.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"[rig_preview] building the rig scene (az {args.azimuth:.0f}°, "
          f"el {args.elevation:.0f}°, dist {args.distance:.2f} m)...", flush=True)
    overview = build_scene(args.azimuth, args.elevation, args.distance)
    print(f"[rig_preview] rendering ({args.samples} samples)...", flush=True)
    rig.render(bpy.context.scene, overview, (1600, 1000), out, args.samples)
    print(f"[rig_preview] saved {out}", flush=True)


if __name__ == "__main__":
    main()
