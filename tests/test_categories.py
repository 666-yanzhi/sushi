import unittest

from quick_launcher.categories import (
    UNCATEGORIZED_ID,
    category_scope,
    move_orphaned_apps,
    validate_category_layout,
)
from quick_launcher.models import AppEntry, Category


class CategoryMigrationTests(unittest.TestCase):
    def test_moves_apps_from_deleted_category_to_new_uncategorized(self) -> None:
        old = (Category("dev", "开发"), Category("daily", "日常"))
        new = (Category("daily", "日常"),)
        apps = (
            AppEntry("code", "Code", "dev", "Code.exe"),
            AppEntry("notes", "Notes", "daily", "Notes.exe"),
        )

        categories, migrated = move_orphaned_apps(old, new, apps)

        self.assertEqual(categories[-1], Category(UNCATEGORIZED_ID, "未分类"))
        self.assertEqual(migrated[0].category_id, UNCATEGORIZED_ID)
        self.assertEqual(migrated[1], apps[1])

    def test_empty_deleted_category_does_not_create_fallback(self) -> None:
        old = (Category("empty", "空"), Category("daily", "日常"))
        new = (Category("daily", "日常"),)
        categories, apps = move_orphaned_apps(old, new, ())
        self.assertEqual(categories, new)
        self.assertEqual(apps, ())

    def test_reuses_existing_uncategorized_category(self) -> None:
        old = (Category("dev", "开发"), Category("misc", "未分类"))
        new = (Category("misc", "未分类"),)
        apps = (AppEntry("code", "Code", "dev", "Code.exe"),)
        categories, migrated = move_orphaned_apps(old, new, apps)
        self.assertEqual(categories, new)
        self.assertEqual(migrated[0].category_id, "misc")

    def test_parent_scope_includes_direct_children(self) -> None:
        categories = (
            Category("dev", "开发"),
            Category("python", "Python", "dev"),
            Category("daily", "日常"),
        )
        self.assertEqual(category_scope(categories, "dev"), {"dev", "python"})
        self.assertEqual(category_scope(categories, "python"), {"python"})

    def test_layout_allows_reorder_and_one_parent_child_transition(self) -> None:
        previous = (Category("dev", "开发"), Category("study", "学习"))
        reordered = (Category("study", "学习"), Category("dev", "开发"))
        nested = (Category("dev", "开发"), Category("study", "学习", "dev"))
        self.assertIsNone(validate_category_layout(previous, reordered))
        self.assertIsNone(validate_category_layout(previous, nested))

    def test_layout_rejects_missing_ids_third_level_and_uncategorized_child(self) -> None:
        previous = (
            Category("dev", "开发"),
            Category("python", "Python", "dev"),
            Category("misc", "未分类"),
        )
        self.assertIsNotNone(validate_category_layout(previous, previous[:-1]))
        third_level = (
            Category("dev", "开发"),
            Category("python", "Python", "dev"),
            Category("misc", "未分类", "python"),
        )
        self.assertIn("未分类", validate_category_layout(previous, third_level))
        nested_parent = (
            Category("dev", "开发"),
            Category("python", "Python", "dev"),
            Category("misc", "未分类"),
            Category("tools", "工具", "python"),
        )
        self.assertIsNotNone(validate_category_layout(
            (*previous, Category("tools", "工具")), nested_parent
        ))


if __name__ == "__main__":
    unittest.main()
