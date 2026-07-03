"""Tray-Icons werden zur Laufzeit gezeichnet – keine Binärdateien im Repo."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

COLOR_ACTIVE = QColor("#2e7d32")   # grün: Erkennung läuft
COLOR_PAUSED = QColor("#9e9e9e")   # grau: pausiert
COLOR_WARNING = QColor("#e65100")  # orange: Blinzelrate zu niedrig
COLOR_ERROR = QColor("#c62828")    # rot: Kamerafehler


def make_eye_icon(color: QColor, closed: bool = False) -> QIcon:
    """Stilisiertes Auge als Icon (offen oder geschlossen)."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 6)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)

    if closed:
        # Geschlossenes Auge: Bogen mit Wimpern
        painter.drawArc(QRectF(8, 6, 48, 44), 200 * 16, 140 * 16)
        for x in (16, 32, 48):
            painter.drawLine(QPointF(x, 44), QPointF(x, 54))
    else:
        # Offenes Auge: Mandelform mit Pupille
        painter.drawArc(QRectF(6, 10, 52, 44), 25 * 16, 130 * 16)
        painter.drawArc(QRectF(6, 10, 52, 44), 205 * 16, 130 * 16)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(32, 32), 9, 9)

    painter.end()
    return QIcon(pixmap)
