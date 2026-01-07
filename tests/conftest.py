"""Shared pytest fixtures."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

    from music_commander.config import Config


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test files."""
    path = Path(tempfile.mkdtemp())
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def sample_config(temp_dir: Path) -> Path:
    """Create a sample config file."""
    config_path = temp_dir / "config.toml"
    config_path.write_text("""[paths]
mixxx_db = "/tmp/test_mixxx.sqlite"
music_repo = "/tmp/test_music"

[display]
colored_output = true

[git_annex]
default_remote = "test-remote"
""")
    return config_path


@pytest.fixture
def sample_mixxx_db(temp_dir: Path) -> Path:
    """Create a sample Mixxx database for testing.

    Uses the pre-built fixture if available, otherwise creates minimal schema.
    """
    fixture_path = Path(__file__).parent / "fixtures" / "mixxxdb_sample.sqlite"

    if fixture_path.exists():
        # Copy fixture to temp location
        db_path = temp_dir / "mixxxdb.sqlite"
        shutil.copy(fixture_path, db_path)
        return db_path

    # Create minimal database
    import sqlite3

    db_path = temp_dir / "mixxxdb.sqlite"
    conn = sqlite3.connect(db_path)

    # Create required tables (minimal schema)
    conn.executescript("""
        CREATE TABLE track_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location TEXT UNIQUE,
            filename TEXT,
            directory TEXT,
            filesize INTEGER,
            fs_deleted INTEGER,
            needs_verification INTEGER
        );

        CREATE TABLE library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT,
            title TEXT,
            album TEXT,
            year TEXT,
            genre TEXT,
            tracknumber TEXT,
            location INTEGER REFERENCES track_locations(id),
            comment TEXT,
            url TEXT,
            duration INTEGER,
            bitrate INTEGER,
            samplerate INTEGER,
            cuepoint INTEGER,
            bpm REAL,
            channels INTEGER,
            datetime_added DATETIME,
            mixxx_deleted INTEGER,
            played INTEGER,
            filetype TEXT DEFAULT '?',
            replaygain REAL DEFAULT 0,
            timesplayed INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 0,
            key TEXT DEFAULT '',
            composer TEXT DEFAULT '',
            bpm_lock INTEGER DEFAULT 0,
            key_id INTEGER DEFAULT 0,
            grouping TEXT DEFAULT '',
            album_artist TEXT DEFAULT '',
            color INTEGER,
            last_played_at DATETIME,
            source_synchronized_ms INTEGER
        );

        CREATE TABLE Playlists (
            id INTEGER PRIMARY KEY,
            name TEXT,
            position INTEGER,
            hidden INTEGER DEFAULT 0,
            locked INTEGER DEFAULT 0,
            date_created DATETIME,
            date_modified DATETIME
        );

        CREATE TABLE PlaylistTracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id INTEGER REFERENCES Playlists(id),
            track_id INTEGER REFERENCES library(id),
            position INTEGER
        );

        CREATE TABLE crates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            count INTEGER DEFAULT 0,
            show INTEGER DEFAULT 1,
            locked INTEGER DEFAULT 0,
            autodj_source INTEGER DEFAULT 0
        );

        CREATE TABLE crate_tracks (
            crate_id INTEGER REFERENCES crates(id),
            track_id INTEGER REFERENCES library(id),
            PRIMARY KEY (crate_id, track_id)
        );

        CREATE TABLE cues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id INTEGER NOT NULL REFERENCES library(id),
            type INTEGER DEFAULT 0,
            position INTEGER DEFAULT -1,
            length INTEGER DEFAULT 0,
            hotcue INTEGER DEFAULT -1,
            label TEXT DEFAULT '',
            color INTEGER DEFAULT 4294901760,
            source INTEGER DEFAULT 2
        );
    """)

    # Insert sample data
    conn.execute("""
        INSERT INTO track_locations (location, filename, directory, filesize)
        VALUES ('/music/Artist1 - Track1.flac', 'Artist1 - Track1.flac', '/music', 52428800)
    """)
    conn.execute("""
        INSERT INTO library (artist, title, album, bpm, key, location, rating)
        VALUES ('Artist1', 'Track1', 'Album1', 128.0, 'Am', 1, 4)
    """)
    conn.execute("""
        INSERT INTO Playlists (id, name, position) VALUES (1, 'Test Playlist', 0)
    """)
    conn.execute("""
        INSERT INTO PlaylistTracks (playlist_id, track_id, position)
        VALUES (1, 1, 0)
    """)
    conn.execute("""
        INSERT INTO crates (name) VALUES ('Test Crate')
    """)
    conn.execute("""
        INSERT INTO crate_tracks (crate_id, track_id) VALUES (1, 1)
    """)

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def git_annex_repo(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a temporary git-annex repository for testing."""
    repo_path = temp_dir / "music_repo"
    repo_path.mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Initialize git-annex
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create and add some files
    music_dir = repo_path / "tracks"
    music_dir.mkdir()

    # Create a test file and annex it
    test_file = music_dir / "test.flac"
    test_file.write_bytes(b"fake flac content " * 1000)

    subprocess.run(
        ["git", "annex", "add", str(test_file.relative_to(repo_path))],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test track"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    yield repo_path


@pytest.fixture
def mock_config(sample_mixxx_db: Path, temp_dir: Path) -> Config:
    """Create a Config object for testing."""
    from music_commander.config import Config

    return Config(
        mixxx_db=sample_mixxx_db,
        music_repo=temp_dir,
        colored_output=False,
        default_remote=None,
    )
