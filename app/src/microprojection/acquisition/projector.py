"""USB control of the Wintech PRO4500 (TI DLP LightCrafter 4500 / DLPC350).

The app drives the PRO4500 **purely over USB** (DLPC350): power management,
display-mode switching, and high-speed pattern sequencing with hardware camera
triggers. There is no HDMI extended-display path — the projector is treated as a
USB-controlled device, not as a second monitor.

This module wraps the unofficial ``pycrafter4500`` library (USB-HID over ``pyusb``
with a libusb backend). In pattern mode the DLPC350 sequences its patterns at up
to kHz rates and fires a trigger-out pulse per pattern so the camera can capture
in lock-step.

Install the hardware extras and a libusb backend before use::

    pip install -e .[hardware]
    # Windows: bind WinUSB/libusb-win32 to the device with Zadig once.

LED *current* is set over I2C (per the brochure) and is not exposed here; use the
TI LightCrafter 4500 GUI for that. ``led_color`` below only selects which LEDs are
enabled in the sequence.
"""
from __future__ import annotations

from contextlib import contextmanager

# DLPC350 USB descriptor (TI LightCrafter 4500 / Wintech PRO4500).
PRO4500_VID = 0x0451
PRO4500_PID = 0x6401

try:
    import usb.core

    import pycrafter4500

    HAS_PYCRAFTER = True
except ImportError:
    HAS_PYCRAFTER = False


def enumerate_projectors() -> list[dict]:
    """Probe for connected DLPC350-based projectors over USB."""
    if not HAS_PYCRAFTER:
        return []
    found = usb.core.find(find_all=True, idVendor=PRO4500_VID, idProduct=PRO4500_PID)
    projectors = []
    for i, _dev in enumerate(found or []):
        projectors.append(
            {
                "backend": "dlpc350",
                "index": i,
                "name": f"DLP LightCrafter 4500 / PRO4500 (DLPC350) #{i}",
            }
        )
    return projectors


class ProjectorController:
    """Thin, GUI-friendly wrapper over ``pycrafter4500`` for the PRO4500.

    Each call opens a short-lived USB connection (matching the library's own
    convenience functions), so there is no persistent handle to leak. Methods
    raise ``RuntimeError`` with an actionable message when the library or a
    libusb backend is missing, rather than failing deep inside pyusb.
    """

    def __init__(self):
        self._in_pattern_mode = False

    # -- availability ------------------------------------------------------

    @property
    def available(self) -> bool:
        """True if ``pycrafter4500``/``pyusb`` are importable."""
        return HAS_PYCRAFTER

    def is_present(self) -> bool:
        """True if a DLPC350 device is currently enumerable on USB."""
        return bool(enumerate_projectors())

    def _require(self):
        if not HAS_PYCRAFTER:
            raise RuntimeError(
                "USB projector control needs the 'hardware' extra: "
                "pip install -e .[hardware] (plus a libusb backend; "
                "on Windows bind WinUSB to the device with Zadig)."
            )

    @contextmanager
    def _dlp(self):
        """Yield a connected ``dlpc350`` for low-level commands."""
        self._require()
        with pycrafter4500.connect_usb() as lcr:
            yield pycrafter4500.dlpc350(lcr)

    # -- power -------------------------------------------------------------

    def power_up(self) -> None:
        """Wake the projector from standby."""
        self._require()
        pycrafter4500.power_up()

    def power_down(self) -> None:
        """Put the projector into standby."""
        self._require()
        pycrafter4500.power_down()

    # -- display modes -----------------------------------------------------

    def video_mode(self) -> None:
        """Return to plain HDMI video display (mirrors the HDMI window 1:1)."""
        self._require()
        pycrafter4500.video_mode()
        self._in_pattern_mode = False

    def pattern_mode(
        self,
        num_pats: int,
        fps: float,
        *,
        bit_depth: int = 8,
        led_color: int = 0b111,
        trigger_type: str = "vsync",
    ) -> None:
        """Configure and start high-speed pattern sequencing over HDMI.

        Args:
            num_pats: number of distinct patterns per sequence (e.g. the phase
                step count) — these must be present in the HDMI frames.
            fps: sequence rate in frames per second; the DLPC350 derives the
                per-pattern exposure/period from this.
            bit_depth: bits per pattern (1 for binary, up to 8 for grayscale
                sinusoids). HDMI 8-bit grayscale streaming tops out at ~120 Hz;
                binary at ~2880 Hz.
            led_color: bitmask of enabled LEDs (bit0=red, bit1=green, bit2=blue).
            trigger_type: pattern trigger source ('vsync' to advance per HDMI
                frame; the per-pattern trigger-out then drives the camera).
        """
        self._require()
        pycrafter4500.pattern_mode(
            num_pats=num_pats,
            fps=fps,
            bit_depth=bit_depth,
            led_color=led_color,
            trigger_type=trigger_type,
        )
        self._in_pattern_mode = True

    # -- sequence control --------------------------------------------------

    def start_sequence(self) -> None:
        """Start/resume the loaded pattern sequence."""
        with self._dlp() as d:
            d.pattern_display("start")
        self._in_pattern_mode = True

    def stop_sequence(self) -> None:
        """Stop the running pattern sequence."""
        with self._dlp() as d:
            d.pattern_display("stop")
        self._in_pattern_mode = False

    def pause_sequence(self) -> None:
        """Pause the running pattern sequence."""
        with self._dlp() as d:
            d.pattern_display("pause")

    @property
    def in_pattern_mode(self) -> bool:
        return self._in_pattern_mode
