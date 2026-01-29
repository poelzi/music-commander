"""Integration tests for search against real git-annex cached data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from music_commander.cache.models import CacheTrack
from music_commander.search.parser import parse_query
from music_commander.search.query import execute_search

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# T018: search returns all tracks
# ---------------------------------------------------------------------------


def test_search_returns_all_tracks(clone_cache_session: Session) -> None:
    """Empty search must return all 6 tracks (present and non-present)."""
    query = parse_query("")
    results = execute_search(clone_cache_session, query)
    assert len(results) == 6


# ---------------------------------------------------------------------------
# T019: field filter includes non-present
# ---------------------------------------------------------------------------


def test_field_filter_includes_non_present(clone_cache_session: Session) -> None:
    """rating:>=4 must include non-present tracks."""
    # Tracks with rating >= 4: track01(5), track02(4), track03(5), track05(4)
    # track05 is non-present (MISSING_TRACKS)
    query = parse_query("rating:>=4")
    results = execute_search(clone_cache_session, query)
    assert len(results) == 4
    assert any(not t.present for t in results), "Should include at least one non-present track"


# ---------------------------------------------------------------------------
# T020: text search
# ---------------------------------------------------------------------------


def test_text_search(clone_cache_session: Session) -> None:
    """Free-text search must find track by title."""
    query = parse_query("DarkPulse")
    results = execute_search(clone_cache_session, query)
    assert len(results) == 1
    assert results[0].title == "DarkPulse"


# ---------------------------------------------------------------------------
# T021: genre filter with non-present
# ---------------------------------------------------------------------------


def test_genre_filter(clone_cache_session: Session) -> None:
    """genre:Ambient must return 2 non-present tracks (track04, track06)."""
    query = parse_query("genre:Ambient")
    results = execute_search(clone_cache_session, query)
    assert len(results) == 2
    assert all(not t.present for t in results), "Both Ambient tracks should be non-present"


# ---------------------------------------------------------------------------
# T022: crate search
# ---------------------------------------------------------------------------


def test_crate_search(clone_cache_session: Session) -> None:
    """crate:Festival must return tracks 1 and 3."""
    query = parse_query("crate:Festival")
    results = execute_search(clone_cache_session, query)
    assert len(results) == 2
    artists = {t.artist for t in results}
    assert artists == {"AlphaArtist", "GammaArtist"}
