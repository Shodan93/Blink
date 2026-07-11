"""Einstellungs-Dialog: Modus, Warnkanäle, Schwellwerte, Autostart."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from blinkguard import autostart
from blinkguard.config import Config


def list_cameras() -> list[str]:
    """Namen der angeschlossenen Kameras (Reihenfolge = OpenCV-Index)."""
    try:
        from PySide6.QtMultimedia import QMediaDevices

        return [device.description() for device in QMediaDevices.videoInputs()]
    except Exception:
        return []


class SettingsDialog(QDialog):
    # Feuert die aktuell im Dialog ausgewählten Werte für einen Warn-Test
    test_requested = Signal(dict)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("BlinkGuard – Einstellungen")
        self.setMinimumWidth(430)

        layout = QVBoxLayout(self)

        # --- Modus ----------------------------------------------------------
        mode_box = QGroupBox("Modus")
        mode_layout = QVBoxLayout(mode_box)
        self.radio_warn = QRadioButton("Blinzelwarnung + Statistik")
        self.radio_stats = QRadioButton("Nur Statistik (keine Warnungen)")
        mode_layout.addWidget(self.radio_warn)
        mode_layout.addWidget(self.radio_stats)
        layout.addWidget(mode_box)

        # --- Warnung --------------------------------------------------------
        self.warn_box = QGroupBox("Blinzelwarnung")
        warn_layout = QFormLayout(self.warn_box)

        self.check_toast = QCheckBox("Windows-Benachrichtigung")
        self.check_overlay = QCheckBox("Blaue Bildschirm-Aura (Glühen am Rand)")
        self.check_sound = QCheckBox("Wassertropfen-Sound")
        warn_layout.addRow(self.check_toast)
        warn_layout.addRow(self.check_overlay)
        warn_layout.addRow(self.check_sound)

        self.spin_threshold = QSpinBox()
        self.spin_threshold.setRange(2, 15)
        self.spin_threshold.setSuffix(" Blinzler/min")
        warn_layout.addRow("Warnen unter (empfohlen: 8):", self.spin_threshold)

        no_blink_row = QHBoxLayout()
        self.check_no_blink = QCheckBox("Sofort warnen ohne Blinzeln für")
        self.spin_no_blink = QSpinBox()
        self.spin_no_blink.setRange(5, 60)
        self.spin_no_blink.setSuffix(" s")
        self.check_no_blink.toggled.connect(self.spin_no_blink.setEnabled)
        no_blink_row.addWidget(self.check_no_blink)
        no_blink_row.addWidget(self.spin_no_blink)
        no_blink_row.addWidget(QLabel("(empfohlen: 10 s)"))
        no_blink_row.addStretch()
        warn_layout.addRow(no_blink_row)

        self.spin_cooldown = QSpinBox()
        self.spin_cooldown.setRange(1, 30)
        self.spin_cooldown.setSuffix(" min")
        warn_layout.addRow("Pause zwischen Warnungen (empfohlen: 3 min):", self.spin_cooldown)

        self.button_test = QPushButton("Warnung jetzt testen")
        self.button_test.setToolTip(
            "Löst die Warnung sofort über die oben angehakten Kanäle aus."
        )
        self.button_test.clicked.connect(
            lambda: self.test_requested.emit(self.values())
        )
        warn_layout.addRow(self.button_test)

        layout.addWidget(self.warn_box)
        self.radio_warn.toggled.connect(self.warn_box.setEnabled)

        # --- Erkennung ------------------------------------------------------
        detect_box = QGroupBox("Erkennung")
        detect_layout = QFormLayout(detect_box)

        self.slider_sensitivity = QSlider(Qt.Horizontal)
        # Auge-zu-Schwellwert 0.15–0.70, als Slider-Wert ×100
        self.slider_sensitivity.setRange(15, 70)
        self.sensitivity_label = QLabel()
        self.slider_sensitivity.valueChanged.connect(
            lambda v: self.sensitivity_label.setText(f"{v / 100:.2f}")
        )
        sens_row = QHBoxLayout()
        sens_row.addWidget(self.slider_sensitivity)
        sens_row.addWidget(self.sensitivity_label)
        detect_layout.addRow("Auge-zu-Schwellwert:", sens_row)
        detect_layout.addRow(
            QLabel(
                "<small>Standard 0.50. Verringern, wenn Blinzler nicht erkannt "
                "werden; erhöhen, wenn zu viele gezählt werden.</small>"
            )
        )

        self.combo_camera = QComboBox()
        camera_names = list_cameras()
        if camera_names:
            for i, name in enumerate(camera_names):
                self.combo_camera.addItem(name, userData=i)
        else:
            for i in range(5):
                self.combo_camera.addItem(f"Kamera {i}", userData=i)
        detect_layout.addRow("Kamera:", self.combo_camera)
        layout.addWidget(detect_box)

        # --- Haltung ----------------------------------------------------------
        posture_box = QGroupBox("Haltungsüberwachung")
        posture_layout = QFormLayout(posture_box)

        self.check_posture = QCheckBox(
            "Haltung überwachen (Referenz per Knopf im Hauptfenster aufnehmen)"
        )
        posture_layout.addRow(self.check_posture)

        self.spin_shoulder = QSpinBox()
        self.spin_shoulder.setRange(2, 20)
        self.spin_shoulder.setSuffix("°")
        posture_layout.addRow("Toleranz Schultern schief (empfohlen: 7°):", self.spin_shoulder)

        self.spin_head = QSpinBox()
        self.spin_head.setRange(2, 20)
        self.spin_head.setSuffix("°")
        posture_layout.addRow("Toleranz Kopf geneigt (empfohlen: 8°):", self.spin_head)

        self.spin_near = QSpinBox()
        self.spin_near.setRange(5, 40)
        self.spin_near.setSuffix(" %")
        posture_layout.addRow("Toleranz zu nah am Bildschirm (empfohlen: 15 %):", self.spin_near)

        self.spin_slump = QSpinBox()
        self.spin_slump.setRange(3, 20)
        self.spin_slump.setSuffix(" %")
        posture_layout.addRow("Toleranz eingesunken (empfohlen: 8 %):", self.spin_slump)

        self.spin_grace = QSpinBox()
        self.spin_grace.setRange(5, 120)
        self.spin_grace.setSuffix(" s")
        posture_layout.addRow(
            "Warnen erst nach anhaltend schlechter Haltung von (empfohlen: 30 s):",
            self.spin_grace,
        )

        self.spin_posture_cooldown = QSpinBox()
        self.spin_posture_cooldown.setRange(1, 30)
        self.spin_posture_cooldown.setSuffix(" min")
        posture_layout.addRow(
            "Pause zwischen Haltungs-Warnungen (empfohlen: 5 min):",
            self.spin_posture_cooldown,
        )

        move_row = QHBoxLayout()
        self.check_move = QCheckBox("Bewegungs-Erinnerung nach")
        self.spin_move = QSpinBox()
        self.spin_move.setRange(10, 120)
        self.spin_move.setSuffix(" min")
        self.check_move.toggled.connect(self.spin_move.setEnabled)
        move_row.addWidget(self.check_move)
        move_row.addWidget(self.spin_move)
        move_row.addWidget(QLabel("Sitzen am Stück (empfohlen: 45 min)"))
        move_row.addStretch()
        posture_layout.addRow(move_row)

        layout.addWidget(posture_box)

        # --- Extras ---------------------------------------------------------
        extras_box = QGroupBox("Extras")
        extras_layout = QVBoxLayout(extras_box)
        self.check_rule = QCheckBox("20-20-20-Erinnerung (alle 20 Minuten)")
        extras_layout.addWidget(self.check_rule)
        self.check_autostart = QCheckBox("Mit Windows starten")
        if not autostart.is_supported():
            self.check_autostart.setEnabled(False)
            self.check_autostart.setToolTip("Nur unter Windows verfügbar.")
        extras_layout.addWidget(self.check_autostart)
        layout.addWidget(extras_box)

        # --- Buttons ---------------------------------------------------------
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_values()

    def _load_values(self):
        cfg = self.config
        warn_mode = cfg.get("mode") == "warn"
        self.radio_warn.setChecked(warn_mode)
        self.radio_stats.setChecked(not warn_mode)
        self.warn_box.setEnabled(warn_mode)

        self.check_toast.setChecked(cfg.get("warn_toast"))
        self.check_overlay.setChecked(cfg.get("warn_overlay"))
        self.check_sound.setChecked(cfg.get("warn_sound"))
        self.spin_threshold.setValue(int(cfg.get("rate_threshold")))
        self.check_no_blink.setChecked(cfg.get("no_blink_enabled"))
        self.spin_no_blink.setValue(int(cfg.get("no_blink_seconds")))
        self.spin_no_blink.setEnabled(cfg.get("no_blink_enabled"))
        self.spin_cooldown.setValue(max(1, int(cfg.get("warn_cooldown_s")) // 60))
        self.slider_sensitivity.setValue(round(float(cfg.get("blink_threshold")) * 100))
        self.sensitivity_label.setText(f"{cfg.get('blink_threshold'):.2f}")
        saved_camera = int(cfg.get("camera_index"))
        pos = self.combo_camera.findData(saved_camera)
        if pos < 0:  # gespeicherte Kamera aktuell nicht angeschlossen
            self.combo_camera.addItem(
                f"Kamera {saved_camera} (nicht gefunden)", userData=saved_camera
            )
            pos = self.combo_camera.count() - 1
        self.combo_camera.setCurrentIndex(pos)
        self.check_rule.setChecked(cfg.get("rule_20_20_20"))
        self.check_autostart.setChecked(autostart.is_enabled())

        self.check_posture.setChecked(bool(cfg.get("posture_enabled")))
        self.spin_shoulder.setValue(int(cfg.get("posture_tol_shoulder_deg")))
        self.spin_head.setValue(int(cfg.get("posture_tol_head_deg")))
        self.spin_near.setValue(int(cfg.get("posture_tol_near_pct")))
        self.spin_slump.setValue(int(cfg.get("posture_tol_slump_pct")))
        self.spin_grace.setValue(int(cfg.get("posture_grace_s")))
        self.spin_posture_cooldown.setValue(
            max(1, int(cfg.get("posture_cooldown_s")) // 60)
        )
        self.check_move.setChecked(bool(cfg.get("move_enabled")))
        self.spin_move.setValue(int(cfg.get("move_minutes")))
        self.spin_move.setEnabled(bool(cfg.get("move_enabled")))

    def values(self) -> dict:
        return {
            "mode": "warn" if self.radio_warn.isChecked() else "stats",
            "warn_toast": self.check_toast.isChecked(),
            "warn_overlay": self.check_overlay.isChecked(),
            "warn_sound": self.check_sound.isChecked(),
            "rate_threshold": self.spin_threshold.value(),
            "no_blink_enabled": self.check_no_blink.isChecked(),
            "no_blink_seconds": self.spin_no_blink.value(),
            "warn_cooldown_s": self.spin_cooldown.value() * 60,
            "blink_threshold": self.slider_sensitivity.value() / 100.0,
            "camera_index": self.combo_camera.currentData(),
            "rule_20_20_20": self.check_rule.isChecked(),
            "autostart": self.check_autostart.isChecked(),
            "posture_enabled": self.check_posture.isChecked(),
            "posture_tol_shoulder_deg": self.spin_shoulder.value(),
            "posture_tol_head_deg": self.spin_head.value(),
            "posture_tol_near_pct": self.spin_near.value(),
            "posture_tol_slump_pct": self.spin_slump.value(),
            "posture_grace_s": self.spin_grace.value(),
            "posture_cooldown_s": self.spin_posture_cooldown.value() * 60,
            "move_enabled": self.check_move.isChecked(),
            "move_minutes": self.spin_move.value(),
        }
