from __future__ import annotations

from typing import Iterable

from sqlalchemy import or_


MULTI_CATEGORY_SEPARATOR = "|"


def _normalize_single_category(value: str) -> str:
    cleaned = " ".join(value.strip().lower().split())
    return cleaned.strip(MULTI_CATEGORY_SEPARATOR).strip(",")


def parse_categories(raw: str | None) -> list[str]:
    if not raw:
        return []

    normalized_raw = raw.strip()
    if not normalized_raw:
        return []

    if normalized_raw.startswith(MULTI_CATEGORY_SEPARATOR) and normalized_raw.endswith(MULTI_CATEGORY_SEPARATOR):
        parts = normalized_raw.split(MULTI_CATEGORY_SEPARATOR)
        return [part for part in (_normalize_single_category(item) for item in parts) if part]

    if "," in normalized_raw:
        return [part for part in (_normalize_single_category(item) for item in normalized_raw.split(",")) if part]

    single = _normalize_single_category(normalized_raw)
    return [single] if single else []


def normalize_categories(raw: str | Iterable[str] | None) -> str | None:
    if raw is None:
        return None

    if isinstance(raw, str):
        items = parse_categories(raw)
    else:
        items = [item for item in (_normalize_single_category(str(part)) for part in raw) if item]

    unique_items = sorted(dict.fromkeys(items))
    if not unique_items:
        return None

    return MULTI_CATEGORY_SEPARATOR + MULTI_CATEGORY_SEPARATOR.join(unique_items) + MULTI_CATEGORY_SEPARATOR


def categories_label(raw: str | None) -> str | None:
    items = parse_categories(raw)
    return ", ".join(items) if items else None


def category_membership_condition(column, category: str):
    normalized = _normalize_single_category(category)
    if not normalized:
        return None

    token = f"{MULTI_CATEGORY_SEPARATOR}{normalized}{MULTI_CATEGORY_SEPARATOR}"
    return or_(
        column == normalized,
        column.ilike(f"%{token}%"),
    )

