@echo off
REM Baut BlinkGuard als eigenstaendige Windows-App (dist\BlinkGuard\BlinkGuard.exe)
REM Voraussetzung: pip install -r requirements.txt pyinstaller

python -m PyInstaller --noconfirm --noconsole --name BlinkGuard ^
    --collect-all mediapipe ^
    --add-data "blinkguard\assets;blinkguard\assets" ^
    blinkguard\__main__.py

echo.
echo Fertig: dist\BlinkGuard\BlinkGuard.exe
pause
