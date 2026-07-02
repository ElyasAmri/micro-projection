"""Single-instance guard.

The first instance listens on a uniquely-named local socket (QLocalServer);
later instances detect it by connecting (QLocalSocket) and bow out, emitting a
nudge so the primary can raise its window. On a crash the stale socket is
removed before re-listening, so the guard self-heals rather than wedging the
app shut.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

KEY = "micro-projection-control"
CONNECT_TIMEOUT_MS = 200


class SingleInstance(QObject):
    """Owns the local server for the primary instance.

    `another_running` is True when a primary already exists (this process should
    exit). Otherwise this instance becomes the primary and emits
    `activate_requested` whenever a later instance tries to launch.
    """

    activate_requested = Signal()

    def __init__(self, key: str = KEY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server: QLocalServer | None = None
        self.another_running = self._primary_exists()
        if not self.another_running:
            self._become_primary()

    def _primary_exists(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._key)
        connected = socket.waitForConnected(CONNECT_TIMEOUT_MS)
        socket.abort()
        return connected

    def _become_primary(self) -> None:
        QLocalServer.removeServer(self._key)  # clear a stale socket left by a crash
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(self._key)

    def _on_new_connection(self) -> None:
        conn = self._server.nextPendingConnection()
        if conn is not None:
            conn.close()
        self.activate_requested.emit()
