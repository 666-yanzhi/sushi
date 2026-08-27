from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget


class HotCornerPreview:
    """Non-interactive overlays that show every active screen's hot-corner zone."""

    def __init__(
        self,
        screens_provider: Callable[[], list] = QGuiApplication.screens,
    ) -> None:
        self._screens_provider = screens_provider
        self._overlays: list[QWidget] = []

    def show(self, position: str, zone_px: int) -> None:
        self.clear()
        for screen in self._screens_provider():
            overlay = QWidget()
            overlay.setObjectName("hotCornerPreview")
            overlay.setWindowFlags(
                Qt.WindowType.ToolTip
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
                | Qt.WindowType.WindowStaysOnTopHint
            )
            overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            overlay.setGeometry(self.corner_rect(screen.geometry(), position, zone_px))
            overlay.setStyleSheet(
                "QWidget#hotCornerPreview {"
                "background-color: rgba(255, 255, 255, 145);"
                "border: 1px solid rgba(255, 255, 255, 235);"
                "}"
            )
            overlay.show()
            overlay.raise_()
            self._overlays.append(overlay)

    def clear(self) -> None:
        for overlay in self._overlays:
            overlay.close()
            overlay.deleteLater()
        self._overlays.clear()

    @staticmethod
    def corner_rect(geometry: QRect, position: str, zone_px: int) -> QRect:
        if position not in {"top_left", "top_right", "bottom_left", "bottom_right"}:
            raise ValueError("unsupported hot-corner position")
        if not 4 <= zone_px <= 48:
            raise ValueError("hot-corner preview size is out of range")
        x = geometry.left() if position.endswith("left") else geometry.right() - zone_px + 1
        y = geometry.top() if position.startswith("top") else geometry.bottom() - zone_px + 1
        return QRect(x, y, zone_px, zone_px)
