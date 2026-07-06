"""Annotated overview render of the rig: the PRO4500 projector, the telecentric
camera assembly, and the fringe-lit specimen on its Z-stage, with the real
hardware modeled to vendor dimensions, frustum/ray lines, and labels so the
geometry is readable at a glance. Feeds the app's "Rig" view.

The device bodies are the lab's actual components (see the *_MM constants and
their sources below): the Wintech PRO4500 projection engine, the FLIR Blackfly S
camera behind an Edmund #58-259 0.09x GoldTL telecentric lens held by its
#56-027 mounting clamp, and an Edmund #66-509 125mm Z-stage carrying the
specimen.

Builds the scene with rig.py (so the preview is exactly the simulated
geometry), then adds emissive visualization aids on top. All aids are marked
shadow-invisible: the drawn lens barrel encloses the spot light's emission
point, so without that it would occlude the projector's own light. They are
also excluded from diffuse/glossy bounces so the (large) emissive bodies never
tint the fringe-lit surface.

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
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rig  # noqa: E402
from geometry_constants import (  # noqa: E402
    CAM_PIXELS,
    CAM_WORKING_DISTANCE_MM,
    D_PROJ_MM,
    H0_MM,
    MM,
    THETA_DEG,
    W0_MM,
    W_PROJ_MM,
)

PROJ_COLOR = (0.25, 0.45, 1.0)
CAM_COLOR = (1.0, 0.38, 0.18)
EDGE_COLOR = (0.55, 0.55, 0.55)
LABEL_COLOR = (0.9, 0.9, 0.9)

# --- Real hardware dimensions (mm) -------------------------------------------
# Wintech PRO4500 optical engine (datasheet, docs/HANDOFF_HARDWARE.md):
# 210x84x54mm overall = 145mm-long body + a dia-30 x 65mm projection lens
# barrel; the light exits at the barrel tip.
PRO4500_BODY_MM = (84.0, 54.0, 145.0)   # width x depth x length (along axis)
PRO4500_BARREL_MM = (30.0, 65.0)        # diameter, protrusion

# Edmund #58-259 0.09x 1/2" GoldTL telecentric lens (vendor spec table):
# 200mm long excluding threads, in three sections behind the front face --
# the dia-110 objective, a taper, and the dia-55 C-mount rear tube.
GOLDTL_FRONT_MM = (110.0, 76.0)         # diameter, length
GOLDTL_TAPER_MM = (110.0, 55.0, 59.0)   # front dia -> rear dia over length
GOLDTL_REAR_MM = (55.0, 65.0)           # diameter, length

# Edmund #56-027 mounting clamp for that lens (vendor drawing): dia-110 bore,
# 50mm deep, 134mm wide, 148mm tall with the bore center 81mm above the base.
CLAMP_OUTER_R_MM = 67.0                 # 148 overall - 81 bore center
CLAMP_BORE_CENTER_MM = 81.0
CLAMP_WIDTH_MM = 134.0
CLAMP_DEPTH_MM = 50.0

# FLIR Blackfly S BFS-U3-13Y3M-C (datasheet, docs/HANDOFF_HARDWARE.md):
# 29x29x30mm body behind the lens's C-mount.
FLIR_BODY_MM = (29.0, 29.0, 30.0)

# Edmund #66-509 125mm metric Z-stage (vendor drawing): 125x125 platform at
# 80-100mm height (20mm travel; modeled mid-travel), 3mm base flange, and a
# dia-18 micrometer reaching 63.5mm past the edge, its axis 20.5mm up.
ZSTAGE_PLATFORM_MM = 125.0
ZSTAGE_HEIGHT_MM = 90.0
ZSTAGE_BASE_MM = 3.0
ZSTAGE_KNOB_MM = (18.0, 63.5, 20.5)     # diameter, reach past edge, height

# The bench: two 1"-grid solid aluminum breadboards -- a 24"x24" base and a
# 48"x24" board standing portrait (24" wide, 48" tall) on the table behind
# it -- braced by a pair of Edmund #11-158 Universal Right Angle Brackets
# (vendor drawing: 12" tall, 6" base, 1" thick) whose feet bolt to the base
# board. The camera clamp bolts to the vertical board rotated 90 degrees,
# its base flush against the board face.
BOARD_THICK_MM = 12.7
HOLE_PITCH_MM = 25.4
HOLE_EDGE_MM = 12.7
HOLE_R_MM = 3.3
BASE_BOARD_MM = 609.6                   # 24" x 24" square
VBOARD_MM = (609.6, 1219.2)             # 24" wide x 48" tall, portrait
BRACKET_MM = (152.4, 304.8, 25.4)       # base leg, height, thickness
# The vertical board's front face: flush with the rotated camera clamp's
# base, i.e. the clamp's bore-center-to-base drop behind the lens axis.
VBOARD_FACE_Y_MM = -CLAMP_BORE_CENTER_MM
BENCH_X_CENTER_MM = 30.0                # boards recentered on the rig's reach

# Orbit center: between the specimen and the devices, so the whole rig stays
# framed as the viewpoint moves. Default framing picked by eye for the
# full-size hardware models; the azimuth looks from +Y, the open side of the
# vertical bench board (from -Y the board hides the whole rig).
AIM = (0.06, 0.0, 0.22)
DEFAULT_AZIMUTH_DEG = 49.2
DEFAULT_ELEVATION_DEG = 14.0
DEFAULT_DISTANCE_M = 1.35

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
    # Viz-only geometry must not shadow the rig's projector, nor light the
    # surface through bounces (see module docstring).
    obj.visible_shadow = False
    obj.visible_diffuse = False
    obj.visible_glossy = False
    obj.visible_transmission = False


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


def _add_cone_section(center: Vector, axis: Vector, r_base, r_tip, depth,
                      color, strength):
    """A truncated cone: radius r_base at center - axis*depth/2, r_tip at
    center + axis*depth/2 (the cone's own +Z is its tip end)."""
    bpy.ops.mesh.primitive_cone_add(radius1=r_base, radius2=r_tip, depth=depth,
                                    location=center)
    obj = bpy.context.active_object
    obj.rotation_euler = axis.to_track_quat("Z", "Y").to_euler()
    _set_mat(obj, color, strength)
    return obj


def _basis_euler(x_axis: Vector, y_axis: Vector, z_axis: Vector):
    """Euler rotation mapping a unit cube's local axes onto the given
    (orthonormal, right-handed) world axes."""
    return Matrix(((x_axis.x, y_axis.x, z_axis.x),
                   (x_axis.y, y_axis.y, z_axis.y),
                   (x_axis.z, y_axis.z, z_axis.z))).to_euler()


def _add_tri_prism(origin: Vector, leg_dir: Vector, up_dir: Vector,
                   leg, height, thick, color, strength):
    """A right-triangle plate (the angle-bracket silhouette): right angle at
    `origin`, one leg along `leg_dir`, the other along `up_dir`, extruded
    `thick` symmetrically about their plane."""
    half = leg_dir.cross(up_dir) * (thick / 2)
    corners = (origin, origin + leg_dir * leg, origin + up_dir * height)
    verts = [c - half for c in corners] + [c + half for c in corners]
    mesh = bpy.data.meshes.new("Bracket")
    mesh.from_pydata([tuple(v) for v in verts], [],
                     [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)])
    mesh.update()
    obj = bpy.data.objects.new("Bracket", mesh)
    bpy.context.collection.objects.link(obj)
    _set_mat(obj, color, strength)
    return obj


def _add_hole_grid(first: Vector, u_dir: Vector, v_dir: Vector, axis: Vector,
                   nu: int, nv: int, color):
    """A breadboard's tapped-hole grid: nu x nv dark disks, `HOLE_PITCH_MM`
    apart, proud of the surface by a hair so they read against the board.
    One template cylinder, mesh shared across copies (a per-hole bpy.ops
    call would dominate the scene build)."""
    bpy.ops.mesh.primitive_cylinder_add(radius=HOLE_R_MM * MM, depth=0.0008,
                                        location=first, vertices=12)
    template = bpy.context.active_object
    template.rotation_euler = axis.to_track_quat("Z", "Y").to_euler()
    _set_mat(template, color, 1.0)
    pitch = HOLE_PITCH_MM * MM
    for i in range(nu):
        for j in range(nv):
            if i == 0 and j == 0:
                continue
            hole = template.copy()  # shares the mesh datablock
            hole.location = first + u_dir * (i * pitch) + v_dir * (j * pitch)
            bpy.context.collection.objects.link(hole)


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
    # The specimen surface at the physical platform extent (the sim's capture
    # margin plane would occlude the stage under it).
    rig.add_surface(projector, size_m=ZSTAGE_PLATFORM_MM * MM)
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

    # Projector: PRO4500 at true size, aimed straight down, the light exiting
    # at its lens-barrel tip (= the spot light's location).
    p_loc = Vector(projector.location)
    barrel_d, barrel_len = (v * MM for v in PRO4500_BARREL_MM)
    body_w, body_d, body_len = (v * MM for v in PRO4500_BODY_MM)
    _add_barrel(p_loc + Vector((0, 0, barrel_len / 2)), Vector((0, 0, 1)),
                barrel_d / 2, barrel_len, PROJ_COLOR, 0.8)
    _add_box(p_loc + Vector((0, 0, barrel_len + body_len / 2)),
             (body_w, body_d, body_len), PROJ_COLOR, 0.35)

    # Projection cone edges + illuminated footprint rectangle on z=0.
    fw, fh = W_PROJ_MM * MM / 2, H0_MM * MM / 2
    corners = [Vector((sx * fw, sy * fh, 0)) for sx, sy in
               ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    for c in corners:
        _add_line(p_loc, c, 0.0005, PROJ_COLOR, 0.6)
    for a, b in zip(corners, corners[1:] + corners[:1]):
        _add_line(a, b, 0.0006, PROJ_COLOR, 1.0)

    # Camera assembly (tilted; orthographic -> parallel rays): the GoldTL
    # telecentric lens with its front face at the working distance, the FLIR
    # body on its C-mount, and the lens's mounting clamp around the objective.
    c_loc = Vector(telecentric_cam.location)
    view_dir = -c_loc.normalized()  # looks at the origin
    back = -view_dir                # from the lens front face toward the camera
    front_d, front_len = (v * MM for v in GOLDTL_FRONT_MM)
    taper_d0, taper_d1, taper_len = (v * MM for v in GOLDTL_TAPER_MM)
    rear_d, rear_len = (v * MM for v in GOLDTL_REAR_MM)
    _add_barrel(c_loc + back * (front_len / 2), back, front_d / 2, front_len,
                CAM_COLOR, 0.45)
    _add_cone_section(c_loc + back * (front_len + taper_len / 2), back,
                      taper_d0 / 2, taper_d1 / 2, taper_len, CAM_COLOR, 0.45)
    lens_len = front_len + taper_len + rear_len
    _add_barrel(c_loc + back * (lens_len - rear_len / 2), back, rear_d / 2,
                rear_len, CAM_COLOR, 0.45)
    flir_w, flir_h, flir_len = (v * MM for v in FLIR_BODY_MM)
    _add_box(c_loc + back * (lens_len + flir_len / 2), (flir_w, flir_h, flir_len),
             CAM_COLOR, 0.9, rotation=back.to_track_quat("Z", "Y").to_euler())

    # The #56-027 clamp grips the objective: a collar around the bore plus the
    # pedestal block from the bore center to its base. Bolted to the vertical
    # bench board, so rotated a quarter turn about the lens axis: the pedestal
    # runs horizontally back to the board face instead of hanging down.
    clamp_center = c_loc + back * (CLAMP_DEPTH_MM * MM / 2 + 0.010)
    hang = Vector((0, -1, 0))
    width_dir = back.cross(hang)
    _add_barrel(clamp_center, back, CLAMP_OUTER_R_MM * MM, CLAMP_DEPTH_MM * MM,
                EDGE_COLOR, 0.20)
    _add_box(clamp_center + hang * (CLAMP_BORE_CENTER_MM * MM / 2),
             (CLAMP_WIDTH_MM * MM, CLAMP_DEPTH_MM * MM, CLAMP_BORE_CENTER_MM * MM),
             EDGE_COLOR, 0.20, rotation=_basis_euler(width_dir, back, hang))

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

    # Z-stage under the specimen: platform plate at the surface height, body,
    # base flange, and the micrometer poking out the -Y side. The simulated
    # surface plane itself stays at z=0 = the platform top (its z_offset_mm
    # calibration sweep is exactly this stage's travel).
    plat = ZSTAGE_PLATFORM_MM * MM
    height = ZSTAGE_HEIGHT_MM * MM
    base_t = ZSTAGE_BASE_MM * MM
    plate_t = 0.010
    top_z = -0.0005  # a hair under the (zero-thickness) surface plane
    _add_box(Vector((0, 0, top_z - plate_t / 2)), (plat, plat, plate_t),
             EDGE_COLOR, 0.35)
    _add_box(Vector((0, 0, top_z - height + base_t / 2)), (plat, plat, base_t),
             EDGE_COLOR, 0.35)
    _add_box(Vector((0, 0, top_z - height / 2)),
             (plat * 0.80, plat * 0.80, height - plate_t - base_t),
             EDGE_COLOR, 0.25)
    # Micrometer out the +X side (the -Y side would run into the bench board).
    knob_d, knob_reach, knob_h = (v * MM for v in ZSTAGE_KNOB_MM)
    knob_z = top_z - height + knob_h
    _add_barrel(Vector((plat / 2 + knob_reach - 0.012, 0, knob_z)),
                Vector((1, 0, 0)), knob_d / 2, 0.024, EDGE_COLOR, 0.6)
    _add_line(Vector((plat / 2, 0, knob_z)),
              Vector((plat / 2 + knob_reach - 0.024, 0, knob_z)),
              0.004, EDGE_COLOR, 0.4)

    # The bench: the vertical board stands landscape on the table (= the base
    # board's underside plane), its front face flush with the camera clamp's
    # base; the base board sits in front of it, back edge against that face,
    # carrying the stage and the two right-angle brackets that brace the pair.
    bench_top = top_z - height
    thick = BOARD_THICK_MM * MM
    base_sz = BASE_BOARD_MM * MM
    vb_w, vb_h = (v * MM for v in VBOARD_MM)
    cx = BENCH_X_CENTER_MM * MM
    face_y = VBOARD_FACE_Y_MM * MM
    table = bench_top - thick
    _add_box(Vector((cx, face_y + base_sz / 2, bench_top - thick / 2)),
             (base_sz, base_sz, thick), EDGE_COLOR, 0.15)
    _add_box(Vector((cx, face_y - thick / 2, table + vb_h / 2)),
             (vb_w, thick, vb_h), EDGE_COLOR, 0.15)
    hole_color = (0.05, 0.05, 0.06)
    edge = HOLE_EDGE_MM * MM
    pitch_in = HOLE_PITCH_MM
    _add_hole_grid(Vector((cx - base_sz / 2 + edge, face_y + edge,
                           bench_top + 0.0003)),
                   Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1)),
                   int(BASE_BOARD_MM // pitch_in), int(BASE_BOARD_MM // pitch_in),
                   hole_color)
    _add_hole_grid(Vector((cx - vb_w / 2 + edge, face_y + 0.0003,
                           table + edge)),
                   Vector((1, 0, 0)), Vector((0, 0, 1)), Vector((0, 1, 0)),
                   int(VBOARD_MM[0] // pitch_in), int(VBOARD_MM[1] // pitch_in),
                   hole_color)
    leg, br_h, br_t = (v * MM for v in BRACKET_MM)
    for bx in (cx - 0.250, cx + 0.250):
        _add_tri_prism(Vector((bx, face_y, bench_top)), Vector((0, 1, 0)),
                       Vector((0, 0, 1)), leg, br_h, br_t, EDGE_COLOR, 0.30)

    _add_label(f"PRO4500 projector\n({D_PROJ_MM:.0f} mm WD)",
               p_loc + Vector((0, 0, barrel_len + body_len + 0.03)), 0.018,
               overview)
    _add_label(f"FLIR + 0.09x GoldTL telecentric\n"
               f"({CAM_WORKING_DISTANCE_MM:.0f} mm WD, {THETA_DEG:.1f}° tilt)",
               c_loc + back * lens_len + Vector((0, 0, 0.055)), 0.018, overview)
    _add_label("Specimen on 125 mm Z-stage\n(fringe-lit, ±10 mm travel)",
               Vector((0.0, plat / 2 + 0.055, top_z - height + 0.042)), 0.018,
               overview)
    # Over the base board's open front corner: the (cropped) portrait board
    # offers no in-frame spot that a billboarded label wouldn't swing behind.
    _add_label('24"x24" + 48"x24" breadboards (1" grid)\n'
               "#11-158 angle bracket pair",
               Vector((cx - 0.18, 0.38, 0.0)), 0.016, overview)
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
