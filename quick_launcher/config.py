from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .models import AppEntry, Category, LauncherConfig


class ConfigError(ValueError):
    """Raised when a user configuration cannot be safely used."""


class AppPaths:
    """Paths which stay writable after the app is packaged and installed."""

    def __init__(self, user_data_dir: Path, default_config: Path) -> None:
        self.user_data_dir = user_data_dir
        self.config_file = user_data_dir / "shortcuts.json"
        self.icon_cache_dir = user_data_dir / "cache" / "icons"
        self.default_config = default_config

    @classmethod
    def for_current_user(cls) -> "AppPaths":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / ".quick-launcher"
        default_config = Path(__file__).parent / "resources" / "default_shortcuts.json"
        return cls(base / "QuickLauncher", default_config)

    def ensure_directories(self) -> None:
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.icon_cache_dir.mkdir(parents=True, exist_ok=True)


class ConfigStore:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def load_or_create(self) -> LauncherConfig:
        self.paths.ensure_directories()
        if not self.paths.config_file.exists():
            self.paths.config_file.write_text(
                self.paths.default_config.read_text(encoding="utf-8"), encoding="utf-8"
            )
        return self.load()

    def load(self) -> LauncherConfig:
        try:
            raw = json.loads(self.paths.config_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ConfigError(f"找不到配置文件：{self.paths.config_file}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"配置文件不是有效 JSON（第 {exc.lineno} 行）。") from exc
        return parse_config(raw)

    def save(self, config: LauncherConfig) -> None:
        """Atomically replace the config so a sudden exit cannot leave half a JSON file."""
        self.paths.ensure_directories()
        raw = {
            "schema_version": config.schema_version,
            "categories": [asdict(category) for category in config.categories],
            "apps": [
                {
                    "id": app.id,
                    "name": app.name,
                    "category_id": app.category_id,
                    "target": app.target,
                    "args": list(app.args),
                    "cwd": app.cwd,
                }
                for app in config.apps
            ],
        }
        descriptor, tmp_name = tempfile.mkstemp(
            prefix="shortcuts-", suffix=".json", dir=self.paths.user_data_dir
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(raw, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            Path(tmp_name).replace(self.paths.config_file)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise


def parse_config(raw: object) -> LauncherConfig:
    if not isinstance(raw, dict):
        raise ConfigError("配置根节点必须是对象。")
    version = raw.get("schema_version")
    if version != 1:
        raise ConfigError("只支持 schema_version 为 1 的配置文件。")

    categories_raw = raw.get("categories")
    apps_raw = raw.get("apps")
    if not isinstance(categories_raw, list) or not isinstance(apps_raw, list):
        raise ConfigError("categories 和 apps 必须是数组。")

    categories = tuple(
        Category(id=_required_text(item, "id", "分类"), name=_required_text(item, "name", "分类"))
        for item in categories_raw
    )
    category_ids = [category.id for category in categories]
    if len(set(category_ids)) != len(category_ids):
        raise ConfigError("分类 id 不能重复。")

    apps: list[AppEntry] = []
    app_ids: set[str] = set()
    for item in apps_raw:
        app_id = _required_text(item, "id", "应用")
        if app_id in app_ids:
            raise ConfigError("应用 id 不能重复。")
        category_id = _required_text(item, "category_id", "应用")
        if category_id not in category_ids:
            raise ConfigError(f"应用“{app_id}”引用了不存在的分类“{category_id}”。")
        args_raw = item.get("args", []) if isinstance(item, dict) else []
        if not isinstance(args_raw, list) or not all(isinstance(arg, str) for arg in args_raw):
            raise ConfigError(f"应用“{app_id}”的 args 必须是字符串数组。")
        cwd = item.get("cwd") if isinstance(item, dict) else None
        if cwd is not None and (not isinstance(cwd, str) or not cwd.strip()):
            raise ConfigError(f"应用“{app_id}”的 cwd 必须是非空字符串或 null。")
        apps.append(
            AppEntry(
                id=app_id,
                name=_required_text(item, "name", "应用"),
                category_id=category_id,
                target=_required_text(item, "target", "应用"),
                args=tuple(args_raw),
                cwd=cwd,
            )
        )
        app_ids.add(app_id)
    return LauncherConfig(schema_version=version, categories=categories, apps=tuple(apps))


def _required_text(item: object, key: str, label: str) -> str:
    if not isinstance(item, dict):
        raise ConfigError(f"{label}条目必须是对象。")
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}缺少有效的 {key}。")
    return value.strip()
