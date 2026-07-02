"""End-to-end proof that the connector talks to a maestro-shaped server.

Stands up a real WebSocket server that speaks maestro's `/ext` framing exactly as
the harness does (register ack, then `request` frames), points the connector at
it via a lockfile, and checks a full round-trip: discovery -> connect -> register
-> request -> action dispatch on a real widget -> response.

This exercises the connector half of the protocol over a real socket; the harness
half (the `qt` tool calling the shared extension bridge) is the same plumbing the
shipped `desktop` and `chrome` tools already use.
"""
from __future__ import annotations

import json
import time

import pytest
from PySide6.QtCore import QObject
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocketServer
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget
from shiboken6 import delete

from microprojection.maestro.connector import MaestroConnector


class FakeHarness(QObject):
    """A minimal stand-in for the harness `/ext` endpoint."""

    def __init__(self, token: str) -> None:
        super().__init__()
        self.token = token
        self.registered: dict | None = None
        self.responses: list[dict] = []
        self._client = None
        self._server = QWebSocketServer("fake-maestro", QWebSocketServer.SslMode.NonSecureMode)
        if not self._server.listen(QHostAddress(QHostAddress.SpecialAddress.LocalHost)):
            raise RuntimeError("could not listen")
        self.port = self._server.serverPort()
        self._server.newConnection.connect(self._on_connection)

    def _on_connection(self) -> None:
        self._client = self._server.nextPendingConnection()
        self._client.textMessageReceived.connect(self._on_message)

    def _on_message(self, raw: str) -> None:
        frame = json.loads(raw)
        if frame.get("t") == "register":
            self.registered = frame
            self._client.sendTextMessage(
                json.dumps({"t": "registered", "kind": frame.get("kind")})
            )
        elif frame.get("t") == "response":
            self.responses.append(frame)

    def send_request(self, payload: dict, req_id: str = "req-1") -> None:
        self._client.sendTextMessage(
            json.dumps({"t": "request", "req_id": req_id, "target": "qt", "payload": payload})
        )

    def close(self) -> None:
        self._server.close()


def _wait_until(qapp, predicate, timeout_ms: int = 5000) -> bool:
    """Pump the event loop until `predicate` holds or the timeout elapses."""
    end = time.monotonic() + timeout_ms / 1000
    while not predicate() and time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)
    return predicate()


def test_connector_round_trip(qapp, tmp_path, monkeypatch):
    token = "live-token"
    harness = FakeHarness(token)

    # Point discovery at our fake server and nothing else.
    monkeypatch.delenv("MAESTRO_SERVER_PORT", raising=False)
    monkeypatch.delenv("MAESTRO_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    servers = tmp_path / ".maestro" / "servers"
    servers.mkdir(parents=True)
    (servers / f"{harness.port}.json").write_text(
        json.dumps({"port": harness.port, "token": token, "started_at_ms": 1})
    )

    # A real window the connector will act on.
    win = QWidget()
    win.setObjectName("main")
    win.setWindowTitle("Live")
    layout = QVBoxLayout(win)
    edit = QLineEdit()
    edit.setObjectName("name_edit")
    edit.setText("before")
    layout.addWidget(edit)
    win.show()

    connector = MaestroConnector(
        commands={"ping": lambda args: {"ok": True, "echo": args}},
        kind="qt",
    )
    connector.start()

    try:
        # 1. Registration handshake.
        assert _wait_until(qapp, lambda: harness.registered is not None), "never registered"
        assert harness.registered["kind"] == "qt"
        assert harness.registered["token"] == token
        assert harness.registered["protocol_version"] == 1

        # 2. An invoke command round-trips its args.
        harness.send_request({"action": "invoke", "command": "ping", "args": {"x": 42}}, "r-invoke")
        assert _wait_until(qapp, lambda: harness.responses), "no invoke response"
        resp = harness.responses[-1]
        assert resp["req_id"] == "r-invoke"
        assert resp["result"] == {"ok": True, "echo": {"x": 42}}

        # 3. A widget action actually mutates the live widget.
        harness.responses.clear()
        harness.send_request(
            {"action": "set_value", "selector": "name_edit", "value": "after", "label": "main"},
            "r-set",
        )
        assert _wait_until(qapp, lambda: harness.responses), "no set_value response"
        assert harness.responses[-1]["result"] == {"set": True, "selector": "name_edit"}
        assert edit.text() == "after"

        # 4. A failing action comes back as an error, not a crash.
        harness.responses.clear()
        harness.send_request({"action": "click", "selector": "nope", "label": "main"}, "r-bad")
        assert _wait_until(qapp, lambda: harness.responses), "no error response"
        assert "error" in harness.responses[-1]
    finally:
        connector.stop()
        harness.close()
        delete(win)
        qapp.processEvents()
