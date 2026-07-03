@echo off
REM Einmalige Einrichtung aus dem Quellcode: legt ein virtuelles Environment an,
REM laedt alle Abhaengigkeiten und baut die fertige BlinkGuard.exe.
REM (Wer nicht selbst bauen will: fertiges ZIP gibt es unter GitHub -> Releases)

where python >nul 2>nul
if errorlevel 1 (
    echo Python wurde nicht gefunden. Bitte von https://www.python.org/downloads/
    echo installieren und dabei "Add python.exe to PATH" anhaken.
    pause
    exit /b 1
)

echo [1/3] Virtuelles Environment anlegen ...
python -m venv .venv
if errorlevel 1 (pause & exit /b 1)

echo [2/3] Abhaengigkeiten installieren (kann einige Minuten dauern) ...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (pause & exit /b 1)

echo [3/3] BlinkGuard.exe bauen ...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --noconsole --name BlinkGuard --collect-all mediapipe blinkguard\__main__.py
if errorlevel 1 (pause & exit /b 1)

echo.
echo Fertig! Die App liegt unter: dist\BlinkGuard\BlinkGuard.exe
pause
