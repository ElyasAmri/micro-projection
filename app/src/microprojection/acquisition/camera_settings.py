"""Camera configuration values applied to the FLIR/PySpin device.

A plain settings record shared by the settings dialog (which edits it) and the
acquisition thread (which applies it to the camera at acquisition start). Field
defaults match the values the acquisition thread used before the dialog existed,
so an untouched instance reproduces the previous fixed configuration.

String fields hold PySpin enum-entry names (e.g. "Off", "Mono8", "Line0") so the
thread can map them straight onto ``PySpin.<Node>_<entry>`` constants.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CameraSettings:
    # Exposure and gain. "Off" uses the fixed value below; "Once"/"Continuous"
    # let the camera drive it.
    exposure_auto: str = "Off"
    exposure_time_us: float = 20000.0
    gain_auto: str = "Off"
    gain_db: float = 0.0

    # Image format. pixel_format and bit_depth are PySpin enum-entry names;
    # bit_depth None leaves the camera default.
    pixel_format: str = "Mono8"
    bit_depth: str | None = None

    # Region of interest. When roi_enable is False the full sensor is used.
    roi_enable: bool = False
    roi_width: int = 0
    roi_height: int = 0
    roi_offset_x: int = 0
    roi_offset_y: int = 0

    # Binning (1 = no binning).
    binning_horizontal: int = 1
    binning_vertical: int = 1

    # Image orientation.
    reverse_x: bool = False
    reverse_y: bool = False

    # Gamma. Off (linear) is wanted for fringe projection so the captured sine
    # is not distorted by a display curve.
    gamma_enable: bool = False
    gamma: float = 1.0

    # Frame rate. 29.97 fps default.
    frame_rate_enable: bool = True
    frame_rate: float = 29.97

    # Trigger: "Off" (free-run), "Software" (fire per frame), or "Hardware".
    trigger_mode: str = "Off"
    trigger_source: str = "Line0"
    trigger_activation: str = "RisingEdge"

    # Stream buffer handling: "NewestOnly" avoids stale frames.
    stream_buffer_mode: str = "NewestOnly"
