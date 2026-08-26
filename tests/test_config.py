import unittest

from quick_launcher.config import ConfigError, parse_config


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
