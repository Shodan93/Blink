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

_pixmap_cache: dict[str, QPixmap | None] = {}


def _asset_pixmap(name: str) -> QPixmap | None:
    if name not in _pixmap_cache:
        path = asset_path(name)
        _pixmap_cache[name] = QPixmap(str(path)) if path.exists() else None
    pm = _pixmap_cache[name]
    return pm if pm is not None and not pm.isNull() else None


def app_icon() -> QIcon:
    logo = _asset_pixmap("logo.png")
    if logo is not None:
        return QIcon(logo)
    return make_eye_icon(COLOR_ACTIVE)


def make_tray_icon(color: QColor, badge: bool = True) -> QIcon:
    """Tray-Auge mit Zustands-Punkt unten rechts; Fallback: gezeichnetes Auge."""
    logo = _asset_pixmap("tray.png") or _asset_pixmap("logo.png")
    if logo is None:
        return make_eye_icon(color)

    size = 128
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    scaled = logo.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    painter.drawPixmap(
        (size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled
    )
    if badge:
        radius = size // 8
        center = QPointF(size - radius - 4, size - radius - 4)
        painter.setPen(QPen(QColor(255, 255, 255, 200), 3))
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
