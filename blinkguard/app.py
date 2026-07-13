"""BlinkGuard-Hauptanwendung: Tray-Icon, Warnlogik und Verdrahtung."""

import sys
import time
from collections import deque

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
    app_icon,
    make_tray_icon,
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
        # Haltung
        self._posture_bad_since = None
        self._posture_last_warn = 0.0
        self._calibration_samples = None  # list = Kalibrierung läuft
        self._posture_window = deque(maxlen=5)  # Glättung über ~5 s
        self._still_window = deque()  # (ts, face_x, face_y, shoulder_y) für Stillsitz
        # Bewegungs-Erinnerung
        self._present_s = 0
        self._absent_s = 0

        # --- Tray -------------------------------------------------------
        self.app.setWindowIcon(app_icon())
        self.icons = {
            "active": make_tray_icon(COLOR_ACTIVE),
            "warning": make_tray_icon(COLOR_WARNING),
            "paused": make_tray_icon(COLOR_PAUSED),
            "error": make_tray_icon(COLOR_ERROR),
        }
        self.tray = QSystemTrayIcon(self.icons["active"])
        self.tray.setToolTip(f"{APP_NAME} – startet …")
        # Menü und Aktionen müssen auf self referenziert bleiben: weder
        # addAction() noch setContextMenu() übernehmen Besitz, sonst räumt
        # der Garbage Collector die Einträge weg.
        self.menu = QMenu()
        self.action_stats = QAction("Statistik anzeigen", self.menu)
        self.action_stats.triggered.connect(self.show_stats)
        self.action_settings = QAction("Einstellungen …", self.menu)
        self.action_settings.triggered.connect(self.show_settings)
        self.action_pause = QAction("Erkennung pausieren", self.menu)
        self.action_pause.triggered.connect(self.toggle_pause)
        self.action_quit = QAction("Beenden", self.menu)
        self.action_quit.triggered.connect(self.quit)
        self.menu.addAction(self.action_stats)
        self.menu.addAction(self.action_settings)
        self.menu.addSeparator()
        self.menu.addAction(self.action_pause)
        self.menu.addSeparator()
        self.menu.addAction(self.action_quit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        # --- Fenster & Benachrichtigungen --------------------------------
        self.stats_window = StatsWindow(self.store, self.config)
        self.stats_window.setWindowIcon(app_icon())
        self.stats_window.sig_settings.connect(self.show_settings)
        self.stats_window.sig_pause.connect(self.toggle_pause)
        self.stats_window.sig_calibrate.connect(self.start_posture_calibration)
        self.stats_window.sig_preview_toggled.connect(self._set_preview)
        self.notifier = Notifier(self.tray, self.config)

        # --- Erkennungs-Thread -------------------------------------------
        self.detector = BlinkDetector(
            camera_index=int(self.config.get("camera_index")),
            blink_threshold=float(self.config.get("blink_threshold")),
        )
        self.detector.sig_blink.connect(self._on_blink)
        self.detector.sig_tick.connect(self._on_tick)
        self.detector.sig_posture.connect(self._on_posture)
        self.detector.sig_preview.connect(self.stats_window.set_preview_image)
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

    def _on_tick(self, rate: float, face_present: bool, face_ratio: float, since_blink: float):
        self.current_rate = rate
        self._recent_face = face_present
        self.accumulator.add_face_second(face_present)
        self.stats_window.set_live(rate, face_present, since_blink, self.paused)

        if self.paused or self.camera_failed:
            return

        # Bewegungs-Erinnerung: durchgehende Sitzzeit zählen; erst eine
        # Abwesenheit von 3 Minuten gilt als echte Pause
        if face_present:
            self._present_s += 1 + self._absent_s  # kurze Lücken zählen mit
            self._absent_s = 0
        else:
            self._absent_s += 1
            if self._absent_s >= 180:
                self._present_s = 0
        self.stats_window.set_sitting_minutes(self._present_s // 60)
        if (
            self.config.get("move_enabled")
            and self._present_s >= int(self.config.get("move_minutes")) * 60
        ):
            self._present_s = 0
            self.notifier.remind_move(int(self.config.get("move_minutes")))

        threshold = float(self.config.get("rate_threshold"))
        warn_mode = self.config.get("mode") == "warn"
        now = time.monotonic()
        cooldown_over = (now - self.last_warning_ts) >= float(
            self.config.get("warn_cooldown_s")
        )

        # Sofortwarnung: X Sekunden am Stück kein Blinzeln ("Starren")
        no_blink = (
            warn_mode
            and self.config.get("no_blink_enabled")
            and face_present
            and since_blink >= float(self.config.get("no_blink_seconds"))
        )

        low_rate = (
            warn_mode
            and face_ratio >= MIN_FACE_RATIO
            and (now - self.detection_started_ts) >= WARMUP_S
            and rate < threshold
        )

        if no_blink and cooldown_over:
            self.last_warning_ts = now
            self.notifier.warn_no_blink(since_blink)
        elif low_rate and cooldown_over:
            self.last_warning_ts = now
            self.notifier.warn_low_blink_rate(rate)

        # Tray-Zustand aktualisieren
        self._set_tray_state("warning" if (low_rate or no_blink) else "active")
        if face_present:
            self.tray.setToolTip(f"{APP_NAME} – {rate:.0f} Blinzler/min")
        else:
            self.tray.setToolTip(f"{APP_NAME} – kein Gesicht erkannt")

    def _set_preview(self, enabled: bool):
        self.detector.set_preview(enabled)

    # --- Haltung (Posture) ---------------------------------------------------
    def start_posture_calibration(self):
        """Einige Sekunden Metriken sammeln und als Referenzhaltung speichern."""
        self._calibration_samples = []
        self._calibration_started = time.monotonic()
        self.stats_window.set_posture("Kalibriere … bitte gerade sitzen bleiben", None)

    @staticmethod
    def _average_metrics(samples: list[dict]) -> dict:
        """Mittelwert über Metrik-Samples; Nackenwerte nur aus gültigen Samples."""
        keys = ("eye_dist", "face_y", "head_roll", "face_x", "shoulder_tilt", "shoulder_y", "shoulder_width")
        avg = {k: sum(s.get(k, 0.0) for s in samples) / len(samples) for k in keys}
        for key in ("neck_len", "neck_left", "neck_right"):
            vals = [s[key] for s in samples if s.get(key) is not None]
            # Ohr muss in der Mehrzahl der Samples sichtbar sein
            avg[key] = sum(vals) / len(vals) if len(vals) * 2 > len(samples) else None
        return avg

    def _on_posture(self, m: dict):
        # Kalibrierung läuft?
        if self._calibration_samples is not None:
            if m["valid"]:
                self._calibration_samples.append(m)
            if len(self._calibration_samples) >= 4:
                baseline = self._average_metrics(self._calibration_samples)
                self._calibration_samples = None
                self.config.set("posture_baseline", baseline)
                self.config.set("posture_enabled", True)
                self.config.save()
                hint = (
                    ""
                    if baseline["neck_len"] is not None
                    else " (Ohren waren nicht sichtbar – Geierhals-/Schulter-hochziehen-"
                    "Erkennung inaktiv, ggf. neu kalibrieren)"
                )
                self.tray.showMessage(
                    APP_NAME,
                    f"Referenzhaltung gespeichert – Haltungsüberwachung ist aktiv.{hint}",
                    QSystemTrayIcon.Information,
                    5000,
                )
            elif time.monotonic() - self._calibration_started > 12.0:
                self._calibration_samples = None
                self.stats_window.set_posture(
                    "Kalibrierung fehlgeschlagen – Gesicht und Schultern "
                    "müssen im Bild sein (mehr Abstand zur Kamera?)",
                    False,
                )
                return
            else:
                return

        baseline = self.config.get("posture_baseline")
        enabled = self.config.get("posture_enabled") and baseline
        if not enabled:
            self.stats_window.set_posture("Nicht kalibriert", None)
            return
        if self.paused or not m["valid"]:
            self._posture_window.clear()
            self._still_window.clear()
            self._posture_bad_since = None
            self.stats_window.set_posture("–", None)
            return

        # Glättung: kurzes Wackeln/Messrauschen löst keine Warnung aus
        self._posture_window.append(m)
        avg = self._average_metrics(list(self._posture_window))

        cfg = self.config
        issues = []
        if cfg.get("posture_check_shoulder") and abs(
            avg["shoulder_tilt"] - baseline["shoulder_tilt"]
        ) > float(cfg.get("posture_tol_shoulder_deg")):
            issues.append("Schultern ungleich hoch")
        if cfg.get("posture_check_head") and abs(
            avg["head_roll"] - baseline["head_roll"]
        ) > float(cfg.get("posture_tol_head_deg")):
            issues.append("Kopf geneigt")
        if cfg.get("posture_check_near") and avg["eye_dist"] > baseline["eye_dist"] * (
            1.0 + float(cfg.get("posture_tol_near_pct")) / 100.0
        ):
            issues.append("zu nah am Bildschirm")
        if cfg.get("posture_check_slump"):
            slump = float(cfg.get("posture_tol_slump_pct")) / 100.0
            if (avg["face_y"] - baseline["face_y"]) > slump or (
                avg["shoulder_y"] - baseline["shoulder_y"]
            ) > slump:
                issues.append("eingesunken")
        # Geierhals: Gesicht rückt vor, ohne dass der Oberkörper mitkommt ->
        # das Verhältnis Gesichtsgröße/Schulterbreite steigt
        if cfg.get("posture_check_fhp") and baseline.get("shoulder_width"):
            ratio = (avg["eye_dist"] / avg["shoulder_width"]) / (
                baseline["eye_dist"] / baseline["shoulder_width"]
            )
            if ratio > 1.0 + float(cfg.get("posture_tol_fhp_pct")) / 100.0:
                issues.append("Geierhals (Kopf vorgeschoben)")
        # Hochgezogene Schultern: Abstand Ohr->Schulter schrumpft. Je Seite
        # getrennt geprüft, damit auch einseitiges Hochziehen auffällt.
        if cfg.get("posture_check_shrug"):
            factor = 1.0 - float(cfg.get("posture_tol_shrug_pct")) / 100.0
            sides = [
                s
                for s in ("neck_left", "neck_right", "neck_len")
                if baseline.get(s) and avg.get(s) is not None
            ]
            # per-Seite bevorzugen; neck_len nur als Fallback für alte Baselines
            if "neck_left" in sides or "neck_right" in sides:
                sides = [s for s in sides if s != "neck_len"]
            if any(avg[s] < baseline[s] * factor for s in sides):
                issues.append("Schultern hochgezogen")

        now = time.monotonic()

        # Stillsitz-Erkennung: bewegt sich über Minuten praktisch nichts,
        # ist selbst eine "gute" Haltung ungesund -> ans Bewegen erinnern
        STILL_EPS = 0.02  # ~2 % der Bildgröße
        self._still_window.append((now, avg["face_x"], avg["face_y"], avg["shoulder_y"]))
        still_span = float(cfg.get("still_minutes")) * 60.0
        while self._still_window and self._still_window[0][0] < now - still_span:
            self._still_window.popleft()
        if (
            cfg.get("still_enabled")
            and self.config.get("mode") == "warn"
            and len(self._still_window) > 10
            and now - self._still_window[0][0] >= still_span - 2.0
        ):
            still = all(
                max(s[i] for s in self._still_window) - min(s[i] for s in self._still_window)
                < STILL_EPS
                for i in (1, 2, 3)
            )
            if still:
                self._still_window.clear()
                self.notifier.remind_stillness(int(cfg.get("still_minutes")))
        if issues:
            text = ", ".join(issues)
            self.stats_window.set_posture("⚠ " + text, False)
            if self._posture_bad_since is None:
                self._posture_bad_since = now
            elif (
                self.config.get("mode") == "warn"
                and (now - self._posture_bad_since) >= float(self.config.get("posture_grace_s"))
                and (now - self._posture_last_warn) >= float(self.config.get("posture_cooldown_s"))
            ):
                self._posture_last_warn = now
                self.notifier.warn_posture(text)
        else:
            self._posture_bad_since = None
            self.stats_window.set_posture("✓ Haltung gut", True)

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
        self.stats_window.set_live(0.0, False, 0.0, paused=self.paused)
        if self.paused:
            self.accumulator.flush()
            self._present_s = 0
            self._absent_s = 0
            self._posture_bad_since = None
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
        self.detector.sig_posture.connect(self._on_posture)
        self.detector.sig_preview.connect(self.stats_window.set_preview_image)
        self.detector.set_preview(self.stats_window.preview_active())
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
