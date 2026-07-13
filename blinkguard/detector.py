"""Blinzelerkennung per Webcam.

Läuft in einem eigenen QThread: liest Kamerabilder und ermittelt mit dem
MediaPipe-FaceLandmarker (Tasks-API) die "eyeBlink"-Blendshapes – einen von
0 (Auge offen) bis 1 (Auge geschlossen) laufenden Score. Ein Blinzler =
Score steigt kurz über den Schwellwert und fällt wieder darunter.

Das Landmarker-Modell (~4 MB) wird beim ersten Start automatisch nach
%APPDATA%/BlinkGuard/models heruntergeladen.
"""

import math
import time
import urllib.request
from collections import deque

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision as mp_vision
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from blinkguard.config import data_dir

_MODEL_BASE = "https://storage.googleapis.com/mediapipe-models"
MODELS = {
    "face_landmarker.task": (
        f"{_MODEL_BASE}/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    ),
    # "full" statt "lite": deutlich präzisere Schulter-/Ohr-Punkte, ~37 ms/Frame
    "pose_landmarker_full.task": (
        f"{_MODEL_BASE}/pose_landmarker/pose_landmarker_full/float16/1/"
        "pose_landmarker_full.task"
    ),
}

TARGET_FPS = 20
POSE_EVERY_N = 4     # Haltung ändert sich langsam -> nur jeden 4. Frame (5/s)
RATE_WINDOW_S = 60.0
# Ein Blinzeln dauert 100-400 ms; alles was länger geschlossen ist (z.B.
# Wegschauen nach unten) zählt nicht als Blinzler.
MAX_CLOSED_S = 0.5
# Hysterese: "wieder offen" erst deutlich unter dem Zu-Schwellwert
HYSTERESIS = 0.1

# Gesichts-Landmarken für die Haltungs-Metriken
FACE_RIGHT_EYE_OUTER = 33
FACE_LEFT_EYE_OUTER = 263
FACE_NOSE_TIP = 1
# Augenringe (nur für die Vorschau-Zeichnung)
EYE_RING_RIGHT = [33, 160, 158, 133, 153, 144]
EYE_RING_LEFT = [362, 385, 387, 263, 373, 380]
# Pose-Landmarken
POSE_LEFT_EAR = 7
POSE_RIGHT_EAR = 8
POSE_LEFT_SHOULDER = 11
POSE_RIGHT_SHOULDER = 12

PREVIEW_WIDTH = 420


def ensure_model(filename: str) -> str:
    """Lädt ein MediaPipe-Modell herunter, falls es noch fehlt."""
    path = data_dir() / "models" / filename
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".download")
        urllib.request.urlretrieve(MODELS[filename], tmp)
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
    sig_posture = Signal(dict)         # Haltungs-Metriken, 1x pro Sekunde
    sig_preview = Signal(QImage)       # Kamerabild mit Erkennungs-Overlay (~10/s)
    sig_error = Signal(str)            # Kamera-/Erkennungsfehler (einmalig)

    def __init__(self, camera_index: int, blink_threshold: float, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.blink_threshold = blink_threshold
        self._running = True
        self._paused = False
        self._preview = False

    # --- Steuerung aus dem Hauptthread -------------------------------------
    def stop(self):
        self._running = False

    def set_paused(self, paused: bool):
        self._paused = paused

    def set_blink_threshold(self, value: float):
        self.blink_threshold = value

    def set_preview(self, enabled: bool):
        self._preview = enabled

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
            face_model = ensure_model("face_landmarker.task")
            pose_model = ensure_model("pose_landmarker_full.task")
        except OSError as exc:
            self.sig_error.emit(
                "Die Erkennungsmodelle konnten nicht heruntergeladen werden "
                f"(einmalig ~10 MB, Internet nötig): {exc}"
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
            base_options=mp_tasks.BaseOptions(model_asset_path=face_model),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        landmarker = mp_vision.FaceLandmarker.create_from_options(options)

        pose_options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=pose_model),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
        )
        pose_landmarker = mp_vision.PoseLandmarker.create_from_options(pose_options)

        blink_times = deque()        # Zeitstempel der Blinzler (letzte 60 s)
        face_samples = deque()       # (Zeitstempel, Gesicht sichtbar?)
        closed_since = None          # Beginn der aktuellen Augen-zu-Phase
        eyes_closed = False
        blink_marker = None          # letzter Blinzler bzw. Gesichts-Wiederkehr
        last_tick = 0.0
        start = time.monotonic()
        last_ts_ms = -1
        frame_interval = 1.0 / TARGET_FPS
        frame_no = 0
        face_metrics = None          # (eye_dist, face_y, head_roll)
        pose_metrics = None          # dict mit Schulter-/Nacken-Metriken
        pose_draw = None             # Punktkoordinaten für die Vorschau
        pose_seen_at = 0.0

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
                    face_metrics = None
                    pose_metrics = None
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
                    lm = result.face_landmarks[0]
                    r_eye, l_eye = lm[FACE_RIGHT_EYE_OUTER], lm[FACE_LEFT_EYE_OUTER]
                    face_metrics = (
                        math.hypot(l_eye.x - r_eye.x, l_eye.y - r_eye.y),
                        lm[FACE_NOSE_TIP].y,
                        math.degrees(math.atan2(l_eye.y - r_eye.y, l_eye.x - r_eye.x)),
                        lm[FACE_NOSE_TIP].x,
                    )
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
                    face_metrics = None

                # Haltung: Schultern nur jeden POSE_EVERY_N-ten Frame
                frame_no += 1
                if frame_no % POSE_EVERY_N == 0:
                    pose_result = pose_landmarker.detect_for_video(image, ts_ms)
                    pose_metrics = None
                    pose_draw = None
                    if pose_result.pose_landmarks:
                        plm = pose_result.pose_landmarks[0]
                        ls, rs = plm[POSE_LEFT_SHOULDER], plm[POSE_RIGHT_SHOULDER]
                        le, re = plm[POSE_LEFT_EAR], plm[POSE_RIGHT_EAR]
                        if ls.visibility > 0.5 and rs.visibility > 0.5:
                            width = abs(ls.x - rs.x) or 1e-6
                            # Nackenlänge je Seite: Abstand Ohr->Schulter,
                            # normiert auf die Schulterbreite. Getrennt gemessen,
                            # damit auch einseitiges Hochziehen auffällt.
                            left_ok = le.visibility > 0.5
                            right_ok = re.visibility > 0.5
                            neck_left = (ls.y - le.y) / width if left_ok else None
                            neck_right = (rs.y - re.y) / width if right_ok else None
                            necks = [n for n in (neck_left, neck_right) if n is not None]
                            pose_metrics = {
                                "shoulder_tilt": math.degrees(
                                    math.atan2(ls.y - rs.y, width)
                                ),
                                "shoulder_y": (ls.y + rs.y) / 2.0,
                                "shoulder_width": width,
                                "neck_left": neck_left,
                                "neck_right": neck_right,
                                "neck_len": sum(necks) / len(necks) if necks else None,
                            }
                            pose_seen_at = now
                            pose_draw = {
                                "ls": (ls.x, ls.y),
                                "rs": (rs.x, rs.y),
                                "le": (le.x, le.y) if left_ok else None,
                                "re": (re.x, re.y) if right_ok else None,
                            }

                # Vorschau mit Overlay (nur wenn im Fenster sichtbar)
                if self._preview and frame_no % 2 == 0:
                    self._emit_preview(
                        frame,
                        result.face_landmarks[0] if face_present else None,
                        pose_draw,
                    )

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

                    pose_fresh = pose_metrics is not None and (now - pose_seen_at) < 2.0
                    self.sig_posture.emit(
                        {
                            "valid": face_metrics is not None and pose_fresh,
                            "eye_dist": face_metrics[0] if face_metrics else 0.0,
                            "face_y": face_metrics[1] if face_metrics else 0.0,
                            "head_roll": face_metrics[2] if face_metrics else 0.0,
                            "face_x": face_metrics[3] if face_metrics else 0.0,
                            "shoulder_tilt": pose_metrics["shoulder_tilt"] if pose_fresh else 0.0,
                            "shoulder_y": pose_metrics["shoulder_y"] if pose_fresh else 0.0,
                            "shoulder_width": pose_metrics["shoulder_width"] if pose_fresh else 0.0,
                            "neck_left": pose_metrics["neck_left"] if pose_fresh else None,
                            "neck_right": pose_metrics["neck_right"] if pose_fresh else None,
                            "neck_len": pose_metrics["neck_len"] if pose_fresh else None,
                        }
                    )

                # CPU schonen: auf Ziel-Framerate drosseln
                elapsed = time.monotonic() - loop_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
        finally:
            landmarker.close()
            pose_landmarker.close()
            if cap is not None:
                cap.release()

    def _emit_preview(self, frame, face_landmarks, pose_draw):
        """Erkennungspunkte ins Kamerabild zeichnen und als QImage senden."""
        h, w = frame.shape[:2]

        def px(x, y):
            return (int(x * w), int(y * h))

        if face_landmarks is not None:
            for ring in (EYE_RING_RIGHT, EYE_RING_LEFT):
                pts = [px(face_landmarks[i].x, face_landmarks[i].y) for i in ring]
                for a, b in zip(pts, pts[1:] + pts[:1]):
                    cv2.line(frame, a, b, (80, 230, 80), 2)
            nose = face_landmarks[FACE_NOSE_TIP]
            cv2.circle(frame, px(nose.x, nose.y), 4, (80, 230, 80), -1)

        if pose_draw is not None:
            ls, rs = px(*pose_draw["ls"]), px(*pose_draw["rs"])
            cv2.line(frame, ls, rs, (255, 200, 60), 3)  # Schulterlinie
            cv2.circle(frame, ls, 6, (255, 200, 60), -1)
            cv2.circle(frame, rs, 6, (255, 200, 60), -1)
            for ear, shoulder in ((pose_draw["le"], ls), (pose_draw["re"], rs)):
                if ear is not None:
                    e = px(*ear)
                    cv2.circle(frame, e, 5, (60, 200, 255), -1)
                    cv2.line(frame, e, shoulder, (60, 200, 255), 2)  # Nackenlinie

        preview_h = int(PREVIEW_WIDTH * h / w)
        small = cv2.resize(frame, (PREVIEW_WIDTH, preview_h))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        image = QImage(
            rgb.data, PREVIEW_WIDTH, preview_h, 3 * PREVIEW_WIDTH, QImage.Format_RGB888
        ).copy()
        self.sig_preview.emit(image)
