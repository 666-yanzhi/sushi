from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import AppEntry


class LaunchError(RuntimeError):
    pass


class TargetLauncher:
    """Starts only the V1 targets: executables and Windows shortcut files."""

    def open(self, app: AppEntry) -> None:
        target = os.path.expandvars(app.target)
        try:
            if target.casefold().endswith(".lnk"):
                self._open_shortcut(target)
            else:
                subprocess.Popen([target, *app.args], cwd=app.cwd or None)
        except (OSError, ValueError) as exc:
            raise LaunchError(f"无法启动“{app.name}”：{exc}") from exc

    @staticmethod
    def _open_shortcut(target: str) -> None:
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise LaunchError(".lnk 快捷方式只能在 Windows 上启动。")
        if not Path(target).exists():
            raise LaunchError(f"快捷方式不存在：{target}")
        startfile(target)  # type: ignore[misc]
