from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .models import AppEntry, Category, LauncherConfig, LauncherSettings


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
            "settings": {
                "hotkey": config.settings.hotkey,
                "hot_corner_enabled": config.settings.hot_corner_enabled,
                "hot_corner_position": config.settings.hot_corner_position,
                "hot_corner_zone_px": config.settings.hot_corner_zone_px,
                "hot_corner_dwell_ms": config.settings.hot_corner_dwell_ms,
                "hide_on_focus_lost": config.settings.hide_on_focus_lost,
                "remember_window_position": config.settings.remember_window_position,
                "window_x": config.settings.window_x,
                "window_y": config.settings.window_y,
                "icon_size": config.settings.icon_size,
                "launch_at_login": config.settings.launch_at_login,
                "theme": config.settings.theme,
                "window_opacity": config.settings.window_opacity,
            },
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
    settings = _parse_settings(raw.get("settings", {}))

    categories_raw = raw.get("categories")
    apps_raw = raw.get("apps")
    if not isinstance(categories_raw, list) or not isinstance(apps_raw, list):
        raise ConfigError("categories 和 apps 必须是数组。")

    categories = tuple(
        Category(
            id=_required_text(item, "id", "分类"),
            name=_required_text(item, "name", "分类"),
            parent_id=_optional_text(item, "parent_id", "分类"),
        )
        for item in categories_raw
    )
    category_ids = [category.id for category in categories]
    if len(set(category_ids)) != len(category_ids):
        raise ConfigError("分类 id 不能重复。")
    categories_by_id = {category.id: category for category in categories}
    for category in categories:
        if category.parent_id is None:
            continue
        if category.parent_id == category.id:
            raise ConfigError(f"分类“{category.id}”不能以自己作为父分类。")
        parent = categories_by_id.get(category.parent_id)
        if parent is None:
            raise ConfigError(f"分类“{category.id}”引用了不存在的父分类。")
        if parent.parent_id is not None:
            raise ConfigError("分类最多支持两级。")

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
    return LauncherConfig(
        schema_version=version,
        categories=categories,
        apps=tuple(apps),
        settings=settings,
    )


def _parse_settings(raw: object) -> LauncherSettings:
    """Use defaults for pre-settings V1 config files."""
    if not isinstance(raw, dict):
        raise ConfigError("settings 必须是对象。")
    hotkey = raw.get("hotkey", "Meta+Alt+Space")
    hot_corner_enabled = raw.get("hot_corner_enabled", True)
    hot_corner_position = raw.get("hot_corner_position", "top_right")
    hot_corner_zone_px = raw.get("hot_corner_zone_px", 8)
    hot_corner_dwell_ms = raw.get("hot_corner_dwell_ms", 250)
    hide_on_focus_lost = raw.get("hide_on_focus_lost", True)
    remember_window_position = raw.get("remember_window_position", False)
    window_x = raw.get("window_x")
    window_y = raw.get("window_y")
    icon_size = raw.get("icon_size", 48)
    launch_at_login = raw.get("launch_at_login", False)
    theme = raw.get("theme", "light")
    window_opacity = raw.get("window_opacity", 1.0)
    if not isinstance(hotkey, str) or not hotkey.strip():
        raise ConfigError("settings.hotkey 必须是非空字符串。")
    if not isinstance(hot_corner_enabled, bool):
        raise ConfigError("settings.hot_corner_enabled 必须是 true 或 false。")
    if hot_corner_position not in {"top_left", "top_right", "bottom_left", "bottom_right"}:
        raise ConfigError("settings.hot_corner_position 必须是四个角落之一。")
    if isinstance(hot_corner_zone_px, bool) or not isinstance(hot_corner_zone_px, int) or not 4 <= hot_corner_zone_px <= 48:
        raise ConfigError("settings.hot_corner_zone_px 必须是 4 到 48 之间的整数。")
    if isinstance(hot_corner_dwell_ms, bool) or not isinstance(hot_corner_dwell_ms, int) or not 100 <= hot_corner_dwell_ms <= 1000:
        raise ConfigError("settings.hot_corner_dwell_ms 必须是 100 到 1000 之间的整数。")
    if not isinstance(hide_on_focus_lost, bool):
        raise ConfigError("settings.hide_on_focus_lost 必须是 true 或 false。")
    if not isinstance(remember_window_position, bool):
        raise ConfigError("settings.remember_window_position 必须是 true 或 false。")
    for key, value in (("window_x", window_x), ("window_y", window_y)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ConfigError(f"settings.{key} 必须是整数或 null。")
    if (window_x is None) != (window_y is None):
        raise ConfigError("settings.window_x 与 window_y 必须同时设置或同时为 null。")
    if isinstance(icon_size, bool) or not isinstance(icon_size, int) or not 32 <= icon_size <= 80:
        raise ConfigError("settings.icon_size 必须是 32 到 80 之间的整数。")
    if not isinstance(launch_at_login, bool):
        raise ConfigError("settings.launch_at_login 必须是 true 或 false。")
    if theme not in {"light", "dark"}:
        raise ConfigError("settings.theme 必须是 light 或 dark。")
    if isinstance(window_opacity, bool) or not isinstance(window_opacity, (int, float)):
        raise ConfigError("settings.window_opacity 必须是 0.6 到 1.0 之间的数字。")
    if not 0.6 <= float(window_opacity) <= 1.0:
        raise ConfigError("settings.window_opacity 必须是 0.6 到 1.0 之间的数字。")
    return LauncherSettings(
        hotkey=hotkey.strip(),
        hot_corner_enabled=hot_corner_enabled,
        hot_corner_position=hot_corner_position,
        hot_corner_zone_px=hot_corner_zone_px,
        hot_corner_dwell_ms=hot_corner_dwell_ms,
        hide_on_focus_lost=hide_on_focus_lost,
        remember_window_position=remember_window_position,
        window_x=window_x,
        window_y=window_y,
        icon_size=icon_size,
        launch_at_login=launch_at_login,
        theme=theme,
        window_opacity=float(window_opacity),
    )


def _required_text(item: object, key: str, label: str) -> str:
    if not isinstance(item, dict):
        raise ConfigError(f"{label}条目必须是对象。")
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}缺少有效的 {key}。")
    return value.strip()


def _optional_text(item: object, key: str, label: str) -> str | None:
    if not isinstance(item, dict):
        raise ConfigError(f"{label}条目必须是对象。")
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label}的 {key} 必须是非空字符串或 null。")
    return value.strip()
