"""Display enumeration that hides the user's actual desktop screens.

The projector picker should only list real projection targets, never the
monitor(s) the operator works on. Windows exposes no "this display is a
projector" flag (only the connector technology: HDMI, DisplayPort, internal,
etc.), so we approximate "desktop screen" as:

  * the primary screen (where the desktop and taskbar live), and
  * any built-in / internal panel (a laptop's own screen).

Everything else is an external display and a candidate projection target. The
internal-panel test uses the Win32 ``QueryDisplayConfig`` output technology;
on non-Windows platforms only the primary screen is excluded.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QApplication

# DISPLAYCONFIG_OUTPUT_TECHNOLOGY_INTERNAL: a built-in panel (laptop screen).
_OUTPUT_TECHNOLOGY_INTERNAL = 0x80000000
_QDC_ONLY_ACTIVE_PATHS = 0x00000002
_DEVICE_INFO_GET_SOURCE_NAME = 1
_ERROR_SUCCESS = 0


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("statusFlags", wintypes.UINT),
    ]


class _PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("outputTechnology", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("scaling", wintypes.UINT),
        ("refreshNumerator", wintypes.UINT),
        ("refreshDenominator", wintypes.UINT),
        ("scanLineOrdering", wintypes.UINT),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", wintypes.UINT),
    ]


class _PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", _PATH_SOURCE_INFO),
        ("targetInfo", _PATH_TARGET_INFO),
        ("flags", wintypes.UINT),
    ]


class _MODE_INFO(ctypes.Structure):
    # 16-byte header plus a 48-byte union (largest member is the target mode).
    _fields_ = [
        ("infoType", wintypes.UINT),
        ("id", wintypes.UINT),
        ("adapterId", _LUID),
        ("data", ctypes.c_byte * 48),
    ]


class _DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
    ]


class _SOURCE_DEVICE_NAME(ctypes.Structure):
    _fields_ = [
        ("header", _DEVICE_INFO_HEADER),
        ("viewGdiDeviceName", wintypes.WCHAR * 32),
    ]


def _internal_gdi_names() -> set[str]:
    """GDI device names ("\\\\.\\DISPLAYn") of built-in internal panels."""
    try:
        user32 = ctypes.windll.user32
    except (AttributeError, OSError):
        return set()

    num_path = wintypes.UINT()
    num_mode = wintypes.UINT()
    if user32.GetDisplayConfigBufferSizes(
        _QDC_ONLY_ACTIVE_PATHS, ctypes.byref(num_path), ctypes.byref(num_mode)
    ) != _ERROR_SUCCESS:
        return set()

    paths = (_PATH_INFO * num_path.value)()
    modes = (_MODE_INFO * num_mode.value)()
    if user32.QueryDisplayConfig(
        _QDC_ONLY_ACTIVE_PATHS,
        ctypes.byref(num_path), paths,
        ctypes.byref(num_mode), modes,
        None,
    ) != _ERROR_SUCCESS:
        return set()

    internal: set[str] = set()
    for i in range(num_path.value):
        path = paths[i]
        if path.targetInfo.outputTechnology != _OUTPUT_TECHNOLOGY_INTERNAL:
            continue
        name = _SOURCE_DEVICE_NAME()
        name.header.type = _DEVICE_INFO_GET_SOURCE_NAME
        name.header.size = ctypes.sizeof(name)
        name.header.adapterId = path.sourceInfo.adapterId
        name.header.id = path.sourceInfo.id
        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(name.header)) == _ERROR_SUCCESS:
            internal.add(name.viewGdiDeviceName)
    return internal


def projector_screens() -> list[dict]:
    """External displays usable as projector targets.

    Returns a list of ``{"index", "name"}`` where ``index`` is the position in
    ``QApplication.screens()`` (so callers can resolve it back to a QScreen).
    The primary screen and any internal panel are omitted.
    """
    app = QApplication.instance()
    if app is None:
        return []
    primary = app.primaryScreen()
    internal = _internal_gdi_names() if sys.platform == "win32" else set()

    out: list[dict] = []
    for i, screen in enumerate(app.screens()):
        if screen is primary:
            continue
        if screen.name() in internal:
            continue
        geo = screen.geometry()
        out.append(
            {"index": i, "name": f"{screen.name()} ({geo.width()}x{geo.height()})"}
        )
    return out
