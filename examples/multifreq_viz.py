"""3D PyVista visualization for multi-frequency roughness comparison."""

from pathlib import Path

import numpy as np


def visualize_3d(
    true_roughness: np.ndarray,
    single_roughness: np.ndarray,
    multi_roughness: np.ndarray,
    single_err: dict,
    multi_err: dict,
    output_dir: Path,
):
    """Create 3D PyVista visualization comparing roughness recovery."""
    import pyvista as pv

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    h, w = true_roughness.shape
    x = np.arange(w)
    y = np.arange(h)
    x_grid, y_grid = np.meshgrid(x, y)

    z_scale = 5000.0  # Roughness is small, amplify for visibility

    def create_mesh(height_data, name):
        grid = pv.StructuredGrid(x_grid, y_grid, height_data * z_scale)
        grid[name] = height_data.flatten(order='F')
        return grid

    mesh_truth = create_mesh(true_roughness, "roughness")
    mesh_single = create_mesh(single_roughness, "roughness")
    mesh_multi = create_mesh(multi_roughness, "roughness")

    vmin = min(true_roughness.min(), single_roughness.min(), multi_roughness.min())
    vmax = max(true_roughness.max(), single_roughness.max(), multi_roughness.max())

    pv.global_theme.background = 'white'
    pv.global_theme.font.color = 'black'

    s_sa = single_err["Sa_error_pct"]
    m_sa = multi_err["Sa_error_pct"]

    labels = [
        "Ground Truth Roughness",
        f"Single Freq (Sa err {s_sa:.1f}%)",
        f"Multi Freq (Sa err {m_sa:.1f}%)",
    ]
    meshes = [mesh_truth, mesh_single, mesh_multi]

    # Static screenshot
    plotter = pv.Plotter(shape=(1, 3), off_screen=True, window_size=(1800, 600))
    for j, (mesh, label) in enumerate(zip(meshes, labels)):
        plotter.subplot(0, j)
        plotter.add_mesh(mesh, scalars="roughness", cmap="coolwarm",
                         clim=[vmin, vmax], show_scalar_bar=False)
        plotter.add_text(label, font_size=11, position="upper_edge")

    plotter.link_views()
    plotter.camera_position = 'iso'
    plotter.camera.zoom(0.85)

    output_path = output_dir / "roughness_3d.png"
    plotter.screenshot(str(output_path))
    print(f"    Saved: {output_path}")
    plotter.close()

    # Rotating animation
    plotter = pv.Plotter(shape=(1, 3), off_screen=True, window_size=(1800, 600))
    for j, (mesh, label) in enumerate(zip(meshes, labels)):
        plotter.subplot(0, j)
        plotter.add_mesh(mesh, scalars="roughness", cmap="coolwarm",
                         clim=[vmin, vmax], show_scalar_bar=False)
        plotter.add_text(label, font_size=11, position="upper_edge")

    plotter.link_views()
    plotter.camera_position = 'iso'
    plotter.camera.zoom(0.85)

    video_path = output_dir / "roughness_3d.mp4"
    plotter.open_movie(str(video_path), framerate=30, quality=8)

    for i in range(90):
        angle = 360 * i / 90
        for j in range(3):
            plotter.subplot(0, j)
            plotter.camera.azimuth = angle
            plotter.camera.elevation = 25
        plotter.write_frame()

    plotter.close()
    print(f"    Saved: {video_path}")
