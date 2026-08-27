import unittest
from unittest.mock import patch

from quick_launcher.launcher import TargetLauncher
from quick_launcher.models import AppEntry
from quick_launcher.web_shortcut import (
    WebShortcutError,
    build_web_entry,
    default_web_name,
    favicon_url,
    normalize_web_url,
)


class WebShortcutTests(unittest.TestCase):
    def test_normalizes_url_and_uses_hostname_as_default_name(self) -> None:
        url = normalize_web_url("Example.COM/docs#part")
        self.assertEqual(url, "https://example.com/docs")
        self.assertEqual(default_web_name("https://www.example.com/"), "example.com")
        self.assertEqual(favicon_url(url), "https://example.com/favicon.ico")

    def test_rejects_non_web_scheme_and_duplicate_url(self) -> None:
        with self.assertRaises(WebShortcutError):
            normalize_web_url("file:///C:/secret.txt")
        existing = (AppEntry("web-old", "Example", "daily", "https://example.com/"),)
        with self.assertRaisesRegex(WebShortcutError, "已经添加"):
            build_web_entry("example.com", "Example 2", "daily", existing)

    def test_builds_unique_web_entry(self) -> None:
        entry = build_web_entry("https://example.com", "示例", "daily", ())
        self.assertTrue(entry.id.startswith("web-"))
        self.assertEqual(entry.target, "https://example.com/")
        self.assertEqual(entry.category_id, "daily")

    @patch("quick_launcher.launcher.QDesktopServices.openUrl", return_value=True)
    def test_launcher_opens_web_target_with_default_browser(self, open_url) -> None:
        TargetLauncher().open(AppEntry("web", "Example", "daily", "https://example.com/"))
        open_url.assert_called_once()


if __name__ == "__main__":
    unittest.main()
