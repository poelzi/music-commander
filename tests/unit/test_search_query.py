"""Unit tests for search query execution."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.models import CacheBase, CacheTrack, TrackCrate
from music_commander.search.parser import parse_query
from music_commander.search.query import execute_search


def _setup_session() -> Session:
    """Create an in-memory session with test data and FTS5 table."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    # Create FTS5 table
    session.execute(
        text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
            key, artist, title, album, genre, file
        )
    """)
    )
    session.commit()

    # Insert test data
    tracks = [
        CacheTrack(
            key="k1",
            file="darkpsy/Artist1 - Dark Track.mp3",
            artist="Dark Artist",
            title="Dark Track",
            album="Dark Album",
            genre="Darkpsy",
            bpm=148.0,
            rating=5,
            key_musical="Am",
            year="2023",
        ),
        CacheTrack(
            key="k2",
            file="ambient/Artist2 - Calm Song.flac",
            artist="Ambient Artist",
            title="Calm Song",
            album="Calm Album",
            genre="Ambient",
            bpm=80.0,
            rating=3,
            key_musical="C",
            year="2020",
        ),
        CacheTrack(
            key="k3",
            file="techno/DJ Test - Banger.mp3",
            artist="DJ Test",
            title="Banger",
            album="Club Hits",
            genre="Techno",
            bpm=140.0,
            rating=4,
            key_musical="Dm",
            year="2024",
        ),
        CacheTrack(
            key="k4",
            file="house/House DJ - Groovy.mp3",
            artist="House DJ",
            title="Groovy",
            album="House Collection",
            genre="House",
            bpm=125.0,
            rating=4,
            key_musical="F",
            year="2022",
        ),
        CacheTrack(
            key="k5",
            file="minimal/Minimal - Empty.mp3",
            artist=None,
            title="Empty",
            album=None,
            genre=None,
            bpm=None,
            rating=None,
            key_musical=None,
        ),
    ]
    for t in tracks:
        session.add(t)
    session.commit()

    # Add crate data
    session.add(TrackCrate(key="k1", crate="Festival"))
    session.add(TrackCrate(key="k1", crate="DarkPsy"))
    session.add(TrackCrate(key="k3", crate="Festival"))
    session.add(TrackCrate(key="k3", crate="Club"))
    session.add(TrackCrate(key="k4", crate="Club"))
    session.commit()

    # Populate FTS5 index
    session.execute(
        text("""
        INSERT INTO tracks_fts(key, artist, title, album, genre, file)
        SELECT key, artist, title, album, genre, file FROM tracks
    """)
    )
    session.commit()

    return session


# ---------------------------------------------------------------------------
# Text term (FTS5) tests
# ---------------------------------------------------------------------------


class TestTextTermSearch:
    def test_single_word(self) -> None:
        session = _setup_session()
        q = parse_query("Dark")
        results = execute_search(session, q)
        # Should match "Dark Artist", "Dark Track", "Dark Album", "Darkpsy"
        keys = {r.key for r in results}
        assert "k1" in keys

    def test_two_words_anded(self) -> None:
        session = _setup_session()
        q = parse_query("Calm Song")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert "k2" in keys

    def test_negated_text(self) -> None:
        session = _setup_session()
        q = parse_query("-Dark")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert "k1" not in keys
        # Other tracks should be present
        assert len(results) >= 3


# ---------------------------------------------------------------------------
# Field filter tests
# ---------------------------------------------------------------------------


class TestFieldFilterSearch:
    def test_contains(self) -> None:
        session = _setup_session()
        q = parse_query("artist:Dark")
        results = execute_search(session, q)
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_contains_case_insensitive(self) -> None:
        session = _setup_session()
        q = parse_query("artist:dark")
        results = execute_search(session, q)
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_exact_match(self) -> None:
        session = _setup_session()
        q = parse_query('artist:="DJ Test"')
        results = execute_search(session, q)
        assert len(results) == 1
        assert results[0].key == "k3"

    def test_exact_match_no_partial(self) -> None:
        session = _setup_session()
        q = parse_query('artist:="DJ"')
        results = execute_search(session, q)
        # Should NOT match "DJ Test" or "House DJ" (exact match only)
        assert len(results) == 0

    def test_gt(self) -> None:
        session = _setup_session()
        q = parse_query("bpm:>140")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k1"}  # bpm 148

    def test_gte(self) -> None:
        session = _setup_session()
        q = parse_query("bpm:>=140")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k1", "k3"}  # bpm 148 and 140

    def test_lt(self) -> None:
        session = _setup_session()
        q = parse_query("bpm:<100")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k2"}  # bpm 80

    def test_lte(self) -> None:
        session = _setup_session()
        q = parse_query("rating:<=3")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k2"}  # rating 3

    def test_range(self) -> None:
        session = _setup_session()
        q = parse_query("bpm:120-145")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k3", "k4"}  # bpm 140 and 125

    def test_negated_field(self) -> None:
        session = _setup_session()
        q = parse_query("-genre:Ambient")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert "k2" not in keys
        assert "k1" in keys

    def test_file_search(self) -> None:
        session = _setup_session()
        q = parse_query("file:darkpsy")
        results = execute_search(session, q)
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_key_musical_search(self) -> None:
        session = _setup_session()
        q = parse_query("key:Am")
        results = execute_search(session, q)
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_year_comparison(self) -> None:
        session = _setup_session()
        q = parse_query("year:>2022")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert "k1" in keys  # 2023
        assert "k3" in keys  # 2024


# ---------------------------------------------------------------------------
# Empty field tests
# ---------------------------------------------------------------------------


class TestEmptyField:
    def test_empty_genre(self) -> None:
        session = _setup_session()
        q = parse_query('genre:""')
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert "k5" in keys  # genre is None

    def test_empty_artist(self) -> None:
        session = _setup_session()
        q = parse_query('artist:""')
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert "k5" in keys


# ---------------------------------------------------------------------------
# OR logic tests
# ---------------------------------------------------------------------------


class TestOrSearch:
    def test_or_groups(self) -> None:
        session = _setup_session()
        q = parse_query("genre:House | genre:Techno")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k3", "k4"}

    def test_or_with_text(self) -> None:
        session = _setup_session()
        q = parse_query("genre:Darkpsy | genre:Ambient")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k1", "k2"}


# ---------------------------------------------------------------------------
# Crate tests
# ---------------------------------------------------------------------------


class TestCrateSearch:
    def test_crate_contains(self) -> None:
        session = _setup_session()
        q = parse_query("crate:Festival")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k1", "k3"}

    def test_crate_exact(self) -> None:
        session = _setup_session()
        q = parse_query("crate:=Club")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k3", "k4"}

    def test_negated_crate(self) -> None:
        session = _setup_session()
        q = parse_query("-crate:Festival")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert "k1" not in keys
        assert "k3" not in keys


# ---------------------------------------------------------------------------
# Combined query tests
# ---------------------------------------------------------------------------


class TestCombinedQueries:
    def test_text_and_field(self) -> None:
        session = _setup_session()
        q = parse_query("Dark bpm:>140")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k1"}

    def test_empty_query_returns_all(self) -> None:
        session = _setup_session()
        q = parse_query("")
        results = execute_search(session, q)
        assert len(results) == 5

    def test_field_and_or(self) -> None:
        session = _setup_session()
        q = parse_query("rating:>=4 genre:Techno | rating:>=4 genre:House")
        results = execute_search(session, q)
        keys = {r.key for r in results}
        assert keys == {"k3", "k4"}
