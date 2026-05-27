"""Render a turntable video of the fringe-projection setup in Blender.

Reuses the capture scene builder (projector + fringe-lit surface + telecentric
camera), reveals and colour-codes the device bodies, adds lighting, and orbits a
perspective camera around the rig, rendering an mp4.

Run:  blender -b -P blendersim/render_setup_overview.py -- --output-dir out/setup_overview
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from blendersim.blender_projector_capture import (
    _cm,
    _create_cameras,
    _create_scene_geometry,
    _look_at,
    _reset_scene,
)


def _set_fringe_fast(image, width: int, height: int, *, period_px: float, phase_deg: float) -> None:
    """Vectorized fringe write (the surface only varies along x)."""
    x = np.arange(width, dtype=np.float32)
    row = np.clip(0.5 + 0.5 * np.sin((2.0 * np.pi / period_px) * x + np.radians(phase_deg)), 0.0, 1.0)
    rgba = np.empty((height, width, 4), dtype=np.float32)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = row[None, :]
    rgba[..., 3] = 1.0
    image.pixels.foreach_set(rgba.ravel())
    image.update()


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description="Render a turntable of the projection setup.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--surface-kind", default="rolling-mound")
    parser.add_argument("--fringe-period-px", type=float, default=48.0)
    parser.add_argument("--fringe-width", type=int, default=1024)
    parser.add_argument("--fringe-height", type=int, default=768)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--frames", type=int, default=48, help="Phase-sweep steps over one period.")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--hero-azimuth-deg", type=float, default=22.0, help="Static 3/4 view angle.")
    parser.add_argument("--projector-fov-deg", type=float, default=22.0,
                        help="Projector throw; narrower than the capture FOV so the fringe "
                             "lights only a portion of the plane.")
    parser.add_argument("--plane-scale", type=float, default=1.8,
                        help="Scale the projection plane width/height (the projector footprint "
                             "stays fixed, so the fringe covers a smaller fraction).")
    parser.add_argument("--samples", type=int, default=24)
    parser.add_argument("--mesh-columns", type=int, default=160)
    parser.add_argument("--mesh-rows", type=int, default=120)
    return parser.parse_args(argv)


def _flat_material(name: str, color: tuple[float, float, float], *, emission: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emission > 0.0:
        shader = nt.nodes.new("ShaderNodeEmission")
        shader.inputs["Color"].default_value = (*color, 1.0)
        shader.inputs["Strength"].default_value = emission
        nt.links.new(shader.outputs["Emission"], out.inputs["Surface"])
    else:
        shader = nt.nodes.new("ShaderNodeBsdfPrincipled")
        shader.inputs["Base Color"].default_value = (*color, 1.0)
        if "Roughness" in shader.inputs:
            shader.inputs["Roughness"].default_value = 0.5
        nt.links.new(shader.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _add_plane_base(material, image, base_color: tuple[float, float, float]) -> None:
    """Rebuild the projected-fringe material so the projector footprint shows the
    fringe (emission) while the rest of the plane is a visible diffuse surface.

    The fringe image uses CLIP extension, so its alpha is 1 inside the projected
    footprint and 0 outside -- used here as the mix factor.
    """
    nt = material.node_tree
    nt.nodes.clear()
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "ProjectorUV"
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = image
    img.extension = "CLIP"
    img.interpolation = "Linear"
    emis = nt.nodes.new("ShaderNodeEmission")
    emis.inputs["Strength"].default_value = 1.0
    diff = nt.nodes.new("ShaderNodeBsdfDiffuse")
    diff.inputs["Color"].default_value = (*base_color, 1.0)
    mix = nt.nodes.new("ShaderNodeMixShader")
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(uv.outputs["UV"], img.inputs["Vector"])
    nt.links.new(img.outputs["Color"], emis.inputs["Color"])
    nt.links.new(img.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(diff.outputs["BSDF"], mix.inputs[1])
    nt.links.new(emis.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])


def _projector_footprint_corners(plane_obj):
    """Exact projector footprint corners on the plane.

    UV_PROJECT writes the projector's frame into the plane's ProjectorUV layer, so
    the plane->UV map is the projector homography. Fit it from the plane's four
    corners and invert it to find the world points where UV hits the unit square --
    i.e. the edge of the projected fringe. Robust to FOV/sensor-fit/aspect details.
    """
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_obj = plane_obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    try:
        mw = plane_obj.matrix_world.copy()
        center = mw.translation.copy()
        right = (mw.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
        up = (mw.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
        uv_layer = mesh.uv_layers["ProjectorUV"]
        st: list[tuple[float, float]] = []
        uv: list[tuple[float, float]] = []
        seen: set[int] = set()
        for loop in mesh.loops:
            if loop.vertex_index in seen:
                continue
            seen.add(loop.vertex_index)
            d = (mw @ mesh.vertices[loop.vertex_index].co) - center
            st.append((d.dot(right), d.dot(up)))
            corner_uv = uv_layer.data[loop.index].uv
            uv.append((corner_uv.x, corner_uv.y))
            if len(seen) == 4:
                break
    finally:
        eval_obj.to_mesh_clear()

    rows = []
    for (x, y), (X, Y) in zip(uv, st):  # homography uv -> st (plane coords)
        rows.append([-x, -y, -1, 0, 0, 0, x * X, y * X, X])
        rows.append([0, 0, 0, -x, -y, -1, x * Y, y * Y, Y])
    homography = np.linalg.svd(np.array(rows, dtype=np.float64))[2][-1].reshape(3, 3)
    corners = []
    for u, v in ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)):
        p = homography @ np.array([u, v, 1.0])
        corners.append(center + right * float(p[0] / p[2]) + up * float(p[1] / p[2]))
    return corners


def _diffuse_material(name, color):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfDiffuse")
    bsdf.inputs["Color"].default_value = (*color, 1.0)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _add_fringe_projector_light(projector, fringe_image, *, fov_deg, aspect_w, aspect_h, energy):
    """A real spot light that projects the fringe image (a gobo), so the object
    casts a shadow that masks the fringe off the plane behind it.

    The light direction (Texture Coordinate -> Normal, in light space) is
    perspective-divided and scaled to the projector FOV so the image's unit square
    maps to the projector frustum.
    """
    data = bpy.data.lights.new("FringeProjector", type="SPOT")
    data.energy = energy
    data.spot_size = math.radians(140.0)
    data.spot_blend = 0.0
    data.shadow_soft_size = 0.0
    data.use_nodes = True
    light = bpy.data.objects.new("FringeProjector", data)
    bpy.context.collection.objects.link(light)
    light.matrix_world = projector.matrix_world.copy()

    nt = data.node_tree
    nt.nodes.clear()
    texco = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(texco.outputs["Normal"], sep.inputs[0])
    div_x = nt.nodes.new("ShaderNodeMath"); div_x.operation = "DIVIDE"
    div_y = nt.nodes.new("ShaderNodeMath"); div_y.operation = "DIVIDE"
    nt.links.new(sep.outputs["X"], div_x.inputs[0]); nt.links.new(sep.outputs["Z"], div_x.inputs[1])
    nt.links.new(sep.outputs["Y"], div_y.inputs[0]); nt.links.new(sep.outputs["Z"], div_y.inputs[1])
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(div_x.outputs[0], comb.inputs["X"])
    nt.links.new(div_y.outputs[0], comb.inputs["Y"])
    mapping = nt.nodes.new("ShaderNodeMapping")
    half = math.tan(math.radians(fov_deg / 2.0))
    scale_x = 1.0 / (2.0 * half)
    mapping.inputs["Scale"].default_value = (scale_x, scale_x * (aspect_w / aspect_h), 1.0)
    mapping.inputs["Location"].default_value = (0.5, 0.5, 0.0)
    nt.links.new(comb.outputs["Vector"], mapping.inputs["Vector"])
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = fringe_image
    img.extension = "CLIP"
    nt.links.new(mapping.outputs["Vector"], img.inputs["Vector"])
    emis = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(img.outputs["Color"], emis.inputs["Color"])
    out = nt.nodes.new("ShaderNodeOutputLight")
    nt.links.new(emis.outputs["Emission"], out.inputs["Surface"])
    return light


def _make_frustum_curve(name, cam_obj, scene, *, far_d, persp, color, near_d=0.0,
                        plane_point=None, plane_normal=None, frame_res=None, far_corners=None):
    """Build a camera/projector frustum as glowing tube edges, clipped to a plane.

    Perspective -> a cone from the lens apex; each corner ray is intersected with
    the plane so the far quad is the actual footprint.
    Orthographic -> a parallel tube from the lens; the parallel corner rays are
    likewise intersected with the plane.

    view_frame() uses the scene render aspect, so frame_res temporarily sets it to
    the device's own frame (fringe image / capture sensor) for a matching footprint.
    """
    saved_res = (scene.render.resolution_x, scene.render.resolution_y)
    if frame_res is not None:
        scene.render.resolution_x, scene.render.resolution_y = frame_res
    frame = cam_obj.data.view_frame(scene=scene)
    scene.render.resolution_x, scene.render.resolution_y = saved_res

    mw = cam_obj.matrix_world
    rot = mw.to_3x3()
    verts: list[list[float]] = []
    edges: list[tuple[int, int]] = []
    if persp:
        apex = mw.translation
        verts.append(list(apex))  # 0 = apex
        if far_corners is not None:
            corners = list(far_corners)
        else:
            corners = []
            for c in frame:
                direction = rot @ c  # world ray from the apex through this corner
                if plane_point is not None:
                    t = (plane_point - apex).dot(plane_normal) / direction.dot(plane_normal)
                    corners.append(apex + direction * t)
                else:
                    corners.append(mw @ (c * (far_d / -c.z)))  # view_frame depth != -1
        for far in corners:
            verts.append(list(far))  # 1..4 = far corners (on the plane)
        edges += [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 3), (3, 4), (4, 1)]
    else:
        forward = (rot @ Vector((0.0, 0.0, -1.0))).normalized()
        near = [mw @ Vector((c.x, c.y, -near_d)) for c in frame]
        if plane_point is not None:
            far = [p + forward * ((plane_point - p).dot(plane_normal) / forward.dot(plane_normal))
                   for p in near]
        else:
            far = [mw @ Vector((c.x, c.y, -far_d)) for c in frame]
        verts = [list(p) for p in near] + [list(p) for p in far]
        edges += [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4),
                  (0, 4), (1, 5), (2, 6), (3, 7)]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, edges, [])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.convert(target="CURVE")
    obj.data.bevel_depth = _cm(0.08)  # thin wire (was 0.2)
    obj.data.bevel_resolution = 1
    obj.select_set(False)
    # Matte, non-emissive, zero-reflection guide so the tube reads as a flat
    # colour rather than a glowing/shiny neon edge.
    mat = bpy.data.materials.new(name + "Mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 1.0
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    for spec_name in ("Specular IOR Level", "Specular"):  # name changed across versions
        if spec_name in bsdf.inputs:
            bsdf.inputs[spec_name].default_value = 0.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    obj.data.materials.append(mat)
    obj.visible_shadow = False  # frustum guides should not cast shadows
    return obj


def _try_enable_gpu(scene) -> str:
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            prefs.get_devices()
            gpus = [d for d in prefs.devices if d.type != "CPU"]
            if gpus:
                for d in prefs.devices:
                    d.use = d.type != "CPU"
                scene.cycles.device = "GPU"
                return f"GPU ({backend}): {[d.name for d in gpus]}"
    except Exception as exc:  # noqa: BLE001
        print(f"GPU setup failed: {exc}")
    scene.cycles.device = "CPU"
    return "CPU"


def main() -> None:
    args = _parse_args()
    # Resolve to absolute: Blender resolves bare relative render paths against the
    # drive root, not the CWD, which would scatter frames to C:\out\...
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    scene = _reset_scene()
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.view_settings.view_transform = "Standard"
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.03, 0.035, 0.05, 1.0)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    print("render device:", _try_enable_gpu(scene))

    fringe_image = bpy.data.images.new(
        "ProjectedFringe", width=args.fringe_width, height=args.fringe_height, alpha=True, float_buffer=True
    )
    fringe_image.colorspace_settings.name = "Non-Color"

    projector, capture_camera = _create_cameras(scene, projector_fov_deg=args.projector_fov_deg)
    _create_scene_geometry(
        projector, capture_camera, args.fringe_width, args.fringe_height, fringe_image,
        surface_kind=args.surface_kind, mesh_columns=args.mesh_columns, mesh_rows=args.mesh_rows,
    )
    # Enlarge the backdrop plane (projector footprint is fixed, so the fringe ends
    # up covering a smaller fraction of it).
    plane_obj = bpy.data.objects["ProjectionPlane"]
    plane_obj.scale.x *= args.plane_scale
    plane_obj.scale.y *= args.plane_scale

    # Plane and object are plain diffuse surfaces; the fringe comes from a real
    # projector light (below) so the object casts a shadow that masks the plane.
    surface_mat = _diffuse_material("SurfaceMat", (0.82, 0.82, 0.85))
    for obj_name in ("ProjectionPlane", "ForegroundObject"):
        mesh = bpy.data.objects[obj_name].data
        mesh.materials.clear()
        mesh.materials.append(surface_mat)

    # Real fringe projector: spot light projecting the fringe gobo from the
    # projector position, so the object shadows the fringe off the plane.
    _add_fringe_projector_light(projector, fringe_image, fov_deg=args.projector_fov_deg,
                                aspect_w=args.fringe_width, aspect_h=args.fringe_height, energy=40.0)

    # Represent the devices as their optical frustums (projector = orange cone,
    # telecentric camera = blue parallel tube) rather than solid bodies.
    plane_point = plane_obj.matrix_world.translation.copy()
    plane_normal = (plane_obj.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    # Projector cone: far quad = the exact projected fringe footprint (from the
    # ProjectorUV homography). Camera tube: view frustum clipped to the plane.
    footprint = _projector_footprint_corners(plane_obj)

    # Size the telecentric field to the projected region (+ small margin) rather
    # than hardcoding it: project the footprint corners into the capture camera's
    # image frame and set ortho_scale so the parallel tube just exceeds the fringe.
    # Derived from the actual footprint, so it stays correct if FOV/plane change.
    capture_frame_res = (1028, 752)
    cam_mw = capture_camera.matrix_world
    cam_loc = cam_mw.translation
    cam_rot = cam_mw.to_3x3()
    cam_right = (cam_rot @ Vector((1.0, 0.0, 0.0))).normalized()
    cam_up = (cam_rot @ Vector((0.0, 1.0, 0.0))).normalized()
    frame_aspect = capture_frame_res[0] / capture_frame_res[1]  # ortho_scale spans width
    half_w = max(abs((c - cam_loc).dot(cam_right)) for c in footprint)
    half_h = max(abs((c - cam_loc).dot(cam_up)) for c in footprint)
    field_margin = 1.12  # tube covers ~25% more area than the projected region
    capture_camera.data.ortho_scale = field_margin * max(2.0 * half_w, 2.0 * half_h * frame_aspect)
    print(f"capture ortho_scale set to {capture_camera.data.ortho_scale * 100:.2f} cm "
          f"(footprint {2 * half_w * 100:.2f} x {2 * half_h * 100:.2f} cm in camera frame)")

    _make_frustum_curve("ProjectorFrustum", projector, scene, far_d=0.0, persp=True,
                        color=(0.95, 0.55, 0.10), far_corners=footprint)
    _make_frustum_curve("CameraFrustum", capture_camera, scene, far_d=0.0, persp=False,
                        color=(0.12, 0.55, 0.85), plane_point=plane_point, plane_normal=plane_normal,
                        frame_res=capture_frame_res)

    # Ground plane to ground the rig and catch device shadows.
    bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(_flat_material("GroundMat", (0.05, 0.05, 0.06)))

    # Dim fill so the ground/surfaces are not pure black; kept low so the projected
    # fringe stays the dominant light and its shadow/masking reads clearly.
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 0.6
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(55.0), math.radians(8.0), math.radians(-50.0))

    # Static 3/4 hero view (the rig is single-sided, so no orbit): perspective
    # camera parented to a pivot that is rotated to a fixed viewing angle.
    centre = Vector((_cm(0.0), _cm(-3.0), _cm(8.1)))
    pivot = bpy.data.objects.new("CameraPivot", None)
    bpy.context.collection.objects.link(pivot)
    pivot.location = centre

    cam_data = bpy.data.cameras.new("HeroCamera")
    cam_data.type = "PERSP"
    cam_data.angle = math.radians(50.0)
    cam = bpy.data.objects.new("HeroCamera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = centre + Vector((0.0, _cm(-92.0), _cm(58.0)))
    _look_at(cam, centre)
    cam.parent = pivot
    cam.matrix_parent_inverse = pivot.matrix_world.inverted()
    pivot.rotation_euler = (0.0, 0.0, math.radians(args.hero_azimuth_deg))
    scene.camera = cam

    # This Blender build has no FFMPEG muxer, so render a PNG sequence (assembled to
    # mp4 by the system ffmpeg). The camera is fixed; the fringe sweeps one full
    # period over the frames so the projection looks live and loops seamlessly.
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    for index in range(args.frames):
        phase_deg = 360.0 * index / args.frames
        _set_fringe_fast(fringe_image, args.fringe_width, args.fringe_height,
                         period_px=args.fringe_period_px, phase_deg=phase_deg)
        scene.render.filepath = str(out_dir / f"frame_{index + 1:04d}")
        bpy.ops.render.render(write_still=True)

    produced = sorted(out_dir.glob("frame_*.png"))
    print(f"DONE rendered {len(produced)} frames to {out_dir}")


if __name__ == "__main__":
    main()
