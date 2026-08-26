from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QFileInfo, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFileIconProvider, QStyle

from .models import AppEntry


class IconService:
    """Lazily extracts and persists native file icons on the GUI thread."""

    def __init__(self, cache_dir: Path, fallback_style: QStyle) -> None:
        self._cache_dir = cache_dir
        self._provider = QFileIconProvider()
        self._fallback = fallback_style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    def icon_for(self, app: AppEntry) -> QIcon:
        cache_file = self._cache_dir / f"{self._cache_key(app.target)}.png"
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

    @staticmethod
    def _cache_key(target: str) -> str:
        path = Path(target)
        try:
            stat = path.stat()
            fingerprint = f"{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}"
        except OSError:
            fingerprint = target
        return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
