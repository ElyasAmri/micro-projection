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
    _update_fringe_image,
)


def _parse_args() -> argparse.Namespace:
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser(description="Render a turntable of the projection setup.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--surface-kind", default="ring-crater")
    parser.add_argument("--fringe-period-px", type=float, default=48.0)
    parser.add_argument("--fringe-width", type=int, default=1024)
    parser.add_argument("--fringe-height", type=int, default=768)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--fps", type=int, default=30)
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


def _reveal(obj, material) -> None:
    obj.hide_render = False
    obj.hide_viewport = False
    obj.display_type = "SOLID"
    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)


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

    projector, capture_camera = _create_cameras(scene, projector_fov_deg=50.0)
    _create_scene_geometry(
        projector, capture_camera, args.fringe_width, args.fringe_height, fringe_image,
        surface_kind=args.surface_kind, mesh_columns=args.mesh_columns, mesh_rows=args.mesh_rows,
    )
    _update_fringe_image(fringe_image, args.fringe_width, args.fringe_height,
                         period_px=args.fringe_period_px, phase_deg=0.0)

    # Reveal and colour-code the device bodies (projector = orange, camera = blue).
    _reveal(bpy.data.objects["ProjectorBody"], _flat_material("ProjMat", (0.95, 0.55, 0.10)))
    _reveal(bpy.data.objects["TelecentricHousing"], _flat_material("CamMat", (0.12, 0.55, 0.85)))

    # Ground plane to ground the rig and catch device shadows.
    bpy.ops.mesh.primitive_plane_add(size=4.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.object
    ground.name = "Ground"
    ground.data.materials.append(_flat_material("GroundMat", (0.05, 0.05, 0.06)))

    # Lighting for the device bodies (the fringe surfaces are pure emission, unaffected).
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = 3.0
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(55.0), math.radians(8.0), math.radians(-50.0))

    # Orbit rig: empty at the scene centre, perspective camera parented to it.
    centre = Vector((_cm(0.0), _cm(-3.0), _cm(8.1)))
    empty = bpy.data.objects.new("OrbitPivot", None)
    bpy.context.collection.objects.link(empty)
    empty.location = centre

    cam_data = bpy.data.cameras.new("OrbitCamera")
    cam_data.type = "PERSP"
    cam_data.angle = math.radians(50.0)
    cam = bpy.data.objects.new("OrbitCamera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = centre + Vector((0.0, _cm(-92.0), _cm(58.0)))
    _look_at(cam, centre)
    cam.parent = empty
    cam.matrix_parent_inverse = empty.matrix_world.inverted()
    scene.camera = cam

    # Animate a full turntable loop (frame frames+1 == frame 1 for seamless looping).
    # Linear interpolation gives a constant orbit rate; set it as the keyframe
    # default so we avoid the version-specific action.fcurves API.
    bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
    scene.frame_start = 1
    scene.frame_end = args.frames
    empty.rotation_euler = (0.0, 0.0, 0.0)
    empty.keyframe_insert(data_path="rotation_euler", index=2, frame=1)
    empty.rotation_euler = (0.0, 0.0, 2.0 * math.pi)
    empty.keyframe_insert(data_path="rotation_euler", index=2, frame=args.frames + 1)

    # This Blender build has no FFMPEG muxer, so render a PNG sequence; the mp4 is
    # assembled afterwards with the system ffmpeg.
    scene.render.fps = args.fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.filepath = str(out_dir / "frame_")
    bpy.ops.render.render(animation=True)

    produced = sorted(out_dir.glob("frame_*.png"))
    print(f"DONE rendered {len(produced)} frames to {out_dir}")


if __name__ == "__main__":
    main()
