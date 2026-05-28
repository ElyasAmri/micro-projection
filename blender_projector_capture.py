from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.synthetic_surfaces import SURFACE_KINDS, height_field_depth_m


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description="Build and render a projector/telecentric capture scene.")
    parser.add_argument("--output-dir", required=True, help="Directory for rendered outputs.")
    parser.add_argument("--render-width", type=int, default=1028)
    parser.add_argument("--render-height", type=int, default=752)
    parser.add_argument("--fringe-width", type=int, default=1024)
    parser.add_argument("--fringe-height", type=int, default=768)
    parser.add_argument("--fringe-period-px", type=float, default=48.0)
    parser.add_argument("--projector-fov-deg", type=float, default=50.0)
    parser.add_argument("--surface-kind", default="rolling-mound", choices=SURFACE_KINDS)
    parser.add_argument("--mesh-columns", type=int, default=160)
    parser.add_argument("--mesh-rows", type=int, default=120)
    parser.add_argument("--cycles-samples", type=int, default=8)
    parser.add_argument(
        "--phase-deg",
        type=float,
        nargs="+",
        default=[0.0, 45.0, 90.0, 135.0, 180.0, 225.0, 270.0, 315.0],
    )
    return parser.parse_args(argv)


def _cm(value: float) -> float:
    return value / 100.0


def _look_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _create_height_field_patch(
    plane_center: Vector,
    patch_width: float,
    patch_height: float,
    *,
    surface_kind: str,
    columns: int,
    rows: int,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new("ForegroundObjectMesh")
    obj = bpy.data.objects.new("ForegroundObject", mesh)
    bpy.context.collection.objects.link(obj)

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    for row in range(rows + 1):
        v = (-0.5 + row / rows) * patch_height
        for column in range(columns + 1):
            u = (-0.5 + column / columns) * patch_width
            depth = height_field_depth_m(u, v, patch_width, patch_height, surface_kind=surface_kind)
            vertices.append((plane_center.x + u, plane_center.y - depth, plane_center.z + v))

    stride = columns + 1
    for row in range(rows):
        for column in range(columns):
            start = row * stride + column
            faces.append((start, start + 1, start + stride + 1, start + stride))

    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return obj


def _reset_scene() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 8
    scene.cycles.use_adaptive_sampling = False
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "16"
    scene.view_settings.view_transform = "Raw"
    scene.view_settings.look = "None"
    scene.display_settings.display_device = "sRGB"
    scene.world = bpy.data.worlds.new("World")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes["Background"]
    background.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    background.inputs["Strength"].default_value = 0.0
    return scene


def _create_projected_material(image: bpy.types.Image) -> bpy.types.Material:
    material = bpy.data.materials.new(name="ProjectedFringe")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    uv_node = nodes.new(type="ShaderNodeUVMap")
    uv_node.uv_map = "ProjectorUV"
    image_node = nodes.new(type="ShaderNodeTexImage")
    image_node.image = image
    image_node.extension = "CLIP"
    image_node.interpolation = "Linear"
    emission_node = nodes.new(type="ShaderNodeEmission")
    emission_node.inputs["Strength"].default_value = 1.0
    output_node = nodes.new(type="ShaderNodeOutputMaterial")

    uv_node.location = (-400, 0)
    image_node.location = (-180, 0)
    emission_node.location = (80, 0)
    output_node.location = (280, 0)

    links.new(uv_node.outputs["UV"], image_node.inputs["Vector"])
    links.new(image_node.outputs["Color"], emission_node.inputs["Color"])
    links.new(emission_node.outputs["Emission"], output_node.inputs["Surface"])
    return material


def _apply_projector_uv(
    obj: bpy.types.Object,
    projector: bpy.types.Object,
    fringe_width: int,
    fringe_height: int,
    material: bpy.types.Material,
) -> None:
    mesh = obj.data
    mesh.uv_layers.new(name="ProjectorUV")
    modifier = obj.modifiers.new(name="ProjectorUV", type="UV_PROJECT")
    modifier.uv_layer = "ProjectorUV"
    modifier.projector_count = 1
    modifier.projectors[0].object = projector
    modifier.aspect_x = float(fringe_width)
    modifier.aspect_y = float(fringe_height)
    modifier.scale_x = 1.0
    modifier.scale_y = 1.0
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


def _create_scene_geometry(
    projector: bpy.types.Object,
    capture_camera: bpy.types.Object,
    fringe_width: int,
    fringe_height: int,
    image: bpy.types.Image,
    *,
    surface_kind: str,
    mesh_columns: int,
    mesh_rows: int,
) -> tuple[bpy.types.Object, bpy.types.Object, dict[str, float | str]]:
    plane_center = Vector((_cm(0.0), _cm(10.005), _cm(8.1)))
    plane_width = _cm(20.0)
    plane_height = _cm(16.2)
    patch_width = _cm(9.0)
    patch_height = _cm(6.8)
    target = plane_center

    material = _create_projected_material(image)

    bpy.ops.mesh.primitive_plane_add(location=plane_center, rotation=(math.radians(90.0), 0.0, 0.0))
    plane = bpy.context.object
    plane.name = "ProjectionPlane"
    plane.scale = (plane_width * 0.5, plane_height * 0.5, 1.0)
    _apply_projector_uv(plane, projector, fringe_width, fringe_height, material)

    foreground = _create_height_field_patch(
        plane_center,
        patch_width,
        patch_height,
        surface_kind=surface_kind,
        columns=mesh_columns,
        rows=mesh_rows,
    )
    _apply_projector_uv(foreground, projector, fringe_width, fringe_height, material)

    bpy.ops.mesh.primitive_cube_add(location=projector.location, scale=(_cm(2.5), _cm(4.0), _cm(2.0)))
    projector_body = bpy.context.object
    projector_body.name = "ProjectorBody"
    projector_body.hide_render = True

    bpy.ops.mesh.primitive_cylinder_add(
        radius=_cm(1.0),
        depth=_cm(6.0),
        location=capture_camera.location,
        rotation=(0.0, math.radians(90.0), 0.0),
    )
    telecentric_body = bpy.context.object
    telecentric_body.name = "TelecentricHousing"
    telecentric_body.hide_render = True

    for helper in (projector_body, telecentric_body):
        helper.display_type = "WIRE"
        helper.hide_viewport = True

    _look_at(projector, target)
    _look_at(capture_camera, target)
    return plane, foreground, {
        "foreground_object_kind": "height_field_patch",
        "foreground_surface_kind": surface_kind,
        "foreground_patch_width_m": patch_width,
        "foreground_patch_height_m": patch_height,
        "foreground_mesh_columns": mesh_columns,
        "foreground_mesh_rows": mesh_rows,
    }


def _create_cameras(scene: bpy.types.Scene, projector_fov_deg: float) -> tuple[bpy.types.Object, bpy.types.Object]:
    plane_center = Vector((_cm(0.0), _cm(10.005), _cm(8.1)))

    projector_data = bpy.data.cameras.new("ProjectorCamera")
    projector_data.type = "PERSP"
    projector_data.angle = math.radians(projector_fov_deg)
    projector_data.clip_start = 0.01
    projector_data.clip_end = 10.0
    projector = bpy.data.objects.new("ProjectorCamera", projector_data)
    projector.location = Vector((_cm(-23.03598), _cm(-16.110981), _cm(8.1)))
    bpy.context.collection.objects.link(projector)
    _look_at(projector, plane_center)

    capture_data = bpy.data.cameras.new("CaptureCamera")
    capture_data.type = "ORTHO"
    capture_data.ortho_scale = _cm(22.0)
    capture_data.clip_start = 0.01
    capture_data.clip_end = 10.0
    capture_camera = bpy.data.objects.new("CaptureCamera", capture_data)
    capture_camera.location = Vector((_cm(23.035976), _cm(-16.110981), _cm(8.1)))
    bpy.context.collection.objects.link(capture_camera)
    _look_at(capture_camera, plane_center)

    scene.camera = capture_camera
    return projector, capture_camera


def _update_fringe_image(
    image: bpy.types.Image,
    width: int,
    height: int,
    *,
    period_px: float,
    phase_deg: float,
) -> None:
    phase = math.radians(phase_deg)
    factor = (2.0 * math.pi) / period_px
    pixels: list[float] = []
    for y in range(height):
        for x in range(width):
            wave = math.sin(factor * x + phase)
            value = max(0.0, min(1.0, 0.5 + 0.5 * wave))
            pixels.extend((value, value, value, 1.0))
    image.pixels = pixels
    image.update()


def _camera_frame_bounds(
    camera_obj: bpy.types.Object,
    scene: bpy.types.Scene,
) -> tuple[float, float, float, float, float]:
    frame = camera_obj.data.view_frame(scene=scene)
    xs = [corner.x for corner in frame]
    ys = [corner.y for corner in frame]
    z = frame[0].z
    return (min(xs), max(xs), min(ys), max(ys), z)


def _matrix_to_rows(matrix: bpy.types.Matrix) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix]


def _camera_basis(camera_obj: bpy.types.Object) -> tuple[Vector, Vector, Vector, Vector]:
    matrix = camera_obj.matrix_world.to_3x3()
    right = (matrix @ Vector((1.0, 0.0, 0.0))).normalized()
    up = (matrix @ Vector((0.0, 1.0, 0.0))).normalized()
    forward = (matrix @ Vector((0.0, 0.0, -1.0))).normalized()
    return (camera_obj.matrix_world.translation.copy(), right, up, forward)


def _height_field_intersection(
    ray_origin: Vector,
    ray_direction: Vector,
    plane_center: Vector,
    plane_right: Vector,
    plane_up: Vector,
    plane_normal: Vector,
    patch_width: float,
    patch_height: float,
    surface_kind: str,
) -> tuple[Vector, float, bool] | None:
    denominator = float(ray_direction.dot(plane_normal))
    if abs(denominator) <= 1e-12:
        return None
    plane_t = float((plane_center - ray_origin).dot(plane_normal) / denominator)
    if plane_t <= 1e-9:
        return None

    def signed_height_error(distance: float) -> tuple[float, float]:
        point = ray_origin + ray_direction * distance
        offset = point - plane_center
        u = float(offset.dot(plane_right))
        v = float(offset.dot(plane_up))
        if abs(u) <= patch_width * 0.5 and abs(v) <= patch_height * 0.5:
            depth = height_field_depth_m(u, v, patch_width, patch_height, surface_kind=surface_kind)
        else:
            depth = 0.0
        height = float(offset.dot(plane_normal))
        return height - depth, depth

    t_hi = plane_t
    f_hi, depth_hi = signed_height_error(t_hi)
    max_depth_m = 0.03
    t_lo = max(0.0, plane_t - ((max_depth_m + 0.002) / abs(denominator)))
    f_lo, _ = signed_height_error(t_lo)
    expand_count = 0
    while f_lo <= 0.0 and t_lo > 0.0 and expand_count < 8:
        t_lo = max(0.0, t_lo - ((max_depth_m + 0.002) / abs(denominator)))
        f_lo, _ = signed_height_error(t_lo)
        expand_count += 1
    if f_hi > 0.0:
        return None
    if depth_hi <= 1e-9:
        return ray_origin + ray_direction * plane_t, 0.0, False
    if f_lo <= 0.0:
        return None

    for _ in range(48):
        t_mid = 0.5 * (t_lo + t_hi)
        f_mid, _ = signed_height_error(t_mid)
        if f_mid > 0.0:
            t_lo = t_mid
        else:
            t_hi = t_mid
    point = ray_origin + ray_direction * t_hi
    offset = point - plane_center
    depth = height_field_depth_m(
        float(offset.dot(plane_right)),
        float(offset.dot(plane_up)),
        patch_width,
        patch_height,
        surface_kind=surface_kind,
    )
    return point, depth, True


def _truth_height_maps(
    camera_obj: bpy.types.Object,
    plane: bpy.types.Object,
    foreground_metadata: dict[str, float | str],
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    plane_center = plane.matrix_world.translation.copy()
    plane_normal = (plane.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    plane_right = (plane.matrix_world.to_3x3() @ Vector((1.0, 0.0, 0.0))).normalized()
    plane_up = (plane.matrix_world.to_3x3() @ Vector((0.0, 1.0, 0.0))).normalized()
    min_x, max_x, min_y, max_y, _ = _camera_frame_bounds(camera_obj, bpy.context.scene)
    _, _, _, forward = _camera_basis(camera_obj)
    patch_width = float(foreground_metadata["foreground_patch_width_m"])
    patch_height = float(foreground_metadata["foreground_patch_height_m"])
    surface_kind = str(foreground_metadata.get("foreground_surface_kind", "dome-ridge"))

    truth = np.full((height, width), np.nan, dtype=np.float64)
    valid_mask = np.zeros((height, width), dtype=bool)
    object_mask = np.zeros((height, width), dtype=bool)
    for y in range(height):
        ny = 1.0 - ((y + 0.5) / height)
        local_y = min_y + (max_y - min_y) * ny
        for x in range(width):
            nx = (x + 0.5) / width
            local_x = min_x + (max_x - min_x) * nx
            local_point = Vector((local_x, local_y, 0.0))
            ray_origin = camera_obj.matrix_world @ local_point
            intersection = _height_field_intersection(
                ray_origin,
                forward,
                plane_center,
                plane_right,
                plane_up,
                plane_normal,
                patch_width,
                patch_height,
                surface_kind,
            )
            if intersection is None:
                continue
            _, depth, is_object = intersection
            truth[y, x] = depth
            object_mask[y, x] = is_object
            valid_mask[y, x] = True
    return truth, valid_mask, object_mask


def _render_phase_sequence(
    scene: bpy.types.Scene,
    image: bpy.types.Image,
    output_dir: Path,
    *,
    phases_deg: list[float],
    fringe_width: int,
    fringe_height: int,
    fringe_period_px: float,
    prefix: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for phase_deg in phases_deg:
        _update_fringe_image(
            image,
            fringe_width,
            fringe_height,
            period_px=fringe_period_px,
            phase_deg=phase_deg,
        )
        fringe_path = output_dir.parent / "fringes" / f"fringe_phase_{int(round(phase_deg)):03d}.png"
        fringe_path.parent.mkdir(parents=True, exist_ok=True)
        image.filepath_raw = str(fringe_path)
        image.file_format = "PNG"
        image.save()

        render_path = output_dir / f"{prefix}_phase_{int(round(phase_deg)):03d}.png"
        scene.render.filepath = str(render_path)
        bpy.ops.render.render(write_still=True)
        print(f"Rendered capture to {render_path}")


def main() -> None:
    args = _parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scene = _reset_scene()
    scene.render.resolution_x = args.render_width
    scene.render.resolution_y = args.render_height
    scene.render.resolution_percentage = 100
    scene.cycles.samples = args.cycles_samples

    fringe_image = bpy.data.images.new(
        "ProjectedFringe",
        width=args.fringe_width,
        height=args.fringe_height,
        alpha=True,
        float_buffer=True,
    )
    fringe_image.colorspace_settings.name = "Non-Color"

    projector, capture_camera = _create_cameras(scene, args.projector_fov_deg)
    plane, foreground, foreground_metadata = _create_scene_geometry(
        projector,
        capture_camera,
        args.fringe_width,
        args.fringe_height,
        fringe_image,
        surface_kind=args.surface_kind,
        mesh_columns=args.mesh_columns,
        mesh_rows=args.mesh_rows,
    )

    foreground.hide_render = True
    _render_phase_sequence(
        scene,
        fringe_image,
        output_dir / "reference",
        phases_deg=list(args.phase_deg),
        fringe_width=args.fringe_width,
        fringe_height=args.fringe_height,
        fringe_period_px=args.fringe_period_px,
        prefix="reference",
    )

    foreground.hide_render = False
    _render_phase_sequence(
        scene,
        fringe_image,
        output_dir / "object",
        phases_deg=list(args.phase_deg),
        fringe_width=args.fringe_width,
        fringe_height=args.fringe_height,
        fringe_period_px=args.fringe_period_px,
        prefix="object",
    )

    truth, valid_mask, object_mask = _truth_height_maps(
        capture_camera,
        plane,
        foreground_metadata,
        args.render_width,
        args.render_height,
    )
    np.savez_compressed(
        output_dir / "ground_truth.npz",
        truth=truth,
        valid_mask=valid_mask,
        object_mask=object_mask,
    )

    metadata = {
        "render_width": args.render_width,
        "render_height": args.render_height,
        "fringe_width": args.fringe_width,
        "fringe_height": args.fringe_height,
        "fringe_period_px": args.fringe_period_px,
        "projector_fov_deg": args.projector_fov_deg,
        "cycles_samples": args.cycles_samples,
        "phases_deg": list(args.phase_deg),
        "capture_camera_ortho_scale": capture_camera.data.ortho_scale,
        "capture_camera_location_m": list(capture_camera.location),
        "capture_camera_matrix_world": _matrix_to_rows(capture_camera.matrix_world),
        "capture_camera_frame_bounds_local": list(_camera_frame_bounds(capture_camera, scene)),
        "projector_location_m": list(projector.location),
        "projector_matrix_world": _matrix_to_rows(projector.matrix_world),
        "projector_frame_bounds_local": list(_camera_frame_bounds(projector, scene)),
        "plane_center_m": list(plane.location),
        "plane_matrix_world": _matrix_to_rows(plane.matrix_world),
        **foreground_metadata,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    blend_path = output_dir / "telecentric_projector_scene.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(f"Saved Blender scene to {blend_path}")


if __name__ == "__main__":
    main()
