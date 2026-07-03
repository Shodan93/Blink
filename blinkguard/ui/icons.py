"""App- und Tray-Icons auf Basis des Augen-Logos (blinkguard/assets/logo.png).

Der Erkennungszustand wird als kleiner farbiger Punkt unten rechts auf dem
Logo angezeigt. Fehlt das Logo, wird ersatzweise ein Auge gezeichnet.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap

from blinkguard.config import asset_path

COLOR_ACTIVE = QColor("#2e7d32")   # grün: Erkennung läuft
COLOR_PAUSED = QColor("#9e9e9e")   # grau: pausiert
COLOR_WARNING = QColor("#e65100")  # orange: Blinzelrate zu niedrig
COLOR_ERROR = QColor("#c62828")    # rot: Kamerafehler

_logo_cache: QPixmap | None = None


def logo_pixmap() -> QPixmap | None:
    global _logo_cache
    if _logo_cache is None:
        path = asset_path("logo.png")
        if path.exists():
            _logo_cache = QPixmap(str(path))
    return _logo_cache if _logo_cache and not _logo_cache.isNull() else None


def app_icon() -> QIcon:
    logo = logo_pixmap()
    if logo is not None:
        return QIcon(logo)
    return make_eye_icon(COLOR_ACTIVE)


def make_tray_icon(color: QColor, badge: bool = True) -> QIcon:
    """Logo mit Zustands-Punkt unten rechts; Fallback: gezeichnetes Auge."""
    logo = logo_pixmap()
    if logo is None:
        return make_eye_icon(color)

    size = 128
    pixmap = logo.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    if badge:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        radius = size // 7
        center = QPointF(size - radius - 6, size - radius - 6)
        painter.setPen(QPen(QColor(10, 12, 20), 3))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(center, radius, radius)
        painter.end()
    return QIcon(pixmap)


def make_eye_icon(color: QColor, closed: bool = False) -> QIcon:
    """Stilisiertes Auge als Fallback-Icon (offen oder geschlossen)."""
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
