from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QFileInfo, QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFileIconProvider, QStyle

from .models import AppEntry


class IconService:
    """Lazily extracts and persists native file icons on the GUI thread."""

    def __init__(self, cache_dir: Path, fallback_style: QStyle) -> None:
        self._cache_dir = cache_dir
        self._provider = QFileIconProvider()
        self._fallback = fallback_style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def icon_for(self, app: AppEntry) -> QIcon:
        cache_file = self.cache_file_for(app.target)
        if cache_file.exists():
            return QIcon(str(cache_file))

        source = Path(app.target)
        if not source.exists():
            return self._fallback
        icon = self._provider.icon(QFileInfo(str(source)))
        if icon.isNull():
            return self._fallback
        pixmap = icon.pixmap(QSize(64, 64))
        if not pixmap.isNull():
            pixmap.save(str(cache_file), "PNG")
        return icon

    def cache_file_for(self, target: str) -> Path:
        return self._cache_dir / f"{self._cache_key(target)}.png"

    def save_icon_data(self, target: str, data: bytes) -> bool:
        pixmap = QPixmap()
        if not data or not pixmap.loadFromData(data):
            return False
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        scaled = pixmap.scaled(
            QSize(64, 64),
            aspectMode=Qt.AspectRatioMode.KeepAspectRatio,
            mode=Qt.TransformationMode.SmoothTransformation,
        )
        return scaled.save(str(self.cache_file_for(target)), "PNG")

    @staticmethod
    def _cache_key(target: str) -> str:
        path = Path(target)
        try:
            stat = path.stat()
            fingerprint = f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
        except OSError:
            fingerprint = target
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
