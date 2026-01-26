"""3D Animation using PyVista for GPU-accelerated rendering.

Supports importing 3D models and exporting recovered surfaces.
"""

import argparse
import os
import time
from pathlib import Path

import numpy as np
import pyvista as pv

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence
from micro_projection.processing import extract_phase, unwrap_phase, phase_to_height, remove_plane


def load_surface_from_model(model_path: str, resolution: tuple[int, int]) -> np.ndarray:
    """Load a 3D model and convert to height map.

    Supports STL, OBJ, PLY formats.
    """
    print(f"Loading model: {model_path}")
    mesh = pv.read(model_path)

    # Get bounds
    bounds = mesh.bounds  # (xmin, xmax, ymin, ymax, zmin, zmax)

    # Create a grid for sampling
    x = np.linspace(bounds[0], bounds[1], resolution[1])
    y = np.linspace(bounds[2], bounds[3], resolution[0])
    X, Y = np.meshgrid(x, y)

    # Sample Z values by ray casting from above
    # Create points above the mesh
    z_top = bounds[5] + 1
    points = np.column_stack([X.ravel(), Y.ravel(), np.full(X.size, z_top)])

    # Ray cast downward
    directions = np.zeros_like(points)
    directions[:, 2] = -1

    # Use ray tracing to find surface intersections
    intersection_points, ray_indices, _ = mesh.multi_ray_trace(points, directions)

    # Create height map
    height_map = np.full(resolution, np.nan)

    if len(intersection_points) > 0:
        # Get Z values at intersections
        for i, idx in enumerate(ray_indices):
            row = idx // resolution[1]
            col = idx % resolution[1]
            z_val = intersection_points[i, 2]
            # Keep the highest intersection (closest to ray origin)
            if np.isnan(height_map[row, col]) or z_val > height_map[row, col]:
                height_map[row, col] = z_val

    # Fill NaN values with minimum
    min_z = np.nanmin(height_map) if not np.all(np.isnan(height_map)) else 0
    height_map = np.nan_to_num(height_map, nan=min_z)

    # Normalize to 0-1 range and scale
    height_map = height_map - height_map.min()
    if height_map.max() > 0:
        height_map = height_map / height_map.max() * 0.2  # Scale to reasonable height

    return height_map


def create_procedural_surface(resolution: tuple[int, int]) -> np.ndarray:
    """Create a complex procedural surface for demonstration."""
    y, x = np.mgrid[0:resolution[0], 0:resolution[1]].astype(np.float64)
    cx, cy = resolution[1] / 2, resolution[0] / 2

    # Normalize coordinates
    x_norm = (x - cx) / cx
    y_norm = (y - cy) / cy

    # Main dome
    r2 = x_norm**2 + y_norm**2
    dome = 0.15 * np.exp(-3 * r2)

    # Off-center bump
    r2_bump = (x_norm - 0.4)**2 + (y_norm - 0.3)**2
    bump = 0.08 * np.exp(-15 * r2_bump)

    # Another smaller bump
    r2_bump2 = (x_norm + 0.3)**2 + (y_norm + 0.4)**2
    bump2 = 0.05 * np.exp(-20 * r2_bump2)

    # Sinusoidal ripples
    ripples = 0.02 * np.sin(8 * np.pi * x_norm) * np.exp(-2 * r2)

    # Combine
    surface = dome + bump + bump2 + ripples
    surface = surface - surface.min()

    return surface


def export_surface_as_mesh(surface: np.ndarray, filepath: str, z_scale: float = 1.0):
    """Export a height map as a 3D mesh file (STL, OBJ, or PLY)."""
    resolution = surface.shape
    x_coords = np.arange(resolution[1])
    y_coords = np.arange(resolution[0])
    X, Y = np.meshgrid(x_coords, y_coords)

    # Create structured grid
    grid = pv.StructuredGrid(
        X.astype(np.float32),
        Y.astype(np.float32),
        (surface * z_scale).astype(np.float32)
    )

    # Convert to triangulated surface for export
    surface_mesh = grid.extract_surface().triangulate()

    # Save based on extension
    surface_mesh.save(filepath)
    print(f"Exported: {filepath}")


def create_3d_animation(
    input_model: str = None,
    output_dir: str = "output",
    resolution: tuple[int, int] = (1024, 1024),
    n_steps: int = 128,
    period: int = 160,
):
    """Create 3D animation of fringe projection process.

    Args:
        input_model: Path to input 3D model (STL, OBJ, PLY). If None, uses procedural surface.
        output_dir: Directory for output files.
        resolution: Resolution for processing.
        n_steps: Number of phase-shifting steps.
        period: Fringe period in pixels.
    """
    total_start = time.time()

    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_path.absolute()}")

    # Setup simulation
    print("\nSetting up simulation...")
    t0 = time.time()
    config = SimulationConfig(resolution=resolution, noise_level=0.003)
    source = SimulationSource(config)

    # Load or create surface
    if input_model and os.path.exists(input_model):
        input_surface = load_surface_from_model(input_model, resolution)
    else:
        if input_model:
            print(f"Warning: Model file not found: {input_model}")
            print("Using procedural surface instead.")
        input_surface = create_procedural_surface(resolution)

    source.set_surface(input_surface)
    print(f"  Surface setup: {time.time() - t0:.2f}s")

    # Export input surface as 3D model
    z_scale = resolution[0] * 2  # Scale for visualization
    input_mesh_path = output_path / "input_surface.stl"
    export_surface_as_mesh(input_surface, str(input_mesh_path), z_scale)

    # Generate all patterns
    t0 = time.time()
    patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)
    print(f"  Pattern generation: {time.time() - t0:.2f}s")

    # Capture all frames
    t0 = time.time()
    frames = []
    for p in patterns:
        source.project_pattern(p)
        frames.append(source.capture_frame())
    print(f"  Frame capture: {time.time() - t0:.2f}s")

    # Process to get final result
    print("\nProcessing...")
    t0 = time.time()
    phase_map = extract_phase(frames, n_steps=n_steps)
    print(f"  Phase extraction: {time.time() - t0:.2f}s")

    t0 = time.time()
    phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)
    print(f"  Phase unwrapping: {time.time() - t0:.2f}s")

    t0 = time.time()
    calibration = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
    height_map = phase_to_height(phase_map, calibration)
    height_map = remove_plane(height_map)
    recovered_surface = -height_map.data
    print(f"  Height conversion: {time.time() - t0:.2f}s")

    # Normalize recovered to match input scale
    recovered_surface = recovered_surface - np.mean(recovered_surface)
    input_centered = input_surface - np.mean(input_surface)
    scale = np.std(input_centered) / (np.std(recovered_surface) + 1e-10)
    recovered_surface = recovered_surface * scale
    recovered_surface = recovered_surface - recovered_surface.min()

    # Export recovered surface as 3D model
    recovered_mesh_path = output_path / "recovered_surface.stl"
    export_surface_as_mesh(recovered_surface, str(recovered_mesh_path), z_scale)

    # Also export as OBJ for compatibility
    recovered_obj_path = output_path / "recovered_surface.obj"
    export_surface_as_mesh(recovered_surface, str(recovered_obj_path), z_scale)

    # Create coordinate grids for visualization
    x_coords = np.arange(resolution[1])
    y_coords = np.arange(resolution[0])
    X, Y = np.meshgrid(x_coords, y_coords)

    def create_mesh(surface, texture=None):
        """Create a PyVista StructuredGrid from surface data."""
        grid = pv.StructuredGrid(
            X.astype(np.float32),
            Y.astype(np.float32),
            (surface * z_scale).astype(np.float32)
        )
        if texture is not None:
            grid.point_data['texture'] = texture.flatten(order='F').astype(np.float32)
        else:
            grid.point_data['height'] = surface.flatten(order='F').astype(np.float32)
        return grid

    # Setup PyVista plotter for offscreen rendering
    print("\nRendering animation...")
    t0 = time.time()

    plotter = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(1400, 600))

    # Camera setup
    center_x, center_y = resolution[1] / 2, resolution[0] / 2
    camera_distance = resolution[0] * 2.5
    camera_height = resolution[0] * 1.2

    def get_camera_position(angle_deg):
        angle_rad = np.radians(angle_deg)
        cam_x = center_x + camera_distance * np.cos(angle_rad)
        cam_y = center_y + camera_distance * np.sin(angle_rad)
        return [
            (cam_x, cam_y, camera_height),
            (center_x, center_y, 0),
            (0, 0, 1)
        ]

    start_angle = -45

    # Output GIF path
    gif_path = output_path / "animation.gif"
    plotter.open_gif(str(gif_path), fps=20)

    recovery_frames = n_steps  # Match projection phase for smooth recovery
    hold_frames = 20
    total_frames = n_steps + recovery_frames + hold_frames

    for frame_num in range(total_frames):
        plotter.clear()
        plotter.subplot(0, 0)
        plotter.subplot(0, 1)

        # Calculate camera angle - rotate 90 degrees during fringe projection phase
        if frame_num < n_steps:
            rotation_progress = frame_num / n_steps
            angle = start_angle + 90 * rotation_progress
        else:
            angle = start_angle + 90  # Hold final angle during recovery

        camera_pos = get_camera_position(angle)

        # Phase 1: Fringe projection
        if frame_num < n_steps:
            step_idx = frame_num
            pattern = patterns[step_idx]
            captured = frames[step_idx]

            plotter.subplot(0, 0)
            mesh_left = create_mesh(input_surface, pattern)
            plotter.add_mesh(mesh_left, scalars='texture', cmap='gray',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title(f'Projecting Pattern {step_idx+1}/{n_steps}', font_size=12)
            plotter.camera_position = camera_pos

            plotter.subplot(0, 1)
            mesh_right = create_mesh(input_surface, captured)
            plotter.add_mesh(mesh_right, scalars='texture', cmap='gray',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title(f'Captured Fringes {step_idx+1}/{n_steps}', font_size=12)
            plotter.camera_position = camera_pos

        # Phase 2: Recovery animation
        elif frame_num < n_steps + recovery_frames:
            progress = (frame_num - n_steps + 1) / recovery_frames

            plotter.subplot(0, 0)
            mesh_left = create_mesh(input_surface)
            plotter.add_mesh(mesh_left, scalars='height', cmap='viridis',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title('Input Surface (Ground Truth)', font_size=12)
            plotter.camera_position = camera_pos

            plotter.subplot(0, 1)
            flat_level = np.mean(recovered_surface)
            emerging = flat_level + (recovered_surface - flat_level) * progress
            mesh_right = create_mesh(emerging)
            plotter.add_mesh(mesh_right, scalars='height', cmap='plasma',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title(f'Recovering Surface... {int(progress*100)}%', font_size=12)
            plotter.camera_position = camera_pos

        # Phase 3: Final comparison
        else:
            plotter.subplot(0, 0)
            mesh_left = create_mesh(input_surface)
            plotter.add_mesh(mesh_left, scalars='height', cmap='viridis',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title('Input Surface (Ground Truth)', font_size=12)
            plotter.camera_position = camera_pos

            plotter.subplot(0, 1)
            mesh_right = create_mesh(recovered_surface)
            plotter.add_mesh(mesh_right, scalars='height', cmap='plasma',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title('Recovered Surface (Result)', font_size=12)
            plotter.camera_position = camera_pos

        plotter.write_frame()

        if (frame_num + 1) % 10 == 0:
            print(f"  Frame {frame_num + 1}/{total_frames}")

    plotter.close()
    print(f"  Rendering: {time.time() - t0:.2f}s")

    print(f"\n{'='*50}")
    print(f"Total time: {time.time() - total_start:.2f}s")
    print(f"\nOutput files in '{output_path.absolute()}':")
    print(f"  - input_surface.stl     (input 3D model)")
    print(f"  - recovered_surface.stl (recovered 3D model)")
    print(f"  - recovered_surface.obj (recovered 3D model)")
    print(f"  - animation.gif         (animation)")


def main():
    parser = argparse.ArgumentParser(
        description="3D Fringe Projection Animation with model import/export"
    )
    parser.add_argument(
        "-i", "--input",
        help="Input 3D model file (STL, OBJ, PLY). If not provided, uses procedural surface."
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory for results (default: output)"
    )
    parser.add_argument(
        "-r", "--resolution",
        type=int,
        default=1024,
        help="Resolution (square, default: 1024)"
    )
    parser.add_argument(
        "-n", "--n-steps",
        type=int,
        default=128,
        help="Number of phase-shifting steps (default: 128)"
    )
    parser.add_argument(
        "-p", "--period",
        type=int,
        default=160,
        help="Fringe period in pixels (default: 160)"
    )

    args = parser.parse_args()

    create_3d_animation(
        input_model=args.input,
        output_dir=args.output,
        resolution=(args.resolution, args.resolution),
        n_steps=args.n_steps,
        period=args.period,
    )


if __name__ == "__main__":
    main()
