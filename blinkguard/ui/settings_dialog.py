"""Einstellungs-Dialog: Tabs für Blinzeln, Haltung und Allgemeines."""

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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from blinkguard import autostart
from blinkguard.config import Config

# Physiotherapeutisch motivierte Voreinstellungen für die Haltungsanalyse
POSTURE_PRESETS = {
    "soft": {
        "posture_tol_shoulder_deg": 10,
        "posture_tol_head_deg": 12,
        "posture_tol_near_pct": 22,
        "posture_tol_slump_pct": 12,
        "posture_tol_fhp_pct": 18,
        "posture_tol_shrug_pct": 15,
        "posture_grace_s": 45,
    },
    "balanced": {
        "posture_tol_shoulder_deg": 7,
        "posture_tol_head_deg": 8,
        "posture_tol_near_pct": 15,
        "posture_tol_slump_pct": 8,
        "posture_tol_fhp_pct": 12,
        "posture_tol_shrug_pct": 10,
        "posture_grace_s": 30,
    },
    "strict": {
        "posture_tol_shoulder_deg": 5,
        "posture_tol_head_deg": 6,
        "posture_tol_near_pct": 10,
        "posture_tol_slump_pct": 6,
        "posture_tol_fhp_pct": 8,
        "posture_tol_shrug_pct": 6,
        "posture_grace_s": 20,
    },
}
PRESET_ORDER = ["soft", "balanced", "strict", "custom"]
PRESET_LABELS = {
    "soft": "Sanft – wenig Meldungen",
    "balanced": "Ausgewogen (empfohlen)",
    "strict": "Streng – Physio-Modus",
    "custom": "Eigene Werte",
}


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
        self.setWindowTitle("PC Health Assistant – Einstellungen")
        self.setMinimumWidth(560)
        self._loading = False

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_blink_tab(), "Blinzeln && Warnungen")
        tabs.addTab(self._build_posture_tab(), "Haltung")
        tabs.addTab(self._build_general_tab(), "Allgemein")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_values()

    # --- Tab: Blinzeln & Warnungen ------------------------------------------
    def _build_blink_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        mode_box = QGroupBox("Modus")
        mode_layout = QVBoxLayout(mode_box)
        self.radio_warn = QRadioButton("Warnungen + Statistik")
        self.radio_stats = QRadioButton("Nur Statistik (keine Warnungen)")
        mode_layout.addWidget(self.radio_warn)
        mode_layout.addWidget(self.radio_stats)
        layout.addWidget(mode_box)

        channel_box = QGroupBox("Warnkanäle (gelten für Blinzeln und Haltung)")
        channel_layout = QFormLayout(channel_box)
        self.check_toast = QCheckBox("Windows-Benachrichtigung")
        self.check_overlay = QCheckBox("Blaue Bildschirm-Aura (Glühen am Rand)")
        self.check_sound = QCheckBox("Wassertropfen-Sound")
        channel_layout.addRow(self.check_toast)
        channel_layout.addRow(self.check_overlay)
        channel_layout.addRow(self.check_sound)
        self.button_test = QPushButton("Warnung jetzt testen")
        self.button_test.setToolTip(
            "Löst die Warnung sofort über die oben angehakten Kanäle aus."
        )
        self.button_test.clicked.connect(
            lambda: self.test_requested.emit(self.values())
        )
        channel_layout.addRow(self.button_test)
        layout.addWidget(channel_box)

        self.warn_box = QGroupBox("Blinzelwarnung")
        warn_layout = QFormLayout(self.warn_box)
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
        warn_layout.addRow(
            "Pause zwischen Warnungen (empfohlen: 3 min):", self.spin_cooldown
        )
        layout.addWidget(self.warn_box)
        self.radio_warn.toggled.connect(self.warn_box.setEnabled)
        layout.addStretch()
        return tab

    # --- Tab: Haltung ----------------------------------------------------------
    def _build_posture_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        intro = QLabel(
            "<small>Alle Prüfungen messen relativ zu deiner kalibrierten "
            "Referenzhaltung (Hauptfenster → „als gut speichern“). "
            "<b>Geierhals</b> (vorgeschobener Kopf) überlastet die Halswirbelsäule "
            "und ist eine häufige Ursache für Nackenschmerzen und Spannungs­kopfschmerz; "
            "<b>hochgezogene Schultern</b> verspannen den Trapezmuskel. "
            "Dauerhaft <b>eingesunkenes</b> Sitzen staucht die Bandscheiben.</small>"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.check_posture = QCheckBox("Haltungsüberwachung aktivieren")
        layout.addWidget(self.check_posture)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Profil:"))
        self.combo_preset = QComboBox()
        for key in PRESET_ORDER:
            self.combo_preset.addItem(PRESET_LABELS[key], userData=key)
        self.combo_preset.currentIndexChanged.connect(self._apply_preset)
        preset_row.addWidget(self.combo_preset, stretch=1)
        layout.addLayout(preset_row)

        checks_box = QGroupBox("Prüfungen und Toleranzen")
        form = QFormLayout(checks_box)

        def check_row(label_default: str, spin: QSpinBox, suffix: str, tip: str):
            check = QCheckBox(label_default)
            check.setToolTip(tip)
            spin.setSuffix(suffix)
            spin.setToolTip(tip)
            check.toggled.connect(spin.setEnabled)
            row = QHBoxLayout()
            row.addWidget(check)
            row.addStretch()
            row.addWidget(spin)
            form.addRow(row)
            return check

        self.spin_shoulder = QSpinBox(); self.spin_shoulder.setRange(2, 20)
        self.check_shoulder = check_row(
            "Schultern ungleich hoch", self.spin_shoulder, "°",
            "Seitliches Abkippen der Schulterlinie – typisch beim Aufstützen "
            "auf einen Ellenbogen.",
        )
        self.spin_head = QSpinBox(); self.spin_head.setRange(2, 20)
        self.check_head = check_row(
            "Kopf zur Seite geneigt", self.spin_head, "°",
            "Dauerhafte Seitneigung belastet die Nackenmuskulatur einseitig.",
        )
        self.spin_near = QSpinBox(); self.spin_near.setRange(5, 40)
        self.check_near = check_row(
            "Zu nah am Bildschirm", self.spin_near, " %",
            "Ganzer Oberkörper rückt zum Monitor – Zeichen für Ermüdung oder "
            "zu kleine Schrift.",
        )
        self.spin_slump = QSpinBox(); self.spin_slump.setRange(3, 20)
        self.check_slump = check_row(
            "Eingesunken / abgesackt", self.spin_slump, " %",
            "Kopf und Schultern sinken nach unten – der Rücken wird rund.",
        )
        self.spin_fhp = QSpinBox(); self.spin_fhp.setRange(4, 30)
        self.check_fhp = check_row(
            "Geierhals (Kopf vorgeschoben)", self.spin_fhp, " %",
            "Der Kopf schiebt sich vor, die Schultern bleiben hinten – erkannt "
            "am wachsenden Verhältnis von Gesichtsgröße zu Schulterbreite. "
            "Jeder Zentimeter Vorschub erhöht die Last auf die Halswirbelsäule "
            "spürbar.",
        )
        self.spin_shrug = QSpinBox(); self.spin_shrug.setRange(3, 40)
        self.check_shrug = check_row(
            "Schultern hochgezogen", self.spin_shrug, " %",
            "Die Schultern wandern Richtung Ohren (Nackenlinie verkürzt sich) – "
            "klassische Stress-Verspannung des Trapezmuskels. Wird je Seite "
            "getrennt gemessen, sodass auch einseitiges Hochziehen auffällt. "
            "3–6 % = sehr empfindlich.",
        )
        layout.addWidget(checks_box)

        timing_box = QGroupBox("Zeitverhalten")
        timing = QFormLayout(timing_box)
        self.spin_grace = QSpinBox()
        self.spin_grace.setRange(5, 120)
        self.spin_grace.setSuffix(" s")
        timing.addRow("Warnen erst nach anhaltend schlechter Haltung von:", self.spin_grace)
        self.spin_posture_cooldown = QSpinBox()
        self.spin_posture_cooldown.setRange(1, 30)
        self.spin_posture_cooldown.setSuffix(" min")
        timing.addRow(
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
        timing.addRow(move_row)

        still_row = QHBoxLayout()
        self.check_still = QCheckBox("Stillsitz-Erinnerung nach")
        self.check_still.setToolTip(
            "Erinnert ans Bewegen, wenn sich Kopf und Schultern über den "
            "gesamten Zeitraum praktisch nicht bewegt haben – statisches "
            "Sitzen ermüdet die Muskulatur auch in guter Haltung."
        )
        self.spin_still = QSpinBox()
        self.spin_still.setRange(5, 60)
        self.spin_still.setSuffix(" min")
        self.check_still.toggled.connect(self.spin_still.setEnabled)
        still_row.addWidget(self.check_still)
        still_row.addWidget(self.spin_still)
        still_row.addWidget(QLabel("ohne nennenswerte Bewegung (empfohlen: 10 min)"))
        still_row.addStretch()
        timing.addRow(still_row)
        layout.addWidget(timing_box)

        # Jede manuelle Änderung schaltet das Profil auf "Eigene Werte"
        for spin in (
            self.spin_shoulder, self.spin_head, self.spin_near,
            self.spin_slump, self.spin_fhp, self.spin_shrug, self.spin_grace,
        ):
            spin.valueChanged.connect(self._mark_custom)

        layout.addStretch()
        return tab

    # --- Tab: Allgemein --------------------------------------------------------
    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        detect_box = QGroupBox("Erkennung")
        detect_layout = QFormLayout(detect_box)
        self.slider_sensitivity = QSlider(Qt.Horizontal)
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
                "werden; erhöhen, wenn zu viele gezählt werden. Die KI-Vorschau "
                "im Hauptfenster zeigt, was die Erkennung sieht.</small>"
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

        extras_box = QGroupBox("Extras")
        extras_layout = QVBoxLayout(extras_box)
        self.check_rule = QCheckBox("20-20-20-Erinnerung (alle 20 Minuten)")
        self.check_rule.setToolTip(
            "Alle 20 Minuten 20 Sekunden auf etwas in ~6 m Entfernung schauen – "
            "entspannt den Ziliarmuskel des Auges."
        )
        extras_layout.addWidget(self.check_rule)
        self.check_autostart = QCheckBox("Mit Windows starten")
        if not autostart.is_supported():
            self.check_autostart.setEnabled(False)
            self.check_autostart.setToolTip("Nur unter Windows verfügbar.")
        extras_layout.addWidget(self.check_autostart)
        layout.addWidget(extras_box)
        layout.addStretch()
        return tab

    # --- Presets ---------------------------------------------------------------
    def _apply_preset(self):
        if self._loading:
            return
        key = self.combo_preset.currentData()
        preset = POSTURE_PRESETS.get(key)
        if preset is None:  # "custom"
            return
        self._loading = True
        self.spin_shoulder.setValue(preset["posture_tol_shoulder_deg"])
        self.spin_head.setValue(preset["posture_tol_head_deg"])
        self.spin_near.setValue(preset["posture_tol_near_pct"])
        self.spin_slump.setValue(preset["posture_tol_slump_pct"])
        self.spin_fhp.setValue(preset["posture_tol_fhp_pct"])
        self.spin_shrug.setValue(preset["posture_tol_shrug_pct"])
        self.spin_grace.setValue(preset["posture_grace_s"])
        self._loading = False

    def _mark_custom(self):
        if not self._loading:
            self.combo_preset.setCurrentIndex(PRESET_ORDER.index("custom"))

    # --- Laden / Speichern -------------------------------------------------------
    def _load_values(self):
        cfg = self.config
        self._loading = True

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

        self.check_posture.setChecked(bool(cfg.get("posture_enabled")))
        preset = cfg.get("posture_preset")
        if preset not in PRESET_ORDER:
            preset = "custom"
        self.combo_preset.setCurrentIndex(PRESET_ORDER.index(preset))
        for check, key, spin, tol_key in (
            (self.check_shoulder, "posture_check_shoulder", self.spin_shoulder, "posture_tol_shoulder_deg"),
            (self.check_head, "posture_check_head", self.spin_head, "posture_tol_head_deg"),
            (self.check_near, "posture_check_near", self.spin_near, "posture_tol_near_pct"),
            (self.check_slump, "posture_check_slump", self.spin_slump, "posture_tol_slump_pct"),
            (self.check_fhp, "posture_check_fhp", self.spin_fhp, "posture_tol_fhp_pct"),
            (self.check_shrug, "posture_check_shrug", self.spin_shrug, "posture_tol_shrug_pct"),
        ):
            check.setChecked(bool(cfg.get(key)))
            spin.setValue(int(cfg.get(tol_key)))
            spin.setEnabled(bool(cfg.get(key)))
        self.spin_grace.setValue(int(cfg.get("posture_grace_s")))
        self.spin_posture_cooldown.setValue(max(1, int(cfg.get("posture_cooldown_s")) // 60))
        self.check_move.setChecked(bool(cfg.get("move_enabled")))
        self.spin_move.setValue(int(cfg.get("move_minutes")))
        self.spin_move.setEnabled(bool(cfg.get("move_enabled")))
        self.check_still.setChecked(bool(cfg.get("still_enabled")))
        self.spin_still.setValue(int(cfg.get("still_minutes")))
        self.spin_still.setEnabled(bool(cfg.get("still_enabled")))

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

        self._loading = False

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
            "posture_preset": self.combo_preset.currentData(),
            "posture_check_shoulder": self.check_shoulder.isChecked(),
            "posture_check_head": self.check_head.isChecked(),
            "posture_check_near": self.check_near.isChecked(),
            "posture_check_slump": self.check_slump.isChecked(),
            "posture_check_fhp": self.check_fhp.isChecked(),
            "posture_check_shrug": self.check_shrug.isChecked(),
            "posture_tol_shoulder_deg": self.spin_shoulder.value(),
            "posture_tol_head_deg": self.spin_head.value(),
            "posture_tol_near_pct": self.spin_near.value(),
            "posture_tol_slump_pct": self.spin_slump.value(),
            "posture_tol_fhp_pct": self.spin_fhp.value(),
            "posture_tol_shrug_pct": self.spin_shrug.value(),
            "posture_grace_s": self.spin_grace.value(),
            "posture_cooldown_s": self.spin_posture_cooldown.value() * 60,
            "move_enabled": self.check_move.isChecked(),
            "move_minutes": self.spin_move.value(),
            "still_enabled": self.check_still.isChecked(),
            "still_minutes": self.spin_still.value(),
        }
