"""Maestro connector: let a running maestro agent drive this Qt app.

Embeds a WebSocket client that registers with a local maestro server (kind
"qt") and answers the `qt` tool's action requests against this app's widget
tree, mirroring how maestro drives a Tauri app via `maestro-tauri-connect`.

Use `attach(app, window, commands=...)` from the app entry point; it is a no-op
when no maestro server is running, so it never blocks normal startup.
"""
from __future__ import annotations

from maestro.connector import MaestroConnector, attach

__all__ = ["MaestroConnector", "attach"]
