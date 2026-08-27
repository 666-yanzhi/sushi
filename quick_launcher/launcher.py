from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from .models import AppEntry


class LaunchError(RuntimeError):
    pass


class TargetLauncher:
    """Starts only the V1 targets: executables and Windows shortcut files."""

    def open(self, app: AppEntry) -> None:
        target = os.path.expandvars(app.target)
        try:
            if target.casefold().startswith(("http://", "https://")):
                if not QDesktopServices.openUrl(QUrl(target)):
                    raise LaunchError("系统没有可用的网页浏览器。")
            elif target.casefold().endswith(".lnk"):
                self._open_shortcut(target)
            else:
                subprocess.Popen([target, *app.args], cwd=app.cwd or None)
        except (OSError, ValueError) as exc:
            if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 740:
                self._open_elevated(target, app.args, app.cwd)
                return
            raise LaunchError(f"无法启动“{app.name}”：{exc}") from exc

    @staticmethod
    def _open_shortcut(target: str) -> None:
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise LaunchError(".lnk 快捷方式只能在 Windows 上启动。")
        if not Path(target).exists():
            raise LaunchError(f"快捷方式不存在：{target}")
        startfile(target)  # type: ignore[misc]

    @staticmethod
    def _open_elevated(target: str, args: tuple[str, ...], cwd: str | None) -> None:
        if sys.platform != "win32":
            raise LaunchError("该应用需要管理员权限，但当前系统不支持 Windows UAC。")
        try:
            result, last_error = _shell_execute_runas(target, args, cwd)
        except OSError as exc:
            raise LaunchError(f"无法请求管理员权限：{exc}") from exc
        if result > 32:
            return
        if last_error == 1223:
            raise LaunchError("已取消管理员授权，应用未启动。")
        raise LaunchError(f"无法以管理员权限启动应用（系统错误 {last_error or result}）。")


def _shell_execute_runas(target: str, args: tuple[str, ...], cwd: str | None) -> tuple[int, int]:
    """Ask Windows Shell to start an executable with UAC only after error 740."""
    import ctypes

    parameters = subprocess.list2cmdline(list(args)) if args else None
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell_execute = shell32.ShellExecuteW
    shell_execute.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    result = int(shell_execute(None, "runas", target, parameters, cwd or None, 1) or 0)
    return result, ctypes.get_last_error()
