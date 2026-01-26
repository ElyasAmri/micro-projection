"""3D Animation using PyVista for GPU-accelerated rendering."""

import time
import numpy as np
import pyvista as pv

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence
from micro_projection.processing import extract_phase, unwrap_phase, phase_to_height, remove_plane


def create_3d_animation():
    total_start = time.time()

    # Setup
    resolution = (1024, 1024)
    period = 160
    n_steps = 128

    # Create simulation with a complex surface
    print("Setting up simulation...")
    t0 = time.time()
    config = SimulationConfig(resolution=resolution, noise_level=0.003)
    source = SimulationSource(config)

    # Create a complex surface: multiple gaussians + sinusoidal ripples
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
    input_surface = dome + bump + bump2 + ripples
    input_surface = input_surface - input_surface.min()  # Ensure positive

    source.set_surface(input_surface)
    print(f"  Surface setup: {time.time() - t0:.2f}s")

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
    print("Processing...")
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

    # Create coordinate grids
    x_coords = np.arange(resolution[1])
    y_coords = np.arange(resolution[0])
    X, Y = np.meshgrid(x_coords, y_coords)

    # Scale Z for better visualization (make height more visible)
    z_scale = resolution[0] * 2

    def create_mesh(surface, texture=None):
        """Create a PyVista StructuredGrid from surface data."""
        # Use float32 to avoid warning and improve GPU performance
        grid = pv.StructuredGrid(
            X.astype(np.float32),
            Y.astype(np.float32),
            (surface * z_scale).astype(np.float32)
        )
        if texture is not None:
            grid.point_data['texture'] = texture.flatten(order='F').astype(np.float32)
        else:
            # Use height as scalars for coloring
            grid.point_data['height'] = surface.flatten(order='F').astype(np.float32)
        return grid

    # Setup PyVista plotter for offscreen rendering
    print("Rendering animation...")
    t0 = time.time()

    # Create plotter with two viewports
    plotter = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(1400, 600))

    # Camera setup
    center_x, center_y = resolution[1] / 2, resolution[0] / 2
    camera_distance = resolution[0] * 2.5
    camera_height = resolution[0] * 1.2

    def get_camera_position(angle_deg):
        """Get camera position for a given angle (in degrees)."""
        angle_rad = np.radians(angle_deg)
        cam_x = center_x + camera_distance * np.cos(angle_rad)
        cam_y = center_y + camera_distance * np.sin(angle_rad)
        return [
            (cam_x, cam_y, camera_height),  # position
            (center_x, center_y, 0),  # focal point
            (0, 0, 1)  # up vector
        ]

    # Starting angle
    start_angle = -45

    # Open GIF writer
    plotter.open_gif('fringe_projection_3d_pyvista.gif', fps=20)

    total_frames = n_steps + 20 + 20  # fringe + recovery + hold

    for frame_num in range(total_frames):
        plotter.clear()

        # Left subplot
        plotter.subplot(0, 0)

        # Right subplot
        plotter.subplot(0, 1)

        # Calculate camera angle - rotate 90 degrees during recovery+hold phases
        if frame_num < n_steps:
            angle = start_angle  # Fixed during fringe projection
        else:
            # Rotate from start_angle to start_angle+90 over recovery+hold frames
            rotation_progress = (frame_num - n_steps) / 40  # 40 frames for rotation
            rotation_progress = min(1.0, rotation_progress)  # Cap at 1.0
            angle = start_angle + 90 * rotation_progress

        camera_pos = get_camera_position(angle)

        # Phase 1: Fringe projection (frames 0 to n_steps-1)
        if frame_num < n_steps:
            step_idx = frame_num
            pattern = patterns[step_idx]
            captured = frames[step_idx]

            # Left: Surface with projected pattern
            plotter.subplot(0, 0)
            mesh_left = create_mesh(input_surface, pattern)
            plotter.add_mesh(mesh_left, scalars='texture', cmap='gray',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title(f'Projecting Pattern {step_idx+1}/{n_steps}', font_size=12)
            plotter.camera_position = camera_pos

            # Right: Surface with captured (deformed) fringes
            plotter.subplot(0, 1)
            mesh_right = create_mesh(input_surface, captured)
            plotter.add_mesh(mesh_right, scalars='texture', cmap='gray',
                           show_scalar_bar=False, smooth_shading=True)
            plotter.add_title(f'Captured Fringes {step_idx+1}/{n_steps}', font_size=12)
            plotter.camera_position = camera_pos

        # Phase 2: Recovery animation (frames n_steps to n_steps+19)
        elif frame_num < n_steps + 20:
            progress = (frame_num - n_steps + 1) / 20

            # Left: Ground truth (static)
            plotter.subplot(0, 0)
            mesh_left = create_mesh(input_surface)
            plotter.add_mesh(mesh_left, scalars='height', cmap='viridis', show_scalar_bar=False,
                           smooth_shading=True)
            plotter.add_title('Input Surface (Ground Truth)', font_size=12)
            plotter.camera_position = camera_pos

            # Right: Surface emerging from flat
            plotter.subplot(0, 1)
            flat_level = np.mean(recovered_surface)
            emerging = flat_level + (recovered_surface - flat_level) * progress
            mesh_right = create_mesh(emerging)
            plotter.add_mesh(mesh_right, scalars='height', cmap='plasma', show_scalar_bar=False,
                           smooth_shading=True)
            plotter.add_title(f'Recovering Surface... {int(progress*100)}%', font_size=12)
            plotter.camera_position = camera_pos

        # Phase 3: Final comparison (frames n_steps+20 to end)
        else:
            # Left: Ground truth
            plotter.subplot(0, 0)
            mesh_left = create_mesh(input_surface)
            plotter.add_mesh(mesh_left, scalars='height', cmap='viridis', show_scalar_bar=False,
                           smooth_shading=True)
            plotter.add_title('Input Surface (Ground Truth)', font_size=12)
            plotter.camera_position = camera_pos

            # Right: Recovered surface
            plotter.subplot(0, 1)
            mesh_right = create_mesh(recovered_surface)
            plotter.add_mesh(mesh_right, scalars='height', cmap='plasma', show_scalar_bar=False,
                           smooth_shading=True)
            plotter.add_title('Recovered Surface (Result)', font_size=12)
            plotter.camera_position = camera_pos

        # Write frame
        plotter.write_frame()

        if (frame_num + 1) % 10 == 0:
            print(f"  Frame {frame_num + 1}/{total_frames}")

    plotter.close()
    print(f"  Rendering: {time.time() - t0:.2f}s")

    print(f"\nTotal time: {time.time() - total_start:.2f}s")
    print("Saved: fringe_projection_3d_pyvista.gif")


if __name__ == "__main__":
    create_3d_animation()
