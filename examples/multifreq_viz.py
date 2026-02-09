"""Visualization for multi-frequency roughness comparison."""

from pathlib import Path

import numpy as np


def create_summary_figure(results: list[dict], output_path: Path):
    """Create a publication-quality summary comparing roughness recovery.

    Top: 3 rows x 4 columns of 2D images
      Col 0: Input surface
      Col 1: Ground truth roughness
      Col 2: Single-frequency roughness + Sa error
      Col 3: Multi-frequency roughness + Sa error
    Bottom: Cross-section profile comparison for the complex surface.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec

    n_surfaces = len(results)
    fig = plt.figure(figsize=(14, n_surfaces * 3.4 + 3.6))

    # Main grid: image rows + profile row at the bottom
    outer_gs = GridSpec(
        2, 1, figure=fig,
        height_ratios=[n_surfaces * 3.4, 3.0],
        hspace=0.30,
        left=0.07, right=0.93,
        top=0.93, bottom=0.05,
    )

    # Image grid
    img_gs = outer_gs[0].subgridspec(
        n_surfaces, 4,
        wspace=0.06, hspace=0.18,
    )

    fig.text(
        0.50, 0.97,
        "Multi-Frequency Roughness Recovery: Single vs. Temporal Unwrapping",
        fontsize=14, fontweight="bold", ha="center", va="top",
    )

    col_titles = [
        "Input Surface",
        "Ground Truth Roughness",
        "Single-Freq Roughness",
        "Multi-Freq Roughness",
    ]

    for row, r in enumerate(results):
        surface = r["surface"]
        true_rough = r["true_roughness"]
        single_rough = r["single_roughness"]
        multi_rough = r["multi_roughness"]

        # Tight roughness color limits for visible texture
        valid = true_rough[~np.isnan(true_rough)]
        rough_limit = np.percentile(np.abs(valid), 90)
        rough_clim = (-rough_limit, rough_limit)

        panels = [
            (surface, "terrain", None, None),
            (true_rough, "RdBu_r", rough_clim, None),
            (single_rough, "RdBu_r", rough_clim, r["single_Sa"]),
            (multi_rough, "RdBu_r", rough_clim, r["masked_Sa"]),
        ]

        for col, (data, cmap, clim, sa_err) in enumerate(panels):
            ax = fig.add_subplot(img_gs[row, col])

            plot_data = np.nan_to_num(data, nan=0.0)
            if clim is not None:
                # Clip data to color range for better visibility
                plot_data = np.clip(plot_data, clim[0], clim[1])
                ax.imshow(plot_data, cmap=cmap, vmin=clim[0], vmax=clim[1],
                          aspect="equal", interpolation="nearest")
            else:
                ax.imshow(plot_data, cmap=cmap, aspect="equal",
                          interpolation="nearest")

            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_color("#999999")
                spine.set_linewidth(0.5)

            # Column titles (top row only)
            if row == 0:
                ax.set_title(col_titles[col], fontsize=10, fontweight="bold",
                             pad=6)

            # Row labels (first column only)
            if col == 0:
                label = r["name"].replace("_", " ").title()
                ax.set_ylabel(label, fontsize=10, fontweight="bold",
                              rotation=90, labelpad=8)

            # Sa error badge
            if sa_err is not None:
                bg = "#2e7d32" if sa_err < 10 else "#c62828"
                ax.text(
                    0.97, 0.05,
                    f"Sa err {sa_err:.1f}%",
                    transform=ax.transAxes,
                    fontsize=9, fontweight="bold",
                    ha="right", va="bottom",
                    color="white",
                    bbox=dict(boxstyle="round,pad=0.25",
                              facecolor=bg, alpha=0.9, edgecolor="none"),
                )

    # --- Cross-section profile comparison (complex surface) ---
    challenge = results[-1]  # Last result is complex
    true_r = challenge["true_roughness"]
    single_r = challenge["single_roughness"]
    multi_r = challenge["multi_roughness"]

    mid = true_r.shape[0] // 2
    x_px = np.arange(true_r.shape[1])

    ax_profile = fig.add_subplot(outer_gs[1])
    ax_profile.plot(x_px, true_r[mid, :], color="#333333", linewidth=1.0,
                    label="Ground truth", alpha=0.8)
    ax_profile.plot(x_px, np.nan_to_num(single_r[mid, :], nan=0.0),
                    color="#c62828", linewidth=0.7,
                    label=f"Single-freq (Sa err {challenge['single_Sa']:.1f}%)",
                    alpha=0.7)
    ax_profile.plot(x_px, np.nan_to_num(multi_r[mid, :], nan=0.0),
                    color="#2e7d32", linewidth=0.7,
                    label=f"Multi-freq (Sa err {challenge['masked_Sa']:.1f}%)",
                    alpha=0.7)

    # Y-axis limits: focus on roughness range, single-freq spikes get clipped
    true_valid = true_r[mid, ~np.isnan(true_r[mid, :])]
    profile_limit = np.percentile(np.abs(true_valid), 99.5) * 2.0
    ax_profile.set_ylim(-profile_limit, profile_limit)
    ax_profile.set_xlim(0, true_r.shape[1])
    ax_profile.set_xlabel("Pixel position", fontsize=10)
    ax_profile.set_ylabel("Roughness height", fontsize=10)
    ax_profile.set_title(
        "Cross-Section Profile  \u2014  Challenging Surface (row at y = midpoint)",
        fontsize=10, fontweight="bold", pad=6,
    )
    ax_profile.legend(fontsize=9, loc="upper right", framealpha=0.9)
    ax_profile.tick_params(labelsize=9)
    ax_profile.grid(True, alpha=0.25, linewidth=0.5)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=200, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def visualize_3d(
    ground_truth_surface: np.ndarray,
    true_roughness: np.ndarray,
    single_roughness: np.ndarray,
    multi_roughness: np.ndarray,
    single_err: dict,
    multi_err: dict,
    output_dir: Path,
):
    """Create 3D PyVista visualization comparing roughness recovery.

    Layout: 2x2 grid
      Top-left:     Ground truth surface (form + roughness)
      Top-right:    Ground truth roughness
      Bottom-left:  Single-freq recovered roughness
      Bottom-right: Multi-freq recovered roughness
    """
    import pyvista as pv

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    h, w = true_roughness.shape
    x = np.arange(w, dtype=np.float64)
    y = np.arange(h, dtype=np.float64)
    x_grid, y_grid = np.meshgrid(x, y)

    # --- Auto-scale roughness z to be visible relative to grid size ---
    true_clean = true_roughness[~np.isnan(true_roughness)]
    rough_p99 = np.percentile(np.abs(true_clean), 99)
    # Target: roughness peaks ~15% of grid width for clear texture visibility
    target_z = 0.15 * w
    rough_z_scale = target_z / (rough_p99 + 1e-12)

    # Clip recovered roughness to 4x ground truth range (removes extreme spikes)
    clip_val = rough_p99 * 4.0

    # Surface z-scale: make surface height variation ~40% of grid width
    surf_range = ground_truth_surface.max() - ground_truth_surface.min()
    surf_z_scale = (0.40 * w) / (surf_range + 1e-12)

    def make_roughness_mesh(data, name):
        cleaned = np.nan_to_num(data, nan=0.0)
        clipped = np.clip(cleaned, -clip_val, clip_val)
        z = clipped * rough_z_scale
        grid = pv.StructuredGrid(x_grid, y_grid, z)
        grid[name] = clipped.flatten(order='F')
        return grid

    def make_surface_mesh(data, name):
        z = data * surf_z_scale
        grid = pv.StructuredGrid(x_grid, y_grid, z)
        grid[name] = data.flatten(order='F')
        return grid

    # Build meshes
    mesh_surface = make_surface_mesh(ground_truth_surface, "height")
    mesh_truth = make_roughness_mesh(true_roughness, "roughness")
    mesh_single = make_roughness_mesh(single_roughness, "roughness")
    mesh_multi = make_roughness_mesh(multi_roughness, "roughness")

    rough_clim = [-clip_val, clip_val]
    surf_clim = [ground_truth_surface.min(), ground_truth_surface.max()]

    s_sa = single_err["Sa_error_pct"]
    m_sa = multi_err["Sa_error_pct"]

    pv.global_theme.background = 'white'
    pv.global_theme.font.color = 'black'

    # --- Static screenshot (2x2) ---
    plotter = pv.Plotter(shape=(2, 2), off_screen=True, window_size=(1600, 1200))

    # Top-left: ground truth surface
    plotter.subplot(0, 0)
    plotter.add_mesh(mesh_surface, scalars="height", cmap="terrain",
                     clim=surf_clim, show_scalar_bar=False)
    plotter.add_text("Ground Truth Surface", font_size=10, position="upper_edge")

    # Top-right: ground truth roughness
    plotter.subplot(0, 1)
    plotter.add_mesh(mesh_truth, scalars="roughness", cmap="coolwarm",
                     clim=rough_clim, show_scalar_bar=False)
    plotter.add_text("Ground Truth Roughness", font_size=10, position="upper_edge")

    # Bottom-left: single-freq roughness
    plotter.subplot(1, 0)
    plotter.add_mesh(mesh_single, scalars="roughness", cmap="coolwarm",
                     clim=rough_clim, show_scalar_bar=False)
    plotter.add_text(f"Single Freq (Sa err {s_sa:.1f}%)", font_size=10,
                     position="upper_edge")

    # Bottom-right: multi-freq roughness
    plotter.subplot(1, 1)
    plotter.add_mesh(mesh_multi, scalars="roughness", cmap="coolwarm",
                     clim=rough_clim, show_scalar_bar=False)
    plotter.add_text(f"Multi Freq (Sa err {m_sa:.1f}%)", font_size=10,
                     position="upper_edge")

    plotter.link_views()
    plotter.camera_position = 'iso'
    plotter.camera.zoom(0.85)

    output_path = output_dir / "roughness_3d.png"
    plotter.screenshot(str(output_path))
    print(f"    Saved: {output_path}")
    plotter.close()

    # --- Rotating animation (2x2) ---
    plotter = pv.Plotter(shape=(2, 2), off_screen=True, window_size=(1600, 1200))

    plotter.subplot(0, 0)
    plotter.add_mesh(mesh_surface, scalars="height", cmap="terrain",
                     clim=surf_clim, show_scalar_bar=False)
    plotter.add_text("Ground Truth Surface", font_size=10, position="upper_edge")

    plotter.subplot(0, 1)
    plotter.add_mesh(mesh_truth, scalars="roughness", cmap="coolwarm",
                     clim=rough_clim, show_scalar_bar=False)
    plotter.add_text("Ground Truth Roughness", font_size=10, position="upper_edge")

    plotter.subplot(1, 0)
    plotter.add_mesh(mesh_single, scalars="roughness", cmap="coolwarm",
                     clim=rough_clim, show_scalar_bar=False)
    plotter.add_text(f"Single Freq (Sa err {s_sa:.1f}%)", font_size=10,
                     position="upper_edge")

    plotter.subplot(1, 1)
    plotter.add_mesh(mesh_multi, scalars="roughness", cmap="coolwarm",
                     clim=rough_clim, show_scalar_bar=False)
    plotter.add_text(f"Multi Freq (Sa err {m_sa:.1f}%)", font_size=10,
                     position="upper_edge")

    plotter.link_views()
    plotter.camera_position = 'iso'
    plotter.camera.zoom(0.85)

    video_path = output_dir / "roughness_3d.mp4"
    plotter.open_movie(str(video_path), framerate=30, quality=8)

    n_subplots = 4
    for i in range(90):
        angle = 360 * i / 90
        for row in range(2):
            for col in range(2):
                plotter.subplot(row, col)
                plotter.camera.azimuth = angle
                plotter.camera.elevation = 25
        plotter.write_frame()

    plotter.close()
    print(f"    Saved: {video_path}")
