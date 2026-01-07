"""Unit tests for database models."""

from pathlib import Path

from music_commander.db import Crate, Playlist, Track, get_session


def test_track_repr(sample_mixxx_db: Path) -> None:
    """Test Track string representation."""
    with get_session(sample_mixxx_db) as session:
        track = session.query(Track).first()
        assert track is not None
        assert "Track" in repr(track)
        assert "Artist1" in repr(track)


def test_track_file_path(sample_mixxx_db: Path) -> None:
    """Test Track.file_path property."""
    with get_session(sample_mixxx_db) as session:
        track = session.query(Track).first()
        assert track is not None
        assert track.file_path is not None
        assert "Track1" in track.file_path


def test_playlist_is_locked(sample_mixxx_db: Path) -> None:
    """Test Playlist.is_locked property."""
    with get_session(sample_mixxx_db) as session:
        playlist = session.query(Playlist).first()
        assert playlist is not None
        assert playlist.is_locked is False


def test_crate_is_visible(sample_mixxx_db: Path) -> None:
    """Test Crate.is_visible property."""
    with get_session(sample_mixxx_db) as session:
        crate = session.query(Crate).first()
        assert crate is not None
        assert crate.is_visible is True
