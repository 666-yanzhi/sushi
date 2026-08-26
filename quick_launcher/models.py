from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    id: str
    name: str


@dataclass(frozen=True)
class AppEntry:
    id: str
    name: str
    category_id: str
    target: str
    args: tuple[str, ...] = ()
    cwd: str | None = None


@dataclass(frozen=True)
class LauncherConfig:
    schema_version: int
    categories: tuple[Category, ...]
    apps: tuple[AppEntry, ...]
