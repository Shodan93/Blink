"""Bildschirm-Aura als Blinzelwarnung.

Ein blaues Glühen an allen Bildschirmrändern, das ~20 % in den Bildschirm
hineinfadet – wie die Low-Health-Vignette in Shootern. Deckt den ganzen
Bildschirm ab, ist aber vollständig klick-durchlässig und klaut keinen
Fokus. Pulsiert zweimal sanft und blendet sich dann wieder aus.
"""

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
)
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QWidget

AURA_COLOR = QColor(30, 120, 255)  # kräftiges Blau
EDGE_ALPHA = 190                   # Deckkraft direkt am Rand
DEPTH_RATIO = 0.20                 # wie weit das Glühen in den Bildschirm fadet


class AuraOverlay(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._animation = None

    def paintEvent(self, event):
        painter = QPainter(self)
        w, h = self.width(), self.height()
        depth = max(40, int(min(w, h) * DEPTH_RATIO))

        edge = QColor(AURA_COLOR)
        edge.setAlpha(EDGE_ALPHA)
        transparent = QColor(AURA_COLOR)
        transparent.setAlpha(0)

        # Vier Randverläufe über die volle Länge; in den Ecken überlagern
        # sie sich und glühen dadurch natürlich stärker (Vignette-Effekt).
        gradients = (
            (0, 0, 0, depth, 0, 0, w, depth),          # oben
            (0, h, 0, h - depth, 0, h - depth, w, depth),  # unten
            (0, 0, depth, 0, 0, 0, depth, h),          # links
            (w, 0, w - depth, 0, w - depth, 0, depth, h),  # rechts
        )
        for x1, y1, x2, y2, rx, ry, rw, rh in gradients:
            grad = QLinearGradient(x1, y1, x2, y2)
            grad.setColorAt(0.0, edge)
            grad.setColorAt(1.0, transparent)
            painter.fillRect(rx, ry, rw, rh, grad)

    def flash(self):
        """Aura einblenden, zweimal pulsieren, ausblenden."""
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()

        group = QSequentialAnimationGroup(self)
        steps = (
            (0.0, 1.0, 700),   # einblenden
            (1.0, 0.45, 650),  # Puls 1 ab
            (0.45, 1.0, 650),  # Puls 1 auf
            (1.0, 0.45, 650),  # Puls 2 ab
            (0.45, 1.0, 650),  # Puls 2 auf
            (1.0, 0.0, 900),   # ausblenden
        )
        for start, end, ms in steps:
            anim = QPropertyAnimation(self, b"windowOpacity")
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setDuration(ms)
            anim.setEasingCurve(QEasingCurve.InOutSine)
            group.addAnimation(anim)
        group.finished.connect(self.hide)

        if self._animation is not None:
            self._animation.stop()
        self._animation = group
        group.start()
