import tempfile
import unittest
from pathlib import Path

from quick_launcher.importer import build_import_plan, format_import_summary, persist_import
from quick_launcher.models import AppEntry, Category, LauncherConfig


class ImporterTests(unittest.TestCase):
    def test_builds_entries_for_exe_and_lnk_and_rejects_other_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            exe = root / "Editor.EXE"
            shortcut = root / "Notes.lnk"
            invalid = root / "readme.txt"
            for path in (exe, shortcut, invalid):
                path.touch()

            plan = build_import_plan(
                (str(exe), str(shortcut), str(invalid)),
                (),
                "daily",
            )

            self.assertEqual([entry.name for entry in plan.entries], ["Editor", "Notes"])
            self.assertEqual({entry.category_id for entry in plan.entries}, {"daily"})
            self.assertEqual(len({entry.id for entry in plan.entries}), 2)
            self.assertEqual(plan.invalid, ("readme.txt",))

    def test_skips_existing_and_batch_duplicates_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "Tool.exe"
            executable.touch()
            existing = (AppEntry("old", "Tool", "dev", str(executable).upper()),)

            plan = build_import_plan(
                (str(executable), str(executable)),
                existing,
                "dev",
            )

            self.assertFalse(plan.entries)
            self.assertEqual(len(plan.duplicates), 2)
            self.assertEqual(
                format_import_summary(plan),
                "已添加 0 个应用；跳过 2 个重复项。",
            )

    def test_duplicate_inside_one_batch_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shortcut = Path(temp_dir) / "App.lnk"
            shortcut.touch()
            plan = build_import_plan((str(shortcut), str(shortcut)), (), "dev")
            self.assertEqual(len(plan.entries), 1)
            self.assertEqual(len(plan.duplicates), 1)

    def test_save_failure_keeps_original_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "App.exe"
            executable.touch()
            config = LauncherConfig(1, (Category("dev", "开发"),), ())

            def fail_save(candidate: LauncherConfig) -> None:
                raise OSError("disk full")

            outcome = persist_import(config, (str(executable),), "dev", fail_save)

            self.assertIs(outcome.config, config)
            self.assertEqual(config.apps, ())
            self.assertIn("disk full", outcome.error)


if __name__ == "__main__":
    unittest.main()
