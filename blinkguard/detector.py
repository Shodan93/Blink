"""Blinzelerkennung per Webcam.

Läuft in einem eigenen QThread: liest Kamerabilder, ermittelt mit MediaPipe
FaceMesh die Augen-Landmarken und erkennt Blinzler über die Eye Aspect Ratio
(EAR). Ein Blinzler = EAR fällt kurz unter den Schwellwert und steigt wieder.
"""

import time
from collections import deque

import cv2
import mediapipe as mp
from PySide6.QtCore import QThread, Signal

# MediaPipe-FaceMesh-Landmarken je Auge: [außen, oben1, oben2, innen, unten2, unten1]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
LEFT_EYE = [362, 385, 387, 263, 373, 380]

TARGET_FPS = 15
RATE_WINDOW_S = 60.0
# Ein Blinzeln dauert 100-400 ms; alles was länger geschlossen ist (z.B.
# Wegschauen nach unten) zählt nicht als Blinzler.
MAX_CLOSED_S = 0.5


def _dist(a, b) -> float:
    return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5


def eye_aspect_ratio(landmarks, idx) -> float:
    p = [landmarks[i] for i in idx]
    horizontal = _dist(p[0], p[3])
    if horizontal <= 0.0:
        return 0.0
    vertical = _dist(p[1], p[5]) + _dist(p[2], p[4])
    return vertical / (2.0 * horizontal)


class BlinkDetector(QThread):
    """Kamera-Thread. Signale werden im Qt-Hauptthread verarbeitet."""

    sig_blink = Signal(float)          # Zeitstempel eines erkannten Blinzlers
    sig_tick = Signal(float, bool, float)  # (Rate/min, Gesicht sichtbar, Gesichts-Anteil 60s)
    sig_error = Signal(str)            # Kamera-/Erkennungsfehler (einmalig)

    def __init__(self, camera_index: int, ear_threshold: float, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.ear_threshold = ear_threshold
        self._running = True
        self._paused = False

    # --- Steuerung aus dem Hauptthread -------------------------------------
    def stop(self):
        self._running = False

    def set_paused(self, paused: bool):
        self._paused = paused

    def set_ear_threshold(self, value: float):
        self.ear_threshold = value

    # --- Thread-Hauptschleife ----------------------------------------------
    def run(self):
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0)
        if not cap.isOpened():
            # CAP_DSHOW kann auf manchen Systemen scheitern -> Standard-Backend
            cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.sig_error.emit(
                f"Kamera {self.camera_index} konnte nicht geöffnet werden. "
                "Prüfe die Kameraauswahl in den Einstellungen."
            )
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        blink_times = deque()        # Zeitstempel der Blinzler (letzte 60 s)
        face_samples = deque()       # (Zeitstempel, Gesicht sichtbar?)
        closed_since = None          # Beginn der aktuellen Augen-geschlossen-Phase
        last_tick = 0.0
        frame_interval = 1.0 / TARGET_FPS

        try:
            while self._running:
                loop_start = time.monotonic()

                if self._paused:
                    blink_times.clear()
                    face_samples.clear()
                    closed_since = None
                    time.sleep(0.2)
                    continue

                ok, frame = cap.read()
                now = time.monotonic()
                if not ok:
                    self.sig_error.emit(
                        "Kamerabild konnte nicht gelesen werden. Wird die Kamera "
                        "gerade von einer anderen Anwendung verwendet?"
                    )
                    return

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = face_mesh.process(rgb)

                face_present = bool(result.multi_face_landmarks)
                face_samples.append((now, face_present))

                if face_present:
                    landmarks = result.multi_face_landmarks[0].landmark
                    ear = (
                        eye_aspect_ratio(landmarks, LEFT_EYE)
                        + eye_aspect_ratio(landmarks, RIGHT_EYE)
                    ) / 2.0

                    if ear < self.ear_threshold:
                        if closed_since is None:
                            closed_since = now
                    else:
                        if closed_since is not None:
                            if (now - closed_since) <= MAX_CLOSED_S:
                                blink_times.append(now)
                                self.sig_blink.emit(time.time())
                            closed_since = None
                else:
                    closed_since = None

                # Rollierendes 60-Sekunden-Fenster pflegen
                cutoff = now - RATE_WINDOW_S
                while blink_times and blink_times[0] < cutoff:
                    blink_times.popleft()
                while face_samples and face_samples[0][0] < cutoff:
                    face_samples.popleft()

                # Einmal pro Sekunde Status an den Hauptthread melden
                if now - last_tick >= 1.0:
                    last_tick = now
                    if face_samples:
                        face_ratio = sum(1 for _, p in face_samples if p) / len(face_samples)
                    else:
                        face_ratio = 0.0
                    window = min(RATE_WINDOW_S, max(1.0, now - face_samples[0][0]) if face_samples else 1.0)
                    rate = len(blink_times) * (60.0 / window)
                    self.sig_tick.emit(rate, face_present, face_ratio)

                # CPU schonen: auf Ziel-Framerate drosseln
                elapsed = time.monotonic() - loop_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
        finally:
            face_mesh.close()
            cap.release()
