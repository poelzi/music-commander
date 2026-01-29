"""Integration tests for cache building against real git-annex repos."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from music_commander.cache.builder import build_cache, refresh_cache
from music_commander.cache.models import CacheBase, CacheTrack, TrackCrate

from .conftest import MISSING_TRACKS, PRESENT_TRACKS, TRACK_METADATA

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# T012: All tracks must have a file path (core bug regression)
# ---------------------------------------------------------------------------


def test_all_tracks_have_file_path(clone_cache_session: Session) -> None:
    """Every cached track must have file IS NOT NULL, even non-present ones."""
    tracks = clone_cache_session.query(CacheTrack).all()
    assert len(tracks) == 6
    assert all(t.file is not None for t in tracks), (
        f"Tracks with file=None: {[t.key for t in tracks if t.file is None]}"
    )


# ---------------------------------------------------------------------------
# T013: present field accuracy
# ---------------------------------------------------------------------------


def test_present_field_accuracy(clone_cache_session: Session) -> None:
    """present field must match actual local file availability in partial clone."""
    tracks = clone_cache_session.query(CacheTrack).all()
    assert len(tracks) == 6

    present_filenames = {t["filename"] for t in PRESENT_TRACKS}
    missing_filenames = {t["filename"] for t in MISSING_TRACKS}

    for track in tracks:
        # file is like "tracks/track01.mp3"
        filename = track.file.rsplit("/", 1)[-1] if track.file else None
        if filename in present_filenames:
            assert track.present is True, f"{filename} should be present"
        elif filename in missing_filenames:
            assert track.present is False, f"{filename} should NOT be present"
        else:
            raise AssertionError(f"Unexpected filename: {filename}")


# ---------------------------------------------------------------------------
# T014: metadata correctness
# ---------------------------------------------------------------------------


def test_metadata_correctness(clone_cache_session: Session) -> None:
    """Metadata parsed from real git-annex must match what was set."""
    tracks = clone_cache_session.query(CacheTrack).all()

    # Build lookup by artist (unique per track)
    by_artist = {t.artist: t for t in tracks}

    for expected in TRACK_METADATA:
        track = by_artist.get(expected["artist"])
        assert track is not None, f"Track by {expected['artist']} not found"
        assert track.title == expected["title"]
        assert track.genre == expected["genre"]
        assert track.bpm == float(expected["bpm"])
        assert track.rating == int(expected["rating"])


# ---------------------------------------------------------------------------
# T015: crate data
# ---------------------------------------------------------------------------


def test_crate_data(clone_cache_session: Session) -> None:
    """TrackCrate join table must be populated with correct crate names."""
    crates = clone_cache_session.query(TrackCrate).all()
    assert len(crates) == 6  # one crate per track

    # Build lookup by crate name
    crate_names = {c.crate for c in crates}
    assert "Festival" in crate_names
    assert "Club" in crate_names
    assert "Chill" in crate_names


# ---------------------------------------------------------------------------
# T016: incremental refresh no change
# ---------------------------------------------------------------------------


def test_incremental_refresh_no_change(partial_clone: Path) -> None:
    """refresh_cache returns None when no changes occurred."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    try:
        # Initial build
        build_cache(partial_clone, session)

        # Refresh with no changes
        result = refresh_cache(partial_clone, session)
        assert result is None
    finally:
        session.close()


# ---------------------------------------------------------------------------
# T017: FTS5 search
# ---------------------------------------------------------------------------


def test_fts5_search(clone_cache_session: Session) -> None:
    """FTS5 virtual table must work with real data."""
    result = clone_cache_session.execute(
        text("SELECT key FROM tracks_fts WHERE tracks_fts MATCH 'AlphaArtist'")
    ).fetchall()
    assert len(result) == 1
