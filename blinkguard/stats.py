"""Statistik-Speicher: Blinzler pro Minute in einer lokalen SQLite-Datenbank.

Es werden nur aggregierte Minutenwerte gespeichert (Zeitstempel, Anzahl
Blinzler, Sekunden mit sichtbarem Gesicht) – keine Bilder, keine Videos.
"""

import sqlite3
import time
from datetime import datetime, timedelta

from blinkguard.config import data_dir


class StatsStore:
    def __init__(self):
        self.path = data_dir() / "stats.db"
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS minutes (
                minute_ts INTEGER PRIMARY KEY,  -- Unix-Zeit, auf Minute gerundet
                blinks    INTEGER NOT NULL,
                face_s    REAL    NOT NULL      -- Sekunden mit erkanntem Gesicht
            )
            """
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def add_minute(self, minute_ts: int, blinks: int, face_s: float):
        if blinks == 0 and face_s < 5.0:
            return  # Nutzer war nicht am Platz -> Minute nicht werten
        self.conn.execute(
            """
            INSERT INTO minutes (minute_ts, blinks, face_s) VALUES (?, ?, ?)
            ON CONFLICT(minute_ts) DO UPDATE SET
                blinks = blinks + excluded.blinks,
                face_s = face_s + excluded.face_s
            """,
            (minute_ts, blinks, face_s),
        )
        self.conn.commit()

    @staticmethod
    def _day_bounds(day: datetime | None = None) -> tuple[int, int]:
        day = day or datetime.now()
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(start.timestamp()), int((start + timedelta(days=1)).timestamp())

    def today_minutes(self) -> list[tuple[int, int, float]]:
        """Alle Minutenwerte des heutigen Tages: (minute_ts, blinks, face_s)."""
        start, end = self._day_bounds()
        rows = self.conn.execute(
            "SELECT minute_ts, blinks, face_s FROM minutes"
            " WHERE minute_ts >= ? AND minute_ts < ? ORDER BY minute_ts",
            (start, end),
        ).fetchall()
        return rows

    def today_summary(self) -> tuple[int, float, float]:
        """(Blinzler heute, aktive Minuten heute, Ø Blinzler/min heute)."""
        rows = self.today_minutes()
        total_blinks = sum(r[1] for r in rows)
        active_minutes = sum(r[2] for r in rows) / 60.0
        avg_rate = total_blinks / active_minutes if active_minutes > 0 else 0.0
        return total_blinks, active_minutes, avg_rate


class MinuteAccumulator:
    """Sammelt Blinzler und Gesichts-Sekunden und flusht sie minutenweise."""

    def __init__(self, store: StatsStore):
        self.store = store
        self._minute = self._current_minute()
        self._blinks = 0
        self._face_s = 0.0

    @staticmethod
    def _current_minute() -> int:
        return int(time.time() // 60) * 60

    def add_blink(self):
        self._roll_over()
        self._blinks += 1

    def add_face_second(self, present: bool):
        self._roll_over()
        if present:
            self._face_s += 1.0

    def flush(self):
        if self._blinks or self._face_s:
            self.store.add_minute(self._minute, self._blinks, self._face_s)
        self._blinks = 0
        self._face_s = 0.0

    def _roll_over(self):
        now_minute = self._current_minute()
        if now_minute != self._minute:
            self.flush()
            self._minute = now_minute
