# 👁 BlinkGuard – PC Health Assistant

Dein Gesundheitsassistent für die Bildschirmarbeit, komplett lokal per Webcam: BlinkGuard misst, **wie oft du blinzelst**, analysiert deine **Sitzhaltung physiotherapeutisch fundiert** (Geierhals, hochgezogene Schultern, schiefe Schulterlinie, geneigter Kopf, zu nah am Bildschirm, eingesunken) relativ zu deiner selbst kalibrierten Referenzhaltung, und erinnert dich ans **Aufstehen**, wenn du zu lange am Stück sitzt. Die **KI-Vorschau** zeigt dir live, was die Erkennung sieht.

**Warum?** Gesund sind etwa 15–20 Blinzler pro Minute. Bei konzentrierter Arbeit am Bildschirm sinkt die Rate oft auf 5–7/min – die Augen trocknen aus, werden müde und gereizt. BlinkGuard erkennt das und erinnert dich rechtzeitig.

## Funktionen

- **Blinzelerkennung per Webcam** – MediaPipe FaceMesh + Eye-Aspect-Ratio, läuft komplett lokal, keine Bilder verlassen deinen PC, nichts wird aufgezeichnet
- **Lebt im System-Tray** – kein Fenster im Weg; Linksklick aufs Tray-Icon öffnet die Statistik, das Icon zeigt den Zustand (grün = alles gut, orange = zu wenig geblinzelt, grau = pausiert, rot = Kameraproblem)
- **Zwei Modi** (in den Einstellungen umschaltbar):
  - *Blinzelwarnung + Statistik* – warnt, wenn deine Blinzelrate zu lange unter dem Schwellwert liegt
  - *Nur Statistik* – misst nur, warnt nie
- **Warnkanäle frei kombinierbar**: Windows-Benachrichtigung, **blaue Bildschirm-Aura** (Glühen am Rand, das ~20 % in den Bildschirm fadet – wie die Low-Health-Vignette in Shootern, klick-durchlässig) und **Wassertropfen-Sound** – mit **„Warnung jetzt testen"-Button** in den Einstellungen
- **Zwei Warn-Trigger**: dauerhaft niedrige Blinzelrate (empfohlen: unter 8/min) und **Sofortwarnung nach X Sekunden ohne Blinzeln** (empfohlen: 10 s) – beide einzeln einstellbar, empfohlene Werte stehen direkt daneben
- **Statistik mit Tagesverlauf** – aktuelle Rate, Blinzler heute, Ø-Rate, aktive Zeit und ein Balkendiagramm über den Tag (Speicherung lokal in SQLite, nur Zahlen pro Minute)
- **Hauptfenster mit allem an einem Ort** – Kopfzeile mit Anwesenheitsstatus (● Aktiv / ○ Abwesend / ⏸ Pausiert), Pause-Knopf und ⚙-Einstellungen; Live-Panel, in dem jeder Blinzler sofort aufblitzt (Sitzungszähler + Uhrzeit) und ein Balken „Ohne Blinzeln: X s" bis zur Warnschwelle läuft. Abwesenheit wird automatisch erkannt: ohne Gesicht wird nichts gezählt und nie gewarnt
- **Haltungsüberwachung mit persönlicher Kalibrierung**: Im Hauptfenster einmal gerade hinsetzen und „als gut speichern" klicken – ab dann wird relativ zu *deiner* Referenz geprüft: **Geierhals** (Kopf vorgeschoben, erkannt am Verhältnis Gesichtsgröße/Schulterbreite), **Schultern hochgezogen** (Nackenlinie Ohr→Schulter verkürzt), Schultern ungleich hoch, Kopf geneigt, zu nah am Bildschirm, eingesunken. Jede Prüfung einzeln abschaltbar, alle Toleranzen einstellbar – wahlweise über die Profile **Sanft / Ausgewogen / Streng (Physio-Modus)** oder als eigene Werte. Messwerte werden über ~5 s geglättet, kurzes Bücken löst nichts aus. Grenze der Technik: Die Kamera sieht nur Kopf und Schultern – der untere Rücken bleibt unsichtbar
- **KI-Vorschau**: Ein Klick im Hauptfenster zeigt das Live-Kamerabild mit allem, was die Erkennung sieht – Augenringe (grün), Schulterlinie (gelb), Nackenlinien Ohr→Schulter (orange). Nur lokal, nur solange das Fenster offen ist
- **Bewegungs-Erinnerung**: Wer länger als X Minuten am Stück sitzt (empfohlen: 45), wird ans Aufstehen erinnert; erst 3 Minuten Abwesenheit zählen als echte Pause
- **Extras**: Autostart mit Windows, Pause-Button im Tray-Menü (gibt die Kamera vollständig frei – z. B. für Videocalls), 20-20-20-Erinnerung, einstellbare Empfindlichkeit und Warnschwelle

## Installation (empfohlen): fertige App herunterladen

Auf der [Releases-Seite](https://github.com/Shodan93/Blink/releases) das aktuelle `BlinkGuard-windows.zip` herunterladen, entpacken und `BlinkGuard.exe` starten – fertig, kein Python nötig. Alle Abhängigkeiten sind im ZIP enthalten (gebaut von GitHub Actions, siehe `.github/workflows/release.yml`).

Alternativ aus dem Quellcode: einfach `install.bat` doppelklicken – das Skript legt eine venv an, lädt alle Abhängigkeiten und baut die Exe nach `dist\BlinkGuard\`.

## Schnellstart (aus dem Quellcode, manuell)

Voraussetzung: **Python 3.10 oder neuer** (64-bit, getestet bis 3.14) von [python.org](https://www.python.org/downloads/).

In der **PowerShell** im Projektordner:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m blinkguard
```

(In der klassischen Eingabeaufforderung `cmd` heißt die Aktivierung `.venv\Scripts\activate`, in der PowerShell `.\.venv\Scripts\Activate.ps1` – die Befehle oben funktionieren aber auch ganz ohne Aktivierung.)

Die App startet direkt in den Infobereich (Tray) unten rechts. Beim **ersten Start** lädt sie einmalig das Erkennungsmodell (~4 MB) herunter, und Windows fragt ggf. nach der **Kamera-Berechtigung** – zulassen.

## Als .exe bauen (ohne Python starten)

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --noconsole --name BlinkGuard --collect-all mediapipe blinkguard\__main__.py
```

(oder nach Aktivierung der venv einfach `.\build.bat`)

Danach liegt die fertige App unter `dist\BlinkGuard\BlinkGuard.exe`. Den ganzen `BlinkGuard`-Ordner kannst du beliebig verschieben; ein Doppelklick auf die Exe startet die App ohne Konsolenfenster.

## Bedienung

| Aktion | Wirkung |
|---|---|
| Linksklick auf Tray-Icon | Statistik-Fenster öffnen |
| Rechtsklick auf Tray-Icon | Menü: Statistik, Einstellungen, Pause, Beenden |
| Statistik-Fenster schließen | Fenster wird nur versteckt, App läuft im Tray weiter |

## Einstellungen

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Modus | Warnung + Statistik | Oder „Nur Statistik“ – dann gibt es nie Warnungen |
| Warnkanäle | Benachrichtigung | Toast, Overlay und Ton beliebig kombinierbar |
| Warnen unter | 8 Blinzler/min | Schwellwert für die Raten-Warnung |
| Sofortwarnung ohne Blinzeln | an, 10 s | Warnt direkt, wenn so lange kein Blinzeln erkannt wurde |
| Pause zwischen Warnungen | 3 min | Damit die Erinnerung nicht nervt |
| Auge-zu-Schwellwert | 0.50 | Verringern, wenn Blinzler nicht erkannt werden; erhöhen bei Fehlzählungen |
| Kamera | Systemstandard | Dropdown mit den Namen aller erkannten Kameras |
| 20-20-20-Erinnerung | aus | Alle 20 min: 20 s auf etwas in ~6 m Entfernung schauen |
| Autostart | aus | Startet BlinkGuard beim Windows-Login |

Gewarnt wird nur, wenn du auch wirklich vor dem Bildschirm sitzt (Gesicht in mindestens 70 % der letzten Minute erkannt) – Aufstehen oder Wegschauen löst keine Fehlwarnung aus.

## Datenschutz

- Die Kamerabilder werden **nur im Arbeitsspeicher** analysiert und sofort verworfen – nichts wird gespeichert oder gesendet.
- Gespeichert werden ausschließlich Zahlen: Blinzler pro Minute und Sekunden mit erkanntem Gesicht, lokal in `%APPDATA%\BlinkGuard\stats.db`.
- Einstellungen liegen in `%APPDATA%\BlinkGuard\config.json`, das Erkennungsmodell in `%APPDATA%\BlinkGuard\models\`.

## Technik

- **Erkennung:** Der MediaPipe-FaceLandmarker (Tasks-API) liefert neben 478 Gesichts-Landmarken auch *Blendshapes*, darunter `eyeBlinkLeft`/`eyeBlinkRight` – einen Score von 0 (Auge offen) bis 1 (geschlossen). Steigt der Mittelwert beider Augen kurz (≤ 0,5 s) über den Schwellwert und fällt wieder (mit Hysterese), zählt das als Blinzler.
- **Rate:** Blinzler in einem rollierenden 60-Sekunden-Fenster.
- **UI:** PySide6 (Qt) – Tray-Icon, Einstellungs-Dialog, Statistik-Fenster mit selbst gezeichnetem Diagramm.
- **Ressourcen:** Die Kamera wird mit ~15 fps bei 640×480 ausgelesen, um die CPU zu schonen.
