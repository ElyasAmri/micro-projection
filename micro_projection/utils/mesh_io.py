"""3D mesh loading and conversion utilities."""

import numpy as np

try:
    import pyvista as pv
    HAS_PYVISTA = True
except ImportError:
    HAS_PYVISTA = False


def load_surface_from_model(model_path: str, resolution: tuple[int, int]) -> np.ndarray:
    """Load a 3D model and convert to height map.

    Supports STL, OBJ, PLY formats using PyVista.

    Args:
        model_path: Path to the 3D model file
        resolution: Target resolution (height, width)

    Returns:
        Height map as numpy array

    Raises:
        ImportError: If PyVista is not installed
    """
    if not HAS_PYVISTA:
        raise ImportError(
            "PyVista is required to load 3D models. Install with: pip install pyvista"
        )

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

    # Normalize to 0-1 range and scale to appropriate height
    height_map = height_map - height_map.min()
    if height_map.max() > 0:
        height_map = height_map / height_map.max() * 0.1  # Scale to reasonable height

    return height_map
