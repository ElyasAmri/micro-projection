import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ProjectorWindow(QWidget):
    """Fullscreen borderless window for projecting fringe patterns onto a secondary display."""

    def __init__(self, screen=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setStyleSheet("background-color: black;")

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        if screen is not None:
            self.move_to_screen(screen)

    def move_to_screen(self, screen):
        """Position this window fullscreen on the given QScreen."""
        geo = screen.geometry()
        self.setGeometry(geo)
        self._screen_size = (geo.width(), geo.height())
        self.showFullScreen()

    def update_pattern(self, pattern: np.ndarray):
        """Display a HxW uint8 grayscale or HxWx3 uint8 RGB pattern."""
        if pattern.ndim == 2:
            h, w = pattern.shape
            data = np.ascontiguousarray(pattern)
            qimg = QImage(data.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
        else:
            h, w, ch = pattern.shape
            data = np.ascontiguousarray(pattern)
            qimg = QImage(data.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()

        pixmap = QPixmap.fromImage(qimg)
        # Scale to fill the projector screen
        scaled = pixmap.scaled(
            self._label.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._label.setPixmap(scaled)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)
