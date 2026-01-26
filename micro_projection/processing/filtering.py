"""Surface filtering for separating form (waviness) from finish (roughness)."""

import numpy as np
from typing import Literal
from scipy import ndimage

from ..core.datatypes import HeightMap, SurfaceAnalysis


def separate_surface(
    height_map: HeightMap,
    cutoff_wavelength: float,
    method: Literal["gaussian", "lowpass", "highpass"] = "gaussian",
) -> SurfaceAnalysis:
    """Separate surface into form (low-frequency) and finish (high-frequency) components.

    This implements the dual-frequency separation approach where:
        total = form + finish
        h = h1 + h2

    Where:
        - form (h1): Low-frequency waviness, shape deviations
        - finish (h2): High-frequency roughness, surface texture

    Args:
        height_map: Input height map to separate
        cutoff_wavelength: Cutoff wavelength in the same unit as pixel_pitch
                          Features larger than this go to form, smaller to finish
        method: Filtering method to use:
            - "gaussian": Gaussian low-pass filter (recommended)
            - "lowpass": Simple moving average
            - "highpass": Complement of lowpass

    Returns:
        SurfaceAnalysis with total, form, and finish components
    """
    # Convert cutoff wavelength to pixels
    cutoff_pixels = cutoff_wavelength / height_map.pixel_pitch

    if method == "gaussian":
        form_data = _gaussian_filter(height_map.data, cutoff_pixels)
    elif method == "lowpass":
        form_data = _moving_average_filter(height_map.data, cutoff_pixels)
    else:  # highpass - compute form as complement
        form_data = _gaussian_filter(height_map.data, cutoff_pixels)

    # Finish is the high-frequency component (total - form)
    finish_data = height_map.data - form_data

    # Create HeightMap objects for each component
    form_metadata = height_map.metadata.copy()
    form_metadata["component"] = "form"
    form_metadata["cutoff_wavelength"] = cutoff_wavelength
    form_metadata["filter_method"] = method

    finish_metadata = height_map.metadata.copy()
    finish_metadata["component"] = "finish"
    finish_metadata["cutoff_wavelength"] = cutoff_wavelength
    finish_metadata["filter_method"] = method

    form = HeightMap(
        data=form_data,
        unit=height_map.unit,
        pixel_pitch=height_map.pixel_pitch,
        equivalent_wavelength=height_map.equivalent_wavelength,
        metadata=form_metadata,
    )

    finish = HeightMap(
        data=finish_data,
        unit=height_map.unit,
        pixel_pitch=height_map.pixel_pitch,
        equivalent_wavelength=height_map.equivalent_wavelength,
        metadata=finish_metadata,
    )

    return SurfaceAnalysis(total=height_map, form=form, finish=finish)


def _gaussian_filter(data: np.ndarray, sigma_pixels: float) -> np.ndarray:
    """Apply Gaussian low-pass filter.

    The sigma is related to cutoff wavelength by:
        sigma ~= cutoff_wavelength / (2*pi)

    For a Gaussian filter, the -3dB cutoff frequency is at:
        f_c = 1 / (2*pi*sigma)
    """
    # sigma for Gaussian filter
    sigma = sigma_pixels / (2.0 * np.pi)
    return ndimage.gaussian_filter(data, sigma=sigma, mode='reflect')


def _moving_average_filter(data: np.ndarray, window_pixels: float) -> np.ndarray:
    """Apply simple moving average (box) filter.

    Less ideal frequency response than Gaussian but computationally simpler.
    """
    window_size = max(3, int(window_pixels))
    if window_size % 2 == 0:
        window_size += 1  # Ensure odd size

    kernel = np.ones((window_size, window_size)) / (window_size * window_size)
    return ndimage.convolve(data, kernel, mode='reflect')


def compute_roughness_parameters(height_map: HeightMap) -> dict:
    """Compute standard surface roughness parameters.

    Computes common roughness parameters per ISO 25178:
        - Sa: Arithmetical mean height
        - Sq: Root mean square height
        - Sp: Maximum peak height
        - Sv: Maximum valley depth
        - Sz: Maximum height (Sp + Sv)
        - Ssk: Skewness
        - Sku: Kurtosis

    Args:
        height_map: Input height map (typically the finish component)

    Returns:
        Dictionary of roughness parameters with their values
    """
    data = height_map.data

    # Remove any NaN values for statistics
    valid_data = data[~np.isnan(data)]

    if len(valid_data) == 0:
        return {}

    # Mean (should be ~0 for properly filtered finish)
    mean = np.mean(valid_data)
    centered = valid_data - mean

    # Sa: Arithmetical mean height
    sa = np.mean(np.abs(centered))

    # Sq: Root mean square height
    sq = np.sqrt(np.mean(centered**2))

    # Sp: Maximum peak height
    sp = np.max(centered)

    # Sv: Maximum valley depth (positive value)
    sv = -np.min(centered)

    # Sz: Maximum height
    sz = sp + sv

    # Ssk: Skewness
    if sq > 0:
        ssk = np.mean(centered**3) / (sq**3)
    else:
        ssk = 0.0

    # Sku: Kurtosis
    if sq > 0:
        sku = np.mean(centered**4) / (sq**4)
    else:
        sku = 0.0

    return {
        "Sa": sa,
        "Sq": sq,
        "Sp": sp,
        "Sv": sv,
        "Sz": sz,
        "Ssk": ssk,
        "Sku": sku,
        "unit": height_map.unit,
    }


def apply_bandpass_filter(
    height_map: HeightMap,
    low_cutoff: float,
    high_cutoff: float,
) -> HeightMap:
    """Apply bandpass filter to extract specific wavelength range.

    Useful for analyzing specific spatial frequency bands.

    Args:
        height_map: Input height map
        low_cutoff: Lower cutoff wavelength (larger features removed)
        high_cutoff: Upper cutoff wavelength (smaller features removed)

    Returns:
        Filtered HeightMap containing only the specified wavelength range
    """
    if low_cutoff <= high_cutoff:
        raise ValueError("low_cutoff must be greater than high_cutoff")

    # Convert to pixels
    low_sigma = low_cutoff / (height_map.pixel_pitch * 2.0 * np.pi)
    high_sigma = high_cutoff / (height_map.pixel_pitch * 2.0 * np.pi)

    # Bandpass = lowpass(low) - lowpass(high)
    low_filtered = ndimage.gaussian_filter(height_map.data, sigma=low_sigma, mode='reflect')
    high_filtered = ndimage.gaussian_filter(height_map.data, sigma=high_sigma, mode='reflect')

    bandpass_data = low_filtered - high_filtered

    metadata = height_map.metadata.copy()
    metadata["filter_type"] = "bandpass"
    metadata["low_cutoff"] = low_cutoff
    metadata["high_cutoff"] = high_cutoff

    return HeightMap(
        data=bandpass_data,
        unit=height_map.unit,
        pixel_pitch=height_map.pixel_pitch,
        equivalent_wavelength=height_map.equivalent_wavelength,
        metadata=metadata,
    )
