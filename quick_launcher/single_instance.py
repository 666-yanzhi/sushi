from __future__ import annotations

import ctypes
import sys


class SingleInstance:
    """Prevent duplicate trays and competing global-hotkey registrations on Windows."""

    NAME = "Local\\QuickLauncherV1"
    ERROR_ALREADY_EXISTS = 183

    def __init__(self) -> None:
        self._handle: int | None = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        ctypes.windll.kernel32.SetLastError(0)
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.NAME)
        if not handle:
            return False
        self._handle = handle
        if ctypes.windll.kernel32.GetLastError() == self.ERROR_ALREADY_EXISTS:
            self.release()
            return False
        return True

    def release(self) -> None:
        if self._handle is not None and sys.platform == "win32":
            ctypes.windll.kernel32.CloseHandle(self._handle)
            self._handle = None
