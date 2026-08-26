from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter

IS_WINDOWS = sys.platform == "win32"
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


if IS_WINDOWS:
    from ctypes import wintypes

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
            ("lPrivate", wintypes.DWORD),
        ]


class NativeHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type: bytes, message: object) -> tuple[bool, int]:
        if IS_WINDOWS and event_type == b"windows_generic_MSG":
            msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents
            if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
                self._callback()
                return True, 0
        return False, 0


class WindowsHotkey:
    """Win + Alt + Space backed by RegisterHotKey, with deterministic cleanup."""

    HOTKEY_ID = 0x514C

    def __init__(self, callback: Callable[[], None]) -> None:
        self._filter = NativeHotkeyFilter(self.HOTKEY_ID, callback)
        self._registered = False

    def register(self) -> tuple[bool, str | None]:
        if not IS_WINDOWS:
            return False, "全局快捷键仅在 Windows 上可用。"
        user32 = ctypes.windll.user32
        ctypes.windll.kernel32.SetLastError(0)
        success = user32.RegisterHotKey(
            None, self.HOTKEY_ID, MOD_WIN | MOD_ALT | MOD_NOREPEAT, VK_SPACE
        )
        if not success:
            error = ctypes.windll.kernel32.GetLastError()
            if error == ERROR_HOTKEY_ALREADY_REGISTERED:
                return False, "Win + Alt + Space 已被其他程序占用。"
            return False, f"无法注册 Win + Alt + Space（Windows 错误 {error}）。"
        self._registered = True
        return True, None

    @property
    def native_filter(self) -> NativeHotkeyFilter:
        return self._filter

    def unregister(self) -> None:
        if self._registered and IS_WINDOWS:
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False
