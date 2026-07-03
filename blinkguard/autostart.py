"""Autostart beim Windows-Login über die Registry (HKCU\\...\\Run)."""

import sys
from pathlib import Path

from blinkguard import APP_NAME

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller-Exe: direkt die Exe starten
        return f'"{sys.executable}"'
    # Aus dem Quellcode: pythonw (ohne Konsole) mit dem Paket starten
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else python
    return f'"{interpreter}" -m blinkguard'


def is_supported() -> bool:
    return sys.platform == "win32"


def is_enabled() -> bool:
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Autostart setzen/entfernen. Gibt False zurück, wenn es fehlschlägt."""
    if not is_supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
