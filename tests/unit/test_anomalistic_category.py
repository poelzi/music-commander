"""Unit tests for Anomalistic portal category classification."""

from __future__ import annotations

from music_commander.anomalistic.category import (
    GENRE_IDS,
    IGNORED_IDS,
    CategoryType,
    PortalCategory,
    classify_categories,
    get_release_genres,
    get_release_labels,
)


def _make_cat(cat_id: int, name: str, slug: str = "", count: int = 1) -> dict:
    """Create a raw category dict matching WordPress API format."""
    return {
        "id": cat_id,
        "name": name,
        "slug": slug or name.lower().replace(" ", "-"),
        "count": count,
    }


class TestClassifyCategories:
    """Tests for classify_categories()."""

    def test_genre_classification(self):
        raw = [_make_cat(9, "DarkPsy")]
        result = classify_categories(raw)
        assert result[9].type == CategoryType.GENRE
        assert result[9].name == "DarkPsy"

    def test_label_classification(self):
        raw = [_make_cat(21, "Anomalistic Records")]
        result = classify_categories(raw)
        assert result[21].type == CategoryType.LABEL

    def test_ignored_classification(self):
        raw = [_make_cat(3, "All Releases")]
        result = classify_categories(raw)
        assert result[3].type == CategoryType.IGNORED

    def test_ignored_id_42(self):
        raw = [_make_cat(42, "P")]
        result = classify_categories(raw)
        assert result[42].type == CategoryType.IGNORED

    def test_ignored_id_1(self):
        raw = [_make_cat(1, "Uncategorized")]
        result = classify_categories(raw)
        assert result[1].type == CategoryType.IGNORED

    def test_mixed_categories(self):
        raw = [
            _make_cat(9, "DarkPsy"),
            _make_cat(21, "Anomalistic Records"),
            _make_cat(3, "All Releases"),
            _make_cat(12, "Hi-Tech"),
            _make_cat(50, "Some Label"),
        ]
        result = classify_categories(raw)
        assert result[9].type == CategoryType.GENRE
        assert result[21].type == CategoryType.LABEL
        assert result[3].type == CategoryType.IGNORED
        assert result[12].type == CategoryType.GENRE
        assert result[50].type == CategoryType.LABEL

    def test_all_genre_ids(self):
        """Verify all known genre IDs are classified correctly."""
        raw = [_make_cat(gid, f"Genre{gid}") for gid in GENRE_IDS]
        result = classify_categories(raw)
        for gid in GENRE_IDS:
            assert result[gid].type == CategoryType.GENRE

    def test_all_ignored_ids(self):
        """Verify all known ignored IDs are classified correctly."""
        raw = [_make_cat(iid, f"Ignored{iid}") for iid in IGNORED_IDS]
        result = classify_categories(raw)
        for iid in IGNORED_IDS:
            assert result[iid].type == CategoryType.IGNORED

    def test_unknown_id_is_label(self):
        """Any ID not in GENRE_IDS or IGNORED_IDS should be LABEL."""
        raw = [_make_cat(999, "Unknown Label")]
        result = classify_categories(raw)
        assert result[999].type == CategoryType.LABEL

    def test_empty_input(self):
        result = classify_categories([])
        assert result == {}

    def test_count_preserved(self):
        raw = [_make_cat(9, "DarkPsy", count=42)]
        result = classify_categories(raw)
        assert result[9].count == 42

    def test_missing_count_defaults_zero(self):
        raw = [{"id": 9, "name": "DarkPsy", "slug": "darkpsy"}]
        result = classify_categories(raw)
        assert result[9].count == 0


class TestGetReleaseGenres:
    """Tests for get_release_genres()."""

    def test_returns_genre_names(self):
        categories = classify_categories(
            [
                _make_cat(9, "DarkPsy"),
                _make_cat(12, "Hi-Tech"),
                _make_cat(21, "Anomalistic Records"),
            ]
        )
        result = get_release_genres([9, 21, 12], categories)
        assert result == ["DarkPsy", "Hi-Tech"]

    def test_preserves_input_order(self):
        categories = classify_categories(
            [
                _make_cat(9, "DarkPsy"),
                _make_cat(12, "Hi-Tech"),
            ]
        )
        result = get_release_genres([12, 9], categories)
        assert result == ["Hi-Tech", "DarkPsy"]

    def test_no_genres(self):
        categories = classify_categories([_make_cat(21, "Some Label")])
        result = get_release_genres([21], categories)
        assert result == []

    def test_empty_category_ids(self):
        categories = classify_categories([_make_cat(9, "DarkPsy")])
        result = get_release_genres([], categories)
        assert result == []

    def test_unknown_category_id_ignored(self):
        categories = classify_categories([_make_cat(9, "DarkPsy")])
        result = get_release_genres([9, 999], categories)
        assert result == ["DarkPsy"]


class TestGetReleaseLabels:
    """Tests for get_release_labels()."""

    def test_returns_label_names(self):
        categories = classify_categories(
            [
                _make_cat(9, "DarkPsy"),
                _make_cat(21, "Anomalistic Records"),
                _make_cat(50, "Other Label"),
            ]
        )
        result = get_release_labels([9, 21, 50], categories)
        assert result == ["Anomalistic Records", "Other Label"]

    def test_preserves_input_order(self):
        categories = classify_categories(
            [
                _make_cat(21, "Anomalistic Records"),
                _make_cat(50, "Other Label"),
            ]
        )
        result = get_release_labels([50, 21], categories)
        assert result == ["Other Label", "Anomalistic Records"]

    def test_no_labels(self):
        categories = classify_categories([_make_cat(9, "DarkPsy")])
        result = get_release_labels([9], categories)
        assert result == []

    def test_ignores_ignored_categories(self):
        categories = classify_categories(
            [
                _make_cat(3, "All Releases"),
                _make_cat(21, "Anomalistic Records"),
            ]
        )
        result = get_release_labels([3, 21], categories)
        assert result == ["Anomalistic Records"]


class TestGenreAndIgnoredSets:
    """Tests for the hardcoded ID sets."""

    def test_genre_ids_no_overlap_with_ignored(self):
        assert GENRE_IDS.isdisjoint(IGNORED_IDS)

    def test_genre_ids_count(self):
        assert len(GENRE_IDS) == 17

    def test_ignored_ids_count(self):
        assert len(IGNORED_IDS) == 4
