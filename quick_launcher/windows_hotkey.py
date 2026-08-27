from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, Qt
from PySide6.QtGui import QKeySequence

IS_WINDOWS = sys.platform == "win32"
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
DEFAULT_HOTKEY = "Meta+Alt+Space"

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


class HotkeyError(ValueError):
    pass


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


def display_hotkey(shortcut: str) -> str:
    """Use the familiar Windows name instead of Qt's portable Meta label."""
    return shortcut.replace("Meta", "Win")


def shortcut_to_native(shortcut: str) -> tuple[int, int]:
    """Convert one portable Qt key sequence into RegisterHotKey arguments."""
    sequence = QKeySequence.fromString(shortcut, QKeySequence.SequenceFormat.PortableText)
    if sequence.isEmpty() or sequence.count() != 1:
        raise HotkeyError("快捷键必须是一组组合键，例如 Win + Alt + Space。")

    combination = sequence[0]
    key = _enum_value(combination.key())
    modifiers = _enum_value(combination.keyboardModifiers())
    modifier_map = (
        (Qt.KeyboardModifier.AltModifier, MOD_ALT),
        (Qt.KeyboardModifier.ControlModifier, MOD_CONTROL),
        (Qt.KeyboardModifier.ShiftModifier, MOD_SHIFT),
        (Qt.KeyboardModifier.MetaModifier, MOD_WIN),
    )
    allowed_modifiers = 0
    native_modifiers = 0
    for qt_modifier, native_modifier in modifier_map:
        qt_value = _enum_value(qt_modifier)
        allowed_modifiers |= qt_value
        if modifiers & qt_value:
            native_modifiers |= native_modifier
    if modifiers & ~allowed_modifiers or native_modifiers == 0:
        raise HotkeyError("快捷键必须包含 Alt、Ctrl、Shift 或 Win，且不支持额外修饰键。")
    if not _is_supported_virtual_key(key):
        raise HotkeyError("仅支持 Space、A-Z、0-9 和 F1-F24 作为快捷键主键。")
    return native_modifiers | MOD_NOREPEAT, _to_windows_virtual_key(key)


def _enum_value(value: object) -> int:
    raw_value = getattr(value, "value", value)
    return int(raw_value)


def _is_supported_virtual_key(key: int) -> bool:
    return (
        key == _enum_value(Qt.Key.Key_Space)
        or _enum_value(Qt.Key.Key_0) <= key <= _enum_value(Qt.Key.Key_9)
        or _enum_value(Qt.Key.Key_A) <= key <= _enum_value(Qt.Key.Key_Z)
        or _enum_value(Qt.Key.Key_F1) <= key <= _enum_value(Qt.Key.Key_F24)
    )


def _to_windows_virtual_key(key: int) -> int:
    first_function_key = _enum_value(Qt.Key.Key_F1)
    if first_function_key <= key <= _enum_value(Qt.Key.Key_F24):
        return 0x70 + (key - first_function_key)
    return key


class WindowsHotkey:
    """Configurable RegisterHotKey binding with rollback on an invalid replacement."""

    HOTKEY_ID = 0x514C

    def __init__(self, callback: Callable[[], None], shortcut: str = DEFAULT_HOTKEY) -> None:
        self._filter = NativeHotkeyFilter(self.HOTKEY_ID, callback)
        self._shortcut = shortcut
        self._registered = False

    @property
    def native_filter(self) -> NativeHotkeyFilter:
        return self._filter

    @property
    def shortcut(self) -> str:
        return self._shortcut

    @property
    def display_name(self) -> str:
        return display_hotkey(self._shortcut)

    def register(self) -> tuple[bool, str | None]:
        if not IS_WINDOWS:
            return False, "全局快捷键仅在 Windows 上可用。"
        try:
            modifiers, virtual_key = shortcut_to_native(self._shortcut)
        except HotkeyError as exc:
            return False, str(exc)

        user32 = ctypes.windll.user32
        ctypes.windll.kernel32.SetLastError(0)
        success = user32.RegisterHotKey(None, self.HOTKEY_ID, modifiers, virtual_key)
        if not success:
            error = ctypes.windll.kernel32.GetLastError()
            if error == ERROR_HOTKEY_ALREADY_REGISTERED:
                return False, f"{self.display_name} 已被其他程序占用。"
            return False, f"无法注册 {self.display_name}（Windows 错误 {error}）。"
        self._registered = True
        return True, None

    def rebind(self, shortcut: str) -> tuple[bool, str | None]:
        shortcut = shortcut.strip()
        if shortcut == self._shortcut:
            return (True, None) if self._registered else self.register()
        previous_shortcut = self._shortcut
        was_registered = self._registered
        if was_registered:
            self.unregister()
        self._shortcut = shortcut
        registered, error = self.register()
        if registered:
            return True, None

        self._shortcut = previous_shortcut
        if was_registered:
            restored, restore_error = self.register()
            if not restored:
                return False, f"{error}；恢复原快捷键失败：{restore_error}"
        return False, error

    def unregister(self) -> None:
        if self._registered and IS_WINDOWS:
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False
