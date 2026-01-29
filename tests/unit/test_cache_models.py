"""Unit tests for cache models and session management."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.models import CacheBase, CacheState, CacheTrack, TrackCrate
from music_commander.cache.session import CACHE_DB_NAME, delete_cache, get_cache_session


def _in_memory_session() -> Session:
    """Create an in-memory SQLite session with cache tables."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestCacheTrack:
    def test_create_and_query(self) -> None:
        session = _in_memory_session()
        track = CacheTrack(
            key="SHA256E-s6850832--abc123.mp3",
            file="ambient/Artist - Track.mp3",
            artist="Test Artist",
            title="Test Track",
            album="Test Album",
            genre="Ambient",
            bpm=120.5,
            rating=4,
            key_musical="Am",
            year="2024",
            tracknumber="03",
            comment="A test track",
            color="#FF0000",
        )
        session.add(track)
        session.commit()

        result = session.query(CacheTrack).filter_by(key="SHA256E-s6850832--abc123.mp3").one()
        assert result.file == "ambient/Artist - Track.mp3"
        assert result.artist == "Test Artist"
        assert result.title == "Test Track"
        assert result.album == "Test Album"
        assert result.genre == "Ambient"
        assert result.bpm == 120.5
        assert result.rating == 4
        assert result.key_musical == "Am"
        assert result.year == "2024"
        assert result.tracknumber == "03"
        assert result.comment == "A test track"
        assert result.color == "#FF0000"

    def test_nullable_fields(self) -> None:
        session = _in_memory_session()
        track = CacheTrack(
            key="SHA256E-s100--minimal.flac",
            file="minimal.flac",
        )
        session.add(track)
        session.commit()

        result = session.query(CacheTrack).one()
        assert result.artist is None
        assert result.bpm is None
        assert result.rating is None
        assert result.key_musical is None

    def test_repr(self) -> None:
        track = CacheTrack(
            key="SHA256E-s6850832--abc123def456.mp3",
            file="test.mp3",
        )
        r = repr(track)
        assert "CacheTrack" in r
        assert "test.mp3" in r

    def test_query_by_bpm_range(self) -> None:
        session = _in_memory_session()
        for i, bpm in enumerate([100.0, 130.0, 145.0, 160.0]):
            session.add(
                CacheTrack(
                    key=f"key-{i}",
                    file=f"track-{i}.mp3",
                    bpm=bpm,
                )
            )
        session.commit()

        results = (
            session.query(CacheTrack).filter(CacheTrack.bpm >= 130.0, CacheTrack.bpm <= 150.0).all()
        )
        assert len(results) == 2
        assert {r.bpm for r in results} == {130.0, 145.0}

    def test_query_by_rating(self) -> None:
        session = _in_memory_session()
        for i, rating in enumerate([1, 3, 4, 5]):
            session.add(
                CacheTrack(
                    key=f"key-{i}",
                    file=f"track-{i}.mp3",
                    rating=rating,
                )
            )
        session.commit()

        results = session.query(CacheTrack).filter(CacheTrack.rating >= 4).all()
        assert len(results) == 2

    def test_query_by_artist(self) -> None:
        session = _in_memory_session()
        session.add(CacheTrack(key="k1", file="a.mp3", artist="Aphex Twin"))
        session.add(CacheTrack(key="k2", file="b.mp3", artist="Boards of Canada"))
        session.add(CacheTrack(key="k3", file="c.mp3", artist="Aphex Twin"))
        session.commit()

        results = session.query(CacheTrack).filter(CacheTrack.artist == "Aphex Twin").all()
        assert len(results) == 2


class TestTrackCrate:
    def test_create_and_query(self) -> None:
        session = _in_memory_session()
        session.add(CacheTrack(key="k1", file="track.mp3"))
        session.add(TrackCrate(key="k1", crate="Festival"))
        session.add(TrackCrate(key="k1", crate="DarkPsy"))
        session.commit()

        crates = session.query(TrackCrate).filter_by(key="k1").all()
        assert len(crates) == 2
        assert {c.crate for c in crates} == {"Festival", "DarkPsy"}

    def test_composite_primary_key(self) -> None:
        session = _in_memory_session()
        session.add(CacheTrack(key="k1", file="a.mp3"))
        session.add(CacheTrack(key="k2", file="b.mp3"))
        session.add(TrackCrate(key="k1", crate="Crate1"))
        session.add(TrackCrate(key="k2", crate="Crate1"))
        session.commit()

        results = session.query(TrackCrate).filter_by(crate="Crate1").all()
        assert len(results) == 2

    def test_repr(self) -> None:
        tc = TrackCrate(key="SHA256E-s100--abcdef.mp3", crate="TestCrate")
        r = repr(tc)
        assert "TrackCrate" in r
        assert "TestCrate" in r


class TestCacheState:
    def test_singleton_pattern(self) -> None:
        session = _in_memory_session()
        state = CacheState(
            id=1,
            annex_branch_commit="abc123def456",
            last_updated="2026-01-29T00:00:00Z",
            track_count=1000,
        )
        session.add(state)
        session.commit()

        result = session.query(CacheState).filter_by(id=1).one()
        assert result.annex_branch_commit == "abc123def456"
        assert result.last_updated == "2026-01-29T00:00:00Z"
        assert result.track_count == 1000

    def test_update_state(self) -> None:
        session = _in_memory_session()
        state = CacheState(id=1, annex_branch_commit="old", track_count=100)
        session.add(state)
        session.commit()

        state.annex_branch_commit = "new"
        state.track_count = 200
        session.commit()

        result = session.query(CacheState).one()
        assert result.annex_branch_commit == "new"
        assert result.track_count == 200

    def test_repr(self) -> None:
        state = CacheState(annex_branch_commit="abc123", track_count=500)
        r = repr(state)
        assert "CacheState" in r
        assert "abc123" in r


class TestGetCacheSession:
    def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / CACHE_DB_NAME
        assert not db_path.exists()

        with get_cache_session(tmp_path) as session:
            # Verify we can query (tables exist)
            result = session.query(CacheTrack).all()
            assert result == []

        assert db_path.exists()

    def test_tables_created(self, tmp_path: Path) -> None:
        with get_cache_session(tmp_path) as session:
            result = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            tables = {row[0] for row in result}

        assert "tracks" in tables
        assert "track_crates" in tables
        assert "cache_state" in tables

    def test_crud_operations(self, tmp_path: Path) -> None:
        with get_cache_session(tmp_path) as session:
            session.add(
                CacheTrack(
                    key="test-key",
                    file="test.mp3",
                    artist="Test",
                )
            )

        # Verify persistence in a new session
        with get_cache_session(tmp_path) as session:
            track = session.query(CacheTrack).one()
            assert track.key == "test-key"
            assert track.artist == "Test"

    def test_rollback_on_error(self, tmp_path: Path) -> None:
        with get_cache_session(tmp_path) as session:
            session.add(CacheTrack(key="good", file="good.mp3"))

        try:
            with get_cache_session(tmp_path) as session:
                session.add(CacheTrack(key="bad", file="bad.mp3"))
                raise ValueError("simulated error")
        except ValueError:
            pass

        with get_cache_session(tmp_path) as session:
            tracks = session.query(CacheTrack).all()
            assert len(tracks) == 1
            assert tracks[0].key == "good"


class TestDeleteCache:
    def test_delete_existing(self, tmp_path: Path) -> None:
        cache_path = tmp_path / CACHE_DB_NAME
        cache_path.write_text("fake db")
        assert cache_path.exists()

        deleted = delete_cache(tmp_path)
        assert deleted is True
        assert not cache_path.exists()

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        deleted = delete_cache(tmp_path)
        assert deleted is False
