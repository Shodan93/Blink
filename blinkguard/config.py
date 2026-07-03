"""Laden und Speichern der Benutzereinstellungen (JSON in %APPDATA%/BlinkGuard)."""

import json
import os
import sys
from pathlib import Path

APP_DIR_NAME = "BlinkGuard"

DEFAULTS = {
    # "warn" = Blinzelwarnung + Statistik, "stats" = nur Statistik
    "mode": "warn",
    # Warnkanäle (beliebig kombinierbar)
    "warn_toast": True,
    "warn_overlay": False,
    "warn_sound": False,
    # Warnung, wenn Blinzelrate (Blinzler/Minute) unter diesen Wert fällt
    "rate_threshold": 8,
    # Mindestabstand zwischen zwei Warnungen in Sekunden
    "warn_cooldown_s": 180,
    # Auge-zu-Schwellwert für den eyeBlink-Score (0-1); kleiner = empfindlicher
    "blink_threshold": 0.5,
    # Index der Webcam (0 = Standardkamera)
    "camera_index": 0,
    # App beim Windows-Login automatisch starten
    "autostart": False,
    # Alle 20 Minuten an die 20-20-20-Regel erinnern
    "rule_20_20_20": False,
}


def data_dir() -> Path:
    """Verzeichnis für Einstellungen und Statistik-Datenbank."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA", str(Path.home()))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    d = Path(base) / APP_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


class Config:
    def __init__(self):
        self.path = data_dir() / "config.json"
        self._values = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            for key in DEFAULTS:
                if key in stored:
                    self._values[key] = stored[key]
        except (OSError, ValueError):
            pass  # erste Ausführung oder defekte Datei -> Defaults

    def save(self):
        try:
            self.path.write_text(
                json.dumps(self._values, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def get(self, key):
        return self._values[key]

    def set(self, key, value):
        self._values[key] = value

    def update(self, values: dict):
        for key, value in values.items():
            if key in DEFAULTS:
                self._values[key] = value
        self.save()
