"""Shared rig-building blocks for the PRO4500 + telecentric camera model.

Numbers are the results derived in report/math.tex: the camera's fixed
telecentric FOV, the PRO4500 working distance that matches its height, and
the camera tilt angle that matches its width.

The camera is a Blender orthographic camera (parallel rays == telecentric).

The projector is a plain Spot light for illumination; the fringe pattern
itself is painted onto the *surface's material* as a procedural Wave
Texture, gated by a rectangular mask -- both driven by the shading point's
position in the projector's local space (an Object-coordinate perspective
divide, the standard "gobo" computation). This lives on the material rather
than the light because Cycles light node trees (Spot and Area, via TexCoord
Object/Normal/Generated, and Geometry Incoming) do not vary spatially in
this Blender build -- verified directly, every attempt rendered a flat,
direction-independent color. Material node trees do support this correctly.

The mask (from the *unshifted* u, v) and the fringe pattern (from u offset
by the phase-shift step) are computed separately and multiplied together,
so the illuminated rectangle stays fixed in place while only the internal
striping shifts across an 8-step phase sequence -- matching what a real
projector does.

Also verified directly in this Blender build: a light's `.energy` (Watts)
does not drive its auto-generated node tree's Emission Strength -- the two
are disconnected -- so brightness is set on that Emission node itself.
"""
from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

import surfaces
from geometry_constants import (
    CAM_PIXELS,
    CAM_WORKING_DISTANCE_MM,
    D_PROJ_MM,
    H0_MM,
    MM,
    SPOT_CONE_DEG,
    SURFACE_GRID_SUBDIVISIONS,
    SURFACE_SIZE_M,
    THETA_DEG,
    THROW_RATIO_H,
    THROW_RATIO_W,
    W0_MM,
    W_PROJ_MM,
)


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    bpy.context.scene.world = world
    bpy.context.scene.view_settings.view_transform = "Standard"


def look_at(obj, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def add_projector():
    """Plain spot light: illumination only. The fringe pattern itself is
    painted onto the surface's material in add_surface(), see module docstring."""
    light_data = bpy.data.lights.new("Pro4500", type="SPOT")
    light_data.spot_size = math.radians(SPOT_CONE_DEG)
    light_data.spot_blend = 0.2
    light_data.node_tree.nodes["Emission"].inputs["Strength"].default_value = 0.08

    light_obj = bpy.data.objects.new("Projector_PRO4500", light_data)
    bpy.context.collection.objects.link(light_obj)
    light_obj.location = Vector((0.0, 0.0, D_PROJ_MM * MM))
    look_at(light_obj, Vector((0.0, 0.0, 0.0)))
    return light_obj


def _mask_node(nt, value_socket):
    """1.0 where 0 < value < 1, else 0.0."""
    ge0 = nt.nodes.new("ShaderNodeMath")
    ge0.operation = "GREATER_THAN"
    ge0.inputs[1].default_value = 0.0
    nt.links.new(value_socket, ge0.inputs[0])

    le1 = nt.nodes.new("ShaderNodeMath")
    le1.operation = "LESS_THAN"
    le1.inputs[1].default_value = 1.0
    nt.links.new(value_socket, le1.inputs[0])

    both = nt.nodes.new("ShaderNodeMath")
    both.operation = "MULTIPLY"
    nt.links.new(ge0.outputs[0], both.inputs[0])
    nt.links.new(le1.outputs[0], both.inputs[1])
    return both.outputs[0]


def add_surface(projector_obj, n_periods: float = 8.0, height_fn=surfaces.bump_height_mm):
    """Add the surface, with the projected fringe pattern computed live in
    its material. Returns (surface_object, phase_fraction_node) -- update
    phase_fraction_node.outputs[0].default_value (a fraction of one cycle,
    0..1) between renders to step through a phase-shifting sequence without
    rebuilding the scene.

    height_fn(x_mm, y_mm) -> z_mm deforms the surface with a known
    ground-truth shape (see surfaces.py); pass None for a flat plane. The
    projected pattern's material graph doesn't need to know about this --
    it already reads the real shading-point position, so it distorts over
    the bump exactly as a real projector's fringes would.
    """
    if height_fn is None:
        bpy.ops.mesh.primitive_plane_add(size=SURFACE_SIZE_M, location=(0.0, 0.0, 0.0))
    else:
        bpy.ops.mesh.primitive_grid_add(
            x_subdivisions=SURFACE_GRID_SUBDIVISIONS,
            y_subdivisions=SURFACE_GRID_SUBDIVISIONS,
            size=SURFACE_SIZE_M,
            location=(0.0, 0.0, 0.0),
        )
    surface = bpy.context.active_object
    surface.name = "Surface"

    if height_fn is not None:
        mesh = surface.data
        for vert in mesh.vertices:
            vert.co.z = float(height_fn(vert.co.x / MM, vert.co.y / MM)) * MM
        mesh.update()
        bpy.ops.object.shade_smooth()

    mat = bpy.data.materials.new("SurfaceMaterial")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.6
    # A specular highlight would otherwise appear as a bright, texture-
    # independent "hotspot" on top of the projected pattern.
    bsdf.inputs["Specular IOR Level"].default_value = 0.0

    # Perspective divide of the shading point's position in the projector's
    # local space -- the standard gobo-projection computation.
    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.object = projector_obj

    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], sep.inputs["Vector"])

    neg_z = nt.nodes.new("ShaderNodeMath")
    neg_z.operation = "MULTIPLY"
    neg_z.inputs[1].default_value = -1.0
    nt.links.new(sep.outputs["Z"], neg_z.inputs[0])

    div_x = nt.nodes.new("ShaderNodeMath")
    div_x.operation = "DIVIDE"
    nt.links.new(sep.outputs["X"], div_x.inputs[0])
    nt.links.new(neg_z.outputs[0], div_x.inputs[1])

    div_y = nt.nodes.new("ShaderNodeMath")
    div_y.operation = "DIVIDE"
    nt.links.new(sep.outputs["Y"], div_y.inputs[0])
    nt.links.new(neg_z.outputs[0], div_y.inputs[1])

    u = nt.nodes.new("ShaderNodeMath")
    u.operation = "MULTIPLY_ADD"
    u.inputs[1].default_value = THROW_RATIO_W
    u.inputs[2].default_value = 0.5
    nt.links.new(div_x.outputs[0], u.inputs[0])

    v = nt.nodes.new("ShaderNodeMath")
    v.operation = "MULTIPLY_ADD"
    v.inputs[1].default_value = THROW_RATIO_H
    v.inputs[2].default_value = 0.5
    nt.links.new(div_y.outputs[0], v.inputs[0])

    # Rectangle mask from the *unshifted* u, v: the illuminated footprint's
    # position/size must not move as the fringe phase steps.
    mask = nt.nodes.new("ShaderNodeMath")
    mask.operation = "MULTIPLY"
    nt.links.new(_mask_node(nt, u.outputs[0]), mask.inputs[0])
    nt.links.new(_mask_node(nt, v.outputs[0]), mask.inputs[1])

    # Phase-shift step, as a fraction of one cycle (0..1) -- update
    # phase_fraction.outputs[0].default_value between renders.
    #
    # The fringe itself is built from an explicit Math "Sine" node rather
    # than a Wave Texture: tested directly (rendered probe strips, measured
    # period and histogram), ShaderNodeTexWave's "Scale" needed an
    # unexplained /4 correction to match its documented meaning, its "Phase
    # Offset" input didn't shift the pattern by a consistent, predictable
    # fraction of a period, and its "SIN" profile's rendered histogram was
    # bimodal (~86% of samples pinned near 0 or 1) rather than the smooth,
    # symmetric distribution a true sinusoid produces. Computing
    # 0.5 + 0.5*sin(2*pi*n_periods*u + 2*pi*phase_fraction) directly from a
    # Math node leaves no room for hidden internal scaling.
    phase_fraction = nt.nodes.new("ShaderNodeValue")
    phase_fraction.outputs[0].default_value = 0.0

    phase_arg = nt.nodes.new("ShaderNodeMath")
    phase_arg.operation = "MULTIPLY_ADD"
    phase_arg.inputs[1].default_value = 2.0 * math.pi * n_periods
    # inputs[2] (added after scaling) carries the phase-shift term.
    nt.links.new(u.outputs[0], phase_arg.inputs[0])

    phase_shift_rad = nt.nodes.new("ShaderNodeMath")
    phase_shift_rad.operation = "MULTIPLY"
    phase_shift_rad.inputs[1].default_value = 2.0 * math.pi
    nt.links.new(phase_fraction.outputs[0], phase_shift_rad.inputs[0])
    nt.links.new(phase_shift_rad.outputs[0], phase_arg.inputs[2])

    sine = nt.nodes.new("ShaderNodeMath")
    sine.operation = "SINE"
    nt.links.new(phase_arg.outputs[0], sine.inputs[0])

    fringe = nt.nodes.new("ShaderNodeMath")
    fringe.operation = "MULTIPLY_ADD"
    fringe.inputs[1].default_value = 0.5
    fringe.inputs[2].default_value = 0.5
    nt.links.new(sine.outputs[0], fringe.inputs[0])

    masked = nt.nodes.new("ShaderNodeMath")
    masked.operation = "MULTIPLY"
    nt.links.new(fringe.outputs[0], masked.inputs[0])
    nt.links.new(mask.outputs[0], masked.inputs[1])

    to_rgb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(masked.outputs[0], to_rgb.inputs["X"])
    nt.links.new(masked.outputs[0], to_rgb.inputs["Y"])
    nt.links.new(masked.outputs[0], to_rgb.inputs["Z"])
    nt.links.new(to_rgb.outputs["Vector"], bsdf.inputs["Base Color"])

    surface.data.materials.append(mat)
    return surface, phase_fraction


def add_telecentric_camera():
    cam_data = bpy.data.cameras.new("TelecentricLens")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = W0_MM * MM
    cam_data.sensor_fit = "HORIZONTAL"

    cam_obj = bpy.data.objects.new("Camera_Telecentric", cam_data)
    bpy.context.collection.objects.link(cam_obj)

    theta = math.radians(THETA_DEG)
    wd = CAM_WORKING_DISTANCE_MM * MM
    cam_obj.location = Vector((wd * math.sin(theta), 0.0, wd * math.cos(theta)))
    look_at(cam_obj, Vector((0.0, 0.0, 0.0)))
    # to_track_quat('-Z','Y') puts local +X along world Y and local +Y in the
    # tilt (X-Z) plane for this direction -- verified directly by reading
    # back matrix_world. report/math.tex's derivation assumes the opposite
    # (sensor width axis tilted, matching the projector's wide axis; sensor
    # height axis untouched), so roll 90 degrees about the view axis to
    # match: local +X (columns, sensor width) now falls in the tilt plane.
    cam_obj.rotation_euler = (
        cam_obj.rotation_euler.to_quaternion() @ Quaternion((0.0, 0.0, 1.0), math.radians(90.0))
    ).to_euler()

    scene = bpy.context.scene
    scene.render.resolution_x, scene.render.resolution_y = CAM_PIXELS
    return cam_obj


def add_overview_camera():
    cam_data = bpy.data.cameras.new("Overview")
    cam_data.type = "PERSP"
    cam_data.lens = 35.0
    cam_obj = bpy.data.objects.new("Camera_Overview", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    cam_obj.location = Vector((0.35, -0.45, 0.30))
    look_at(cam_obj, Vector((0.0, 0.0, 0.0)))
    return cam_obj


def add_marker(name: str, location: Vector, color, radius: float = 0.006):
    """Small emissive sphere marking a device position -- offset above the
    actual location so it doesn't sit on top of (and self-occlude) the
    projector's light source."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location + Vector((0.0, 0.0, 0.02)))
    marker = bpy.context.active_object
    marker.name = name
    mat = bpy.data.materials.new(f"{name}Material")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    emission = nt.nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (*color, 1.0)
    emission.inputs["Strength"].default_value = 2.0
    output = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    marker.data.materials.append(mat)
    return marker


def render(scene, camera_obj, resolution, path: Path, samples: int) -> None:
    scene.camera = camera_obj
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.device = "CPU"
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
