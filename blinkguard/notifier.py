"""Auslösen der Blinzelwarnung über die konfigurierten Kanäle."""

import sys

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from blinkguard.config import Config
from blinkguard.ui.overlay import OverlayWarning

WARN_TITLE = "BlinkGuard – Augen-Erinnerung"
WARN_TEXT = (
    "Du blinzelst gerade sehr selten ({rate:.0f}×/min). "
    "Blinzle ein paar Mal bewusst, das hält die Augen feucht."
)
RULE_TITLE = "BlinkGuard – 20-20-20-Regel"
RULE_TEXT = (
    "Kurze Augenpause: Schau 20 Sekunden auf etwas, "
    "das mindestens 6 Meter entfernt ist."
)


def _play_sound():
    if sys.platform == "win32":
        import winsound

        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    else:
        QApplication.beep()


class Notifier:
    def __init__(self, tray: QSystemTrayIcon, config: Config):
        self.tray = tray
        self.config = config
        self.overlay = OverlayWarning()

    def warn_low_blink_rate(self, rate: float):
        text = WARN_TEXT.format(rate=rate)
        if self.config.get("warn_toast"):
            self.tray.showMessage(WARN_TITLE, text, QSystemTrayIcon.Information, 6000)
        if self.config.get("warn_overlay"):
            self.overlay.show_message("Blinzeln nicht vergessen! 👁")
        if self.config.get("warn_sound"):
            _play_sound()

    def remind_20_20_20(self):
        self.tray.showMessage(RULE_TITLE, RULE_TEXT, QSystemTrayIcon.Information, 8000)
        if self.config.get("warn_sound"):
            _play_sound()

    def camera_error(self, message: str):
        self.tray.showMessage(
            "BlinkGuard – Kameraproblem", message, QSystemTrayIcon.Warning, 8000
        )
