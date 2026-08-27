from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: str
    name: str
    parent_id: str | None = None


@dataclass(frozen=True)
class AppEntry:
    id: str
    name: str
    category_id: str
    target: str
    args: tuple[str, ...] = ()
    cwd: str | None = None


@dataclass(frozen=True)
class LauncherSettings:
    """The user-configurable ways to summon the launcher."""

    hotkey: str = "Meta+Alt+Space"
    hot_corner_enabled: bool = True
    hot_corner_position: str = "top_right"
    hot_corner_zone_px: int = 8
    hot_corner_dwell_ms: int = 250
    hide_on_focus_lost: bool = True
    remember_window_position: bool = False
    window_x: int | None = None
    window_y: int | None = None
    icon_size: int = 48
    launch_at_login: bool = False
    theme: str = "light"
    window_opacity: float = 1.0


@dataclass(frozen=True)
class LauncherConfig:
    schema_version: int
    categories: tuple[Category, ...]
    apps: tuple[AppEntry, ...]
    settings: LauncherSettings = LauncherSettings()
