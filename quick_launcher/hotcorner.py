from __future__ import annotations

import time

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication


class HotCorner(QObject):
    """Event-loop friendly top-right hot-corner detector for every display."""

    activated = Signal()

    def __init__(
        self,
        interval_ms: int = 100,
        dwell_ms: int = 250,
        zone_px: int = 8,
        position: str = "top_right",
    ) -> None:
        super().__init__()
        self._dwell_seconds = dwell_ms / 1000
        self._zone_px = zone_px
        self._position = position
        self._entered_at: float | None = None
        self._cooldown_until = 0.0
        self._armed = True
        self._enabled = True
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        if self._enabled:
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def set_enabled(self, enabled: bool) -> None:
        """Apply a settings change immediately without recreating the timer."""
        self._enabled = enabled
        self._entered_at = None
        self._armed = True
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()

    def configure(self, position: str, zone_px: int, dwell_ms: int) -> None:
        """Update the watched corner without rebuilding the QObject or timer."""
        if position not in {"top_left", "top_right", "bottom_left", "bottom_right"}:
            raise ValueError("unsupported hot-corner position")
        if not 4 <= zone_px <= 48 or not 100 <= dwell_ms <= 1000:
            raise ValueError("hot-corner values are out of range")
        self._position = position
        self._zone_px = zone_px
        self._dwell_seconds = dwell_ms / 1000
        self._entered_at = None
        self._armed = True

    def launcher_hidden(self) -> None:
        self._cooldown_until = time.monotonic() + 1.0
        self._entered_at = None
        self._armed = False

    def _check(self) -> None:
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor)
        if screen is None:
            return
        in_corner = self._contains(cursor, screen.geometry())
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

    def _contains(self, cursor: QPoint, geometry: QRect) -> bool:
        """Return whether a cursor lies in this detector's configured corner."""
        near_left = cursor.x() <= geometry.left() + self._zone_px - 1
        near_right = cursor.x() >= geometry.right() - self._zone_px + 1
        near_top = cursor.y() <= geometry.top() + self._zone_px - 1
        near_bottom = cursor.y() >= geometry.bottom() - self._zone_px + 1
        return {
            "top_left": near_left and near_top,
            "top_right": near_right and near_top,
            "bottom_left": near_left and near_bottom,
            "bottom_right": near_right and near_bottom,
        }[self._position]
