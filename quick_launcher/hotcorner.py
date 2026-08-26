from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication


class HotCorner(QObject):
    """Event-loop friendly top-right hot-corner detector for every display."""

    activated = Signal()

    def __init__(self, interval_ms: int = 100, dwell_ms: int = 250, zone_px: int = 8) -> None:
        super().__init__()
        self._dwell_seconds = dwell_ms / 1000
        self._zone_px = zone_px
        self._entered_at: float | None = None
        self._cooldown_until = 0.0
        self._armed = True
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def launcher_hidden(self) -> None:
        self._cooldown_until = time.monotonic() + 1.0
        self._entered_at = None
        self._armed = False

    def _check(self) -> None:
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor)
        if screen is None:
            return
        geometry = screen.geometry()
        in_corner = (
            cursor.x() >= geometry.right() - self._zone_px + 1
            and cursor.y() <= geometry.top() + self._zone_px - 1
        )
        if not in_corner:
            self._armed = True
            self._entered_at = None
            return
        if not self._armed or time.monotonic() < self._cooldown_until:
            return
        now = time.monotonic()
        if self._entered_at is None:
            self._entered_at = now
        elif now - self._entered_at >= self._dwell_seconds:
            self._armed = False
            self.activated.emit()
