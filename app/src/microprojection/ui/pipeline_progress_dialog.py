"""Modal progress dialog for a running acquisition pipeline.

Shows a progress bar and the latest status, and offers a Cancel button. The
dialog only reflects and controls the pipeline through its signals/``cancel``;
it owns no acquisition logic. It closes itself on any terminal signal (finished,
failed, or cancelled), and closing it (Cancel or the window button) cancels a
still-running pipeline.

The pipeline is driven by the camera's frameReady signal on the GUI thread, and
``exec`` keeps the event loop running, so progress advances while the modal is
shown.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialogButtonBox,
    QDialog,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)


class PipelineProgressDialog(QDialog):
    def __init__(self, pipeline, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(380, 130)

        self._pipeline = pipeline

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self._label = QLabel("Starting...")
        layout.addWidget(self._label)

        self._bar = QProgressBar()
        self._bar.setRange(0, max(1, pipeline.total))
        self._bar.setValue(0)
        layout.addWidget(self._bar)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self._cancel)
        layout.addWidget(buttons)

        pipeline.progress.connect(self._on_progress)
        pipeline.status.connect(self._label.setText)
        pipeline.finished.connect(self._on_done)
        pipeline.failed.connect(self._on_done)
        pipeline.cancelled.connect(self._on_done)

    def _on_progress(self, done: int, total: int) -> None:
        self._bar.setMaximum(max(1, total))
        self._bar.setValue(done)
        self._label.setText(f"{done} / {total}")

    def _cancel(self) -> None:
        # cancel() emits cancelled -> _on_done closes the dialog
        self._pipeline.cancel()

    def _on_done(self, *_) -> None:
        self.accept()

    def closeEvent(self, event) -> None:
        # Closing via the window button cancels a still-running pipeline.
        if self._pipeline.running:
            self._pipeline.cancel()
        super().closeEvent(event)
