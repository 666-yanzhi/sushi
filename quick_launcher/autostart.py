from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType


class AutostartError(RuntimeError):
    """Raised when the current user's Windows startup entry cannot be changed."""


class WindowsAutostart:
    """Manage the per-user Run entry without needing administrator privileges."""

    KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    VALUE_NAME = "QuickLauncher"

    def __init__(self, registry: ModuleType | None = None) -> None:
        self._registry = registry

    def set_enabled(self, enabled: bool) -> None:
        registry = self._registry or _load_winreg()
        try:
            with registry.OpenKey(
                registry.HKEY_CURRENT_USER,
                self.KEY_PATH,
                0,
                registry.KEY_SET_VALUE,
            ) as key:
                if enabled:
                    registry.SetValueEx(
                        key,
                        self.VALUE_NAME,
                        0,
                        registry.REG_SZ,
                        startup_command(),
                    )
                else:
                    try:
                        registry.DeleteValue(key, self.VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            action = "启用" if enabled else "关闭"
            raise AutostartError(f"无法{action}开机自启动：{exc}") from exc


def startup_command() -> str:
    """Return a safely quoted command for either frozen or source execution."""
    executable = str(Path(sys.executable).resolve())
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([executable])
    main_script = str(Path(__file__).resolve().parent.parent / "main.py")
    return subprocess.list2cmdline([executable, main_script])


def _load_winreg() -> ModuleType:
    if sys.platform != "win32":
        raise AutostartError("开机自启动仅支持 Windows。")
    import winreg

    return winreg
