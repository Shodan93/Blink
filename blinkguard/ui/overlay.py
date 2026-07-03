"""Dezentes Bildschirm-Overlay als Blinzelerinnerung.

Halbtransparente Einblendung oben mittig, klaut keinen Fokus und blendet
sich nach wenigen Sekunden von selbst wieder aus.
"""

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

SHOW_MS = 4000
FADE_MS = 600


class OverlayWarning(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 16, 28, 16)
        self.icon_label = QLabel("👁")
        self.icon_label.setFont(QFont("Segoe UI Emoji", 22))
        self.text_label = QLabel()
        self.text_label.setFont(QFont("Segoe UI", 13))
        self.text_label.setStyleSheet("color: white;")
        self.icon_label.setStyleSheet("color: white;")
        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._animation = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 18, 18)
        painter.fillPath(path, QColor(30, 30, 30, 215))

    def show_message(self, text: str):
        self.text_label.setText(text)
        self.adjustSize()

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + 48)

        self.setWindowOpacity(0.0)
        self.show()
        self._fade(0.0, 1.0)
        self._hide_timer.start(SHOW_MS)

    def _fade_out(self):
        self._fade(1.0, 0.0, then_hide=True)

    def _fade(self, start: float, end: float, then_hide: bool = False):
        self._animation = QPropertyAnimation(self, b"windowOpacity", self)
        self._animation.setDuration(FADE_MS)
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        if then_hide:
            self._animation.finished.connect(self.hide)
        self._animation.start()
