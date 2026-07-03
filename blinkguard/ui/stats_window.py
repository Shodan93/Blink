"""Statistik-Fenster: Live-Werte und Tagesverlauf als Balkendiagramm."""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from blinkguard.stats import StatsStore

HEALTHY_RATE = 15.0  # untere Grenze der gesunden Blinzelrate/min
BUCKET_MIN = 30      # Diagramm-Auflösung: 30-Minuten-Blöcke


class DayChart(QWidget):
    """Balkendiagramm: Ø Blinzelrate je 30-Minuten-Block des heutigen Tages."""

    def __init__(self, store: StatsStore, rate_threshold_getter):
        super().__init__()
        self.store = store
        self.get_threshold = rate_threshold_getter
        self.setMinimumHeight(220)
        self._buckets: list[float | None] = [None] * (24 * 60 // BUCKET_MIN)

    def refresh(self):
        buckets_blinks = [0] * len(self._buckets)
        buckets_face = [0.0] * len(self._buckets)
        for minute_ts, blinks, face_s in self.store.today_minutes():
            local = datetime.fromtimestamp(minute_ts)
            idx = (local.hour * 60 + local.minute) // BUCKET_MIN
            buckets_blinks[idx] += blinks
            buckets_face[idx] += face_s
        self._buckets = [
            (b / (f / 60.0)) if f >= 60.0 else None
            for b, f in zip(buckets_blinks, buckets_face)
        ]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        margin_left, margin_bottom, margin_top = 34, 24, 10
        w = self.width() - margin_left - 8
        h = self.height() - margin_top - margin_bottom
        max_rate = 25.0
        threshold = float(self.get_threshold())

        def y_for(rate: float) -> float:
            return margin_top + h * (1.0 - min(rate, max_rate) / max_rate)

        # Achsen und Referenzlinien
        axis_pen = QPen(QColor("#888888"), 1)
        painter.setPen(axis_pen)
        painter.drawLine(margin_left, margin_top, margin_left, margin_top + h)
        painter.drawLine(
            margin_left, margin_top + h, margin_left + w, margin_top + h
        )

        small_font = QFont()
        small_font.setPointSize(8)
        painter.setFont(small_font)
        for rate, color, label in (
            (HEALTHY_RATE, QColor("#2e7d32"), "gesund"),
            (threshold, QColor("#e65100"), "Warnung"),
        ):
            pen = QPen(color, 1, Qt.DashLine)
            painter.setPen(pen)
            y = int(y_for(rate))
            painter.drawLine(margin_left, y, margin_left + w, y)
            painter.drawText(margin_left + w - 46, y - 3, label)

        painter.setPen(QPen(QColor("#888888"), 1))
        for rate in (0, 5, 10, 15, 20, 25):
            painter.drawText(4, int(y_for(rate)) + 4, f"{rate:>2}")
        for hour in range(0, 25, 4):
            x = margin_left + w * hour / 24.0
            painter.drawText(int(x) - 8, margin_top + h + 16, f"{hour:02d}h")

        # Balken
        n = len(self._buckets)
        bar_w = max(2.0, w / n - 1.5)
        for i, rate in enumerate(self._buckets):
            if rate is None:
                continue
            x = margin_left + w * i / n
            color = QColor("#2e7d32") if rate >= threshold else QColor("#e65100")
            painter.fillRect(
                int(x), int(y_for(rate)), int(bar_w),
                int(margin_top + h - y_for(rate)), color,
            )


class StatsWindow(QWidget):
    sig_settings = Signal()  # Zahnrad geklickt -> Einstellungen öffnen
    sig_pause = Signal()     # Pause/Fortsetzen geklickt

    def __init__(self, store: StatsStore, config):
        super().__init__()
        self.store = store
        self.config = config
        self.setWindowTitle("BlinkGuard")
        self.resize(560, 440)

        layout = QVBoxLayout(self)

        # --- Kopfzeile: Status + Schnellzugriff -----------------------------
        header = QHBoxLayout()
        self.status_label = QLabel("● startet …")
        header.addWidget(self.status_label)
        header.addStretch()
        self.pause_button = QPushButton("⏸ Pause")
        self.pause_button.setToolTip("Erkennung pausieren/fortsetzen (gibt die Kamera frei)")
        self.pause_button.clicked.connect(self.sig_pause.emit)
        header.addWidget(self.pause_button)
        settings_button = QPushButton("⚙ Einstellungen")
        settings_button.clicked.connect(self.sig_settings.emit)
        header.addWidget(settings_button)
        layout.addLayout(header)

        big_font = QFont()
        big_font.setPointSize(20)
        big_font.setBold(True)

        grid = QGridLayout()
        self.value_labels: dict[str, QLabel] = {}
        for col, (key, caption) in enumerate(
            (
                ("rate", "Aktuelle Rate"),
                ("today", "Blinzler heute"),
                ("avg", "Ø Rate heute"),
                ("active", "Aktive Zeit"),
            )
        ):
            value = QLabel("–")
            value.setFont(big_font)
            value.setAlignment(Qt.AlignCenter)
            caption_label = QLabel(caption)
            caption_label.setAlignment(Qt.AlignCenter)
            grid.addWidget(value, 0, col)
            grid.addWidget(caption_label, 1, col)
            self.value_labels[key] = value
        layout.addLayout(grid)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        # --- Live-Panel: jeder Blinzler sofort sichtbar ---------------------
        live_box = QGroupBox("Live")
        live_layout = QHBoxLayout(live_box)

        self.blink_flash = QLabel("Blinzler!")
        self.blink_flash.setAlignment(Qt.AlignCenter)
        self.blink_flash.setMinimumWidth(90)
        self._flash_off_style = "color: #777777; padding: 2px 8px;"
        self._flash_on_style = (
            "background: #2e7d32; color: white; border-radius: 8px; padding: 2px 8px;"
        )
        self.blink_flash.setStyleSheet(self._flash_off_style)
        live_layout.addWidget(self.blink_flash)

        self.session_label = QLabel("Sitzung: 0")
        self.session_label.setToolTip("Blinzler seit App-Start")
        live_layout.addWidget(self.session_label)

        self.last_blink_label = QLabel("zuletzt: –")
        live_layout.addWidget(self.last_blink_label)

        self.no_blink_bar = QProgressBar()
        self.no_blink_bar.setRange(0, 100)
        self.no_blink_bar.setFormat("Ohne Blinzeln: – s")
        self.no_blink_bar.setToolTip(
            "Zeit seit dem letzten Blinzler. Läuft der Balken voll, "
            "kommt die Ohne-Blinzeln-Warnung (falls aktiviert)."
        )
        live_layout.addWidget(self.no_blink_bar, stretch=1)

        layout.addWidget(live_box)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(350)
        self._flash_timer.timeout.connect(
            lambda: self.blink_flash.setStyleSheet(self._flash_off_style)
        )

        layout.addWidget(QLabel("Blinzelrate im Tagesverlauf (Ø je 30 Minuten):"))
        self.chart = DayChart(store, lambda: self.config.get("rate_threshold"))
        layout.addWidget(self.chart, stretch=1)

        hint = QLabel(
            "<small>Gesund sind etwa 15–20 Blinzler pro Minute. Bei konzentrierter "
            "Bildschirmarbeit sinkt die Rate oft auf 5–7 – dann werden die Augen "
            "trocken.</small>"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._live_rate = 0.0
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self.refresh)

    def on_blink(self, session_count: int):
        """Vom Detector gemeldeter Blinzler – live anzeigen."""
        self.session_label.setText(f"Sitzung: {session_count}")
        self.last_blink_label.setText(datetime.now().strftime("zuletzt: %H:%M:%S"))
        if self.isVisible():
            self.blink_flash.setStyleSheet(self._flash_on_style)
            self._flash_timer.start()

    def set_live(self, rate: float, face_present: bool, since_blink: float, paused: bool):
        """Sekündlicher Live-Status aus dem Kamera-Thread."""
        self._live_rate = rate
        if not self.isVisible():
            return
        self.value_labels["rate"].setText(f"{rate:.0f}/min")
        if paused:
            self.status_label.setText("⏸ Pausiert")
            self.status_label.setStyleSheet("color: #9e9e9e; font-weight: bold;")
            self.pause_button.setText("▶ Fortsetzen")
        elif face_present:
            self.status_label.setText("● Aktiv")
            self.status_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
            self.pause_button.setText("⏸ Pause")
        else:
            self.status_label.setText("○ Abwesend")
            self.status_label.setStyleSheet("color: #e65100; font-weight: bold;")
            self.pause_button.setText("⏸ Pause")

        if paused or not face_present:
            self.no_blink_bar.setValue(0)
            self.no_blink_bar.setFormat("Ohne Blinzeln: – s")
            return
        limit = max(1, int(self.config.get("no_blink_seconds")))
        if self.config.get("no_blink_enabled"):
            self.no_blink_bar.setValue(min(100, round(since_blink / limit * 100)))
            self.no_blink_bar.setFormat(
                f"Ohne Blinzeln: {since_blink:.0f} s  (Warnung bei {limit} s)"
            )
        else:
            self.no_blink_bar.setValue(0)
            self.no_blink_bar.setFormat(f"Ohne Blinzeln: {since_blink:.0f} s")

    def refresh(self):
        total, active_min, avg = self.store.today_summary()
        self.value_labels["rate"].setText(f"{self._live_rate:.0f}/min")
        self.value_labels["today"].setText(f"{total}")
        self.value_labels["avg"].setText(f"{avg:.1f}/min")
        hours, minutes = divmod(int(active_min), 60)
        self.value_labels["active"].setText(f"{hours}h {minutes:02d}m")
        self.chart.refresh()

    def showEvent(self, event):
        self.refresh()
        self._refresh_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._refresh_timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        # Fenster nur verstecken – die App lebt im Tray weiter
        event.ignore()
        self.hide()
