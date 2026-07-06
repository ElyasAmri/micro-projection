"""Dispatch a maestro `qt` request payload to work against the Qt widget tree.

Every function here runs on the GUI thread (the connector calls them from a
QWebSocket signal handler, which Qt delivers on the thread the socket lives on),
so direct widget access is safe -- no cross-thread marshaling needed.

Widgets are addressed by `selector`, matched against `objectName` (exact, then
substring) and finally the class name. The app must call `setObjectName(...)` on
the widgets it wants reachable.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSlider,
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QSpinBox,
    QDoubleSpinBox,
    QTextEdit,
    QWidget,
)

# A command the app exposes to `invoke`: takes the args object, returns anything
# JSON-serializable (or a value we stringify).
Command = Callable[[dict], Any]


def _windows(label: str | None) -> list[QWidget]:
    """Top-level windows, optionally filtered to the one named `label`.

    Ranked, not raw enumeration order: topLevelWidgets() also contains hidden
    popups (a closed QMenu, tooltips), so the no-selector actions (screenshot,
    read) would otherwise land on whichever happens to enumerate first. Visible
    windows sort ahead of hidden ones, main windows ahead of the rest.
    """
    tops = [w for w in QApplication.topLevelWidgets() if w.isWindow()]
    if label:
        tops = [w for w in tops if _window_label(w) == label]
    tops.sort(key=lambda w: (not w.isVisible(), not isinstance(w, QMainWindow)))
    return tops


def _window_label(w: QWidget) -> str:
    return w.objectName() or w.windowTitle() or type(w).__name__


def _iter_widgets(root: QWidget) -> Iterable[QWidget]:
    """`root` and every descendant widget, in tree order."""
    yield root
    for child in root.findChildren(QWidget):
        yield child


def _all_widgets(label: str | None) -> Iterable[QWidget]:
    for win in _windows(label):
        yield from _iter_widgets(win)


def _matches(w: QWidget, selector: str) -> bool:
    name = w.objectName()
    return name == selector or (bool(name) and selector in name) or type(w).__name__ == selector


def find_widget(selector: str, label: str | None) -> QWidget | None:
    """First widget whose objectName/class matches `selector`, tree order.

    Prefers an exact objectName match anywhere before falling back to a
    substring/class match, so a precise selector is never shadowed by a looser
    hit earlier in the tree.
    """
    widgets = list(_all_widgets(label))
    for w in widgets:
        if w.objectName() == selector:
            return w
    for w in widgets:
        if _matches(w, selector):
            return w
    return None


def _visible_text(w: QWidget) -> str:
    for getter in ("text", "currentText", "windowTitle", "toPlainText"):
        fn = getattr(w, getter, None)
        if callable(fn):
            try:
                value = fn()
            except TypeError:
                continue
            if isinstance(value, str):
                return value
    return ""


def widget_value(w: QWidget) -> Any:
    """Best-effort current value of a widget, typed per its kind."""
    if isinstance(w, QAbstractButton) and w.isCheckable():
        return w.isChecked()
    if isinstance(w, (QSpinBox, QDoubleSpinBox, QAbstractSlider)):
        return w.value()
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QLineEdit):
        return w.text()
    if isinstance(w, (QPlainTextEdit,)):
        return w.toPlainText()
    if isinstance(w, (QTextEdit,)):
        return w.toPlainText()
    if isinstance(w, QLabel):
        return w.text()
    return _visible_text(w)


def set_widget_value(w: QWidget, value: str) -> None:
    """Coerce and apply `value` to an input widget by its kind."""
    if isinstance(w, QAbstractButton) and w.isCheckable():
        w.setChecked(_as_bool(value))
        return
    if isinstance(w, (QSpinBox, QAbstractSlider)):
        w.setValue(int(float(value)))
        return
    if isinstance(w, QDoubleSpinBox):
        w.setValue(float(value))
        return
    if isinstance(w, QComboBox):
        w.setCurrentText(value)
        return
    if isinstance(w, QLineEdit):
        w.setText(value)
        return
    if isinstance(w, QPlainTextEdit):
        w.setPlainText(value)
        return
    if isinstance(w, QTextEdit):
        w.setPlainText(value)
        return
    setter = getattr(w, "setText", None)
    if callable(setter):
        setter(value)
        return
    raise ValueError(f"widget {w.objectName() or type(w).__name__} has no settable value")


def _as_bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on", "checked")


def _rect(w: QWidget) -> dict:
    g = w.geometry()
    return {"x": g.x(), "y": g.y(), "width": g.width(), "height": g.height()}


def _require_widget(selector: str | None, label: str | None) -> QWidget:
    if not selector:
        raise ValueError("requires `selector`")
    w = find_widget(selector, label)
    if w is None:
        raise ValueError(f"no widget matching selector {selector!r}")
    return w


# --- individual actions ------------------------------------------------------


def list_windows(payload: dict) -> dict:
    windows = []
    for w in _windows(payload.get("label")):
        windows.append(
            {
                "label": _window_label(w),
                "title": w.windowTitle(),
                "class": type(w).__name__,
                "visible": w.isVisible(),
                "width": w.width(),
                "height": w.height(),
            }
        )
    return {"windows": windows}


def read(payload: dict) -> dict:
    label = payload.get("label")
    selector = payload.get("selector")
    if not selector:
        wins = _windows(label)
        if not wins:
            raise ValueError("no window to read")
        return {"text": _visible_text(wins[0]), "matched": _window_label(wins[0])}
    w = _require_widget(selector, label)
    return {"text": widget_value(w), "matched": w.objectName() or type(w).__name__}


def find(payload: dict) -> dict:
    label = payload.get("label")
    selector = payload.get("selector")
    text = payload.get("text")
    if not selector and not text:
        raise ValueError("find requires `selector` or `text`")
    matches = []
    for w in _all_widgets(label):
        if selector and not _matches(w, selector):
            continue
        wtext = _visible_text(w)
        if text and text.lower() not in wtext.lower():
            continue
        matches.append(
            {
                "selector": w.objectName(),
                "class": type(w).__name__,
                "text": wtext,
                "rect": _rect(w),
            }
        )
    return {"matches": matches}


def click(payload: dict) -> dict:
    w = _require_widget(payload.get("selector"), payload.get("label"))
    if isinstance(w, QAbstractButton):
        w.click()
    else:
        clicker = getattr(w, "click", None)
        if not callable(clicker):
            raise ValueError(f"widget {w.objectName() or type(w).__name__} is not clickable")
        clicker()
    return {"clicked": True, "selector": w.objectName() or type(w).__name__}


def set_value(payload: dict) -> dict:
    value = payload.get("value")
    if value is None:
        raise ValueError("set_value requires `value`")
    w = _require_widget(payload.get("selector"), payload.get("label"))
    set_widget_value(w, str(value))
    return {"set": True, "selector": w.objectName() or type(w).__name__}


def screenshot(payload: dict) -> dict:
    label = payload.get("label")
    selector = payload.get("selector")
    if selector:
        target = _require_widget(selector, label)
    else:
        wins = _windows(label)
        if not wins:
            raise ValueError("no window to screenshot")
        target = wins[0]
    pixmap = target.grab()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    return {"format": "png", "base64": bytes(data.toBase64()).decode("ascii")}


def invoke(payload: dict, commands: dict[str, Command]) -> Any:
    name = payload.get("command")
    if not name:
        raise ValueError("invoke requires `command`")
    fn = commands.get(name)
    if fn is None:
        raise ValueError(f"unknown command {name!r}")
    args = payload.get("args") or {}
    if not isinstance(args, dict):
        raise ValueError("`args` must be an object")
    return fn(args)


# --- dispatch ----------------------------------------------------------------


def run_one(payload: dict, commands: dict[str, Command]) -> Any:
    """Route a single action payload to its handler. Raises on bad input; the
    connector turns the exception into a `{ "error": ... }` response."""
    action = payload.get("action")
    if action == "batch":
        raise ValueError("nested batch is not allowed")
    if action == "list_windows":
        return list_windows(payload)
    if action == "read":
        return read(payload)
    if action == "find":
        return find(payload)
    if action == "click":
        return click(payload)
    if action == "set_value":
        return set_value(payload)
    if action == "screenshot":
        return screenshot(payload)
    if action == "invoke":
        return invoke(payload, commands)
    raise ValueError(f"unknown qt action: {action!r}")


def batch(payload: dict, commands: dict[str, Command]) -> dict:
    """Run each entry of `actions` in order, collecting a per-entry result. A
    failing entry is recorded and the batch continues, mirroring the browser and
    desktop tools' batch shape."""
    actions = payload.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("batch requires a non-empty `actions` array")
    results = []
    for item in actions:
        if not isinstance(item, dict):
            results.append({"ok": False, "error": "each action must be an object"})
            continue
        try:
            results.append({"ok": True, "result": run_one(item, commands)})
        except Exception as exc:  # noqa: BLE001 - report, do not abort the batch
            results.append({"ok": False, "error": str(exc)})
    return {"results": results}


def dispatch(payload: dict, commands: dict[str, Command]) -> Any:
    """Top-level entry: `batch` fans out, everything else is one action."""
    if payload.get("action") == "batch":
        return batch(payload, commands)
    return run_one(payload, commands)
