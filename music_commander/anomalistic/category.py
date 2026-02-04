"""Category classification for the Dark Psy Portal.

Classifies WordPress categories into genres, labels, and ignored categories
based on hardcoded ID sets derived from the portal's category structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CategoryType(Enum):
    """Classification type for a portal category."""

    GENRE = "genre"
    LABEL = "label"
    IGNORED = "ignored"


@dataclass(frozen=True)
class PortalCategory:
    """A classified category from the Dark Psy Portal."""

    id: int
    name: str
    slug: str
    type: CategoryType
    count: int


# Genre category IDs from research.md R3
GENRE_IDS: frozenset[int] = frozenset(
    {7, 8, 9, 10, 11, 12, 14, 15, 16, 28, 29, 30, 33, 44, 47, 48, 69}
)

# Ignored category IDs (meta-categories, not content descriptors)
IGNORED_IDS: frozenset[int] = frozenset({1, 3, 6, 42})


def classify_categories(raw_categories: list[dict[str, Any]]) -> dict[int, PortalCategory]:
    """Classify raw WordPress category dicts into typed PortalCategory objects.

    Args:
        raw_categories: List of category dicts from the WordPress API.
            Each dict has keys: id, name, slug, count.

    Returns:
        Dict mapping category ID to PortalCategory.
    """
    result: dict[int, PortalCategory] = {}

    for cat in raw_categories:
        cat_id = cat["id"]
        if cat_id in IGNORED_IDS:
            cat_type = CategoryType.IGNORED
        elif cat_id in GENRE_IDS:
            cat_type = CategoryType.GENRE
        else:
            cat_type = CategoryType.LABEL

        result[cat_id] = PortalCategory(
            id=cat_id,
            name=cat["name"],
            slug=cat["slug"],
            type=cat_type,
            count=cat.get("count", 0),
        )

    return result


def get_release_genres(category_ids: list[int], categories: dict[int, PortalCategory]) -> list[str]:
    """Get genre names for a release from its category IDs.

    Args:
        category_ids: List of WordPress category IDs assigned to the release.
        categories: Classified category lookup from classify_categories().

    Returns:
        List of genre names, ordered by input category_ids.
    """
    return [
        categories[cid].name
        for cid in category_ids
        if cid in categories and categories[cid].type == CategoryType.GENRE
    ]


def get_release_labels(category_ids: list[int], categories: dict[int, PortalCategory]) -> list[str]:
    """Get label names for a release from its category IDs.

    Args:
        category_ids: List of WordPress category IDs assigned to the release.
        categories: Classified category lookup from classify_categories().

    Returns:
        List of label names, ordered by input category_ids.
    """
    return [
        categories[cid].name
        for cid in category_ids
        if cid in categories and categories[cid].type == CategoryType.LABEL
    ]
