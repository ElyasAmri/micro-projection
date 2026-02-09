"""Surface filtering for separating form (waviness) from finish (roughness)."""

import numpy as np
from typing import Literal, Optional
from scipy import ndimage
from scipy import fft

from ..core.datatypes import HeightMap, SurfaceAnalysis


def separate_surface(
    height_map: HeightMap,
    cutoff_wavelength: float,
    method: Literal["gaussian", "lowpass", "highpass", "butterworth", "ideal", "morphological"] = "gaussian",
    order: int = 2,
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
            - "gaussian": Gaussian low-pass filter (smooth rolloff, recommended)
            - "lowpass": Simple moving average
            - "highpass": Complement of lowpass
            - "butterworth": Butterworth filter (sharper cutoff than Gaussian)
            - "ideal": Brick-wall filter (WARNING: causes ringing artifacts)
            - "morphological": Opening/closing average (robust at step edges)
        order: Filter order for Butterworth filter (default 2).
               Higher order = sharper cutoff but may cause ringing.
               Typical values: 2-6.

    Returns:
        SurfaceAnalysis with total, form, and finish components
    """
    # Convert cutoff wavelength to pixels
    cutoff_pixels = cutoff_wavelength / height_map.pixel_pitch

    if method == "gaussian":
        form_data = _gaussian_filter(height_map.data, cutoff_pixels)
    elif method == "lowpass":
        form_data = _moving_average_filter(height_map.data, cutoff_pixels)
    elif method == "butterworth":
        form_data = _butterworth_filter(height_map.data, cutoff_pixels, order)
    elif method == "ideal":
        form_data = _ideal_filter(height_map.data, cutoff_pixels)
    elif method == "morphological":
        form_data = _morphological_filter(height_map.data, cutoff_pixels)
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


def _ideal_filter(data: np.ndarray, cutoff_pixels: float) -> np.ndarray:
    """Apply ideal (brick-wall) low-pass filter in frequency domain.

    WARNING: Ideal filters cause Gibbs phenomenon (ringing artifacts) near
    sharp features. Not recommended for production use - prefer Butterworth
    for a balance of sharpness and artifact avoidance.

    Args:
        data: Input 2D array
        cutoff_pixels: Cutoff wavelength in pixels

    Returns:
        Filtered array (low-frequency component)
    """
    rows, cols = data.shape

    # Compute 2D FFT
    data_fft = fft.fft2(data)
    data_fft_shifted = fft.fftshift(data_fft)

    # Create frequency grid
    freq_y = fft.fftshift(fft.fftfreq(rows))
    freq_x = fft.fftshift(fft.fftfreq(cols))
    fx, fy = np.meshgrid(freq_x, freq_y)

    # Radial frequency
    freq_radius = np.sqrt(fx**2 + fy**2)

    # Cutoff frequency
    cutoff_freq = 1.0 / cutoff_pixels

    # Ideal brick-wall: 1 below cutoff, 0 above
    ideal_h = (freq_radius <= cutoff_freq).astype(np.float64)

    # Apply filter
    filtered_fft = data_fft_shifted * ideal_h

    # Inverse FFT
    filtered_fft_unshifted = fft.ifftshift(filtered_fft)
    filtered_data = fft.ifft2(filtered_fft_unshifted)

    return np.real(filtered_data)


def _butterworth_filter(data: np.ndarray, cutoff_pixels: float, order: int = 2) -> np.ndarray:
    """Apply Butterworth low-pass filter in frequency domain.

    The Butterworth filter provides a maximally flat passband with sharper
    cutoff than Gaussian. Higher orders give sharper cutoffs but may cause
    ringing artifacts.

    Transfer function: H(f) = 1 / sqrt(1 + (f/fc)^(2n))

    Args:
        data: Input 2D array
        cutoff_pixels: Cutoff wavelength in pixels
        order: Filter order (default 2). Higher = sharper cutoff.

    Returns:
        Filtered array (low-frequency component)
    """
    rows, cols = data.shape

    # Compute 2D FFT
    data_fft = fft.fft2(data)
    data_fft_shifted = fft.fftshift(data_fft)

    # Create frequency grid (normalized to Nyquist)
    freq_y = fft.fftshift(fft.fftfreq(rows))
    freq_x = fft.fftshift(fft.fftfreq(cols))
    fx, fy = np.meshgrid(freq_x, freq_y)

    # Radial frequency (distance from center in frequency space)
    freq_radius = np.sqrt(fx**2 + fy**2)

    # Cutoff frequency (cycles per pixel)
    # cutoff_pixels is wavelength, so cutoff frequency = 1/cutoff_pixels
    cutoff_freq = 1.0 / cutoff_pixels

    # Butterworth transfer function: H(f) = 1 / sqrt(1 + (f/fc)^(2n))
    # Avoid division by zero at DC
    with np.errstate(divide='ignore', invalid='ignore'):
        freq_ratio = freq_radius / cutoff_freq
        butterworth_h = 1.0 / np.sqrt(1.0 + np.power(freq_ratio, 2 * order))

    # Handle DC component (should be 1.0)
    butterworth_h[rows // 2, cols // 2] = 1.0

    # Apply filter in frequency domain
    filtered_fft = data_fft_shifted * butterworth_h

    # Inverse FFT
    filtered_fft_unshifted = fft.ifftshift(filtered_fft)
    filtered_data = fft.ifft2(filtered_fft_unshifted)

    return np.real(filtered_data)


def _morphological_filter(data: np.ndarray, cutoff_pixels: float) -> np.ndarray:
    """Extract form using morphological opening + closing average.

    This is robust at step discontinuities because morphological operations
    follow the surface shape without bleeding across edges (unlike Gaussian).

    The form is computed as: (opening + closing) / 2
    - Opening (erode then dilate) removes peaks
    - Closing (dilate then erode) fills valleys
    - Average gives a robust envelope estimate
    """
    from scipy.ndimage import grey_opening, grey_closing

    # Structuring element size from cutoff wavelength
    size = max(3, int(cutoff_pixels / (2 * np.pi)))
    if size % 2 == 0:
        size += 1

    opened = grey_opening(data, size=(size, size))
    closed = grey_closing(data, size=(size, size))
    return (opened + closed) / 2.0


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
    method: Literal["gaussian", "butterworth", "ideal"] = "gaussian",
    order: int = 2,
) -> HeightMap:
    """Apply bandpass filter to extract specific wavelength range.

    Useful for analyzing specific spatial frequency bands.

    Args:
        height_map: Input height map
        low_cutoff: Lower cutoff wavelength (larger features removed)
        high_cutoff: Upper cutoff wavelength (smaller features removed)
        method: Filter method - "gaussian", "butterworth", or "ideal"
        order: Filter order for Butterworth (default 2)

    Returns:
        Filtered HeightMap containing only the specified wavelength range
    """
    if low_cutoff <= high_cutoff:
        raise ValueError(
            "low_cutoff (larger wavelength) must be greater than high_cutoff (smaller wavelength). "
            "low_cutoff removes larger features, high_cutoff removes smaller features."
        )

    # Convert to pixels
    low_pixels = low_cutoff / height_map.pixel_pitch
    high_pixels = high_cutoff / height_map.pixel_pitch

    if method == "butterworth":
        low_filtered = _butterworth_filter(height_map.data, low_pixels, order)
        high_filtered = _butterworth_filter(height_map.data, high_pixels, order)
    elif method == "ideal":
        low_filtered = _ideal_filter(height_map.data, low_pixels)
        high_filtered = _ideal_filter(height_map.data, high_pixels)
    else:  # gaussian
        low_sigma = low_pixels / (2.0 * np.pi)
        high_sigma = high_pixels / (2.0 * np.pi)
        low_filtered = ndimage.gaussian_filter(height_map.data, sigma=low_sigma, mode='reflect')
        high_filtered = ndimage.gaussian_filter(height_map.data, sigma=high_sigma, mode='reflect')

    bandpass_data = low_filtered - high_filtered

    metadata = height_map.metadata.copy()
    metadata["filter_type"] = "bandpass"
    metadata["filter_method"] = method
    metadata["low_cutoff"] = low_cutoff
    metadata["high_cutoff"] = high_cutoff
    if method == "butterworth":
        metadata["filter_order"] = order

    return HeightMap(
        data=bandpass_data,
        unit=height_map.unit,
        pixel_pitch=height_map.pixel_pitch,
        equivalent_wavelength=height_map.equivalent_wavelength,
        metadata=metadata,
    )
