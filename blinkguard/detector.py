"""Blinzelerkennung per Webcam.

Läuft in einem eigenen QThread: liest Kamerabilder und ermittelt mit dem
MediaPipe-FaceLandmarker (Tasks-API) die "eyeBlink"-Blendshapes – einen von
0 (Auge offen) bis 1 (Auge geschlossen) laufenden Score. Ein Blinzler =
Score steigt kurz über den Schwellwert und fällt wieder darunter.

Das Landmarker-Modell (~4 MB) wird beim ersten Start automatisch nach
%APPDATA%/BlinkGuard/models heruntergeladen.
"""

import time
import urllib.request
from collections import deque

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision
from PySide6.QtCore import QThread, Signal

from blinkguard.config import data_dir

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)

TARGET_FPS = 15
RATE_WINDOW_S = 60.0
# Ein Blinzeln dauert 100-400 ms; alles was länger geschlossen ist (z.B.
# Wegschauen nach unten) zählt nicht als Blinzler.
MAX_CLOSED_S = 0.5
# Hysterese: "wieder offen" erst deutlich unter dem Zu-Schwellwert
HYSTERESIS = 0.1


def model_path():
    return data_dir() / "models" / "face_landmarker.task"


def ensure_model() -> str:
    """Lädt das FaceLandmarker-Modell herunter, falls es noch fehlt."""
    path = model_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".download")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(path)
    return str(path)


def blink_score(result) -> float:
    """Mittlerer eyeBlink-Score beider Augen (0 = offen, 1 = geschlossen)."""
    scores = [
        b.score
        for b in result.face_blendshapes[0]
        if b.category_name in ("eyeBlinkLeft", "eyeBlinkRight")
    ]
    return sum(scores) / len(scores) if scores else 0.0


class BlinkDetector(QThread):
    """Kamera-Thread. Signale werden im Qt-Hauptthread verarbeitet."""

    sig_blink = Signal(float)          # Zeitstempel eines erkannten Blinzlers
    # (Rate/min, Gesicht sichtbar, Gesichts-Anteil 60s, Sekunden ohne Blinzeln)
    sig_tick = Signal(float, bool, float, float)
    sig_error = Signal(str)            # Kamera-/Erkennungsfehler (einmalig)

    def __init__(self, camera_index: int, blink_threshold: float, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.blink_threshold = blink_threshold
        self._running = True
        self._paused = False

    # --- Steuerung aus dem Hauptthread -------------------------------------
    def stop(self):
        self._running = False

    def set_paused(self, paused: bool):
        self._paused = paused

    def set_blink_threshold(self, value: float):
        self.blink_threshold = value

    def _open_capture(self):
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0)
        if not cap.isOpened():
            # CAP_DSHOW kann auf manchen Systemen scheitern -> Standard-Backend
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        return cap

    # --- Thread-Hauptschleife ----------------------------------------------
    def run(self):
        try:
            model_file = ensure_model()
        except OSError as exc:
            self.sig_error.emit(
                "Das Erkennungsmodell konnte nicht heruntergeladen werden "
                f"(einmalig ~4 MB, Internet nötig): {exc}"
            )
            return

        cap = self._open_capture()
        if cap is None:
            self.sig_error.emit(
                f"Kamera {self.camera_index} konnte nicht geöffnet werden. "
                "Prüfe die Kameraauswahl in den Einstellungen."
            )
            return

        options = mp_vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=model_file),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        landmarker = mp_vision.FaceLandmarker.create_from_options(options)

        blink_times = deque()        # Zeitstempel der Blinzler (letzte 60 s)
        face_samples = deque()       # (Zeitstempel, Gesicht sichtbar?)
        closed_since = None          # Beginn der aktuellen Augen-zu-Phase
        eyes_closed = False
        blink_marker = None          # letzter Blinzler bzw. Gesichts-Wiederkehr
        last_tick = 0.0
        start = time.monotonic()
        last_ts_ms = -1
        frame_interval = 1.0 / TARGET_FPS

        try:
            while self._running:
                loop_start = time.monotonic()

                if self._paused:
                    # Kamera komplett freigeben: LED aus, andere Apps (z.B.
                    # Videocalls) können sie nutzen
                    if cap is not None:
                        cap.release()
                        cap = None
                    blink_times.clear()
                    face_samples.clear()
                    closed_since = None
                    eyes_closed = False
                    blink_marker = None
                    time.sleep(0.2)
                    continue

                if cap is None:  # nach Pause wieder öffnen
                    cap = self._open_capture()
                    if cap is None:
                        self.sig_error.emit(
                            f"Kamera {self.camera_index} konnte nach der Pause "
                            "nicht wieder geöffnet werden."
                        )
                        return

                ok, frame = cap.read()
                now = time.monotonic()
                if not ok:
                    self.sig_error.emit(
                        "Kamerabild konnte nicht gelesen werden. Wird die Kamera "
                        "gerade von einer anderen Anwendung verwendet?"
                    )
                    return

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                # detect_for_video verlangt streng steigende Zeitstempel
                ts_ms = max(int((now - start) * 1000), last_ts_ms + 1)
                last_ts_ms = ts_ms
                result = landmarker.detect_for_video(image, ts_ms)

                face_present = bool(result.face_landmarks)
                face_samples.append((now, face_present))

                if face_present:
                    if blink_marker is None:
                        # Gesicht (wieder) da: Ohne-Blinzeln-Uhr neu starten
                        blink_marker = now
                    score = blink_score(result)
                    if not eyes_closed and score >= self.blink_threshold:
                        eyes_closed = True
                        closed_since = now
                    elif eyes_closed and score < self.blink_threshold - HYSTERESIS:
                        eyes_closed = False
                        if closed_since is not None and (now - closed_since) <= MAX_CLOSED_S:
                            blink_times.append(now)
                            blink_marker = now
                            self.sig_blink.emit(time.time())
                        closed_since = None
                else:
                    closed_since = None
                    eyes_closed = False
                    blink_marker = None

                # Rollierendes 60-Sekunden-Fenster pflegen
                cutoff = now - RATE_WINDOW_S
                while blink_times and blink_times[0] < cutoff:
                    blink_times.popleft()
                while face_samples and face_samples[0][0] < cutoff:
                    face_samples.popleft()

                # Einmal pro Sekunde Status an den Hauptthread melden
                if now - last_tick >= 1.0:
                    last_tick = now
                    face_ratio = sum(1 for _, p in face_samples if p) / len(face_samples)
                    window = min(RATE_WINDOW_S, max(1.0, now - face_samples[0][0]))
                    rate = len(blink_times) * (60.0 / window)
                    since_blink = (now - blink_marker) if blink_marker is not None else 0.0
                    self.sig_tick.emit(rate, face_present, face_ratio, since_blink)

                # CPU schonen: auf Ziel-Framerate drosseln
                elapsed = time.monotonic() - loop_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
        finally:
            landmarker.close()
            if cap is not None:
                cap.release()
