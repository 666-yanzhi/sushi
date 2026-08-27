from __future__ import annotations

from collections.abc import Collection, Iterable

from .models import AppEntry


def filter_apps(
    apps: Iterable[AppEntry],
    category_id: str | None,
    query: str,
    category_ids: Collection[str] | None = None,
) -> list[AppEntry]:
    """Return visible apps using a predictable, case-insensitive V1 search."""
    normalized_query = query.strip().casefold()
    return [
        app
        for app in apps
        if (category_id is None or app.category_id in (category_ids or {category_id}))
        and (not normalized_query or normalized_query in app.name.casefold())
    ]
