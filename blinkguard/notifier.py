"""Auslösen der Blinzelwarnung über die konfigurierten Kanäle."""

import sys
import threading

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from blinkguard.config import Config, asset_path
from blinkguard.ui.aura import AuraOverlay

WARN_TITLE = "BlinkGuard – Augen-Erinnerung"
WARN_TEXT = (
    "Du blinzelst gerade sehr selten ({rate:.0f}×/min). "
    "Blinzle ein paar Mal bewusst, das hält die Augen feucht."
)
NO_BLINK_TEXT = (
    "Seit {seconds:.0f} Sekunden kein Blinzeln – "
    "kurz die Augen schließen tut gut."
)
RULE_TITLE = "BlinkGuard – 20-20-20-Regel"
RULE_TEXT = (
    "Kurze Augenpause: Schau 20 Sekunden auf etwas, "
    "das mindestens 6 Meter entfernt ist."
)


def _play_sound():
    """Wassertropfen-Sound (läuft asynchron, blockiert die UI nicht)."""
    wav = asset_path("water_drop.wav")
    if sys.platform == "win32" and wav.exists():
        import winsound

        winsound.PlaySound(
            str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT
        )
        return

    def _fallback():
        try:
            if sys.platform == "win32":
                import winsound

                winsound.Beep(740, 140)
                winsound.Beep(988, 200)
            else:
                QApplication.beep()
        except Exception:
            QApplication.beep()

    threading.Thread(target=_fallback, daemon=True).start()


class Notifier:
    def __init__(self, tray: QSystemTrayIcon, config: Config):
        self.tray = tray
        self.config = config
        self.aura = AuraOverlay()

    def _fire(self, text: str, channels: dict):
        if channels.get("warn_toast"):
            self.tray.showMessage(WARN_TITLE, text, QSystemTrayIcon.Information, 6000)
        if channels.get("warn_overlay"):
            self.aura.flash()
        if channels.get("warn_sound"):
            _play_sound()

    def _config_channels(self) -> dict:
        return {
            "warn_toast": self.config.get("warn_toast"),
            "warn_overlay": self.config.get("warn_overlay"),
            "warn_sound": self.config.get("warn_sound"),
        }

    def warn_low_blink_rate(self, rate: float):
        self._fire(WARN_TEXT.format(rate=rate), self._config_channels())

    def warn_no_blink(self, seconds: float):
        self._fire(NO_BLINK_TEXT.format(seconds=seconds), self._config_channels())

    def test_warning(self, channels: dict):
        """Warnung sofort auslösen – für den Test-Button in den Einstellungen.

        Nutzt die im Dialog gerade ausgewählten Kanäle, nicht die
        gespeicherte Konfiguration.
        """
        self._fire("Testwarnung – so sieht die Blinzelerinnerung aus.", channels)

    def remind_20_20_20(self):
        self.tray.showMessage(RULE_TITLE, RULE_TEXT, QSystemTrayIcon.Information, 8000)
        if self.config.get("warn_sound"):
            _play_sound()

    def camera_error(self, message: str):
        self.tray.showMessage(
            "BlinkGuard – Kameraproblem", message, QSystemTrayIcon.Warning, 8000
        )
