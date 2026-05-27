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
    parser.add_argument("--surface-kind", default="ring-crater")
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

    projector, capture_camera = _create_cameras(scene, projector_fov_deg=args.projector_fov_deg)
    _create_scene_geometry(
        projector, capture_camera, args.fringe_width, args.fringe_height, fringe_image,
        surface_kind=args.surface_kind, mesh_columns=args.mesh_columns, mesh_rows=args.mesh_rows,
    )
    # Show the fringe only on the projector footprint; the rest of the plane is a
    # visible diffuse surface instead of pure (invisible) emission.
    _add_plane_base(bpy.data.materials["ProjectedFringe"], fringe_image, base_color=(0.32, 0.33, 0.36))

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
