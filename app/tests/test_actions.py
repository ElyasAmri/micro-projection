"""Exercise the maestro `qt` action dispatch against a real widget tree."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
from shiboken6 import delete

from maestro import actions


@pytest.fixture
def window(qapp):
    """A throwaway top-level window with a few named, addressable widgets.

    The window carries a unique objectName ("testwin") so list_windows / label
    scoping isolate it from any windows other tests leave behind.
    """
    win = QWidget()
    win.setObjectName("testwin")
    win.setWindowTitle("Test Window")
    layout = QVBoxLayout(win)

    edit = QLineEdit()
    edit.setObjectName("name_edit")
    edit.setText("hello")
    layout.addWidget(edit)

    label = QLabel("Status: ready")
    label.setObjectName("status")
    layout.addWidget(label)

    button = QPushButton("Run")
    button.setObjectName("run_btn")
    layout.addWidget(button)

    win.show()  # offscreen; makes widgets visible() so find/screenshot behave
    try:
        yield win, edit, label, button
    finally:
        # Destroy the C++ object now: deleteLater posts a DeferredDelete that
        # processEvents does not flush, so reusing the "testwin" objectName would
        # otherwise leak windows that collide in find_widget across tests.
        win.close()
        delete(win)
        qapp.processEvents()


def test_list_windows_reports_our_window(window):
    result = actions.dispatch({"action": "list_windows", "label": "testwin"}, {})
    assert len(result["windows"]) == 1
    win = result["windows"][0]
    assert win["label"] == "testwin"
    assert win["title"] == "Test Window"


def test_read_returns_widget_value(window):
    result = actions.dispatch(
        {"action": "read", "selector": "name_edit", "label": "testwin"}, {}
    )
    assert result["text"] == "hello"
    assert result["matched"] == "name_edit"


def test_find_by_text(window):
    result = actions.dispatch(
        {"action": "find", "text": "Status", "label": "testwin"}, {}
    )
    selectors = [m["selector"] for m in result["matches"]]
    assert "status" in selectors


def test_click_invokes_button(window):
    _win, _edit, _label, button = window
    clicks: list[bool] = []
    button.clicked.connect(lambda: clicks.append(True))

    result = actions.dispatch(
        {"action": "click", "selector": "run_btn", "label": "testwin"}, {}
    )
    assert result == {"clicked": True, "selector": "run_btn"}
    assert clicks == [True]


def test_set_value_updates_widget(window):
    _win, edit, _label, _button = window
    result = actions.dispatch(
        {"action": "set_value", "selector": "name_edit", "value": "world", "label": "testwin"},
        {},
    )
    assert result == {"set": True, "selector": "name_edit"}
    assert edit.text() == "world"


def test_screenshot_returns_png_base64(window):
    result = actions.dispatch(
        {"action": "screenshot", "selector": "run_btn", "label": "testwin"}, {}
    )
    assert result["format"] == "png"
    assert isinstance(result["base64"], str) and result["base64"]


def test_invoke_calls_registered_command(window):
    commands = {"ping": lambda args: {"ok": True, "echo": args}}
    result = actions.dispatch(
        {"action": "invoke", "command": "ping", "args": {"x": 1}}, commands
    )
    assert result == {"ok": True, "echo": {"x": 1}}


def test_invoke_unknown_command_raises(window):
    with pytest.raises(ValueError, match="unknown command"):
        actions.dispatch({"action": "invoke", "command": "nope"}, {})


def test_unknown_action_raises(window):
    with pytest.raises(ValueError, match="unknown qt action"):
        actions.dispatch({"action": "bogus"}, {})


def test_missing_selector_raises(window):
    with pytest.raises(ValueError, match="requires `selector`"):
        actions.dispatch({"action": "click"}, {})


def test_batch_collects_per_action_results(window):
    payload = {
        "action": "batch",
        "actions": [
            {"action": "list_windows", "label": "testwin"},
            {"action": "set_value", "selector": "name_edit", "value": "v2", "label": "testwin"},
            {"action": "click"},  # missing selector -> recorded as an error
        ],
    }
    result = actions.dispatch(payload, {})
    oks = [entry["ok"] for entry in result["results"]]
    assert oks == [True, True, False]
    assert "selector" in result["results"][2]["error"]


def test_batch_rejects_nested_batch(window):
    payload = {"action": "batch", "actions": [{"action": "batch", "actions": []}]}
    result = actions.dispatch(payload, {})
    assert result["results"][0]["ok"] is False
    assert "nested batch" in result["results"][0]["error"]
