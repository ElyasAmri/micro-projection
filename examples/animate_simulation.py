"""Animation of the fringe projection simulation process."""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.gridspec import GridSpec

from micro_projection import SimulationSource, SimulationConfig, CalibrationParams
from micro_projection.patterns import generate_phase_sequence
from micro_projection.processing import extract_phase, unwrap_phase, phase_to_height


def create_animation():
    # Setup
    resolution = (256, 256)
    period = 32
    n_steps = 8

    # Create simulation with a sphere surface
    config = SimulationConfig(resolution=resolution, noise_level=0.005)
    source = SimulationSource(config)
    source.set_test_surface("sphere", amplitude=0.15, radius=0.8)

    input_surface = source.get_surface()

    # Generate all patterns
    patterns = generate_phase_sequence(resolution, period=period, n_steps=n_steps)

    # Capture all frames
    frames = []
    for p in patterns:
        source.project_pattern(p)
        frames.append(source.capture_frame())

    # Process to get final result
    phase_map = extract_phase(frames, n_steps=n_steps)
    phase_map.unwrapped = unwrap_phase(phase_map.wrapped, phase_map.quality)
    calibration = CalibrationParams(equivalent_wavelength=1.0, pixel_pitch=1.0)
    height_map = phase_to_height(phase_map, calibration)

    # Create figure
    fig = plt.figure(figsize=(14, 8))
    gs = GridSpec(2, 3, figure=fig, hspace=0.3, wspace=0.3)

    # Axes
    ax_surface = fig.add_subplot(gs[0, 0])
    ax_pattern = fig.add_subplot(gs[0, 1])
    ax_captured = fig.add_subplot(gs[0, 2])
    ax_phase = fig.add_subplot(gs[1, 0])
    ax_unwrapped = fig.add_subplot(gs[1, 1])
    ax_height = fig.add_subplot(gs[1, 2])

    # Static: Input surface
    im_surface = ax_surface.imshow(input_surface, cmap='viridis')
    ax_surface.set_title('Input Surface\n(What we measure)', fontsize=11)
    plt.colorbar(im_surface, ax=ax_surface, label='Height')

    # Animated: Projected pattern
    im_pattern = ax_pattern.imshow(patterns[0], cmap='gray', vmin=0, vmax=1)
    ax_pattern.set_title('Projected Pattern\n(Phase step 1/8)', fontsize=11)

    # Animated: Captured deformed fringes
    im_captured = ax_captured.imshow(frames[0], cmap='gray', vmin=0, vmax=1)
    ax_captured.set_title('Captured Fringes\n(Deformed by surface)', fontsize=11)

    # Building: Wrapped phase (starts empty)
    phase_display = np.zeros_like(phase_map.wrapped)
    im_phase = ax_phase.imshow(phase_display, cmap='twilight', vmin=-np.pi, vmax=np.pi)
    ax_phase.set_title('Wrapped Phase\n(Computing...)', fontsize=11)
    plt.colorbar(im_phase, ax=ax_phase, label='Phase (rad)')

    # Building: Unwrapped phase (starts empty)
    unwrap_display = np.zeros_like(phase_map.unwrapped)
    im_unwrapped = ax_unwrapped.imshow(unwrap_display, cmap='viridis')
    ax_unwrapped.set_title('Unwrapped Phase\n(Waiting...)', fontsize=11)
    plt.colorbar(im_unwrapped, ax=ax_unwrapped, label='Phase (rad)')

    # Final: Height map (starts empty)
    height_display = np.zeros_like(height_map.data)
    im_height = ax_height.imshow(height_display, cmap='viridis')
    ax_height.set_title('Recovered Height\n(Waiting...)', fontsize=11)
    plt.colorbar(im_height, ax=ax_height, label='Height')

    # Animation state
    state = {'step': 0, 'phase': 'capturing'}

    def init():
        return [im_pattern, im_captured, im_phase, im_unwrapped, im_height]

    def animate(frame_num):
        # Phase 1: Show pattern projection and capture (frames 0-7)
        if frame_num < n_steps:
            step = frame_num
            im_pattern.set_data(patterns[step])
            ax_pattern.set_title(f'Projected Pattern\n(Phase step {step+1}/{n_steps})', fontsize=11)

            im_captured.set_data(frames[step])
            ax_captured.set_title(f'Captured Fringes\n(Frame {step+1}/{n_steps})', fontsize=11)

            ax_phase.set_title('Wrapped Phase\n(Capturing frames...)', fontsize=11)

        # Phase 2: Show phase computation (frame 8)
        elif frame_num == n_steps:
            im_phase.set_data(phase_map.wrapped)
            ax_phase.set_title('Wrapped Phase\n(Computed!)', fontsize=11)
            ax_unwrapped.set_title('Unwrapped Phase\n(Unwrapping...)', fontsize=11)

        # Phase 3: Show unwrapped phase (frame 9)
        elif frame_num == n_steps + 1:
            im_unwrapped.set_data(phase_map.unwrapped)
            im_unwrapped.set_clim(phase_map.unwrapped.min(), phase_map.unwrapped.max())
            ax_unwrapped.set_title('Unwrapped Phase\n(Complete!)', fontsize=11)
            ax_height.set_title('Recovered Height\n(Converting...)', fontsize=11)

        # Phase 4: Show final height map (frame 10)
        elif frame_num == n_steps + 2:
            # Negate for correct sign convention
            height_data = -height_map.data
            im_height.set_data(height_data)
            im_height.set_clim(height_data.min(), height_data.max())
            ax_height.set_title('Recovered Height\n(Complete!)', fontsize=11)

        # Phase 5: Hold final result (frames 11-14)
        # Just hold the current state

        return [im_pattern, im_captured, im_phase, im_unwrapped, im_height]

    # Total frames: 8 capture + 3 processing + 4 hold = 15
    total_frames = n_steps + 3 + 4
    anim = animation.FuncAnimation(
        fig, animate, init_func=init,
        frames=total_frames, interval=500, blit=False
    )

    # Save as GIF
    print("Saving animation as GIF (this may take a moment)...")
    anim.save('fringe_projection_animation.gif', writer='pillow', fps=2, dpi=100)
    print("Saved: fringe_projection_animation.gif")

    # Also save as MP4 if ffmpeg is available
    try:
        anim.save('fringe_projection_animation.mp4', writer='ffmpeg', fps=2, dpi=100)
        print("Saved: fringe_projection_animation.mp4")
    except Exception as e:
        print(f"MP4 not saved (ffmpeg not available): {e}")

    plt.close()


if __name__ == "__main__":
    create_animation()
