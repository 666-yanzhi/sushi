import tempfile
import unittest
from pathlib import Path


from quick_launcher.config import AppPaths, ConfigError, ConfigStore, parse_config
from quick_launcher.importer import persist_import
from quick_launcher.models import Category, LauncherConfig, LauncherSettings


class ConfigParsingTests(unittest.TestCase):
    def test_accepts_valid_v1_config(self) -> None:
        config = parse_config(
            {
                "schema_version": 1,
                "categories": [{"id": "dev", "name": "开发"}],
                "apps": [
                    {
                        "id": "code",
                        "name": "VS Code",
                        "category_id": "dev",
                        "target": "Code.exe",
                        "args": ["--reuse-window"],
                        "cwd": None,
                    }
                ],
            }
        )
        self.assertEqual(config.apps[0].args, ("--reuse-window",))

    def test_rejects_unknown_category(self) -> None:
        with self.assertRaisesRegex(ConfigError, "不存在的分类"):
            parse_config(
                {
                    "schema_version": 1,
                    "categories": [{"id": "dev", "name": "开发"}],
                    "apps": [
                        {
                            "id": "code",
                            "name": "VS Code",
                            "category_id": "other",
                            "target": "Code.exe",
                        }
                    ],
                }
            )

    def test_rejects_duplicate_app_ids(self) -> None:
        app = {"id": "same", "name": "应用", "category_id": "dev", "target": "app.exe"}
        with self.assertRaisesRegex(ConfigError, "应用 id 不能重复"):
            parse_config(
                {
                    "schema_version": 1,
                    "categories": [{"id": "dev", "name": "开发"}],
                    "apps": [app, app],
                }
            )

    def test_legacy_config_uses_activation_defaults(self) -> None:
        config = parse_config(
            {
                "schema_version": 1,
                "categories": [{"id": "dev", "name": "开发"}],
                "apps": [],
            }
        )
        self.assertEqual(config.settings.hotkey, "Meta+Alt+Space")
        self.assertTrue(config.settings.hot_corner_enabled)
        self.assertTrue(config.settings.hide_on_focus_lost)
        self.assertEqual(config.settings.icon_size, 48)
        self.assertEqual(config.settings.hot_corner_position, "top_right")
        self.assertEqual(config.settings.hot_corner_zone_px, 8)
        self.assertEqual(config.settings.hot_corner_dwell_ms, 250)
        self.assertFalse(config.settings.remember_window_position)
        self.assertIsNone(config.settings.window_x)
        self.assertEqual(config.settings.theme, "light")
        self.assertEqual(config.settings.window_opacity, 1.0)
        self.assertFalse(config.settings.launch_at_login)

    def test_rejects_invalid_hot_corner_setting(self) -> None:
        with self.assertRaisesRegex(ConfigError, "hot_corner_enabled"):
            parse_config(
                {
                    "schema_version": 1,
                    "settings": {"hotkey": "Meta+Alt+Space", "hot_corner_enabled": "yes"},
                    "categories": [{"id": "dev", "name": "开发"}],
                    "apps": [],
                }
            )

    def test_rejects_invalid_icon_size(self) -> None:
        with self.assertRaisesRegex(ConfigError, "icon_size"):
            parse_config(
                {
                    "schema_version": 1,
                    "settings": {"icon_size": 120},
                    "categories": [],
                    "apps": [],
                }
            )

    def test_rejects_invalid_new_window_and_theme_settings(self) -> None:
        invalid_settings = (
            {"hot_corner_position": "center"},
            {"hot_corner_zone_px": 3},
            {"hot_corner_dwell_ms": 1001},
            {"remember_window_position": "yes"},
            {"window_x": 10, "window_y": None},
            {"theme": "blue"},
            {"window_opacity": 0.59},
            {"window_opacity": 1.01},
            {"window_opacity": "0.8"},
            {"launch_at_login": "yes"},
        )
        for settings in invalid_settings:
            with self.subTest(settings=settings), self.assertRaises(ConfigError):
                parse_config({"schema_version": 1, "settings": settings,
                              "categories": [], "apps": []})

    def test_round_trips_new_window_and_theme_settings(self) -> None:
        settings = LauncherSettings(
            hot_corner_position="bottom_left",
            hot_corner_zone_px=24,
            hot_corner_dwell_ms=600,
            remember_window_position=True,
            window_x=420,
            window_y=180,
            launch_at_login=True,
            theme="dark",
            window_opacity=0.75,
        )
        config = parse_config({
            "schema_version": 1,
            "settings": {
                "hot_corner_position": settings.hot_corner_position,
                "hot_corner_zone_px": settings.hot_corner_zone_px,
                "hot_corner_dwell_ms": settings.hot_corner_dwell_ms,
                "remember_window_position": settings.remember_window_position,
                "window_x": settings.window_x,
                "window_y": settings.window_y,
                "launch_at_login": settings.launch_at_login,
                "theme": settings.theme,
                "window_opacity": settings.window_opacity,
            },
            "categories": [], "apps": [],
        })
        self.assertEqual(config.settings, settings)

    def test_accepts_two_level_categories_and_rejects_third_level(self) -> None:
        config = parse_config(
            {
                "schema_version": 1,
                "categories": [
                    {"id": "dev", "name": "开发"},
                    {"id": "python", "name": "Python", "parent_id": "dev"},
                ],
                "apps": [],
            }
        )
        self.assertEqual(config.categories[1].parent_id, "dev")
        with self.assertRaisesRegex(ConfigError, "最多支持两级"):
            parse_config(
                {
                    "schema_version": 1,
                    "categories": [
                        {"id": "dev", "name": "开发"},
                        {"id": "python", "name": "Python", "parent_id": "dev"},
                        {"id": "tools", "name": "工具", "parent_id": "python"},
                    ],
                    "apps": [],
                }
            )

    def test_store_round_trips_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default = root / "default.json"
            default.write_text(
                '{"schema_version": 1, "categories": [], "apps": []}', encoding="utf-8"
            )
            store = ConfigStore(AppPaths(root / "user", default))
            config = LauncherConfig(
                schema_version=1,
                categories=(),
                apps=(),
                settings=LauncherSettings("Ctrl+Shift+F12", False),
            )
            store.save(config)
            self.assertEqual(store.load().settings, config.settings)


class CategoryConfigTests(unittest.TestCase):
    def test_category_order_and_names_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            default = root / "default.json"
            default.write_text(
                '{"schema_version": 1, "categories": [], "apps": []}', encoding="utf-8"
            )
            store = ConfigStore(AppPaths(root / "user", default))
            categories = (
                Category("study", "学习"),
                Category("dev", "开发工具"),
                Category("python", "Python", "dev"),
            )
            config = LauncherConfig(
                schema_version=1,
                categories=categories,
                apps=(),
                settings=LauncherSettings(),
            )
            store.save(config)
            self.assertEqual(store.load().categories, categories)

    def test_imported_apps_round_trip_without_reordering_existing_apps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "Tool.exe"
            executable.touch()
            default = root / "default.json"
            default.write_text(
                '{"schema_version": 1, "categories": [], "apps": []}', encoding="utf-8"
            )
            store = ConfigStore(AppPaths(root / "user", default))
            config = parse_config(
                {
                    "schema_version": 1,
                    "categories": [{"id": "dev", "name": "开发"}],
                    "apps": [
                        {
                            "id": "existing",
                            "name": "已有应用",
                            "category_id": "dev",
                            "target": "existing.exe",
                        }
                    ],
                }
            )
            outcome = persist_import(config, (str(executable),), "dev", store.save)

            loaded = store.load()
            self.assertIsNone(outcome.error)
            self.assertEqual([app.id for app in loaded.apps[:1]], ["existing"])
            self.assertEqual(loaded.apps[1].target, str(executable.resolve()))
            self.assertNotEqual(loaded.apps[0].id, loaded.apps[1].id)
