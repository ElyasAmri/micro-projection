"""3D Animation of the fringe projection simulation process."""

import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from mpl_toolkits.mplot3d import Axes3D

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence
from micro_projection.processing import extract_phase, unwrap_phase, phase_to_height, remove_plane


def create_3d_animation():
    total_start = time.time()
    # Setup
    resolution = (512, 512)  # Moderate resolution - rcount/ccount handles smoothness
    period = 80  # Scale period with resolution
    n_steps = 64

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
    height_map = remove_plane(height_map)  # Remove tilt from unwrapping
    recovered_surface = -height_map.data  # Sign correction
    print(f"  Height conversion: {time.time() - t0:.2f}s")

    # Create coordinate grids
    x = np.arange(resolution[1])
    y = np.arange(resolution[0])
    X, Y = np.meshgrid(x, y)

    # Use full resolution for smoother surface
    Xs, Ys = X, Y
    input_s = input_surface
    recovered_s = recovered_surface

    # Normalize recovered to match input scale for comparison
    # Center around zero first, then scale
    recovered_s = recovered_s - np.mean(recovered_s)
    input_centered = input_s - np.mean(input_s)
    scale = np.std(input_centered) / (np.std(recovered_s) + 1e-10)
    recovered_s = recovered_s * scale
    # Shift to match input range
    recovered_s = recovered_s - recovered_s.min()

    # Pre-render ground truth to avoid flickering
    print("Pre-rendering ground truth...")
    t0 = time.time()
    fig_static = plt.figure(figsize=(7, 6))
    ax_static = fig_static.add_subplot(111, projection='3d')
    ax_static.set_xlabel('X')
    ax_static.set_ylabel('Y')
    ax_static.set_zlabel('Height')
    ax_static.set_zlim(0, 0.25)
    ax_static.view_init(elev=25, azim=45)
    ax_static.plot_surface(Xs, Ys, input_s, cmap='viridis', alpha=1.0, linewidth=0, antialiased=True, rcount=400, ccount=400, shade=True)
    ax_static.set_title('Input Surface (Ground Truth)', fontsize=12, pad=10)
    fig_static.tight_layout()
    fig_static.canvas.draw()
    ground_truth_image = np.array(fig_static.canvas.renderer.buffer_rgba())
    plt.close(fig_static)
    print(f"  Pre-render: {time.time() - t0:.2f}s")

    # Create figure with two subplots
    fig = plt.figure(figsize=(14, 6))
    fig.subplots_adjust(left=0.05, right=0.95, top=0.9, bottom=0.1, wspace=0.1)

    ax1 = fig.add_subplot(121, projection='3d')
    ax2 = fig.add_subplot(122, projection='3d')

    # Also create an axes for the static image (used during recovery)
    ax1_static = fig.add_axes([0.05, 0.1, 0.4, 0.8])
    ax1_static.set_visible(False)

    def animate(frame_num):
        # Fixed view angle
        azim = 45

        # During recovery phase, use pre-rendered ground truth
        if frame_num >= n_steps:
            ax1.set_visible(False)
            ax1_static.set_visible(True)
            ax1_static.clear()
            ax1_static.imshow(ground_truth_image)
            ax1_static.axis('off')
        else:
            ax1.set_visible(True)
            ax1_static.set_visible(False)
            ax1.clear()
            # Common axis settings for ax1
            ax1.set_xlabel('X')
            ax1.set_ylabel('Y')
            ax1.set_zlabel('Height')
            ax1.set_zlim(0, 0.25)
            ax1.view_init(elev=25, azim=azim)

        ax2.clear()
        # Common axis settings for ax2
        ax2.set_xlabel('X')
        ax2.set_ylabel('Y')
        ax2.set_zlabel('Height')
        ax2.set_zlim(0, 0.25)
        ax2.view_init(elev=25, azim=azim)

        # Phase 1: Fringe projection
        if frame_num < n_steps:
            step_idx = frame_num
            pattern = patterns[step_idx]
            captured = frames[step_idx]

            # Left: 3D surface with fringe pattern texture
            ax1.plot_surface(Xs, Ys, input_s, facecolors=plt.cm.gray(pattern),
                           alpha=1.0, shade=False, linewidth=0, antialiased=True, rcount=400, ccount=400)
            ax1.set_title(f'Projecting Pattern {step_idx+1}/{n_steps}', fontsize=12, pad=10)

            # Right: 3D surface showing captured (deformed) fringes
            ax2.plot_surface(Xs, Ys, input_s, facecolors=plt.cm.gray(captured),
                           alpha=1.0, shade=False, linewidth=0, antialiased=True, rcount=400, ccount=400)
            ax2.set_title(f'Captured Fringes {step_idx+1}/{n_steps}', fontsize=12, pad=10)

        # Phase 2: Recovery animation - surface emerges from flat
        elif frame_num < n_steps + 20:
            progress = (frame_num - n_steps + 1) / 20  # 0.05 to 1.0

            # Left: Uses pre-rendered ground truth (handled above)

            # Right: Recovered surface emerging from flat
            flat_level = np.mean(recovered_s)
            emerging = flat_level + (recovered_s - flat_level) * progress
            ax2.plot_surface(Xs, Ys, emerging, cmap='plasma', alpha=1.0, linewidth=0, antialiased=True, rcount=400, ccount=400, shade=True)
            ax2.set_title(f'Recovering Surface... {int(progress*100)}%', fontsize=12, pad=10)

        # Phase 3: Final comparison - hold
        else:
            # Left: Uses pre-rendered ground truth (handled above)

            # Right: Fully recovered surface
            ax2.plot_surface(Xs, Ys, recovered_s, cmap='plasma', alpha=1.0, linewidth=0, antialiased=True, rcount=400, ccount=400, shade=True)
            ax2.set_title('Recovered Surface (Result)', fontsize=12, pad=10)

        return []

    # Total frames: 64 fringe + 20 recovery + 20 hold = 104
    total_frames = n_steps + 20 + 20
    anim = animation.FuncAnimation(
        fig, animate,
        frames=total_frames, interval=50, blit=False
    )

    # Save as GIF with higher FPS
    print("Rendering animation...")
    t0 = time.time()
    anim.save('fringe_projection_3d.gif', writer='pillow', fps=20, dpi=100)
    print(f"  Rendering: {time.time() - t0:.2f}s")

    print(f"\nTotal time: {time.time() - total_start:.2f}s")
    print("Saved: fringe_projection_3d.gif")

    plt.close()


if __name__ == "__main__":
    create_3d_animation()
