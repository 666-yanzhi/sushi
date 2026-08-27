from __future__ import annotations

import ntpath
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .models import AppEntry, LauncherConfig


@dataclass(frozen=True)
class ImportPlan:
    entries: tuple[AppEntry, ...]
    invalid: tuple[str, ...]
    duplicates: tuple[str, ...]


@dataclass(frozen=True)
class ImportOutcome:
    config: LauncherConfig
    plan: ImportPlan
    error: str | None = None


def build_import_plan(
    paths: tuple[str, ...],
    existing_apps: tuple[AppEntry, ...],
    category_id: str,
) -> ImportPlan:
    """Validate dropped files and build entries without changing configuration."""
    existing_targets = {_windows_path_key(app.target) for app in existing_apps}
    existing_ids = {app.id for app in existing_apps}
    entries: list[AppEntry] = []
    invalid: list[str] = []
    duplicates: list[str] = []

    for raw_path in paths:
        path = Path(raw_path).expanduser()
        label = path.name or raw_path
        try:
            absolute = path.resolve(strict=True)
        except OSError:
            invalid.append(label)
            continue
        if not absolute.is_file() or absolute.suffix.casefold() not in {".exe", ".lnk"}:
            invalid.append(label)
            continue

        target_key = _windows_path_key(str(absolute))
        if target_key in existing_targets:
            duplicates.append(label)
            continue

        app_id = _new_app_id(existing_ids)
        existing_ids.add(app_id)
        existing_targets.add(target_key)
        entries.append(
            AppEntry(
                id=app_id,
                name=absolute.stem,
                category_id=category_id,
                target=str(absolute),
            )
        )

    return ImportPlan(tuple(entries), tuple(invalid), tuple(duplicates))


def format_import_summary(plan: ImportPlan) -> str:
    parts = [f"已添加 {len(plan.entries)} 个应用"]
    if plan.duplicates:
        parts.append(f"跳过 {len(plan.duplicates)} 个重复项")
    if plan.invalid:
        parts.append(f"忽略 {len(plan.invalid)} 个无效文件")
    return "；".join(parts) + "。"


def persist_import(
    config: LauncherConfig,
    paths: tuple[str, ...],
    category_id: str,
    save_config: Callable[[LauncherConfig], None],
) -> ImportOutcome:
    """Save a complete candidate before exposing it as the new runtime config."""
    plan = build_import_plan(paths, config.apps, category_id)
    if not plan.entries:
        return ImportOutcome(config, plan)
    candidate = replace(config, apps=(*config.apps, *plan.entries))
    try:
        save_config(candidate)
    except OSError as exc:
        return ImportOutcome(config, plan, f"保存应用失败：{exc}")
    return ImportOutcome(candidate, plan)


def _windows_path_key(target: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(target))
    absolute = os.path.abspath(os.path.normpath(expanded))
    return ntpath.normcase(ntpath.normpath(absolute))


def _new_app_id(existing_ids: set[str]) -> str:
    while True:
        candidate = f"app-{uuid.uuid4().hex[:12]}"
        if candidate not in existing_ids:
            return candidate
