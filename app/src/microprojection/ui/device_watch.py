"""Windows device hot-plug watcher.

Installs as a Qt native event filter and emits ``changed`` whenever the OS
reports a device-tree change (``WM_DEVICECHANGE`` / ``DBT_DEVNODES_CHANGED``),
so the camera list can refresh itself instead of needing a manual button.
Windows fires several messages per physical plug event, so emissions are
debounced into a single ``changed`` after things settle.

No-op on non-Windows platforms (the event filter simply never matches).
"""
from __future__ import annotations

import sys
from ctypes.wintypes import MSG

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal

WM_DEVICECHANGE = 0x0219
DBT_DEVNODES_CHANGED = 0x0007       # generic device-tree change (no registration)
DBT_DEVICEARRIVAL = 0x8000
DBT_DEVICEREMOVECOMPLETE = 0x8004

_DEVICE_EVENTS = {
    DBT_DEVNODES_CHANGED,
    DBT_DEVICEARRIVAL,
    DBT_DEVICEREMOVECOMPLETE,
}


class DeviceWatcher(QAbstractNativeEventFilter, QObject):
    """Emits ``changed`` (debounced) when a device is plugged or unplugged."""

    changed = Signal()

    def __init__(self, debounce_ms: int = 800, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self.changed)

    def nativeEventFilter(self, event_type, message):
        # PySide6 contract: return (handled: bool, result: int).
        if sys.platform == "win32" and event_type == "windows_generic_MSG":
            msg = MSG.from_address(int(message))
            if msg.message == WM_DEVICECHANGE and msg.wParam in _DEVICE_EVENTS:
                self._timer.start()  # (re)start the debounce window
        return False, 0
