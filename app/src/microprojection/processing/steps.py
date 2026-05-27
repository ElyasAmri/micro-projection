"""Placeholder processing step functions.

Each function has the correct signature for the real algorithm
to be filled in later. Current implementations return zeros.
"""

import numpy as np


def extract_phase(
    image: np.ndarray, n_steps: int = 4, algorithm: str = "n-step"
) -> np.ndarray:
    """Phase-shifting algorithm. Returns wrapped phase map (HxW float64)."""
    h, w = image.shape[:2]
    return np.zeros((h, w), dtype=np.float64)


def unwrap_phase(wrapped: np.ndarray, method: str = "temporal") -> np.ndarray:
    """Phase unwrapping. Returns continuous phase map."""
    return wrapped.copy()


def compute_height(phase: np.ndarray, lambda_eq: float = 0.32) -> np.ndarray:
    """Convert phase to height. Returns height map in mm."""
    return phase * lambda_eq / (2 * np.pi)


def filter_surface(
    height: np.ndarray, cutoff: float = 0.8, method: str = "gaussian"
) -> tuple[np.ndarray, np.ndarray]:
    """Separate waviness from roughness. Returns (roughness, waviness)."""
    return height, np.zeros_like(height)


def compute_roughness(roughness: np.ndarray) -> dict:
    """Compute roughness parameters."""
    return {"Sa": 0.0, "Sq": 0.0, "Sz": 0.0, "Ssk": 0.0, "Sku": 0.0}
