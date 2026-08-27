from __future__ import annotations

from dataclasses import replace

from .models import AppEntry, Category


UNCATEGORIZED_ID = "uncategorized"
UNCATEGORIZED_NAME = "未分类"


def is_uncategorized(category_id: str, category_name: str) -> bool:
    return category_id == UNCATEGORIZED_ID or category_name.casefold() == UNCATEGORIZED_NAME.casefold()


def move_orphaned_apps(
    old_categories: tuple[Category, ...],
    new_categories: tuple[Category, ...],
    apps: tuple[AppEntry, ...],
) -> tuple[tuple[Category, ...], tuple[AppEntry, ...]]:
    """Move apps from deleted categories into one stable fallback category."""
    old_ids = {category.id for category in old_categories}
    new_ids = {category.id for category in new_categories}
    deleted_ids = old_ids - new_ids
    orphaned_ids = {app.category_id for app in apps if app.category_id in deleted_ids}
    if not orphaned_ids:
        return new_categories, apps

    fallback = next(
        (
            category
            for category in new_categories
            if is_uncategorized(category.id, category.name)
        ),
        None,
    )
    if fallback is None:
        fallback = Category(UNCATEGORIZED_ID, UNCATEGORIZED_NAME)
        new_categories = (*new_categories, fallback)

    moved_apps = tuple(
        replace(app, category_id=fallback.id) if app.category_id in orphaned_ids else app
        for app in apps
    )
    return new_categories, moved_apps


def category_scope(categories: tuple[Category, ...], category_id: str | None) -> set[str] | None:
    if category_id is None:
        return None
    return {
        category.id
        for category in categories
        if category.id == category_id or category.parent_id == category_id
    }


def category_label(categories: tuple[Category, ...], category: Category) -> str:
    if category.parent_id is None:
        return category.name
    parent = next(
        (candidate for candidate in categories if candidate.id == category.parent_id),
        None,
    )
    return f"{parent.name} › {category.name}" if parent is not None else category.name


def category_subtree_ids(categories: tuple[Category, ...], category_id: str) -> set[str]:
    return {
        category.id
        for category in categories
        if category.id == category_id or category.parent_id == category_id
    }


def validate_category_layout(
    previous: tuple[Category, ...],
    candidate: tuple[Category, ...],
) -> str | None:
    """Validate a drag result before it is allowed to replace runtime state."""
    previous_ids = [category.id for category in previous]
    candidate_ids = [category.id for category in candidate]
    if len(candidate_ids) != len(set(candidate_ids)):
        return "分类拖拽结果包含重复项目。"
    if set(candidate_ids) != set(previous_ids):
        return "分类拖拽结果不完整，已恢复原顺序。"
    by_id = {category.id: category for category in candidate}
    uncategorized = next(
        (category for category in candidate if is_uncategorized(category.id, category.name)),
        None,
    )
    if uncategorized is not None and uncategorized.parent_id is not None:
        return "“未分类”必须保持为一级分类。"
    for category in candidate:
        if category.parent_id is None:
            continue
        parent = by_id.get(category.parent_id)
        if parent is None:
            return f"分类“{category.name}”的父分类不存在。"
        if parent.parent_id is not None:
            return "分类最多支持两级。"
        if any(child.parent_id == category.id for child in candidate):
            return "包含子分类的项目不能再归入其他分类。"
    return None
