from __future__ import annotations

from pathlib import Path

from collections.abc import Callable

from PySide6.QtCore import QByteArray, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect, QWidget


LIGHT = {
    "canvas": "#F4F8EE",
    "surface": "#F4F8EE",
    "sidebar": "#E8F2DD",
    "card": "#FFFFFF",
    "input": "#FFFFFF",
    "hover": "#D7EAC5",
    "accent": "#789A63",
    "accent_dark": "#557146",
    "accent_soft": "#B9D99C",
    "text": "#2F3D2A",
    "muted": "#6D7A65",
    "border": "#C9D9BB",
    "error_bg": "#FBEAEA",
    "error": "#A13F3F",
    "success_bg": "#DDEFD0",
    "success": "#466339",
}

DARK = {
    "canvas": "#1E1E1E",
    "surface": "#252526",
    "sidebar": "#252526",
    "card": "#2D2D30",
    "input": "#2D2D30",
    "hover": "#37373D",
    "accent": "#789A63",
    "accent_dark": "#9ABD82",
    "accent_soft": "#34442E",
    "text": "#D4D4D4",
    "muted": "#9D9D9D",
    "border": "#3F3F46",
    "error_bg": "#3A2727",
    "error": "#F5B5B5",
    "success_bg": "#293829",
    "success": "#B3D69C",
}


def colors(theme: str) -> dict[str, str]:
    return DARK if theme == "dark" else LIGHT


def apply_palette(app: QApplication, theme: str) -> None:
    c = colors(theme)
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Window, QColor(c["surface"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(c["input"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c["sidebar"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(c["sidebar"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)


def themed_icon(name: str, theme: str, size: int = 20) -> QIcon:
    path = Path(__file__).parent / "resources" / "icons" / f"{name}.svg"
    try:
        svg = path.read_text(encoding="utf-8")
    except OSError:
        return QIcon()
    svg = svg.replace("currentColor", colors(theme)["accent_dark"])
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return QIcon(pixmap)


def bundled_icon(name: str, fallback: QIcon | None = None) -> QIcon:
    """Load a packaged ICO asset while keeping a caller-provided fallback."""
    icon = QIcon(str(Path(__file__).parent / "resources" / "icons" / name))
    return icon if not icon.isNull() else fallback or QIcon()


class _ThemeSnapshotOverlay(QWidget):
    """Paint a captured window inside the same rounded shape as the launcher."""

    def __init__(self, snapshot: QPixmap, parent: QWidget, corner_radius: float) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._corner_radius = corner_radius
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._corner_radius, self._corner_radius)
        painter.setClipPath(path)
        painter.drawPixmap(self.rect(), self._snapshot)


class ThemeTransition:
    """Cross-fade a widget's previous rendering over a freshly applied theme."""

    def __init__(self, widget: QWidget, duration_ms: int = 180) -> None:
        self._widget = widget
        self._duration_ms = duration_ms
        self._overlay: _ThemeSnapshotOverlay | None = None
        self._animation = None

    def apply(self, change: Callable[[], None]) -> None:
        self._clear()
        if not self._widget.isVisible():
            change()
            return
        snapshot = self._widget.grab()
        change()
        if snapshot.isNull():
            return
        corner_radius = 20.0 if self._widget.objectName() == "launcherWindow" else 0.0
        overlay = _ThemeSnapshotOverlay(snapshot, self._widget, corner_radius)
        overlay.setGeometry(self._widget.rect())
        effect = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(effect)
        overlay.show()
        overlay.raise_()

        animation = QPropertyAnimation(effect, b"opacity", overlay)
        animation.setDuration(self._duration_ms)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: self._finish(animation))
        self._overlay = overlay
        self._animation = animation
        animation.start()

    def _finish(self, animation: QPropertyAnimation) -> None:
        if self._animation is animation:
            self._clear()

    def _clear(self) -> None:
        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None
        if self._overlay is not None:
            self._overlay.deleteLater()
            self._overlay = None
