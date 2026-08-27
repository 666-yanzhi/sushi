import unittest

from quick_launcher.models import AppEntry
from quick_launcher.search import filter_apps


APPS = [
    AppEntry("code", "Visual Studio Code", "dev", "Code.exe"),
    AppEntry("pycharm", "PyCharm", "dev", "pycharm.exe"),
    AppEntry("notepad", "记事本", "daily", "notepad.exe"),
]


class SearchTests(unittest.TestCase):
    def test_filters_by_category_and_case_insensitive_name(self) -> None:
        result = filter_apps(APPS, "dev", "CODE")
        self.assertEqual([app.id for app in result], ["code"])

    def test_empty_search_keeps_selected_category(self) -> None:
        result = filter_apps(APPS, "daily", "")
        self.assertEqual([app.id for app in result], ["notepad"])

    def test_parent_category_scope_includes_child_apps(self) -> None:
        result = filter_apps(APPS, "dev", "", {"dev", "daily"})
        self.assertEqual([app.id for app in result], ["code", "pycharm", "notepad"])
