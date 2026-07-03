"""BlinkGuard-Hauptanwendung: Tray-Icon, Warnlogik und Verdrahtung."""

import sys
import time

from PySide6.QtCore import QSharedMemory, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from blinkguard import APP_NAME, autostart
from blinkguard.config import Config
from blinkguard.detector import BlinkDetector
from blinkguard.notifier import Notifier
from blinkguard.stats import MinuteAccumulator, StatsStore
from blinkguard.ui.icons import (
    COLOR_ACTIVE,
    COLOR_ERROR,
    COLOR_PAUSED,
    COLOR_WARNING,
    make_eye_icon,
)
from blinkguard.ui.settings_dialog import SettingsDialog
from blinkguard.ui.stats_window import StatsWindow

# Erst warnen, wenn das Messfenster gefüllt ist und der Nutzer wirklich
# vor dem Bildschirm sitzt.
MIN_FACE_RATIO = 0.7
WARMUP_S = 75.0


class BlinkGuardApp:
    def __init__(self, app: QApplication):
        self.app = app
        self.config = Config()
        self.store = StatsStore()
        self.accumulator = MinuteAccumulator(self.store)

        self.paused = False
        self.camera_failed = False
        self.last_warning_ts = 0.0
        self.detection_started_ts = time.monotonic()
        self.current_rate = 0.0
        self.session_blinks = 0

        # --- Tray -------------------------------------------------------
        self.icons = {
            "active": make_eye_icon(COLOR_ACTIVE),
            "warning": make_eye_icon(COLOR_WARNING),
            "paused": make_eye_icon(COLOR_PAUSED, closed=True),
            "error": make_eye_icon(COLOR_ERROR),
        }
        self.tray = QSystemTrayIcon(self.icons["active"])
        self.tray.setToolTip(f"{APP_NAME} – startet …")
        menu = QMenu()
        self.action_stats = QAction("Statistik anzeigen")
        self.action_stats.triggered.connect(self.show_stats)
        self.action_settings = QAction("Einstellungen …")
        self.action_settings.triggered.connect(self.show_settings)
        self.action_pause = QAction("Erkennung pausieren")
        self.action_pause.triggered.connect(self.toggle_pause)
        action_quit = QAction("Beenden")
        action_quit.triggered.connect(self.quit)
        menu.addAction(self.action_stats)
        menu.addAction(self.action_settings)
        menu.addSeparator()
        menu.addAction(self.action_pause)
        menu.addSeparator()
        menu.addAction(action_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # --- Fenster & Benachrichtigungen --------------------------------
        self.stats_window = StatsWindow(self.store, self.config)
        self.notifier = Notifier(self.tray, self.config)

        # --- Erkennungs-Thread -------------------------------------------
        self.detector = BlinkDetector(
            camera_index=int(self.config.get("camera_index")),
            blink_threshold=float(self.config.get("blink_threshold")),
        )
        self.detector.sig_blink.connect(self._on_blink)
        self.detector.sig_tick.connect(self._on_tick)
        self.detector.sig_error.connect(self._on_camera_error)
        self.detector.start()

        # --- 20-20-20-Erinnerung ------------------------------------------
        self.rule_timer = QTimer()
        self.rule_timer.setInterval(20 * 60 * 1000)
        self.rule_timer.timeout.connect(self._on_rule_timer)
        if self.config.get("rule_20_20_20"):
            self.rule_timer.start()
        self._recent_face = False

        self.app.aboutToQuit.connect(self._cleanup)

    def _set_tray_state(self, state: str):
        if getattr(self, "_tray_state", None) != state:
            self._tray_state = state
            self.tray.setIcon(self.icons[state])

    # --- Signale aus dem Kamera-Thread ------------------------------------
    def _on_blink(self, _ts: float):
        self.accumulator.add_blink()
        self.session_blinks += 1
        self.stats_window.on_blink(self.session_blinks)

    def _on_tick(self, rate: float, face_present: bool, face_ratio: float, score: float):
        self.current_rate = rate
        self._recent_face = face_present
        self.accumulator.add_face_second(face_present)
        self.stats_window.set_live(rate, face_present, score, self.paused)

        if self.paused or self.camera_failed:
            return

        threshold = float(self.config.get("rate_threshold"))
        warn_mode = self.config.get("mode") == "warn"
        now = time.monotonic()

        low_rate = (
            warn_mode
            and face_ratio >= MIN_FACE_RATIO
            and (now - self.detection_started_ts) >= WARMUP_S
            and rate < threshold
        )

        if low_rate and (now - self.last_warning_ts) >= float(
            self.config.get("warn_cooldown_s")
        ):
            self.last_warning_ts = now
            self.notifier.warn_low_blink_rate(rate)

        # Tray-Zustand aktualisieren
        self._set_tray_state("warning" if low_rate else "active")
        if face_present:
            self.tray.setToolTip(f"{APP_NAME} – {rate:.0f} Blinzler/min")
        else:
            self.tray.setToolTip(f"{APP_NAME} – kein Gesicht erkannt")

    def _on_camera_error(self, message: str):
        self.camera_failed = True
        self._set_tray_state("error")
        self.tray.setToolTip(f"{APP_NAME} – Kamerafehler")
        self.notifier.camera_error(message)

    def _on_rule_timer(self):
        # Nur erinnern, wenn gerade jemand vor dem Bildschirm sitzt
        if not self.paused and not self.camera_failed and self._recent_face:
            self.notifier.remind_20_20_20()

    # --- UI-Aktionen --------------------------------------------------------
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # Linksklick
            self.show_stats()

    def show_stats(self):
        self.stats_window.show()
        self.stats_window.raise_()
        self.stats_window.activateWindow()

    def show_settings(self):
        dialog = SettingsDialog(self.config)
        dialog.test_requested.connect(self.notifier.test_warning)
        if not dialog.exec():
            return
        values = dialog.values()
        want_autostart = values.pop("autostart")
        restart_camera = values["camera_index"] != self.config.get("camera_index")
        self.config.update(values)

        self.detector.set_blink_threshold(float(values["blink_threshold"]))

        if values["rule_20_20_20"]:
            if not self.rule_timer.isActive():
                self.rule_timer.start()
        else:
            self.rule_timer.stop()

        if autostart.is_supported() and want_autostart != autostart.is_enabled():
            if not autostart.set_enabled(want_autostart):
                QMessageBox.warning(
                    None,
                    APP_NAME,
                    "Der Autostart-Eintrag konnte nicht geändert werden.",
                )
        self.config.set("autostart", want_autostart)
        self.config.save()

        if restart_camera:
            self._restart_detector()

    def toggle_pause(self):
        self.paused = not self.paused
        self.detector.set_paused(self.paused)
        self.stats_window.set_live(0.0, False, 0.0, self.paused)
        if self.paused:
            self.accumulator.flush()
            self.action_pause.setText("Erkennung fortsetzen")
            self._set_tray_state("paused")
            self.tray.setToolTip(f"{APP_NAME} – pausiert")
        else:
            self.detection_started_ts = time.monotonic()
            self.action_pause.setText("Erkennung pausieren")
            self._set_tray_state("active")

    def _restart_detector(self):
        self.detector.stop()
        self.detector.wait(3000)
        self.camera_failed = False
        self.detection_started_ts = time.monotonic()
        self.detector = BlinkDetector(
            camera_index=int(self.config.get("camera_index")),
            blink_threshold=float(self.config.get("blink_threshold")),
        )
        self.detector.sig_blink.connect(self._on_blink)
        self.detector.sig_tick.connect(self._on_tick)
        self.detector.sig_error.connect(self._on_camera_error)
        self.detector.set_paused(self.paused)
        self.detector.start()

    def quit(self):
        self.app.quit()

    def _cleanup(self):
        self.detector.stop()
        self.detector.wait(3000)
        self.accumulator.flush()
        self.store.close()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)  # App lebt im Tray, nicht in Fenstern

    # Zweitstart verhindern (Kamera kann nur einmal genutzt werden)
    shared = QSharedMemory(f"{APP_NAME}-single-instance")
    if not shared.create(1):
        QMessageBox.information(
            None, APP_NAME, f"{APP_NAME} läuft bereits (siehe Infobereich/Tray)."
        )
        sys.exit(0)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None, APP_NAME, "Kein System-Tray verfügbar – App kann nicht starten."
        )
        sys.exit(1)

    guard = BlinkGuardApp(app)  # noqa: F841 – hält alle Objekte am Leben
    sys.exit(app.exec())
