import unittest

from quick_launcher.windows_hotkey import (
    DEFAULT_HOTKEY,
    HotkeyError,
    MOD_ALT,
    MOD_NOREPEAT,
    MOD_WIN,
    display_hotkey,
    shortcut_to_native,
)


class HotkeyTests(unittest.TestCase):
    def test_default_shortcut_maps_to_windows_hotkey(self) -> None:
        modifiers, key = shortcut_to_native(DEFAULT_HOTKEY)
        self.assertEqual(modifiers, MOD_WIN | MOD_ALT | MOD_NOREPEAT)
        self.assertEqual(key, 0x20)

    def test_accepts_supported_single_chord(self) -> None:
        modifiers, key = shortcut_to_native("Ctrl+Shift+F12")
        self.assertTrue(modifiers & MOD_NOREPEAT)
        self.assertEqual(key, 0x7B)

    def test_rejects_sequence_without_modifier(self) -> None:
        with self.assertRaises(HotkeyError):
            shortcut_to_native("Space")

    def test_rejects_multiple_chords_and_unsupported_keys(self) -> None:
        with self.assertRaises(HotkeyError):
            shortcut_to_native("Ctrl+A, Ctrl+B")
        with self.assertRaises(HotkeyError):
            shortcut_to_native("Ctrl+Tab")

    def test_displays_meta_as_win(self) -> None:
        self.assertEqual(display_hotkey(DEFAULT_HOTKEY), "Win+Alt+Space")


if __name__ == "__main__":
    unittest.main()
