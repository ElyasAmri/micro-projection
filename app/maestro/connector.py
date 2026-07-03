"""WebSocket client that registers this Qt app with a maestro server.

Speaks maestro's `/ext` JSON framing (discriminator field `t`):
  - send    {"t":"register","kind":"qt","token":..,"protocol_version":1}
  - recv    {"t":"registered","kind":"qt"}                       (ack)
  - recv    {"t":"request","req_id":..,"target":"qt","payload":{action,..}}
  - send    {"t":"response","req_id":..,"result":{..}}            (or "error")
  - recv    {"t":"ping"} -> send {"t":"pong"}

It uses Qt's own QWebSocket, so the socket lives on the GUI thread and request
handling touches widgets directly -- no cross-thread marshaling. When no maestro
server is running (or the socket drops) it retries on a timer, so attaching it is
always safe and never blocks app startup.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QObject, QTimer, QUrl, Slot

from maestro.actions import Command, dispatch
from maestro.discovery import Server, discover_one, forget

try:
    from PySide6.QtWebSockets import QWebSocket

    _HAVE_WS = True
except ImportError:  # QtWebSockets is an optional PySide6 module
    QWebSocket = None  # type: ignore[assignment]
    _HAVE_WS = False

logger = logging.getLogger("mp.maestro")

# Must match the harness MAP_PROTOCOL_VERSION; registration is rejected otherwise.
PROTOCOL_VERSION = 1
RECONNECT_MS = 2000


def _coerce(value: Any) -> Any:
    """Ensure a result is JSON-serializable, stringifying it if not."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class MaestroConnector(QObject):
    """Keeps a registered connection to a local maestro server, answering `qt`
    tool requests against this app. Construct via :func:`attach`."""

    def __init__(
        self,
        commands: dict[str, Command] | None = None,
        kind: str = "qt",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._commands: dict[str, Command] = dict(commands or {})
        self._token = ""
        self._registered = False
        # The server this connect attempt targets, and whether the WS
        # handshake completed for it -- lets the error/rejection handlers
        # below tell "never even reached the port" (stale lockfile, prune it)
        # from "was talking to it, then something happened" (ambiguous, leave
        # the lockfile alone; it may still be a genuinely live server).
        self._server: Server | None = None
        self._connected = False

        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.textMessageReceived.connect(self._on_message)
        self._socket.errorOccurred.connect(self._on_socket_error)

        self._reconnect = QTimer(self)
        self._reconnect.setSingleShot(True)
        self._reconnect.setInterval(RECONNECT_MS)
        self._reconnect.timeout.connect(self._connect)

    def register_command(self, name: str, fn: Command) -> None:
        """Expose `fn` to the agent as `invoke command=<name>`."""
        self._commands[name] = fn

    def start(self) -> None:
        """Begin connecting (and keep retrying)."""
        self._connect()

    def stop(self) -> None:
        self._reconnect.stop()
        self._socket.close()

    # -- connection lifecycle -------------------------------------------------

    @Slot()
    def _connect(self) -> None:
        server = discover_one()
        if server is None:
            # No maestro running yet; check again shortly.
            self._reconnect.start()
            return
        self._server = server
        self._connected = False
        self._token = server.token
        self._registered = False
        logger.debug("maestro: connecting to ws://127.0.0.1:%d/ext", server.port)
        self._socket.open(QUrl(f"ws://127.0.0.1:{server.port}/ext"))

    @Slot()
    def _on_connected(self) -> None:
        self._connected = True
        self._send(
            {
                "t": "register",
                "kind": self._kind,
                "token": self._token,
                "protocol_version": PROTOCOL_VERSION,
            }
        )

    @Slot()
    def _on_disconnected(self) -> None:
        if self._registered:
            logger.info("maestro: disconnected; will retry")
        self._registered = False
        self._reconnect.start()

    def _on_socket_error(self, *_args: Any) -> None:
        # A failed open emits errorOccurred (and may not emit disconnected), so
        # ensure a retry is scheduled. The single-shot timer coalesces repeats.
        if self._server is not None and not self._connected:
            # Never even reached the WS handshake: the port is dead (crashed
            # owner) or now belongs to something else entirely. Prune the
            # lockfile so the next attempt, 2s from now, doesn't retry the
            # same dead candidate forever -- discover_one() only ever offers
            # the single best-ranked server, so without this an unreachable
            # top-ranked lockfile would wedge the connector permanently.
            forget(self._server.port)
        if not self._reconnect.isActive():
            self._reconnect.start()

    # -- framing --------------------------------------------------------------

    @Slot(str)
    def _on_message(self, raw: str) -> None:
        try:
            frame = json.loads(raw)
        except ValueError:
            return
        kind = frame.get("t")
        if kind == "request":
            self._handle_request(frame)
        elif kind == "ping":
            self._send({"t": "pong"})
        elif kind == "registered":
            self._registered = True
            logger.info("maestro: registered as kind %r", self._kind)
        elif kind == "error":
            logger.warning("maestro: register rejected: %s", frame.get("message"))
            # Registration is rejected only for a token mismatch, so the
            # lockfile is definitely stale or now describes an unrelated
            # server -- prune it. The harness closes after an error;
            # _on_disconnected reschedules.
            if self._server is not None:
                forget(self._server.port)

    def _handle_request(self, frame: dict) -> None:
        req_id = frame.get("req_id")
        if not isinstance(req_id, str):
            return
        payload = frame.get("payload") or {}
        try:
            result = dispatch(payload, self._commands)
            self._send({"t": "response", "req_id": req_id, "result": _coerce(result)})
        except Exception as exc:  # noqa: BLE001 - any failure becomes a tool error
            self._send({"t": "response", "req_id": req_id, "error": str(exc)})

    def _send(self, frame: dict) -> None:
        self._socket.sendTextMessage(json.dumps(frame))


def attach(
    parent: QObject | None = None,
    commands: dict[str, Command] | None = None,
    kind: str = "qt",
) -> MaestroConnector | None:
    """Start a maestro connector parented to `parent` (e.g. the main window).

    Returns the connector, or None when QtWebSockets is unavailable. Keep a
    reference (parenting to the window does this) so it is not garbage-collected.
    """
    if not _HAVE_WS:
        logger.warning("maestro: PySide6.QtWebSockets not available; connector disabled")
        return None
    connector = MaestroConnector(commands=commands, kind=kind, parent=parent)
    connector.start()
    return connector
