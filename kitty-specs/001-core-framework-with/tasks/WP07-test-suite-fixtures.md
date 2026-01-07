---
work_package_id: "WP07"
subtasks:
  - "T019"
  - "T020"
  - "T021"
  - "T022"
  - "T023"
  - "T024"
title: "Test Suite & Fixtures"
phase: "Phase 3 - Integration"
lane: "planned"
assignee: ""
agent: ""
shell_pid: ""
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-06"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP07 – Test Suite & Fixtures

## Objectives & Success Criteria

- pytest infrastructure with shared fixtures
- Sample Mixxx database for testing
- 80%+ coverage on core modules (config, models, git utils)
- Integration tests for get-commit-files command
- All tests pass via `nix flake check`

## Context & Constraints

**Constitution Requirements**:
- New features MUST include unit tests before merging
- Integration tests MUST cover git-annex operations using fixtures
- Tests MUST be runnable via `nix flake check`
- Test coverage SHOULD be maintained above 80% for core modules

**Reference Documents**:
- `kitty-specs/001-core-framework-with/plan.md` - Testing strategy
- `kitty-specs/001-core-framework-with/data-model.md` - Entity definitions for fixtures

**Dependencies**: WP06 must be complete (all code exists to test)

## Subtasks & Detailed Guidance

### Subtask T019 – Create tests/conftest.py

**Purpose**: Shared pytest fixtures for all tests.

**File**: `tests/conftest.py`

**Implementation**:
```python
"""Shared pytest fixtures."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


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
    config_path.write_text('''
[paths]
mixxx_db = "/tmp/test_mixxx.sqlite"
music_repo = "/tmp/test_music"

[display]
colored_output = true

[git_annex]
default_remote = "test-remote"
''')
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
    conn.executescript('''
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
            duration INTEGER,
            bitrate INTEGER,
            bpm REAL,
            key TEXT,
            rating INTEGER DEFAULT 0,
            timesplayed INTEGER DEFAULT 0,
            mixxx_deleted INTEGER
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
    ''')
    
    # Insert sample data
    conn.execute('''
        INSERT INTO track_locations (location, filename, directory, filesize)
        VALUES ('/music/Artist1 - Track1.flac', 'Artist1 - Track1.flac', '/music', 52428800)
    ''')
    conn.execute('''
        INSERT INTO library (artist, title, album, bpm, key, location, rating)
        VALUES ('Artist1', 'Track1', 'Album1', 128.0, 'Am', 1, 4)
    ''')
    conn.execute('''
        INSERT INTO Playlists (id, name, position) VALUES (1, 'Test Playlist', 0)
    ''')
    conn.execute('''
        INSERT INTO PlaylistTracks (playlist_id, track_id, position)
        VALUES (1, 1, 0)
    ''')
    conn.execute('''
        INSERT INTO crates (name) VALUES ('Test Crate')
    ''')
    conn.execute('''
        INSERT INTO crate_tracks (crate_id, track_id) VALUES (1, 1)
    ''')
    
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
        cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path, check=True, capture_output=True
    )
    
    # Initialize git-annex
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path, check=True, capture_output=True
    )
    
    # Create and add some files
    music_dir = repo_path / "tracks"
    music_dir.mkdir()
    
    # Create a test file and annex it
    test_file = music_dir / "test.flac"
    test_file.write_bytes(b"fake flac content " * 1000)
    
    subprocess.run(
        ["git", "annex", "add", str(test_file.relative_to(repo_path))],
        cwd=repo_path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test track"],
        cwd=repo_path, check=True, capture_output=True
    )
    
    yield repo_path


@pytest.fixture
def mock_config(sample_mixxx_db: Path, temp_dir: Path):
    """Create a Config object for testing."""
    from music_commander.config import Config
    
    return Config(
        mixxx_db=sample_mixxx_db,
        music_repo=temp_dir,
        colored_output=False,
        default_remote=None,
    )
```

### Subtask T020 – Create sample SQLite fixture

**Purpose**: Pre-built Mixxx database with realistic test data.

**File**: `tests/fixtures/mixxxdb_sample.sqlite`

**Implementation**: Create this file using a script or manually:

```python
# Script to generate fixture (run once, commit the .sqlite file)
import sqlite3
from pathlib import Path

fixture_dir = Path("tests/fixtures")
fixture_dir.mkdir(parents=True, exist_ok=True)

db_path = fixture_dir / "mixxxdb_sample.sqlite"
conn = sqlite3.connect(db_path)

# Full schema from data-model.md...
# Insert 10-20 tracks, 2 playlists, 2 crates, some cues

conn.close()
```

**Notes**: The fixture should contain:
- 10-20 tracks with varied metadata
- 2 playlists with tracks
- 2 crates with tracks
- Some cue points on tracks
- Realistic file paths

### Subtask T021 – Create tests/unit/test_config.py

**Purpose**: Unit tests for configuration loading.

**File**: `tests/unit/test_config.py`

**Implementation**:
```python
"""Unit tests for configuration."""

from pathlib import Path

import pytest

from music_commander.config import Config, load_config
from music_commander.exceptions import ConfigParseError, ConfigValidationError


def test_default_config():
    """Test that default config has sensible values."""
    config = Config()
    assert config.colored_output is True
    assert config.default_remote is None


def test_load_missing_config(temp_dir: Path):
    """Test loading when config file doesn't exist."""
    config_path = temp_dir / "nonexistent.toml"
    config, warnings = load_config(config_path)
    
    assert config is not None
    assert len(warnings) > 0  # Should warn about missing file


def test_load_valid_config(sample_config: Path):
    """Test loading a valid config file."""
    config, warnings = load_config(sample_config)
    
    assert config.default_remote == "test-remote"
    assert config.colored_output is True


def test_load_invalid_toml(temp_dir: Path):
    """Test loading invalid TOML raises error."""
    config_path = temp_dir / "invalid.toml"
    config_path.write_text("this is not valid [ toml")
    
    with pytest.raises(ConfigParseError):
        load_config(config_path)


def test_config_validation_invalid_type(temp_dir: Path):
    """Test that invalid types raise validation error."""
    config_path = temp_dir / "bad_types.toml"
    config_path.write_text('''
[display]
colored_output = "not a boolean"
''')
    
    with pytest.raises(ConfigValidationError):
        load_config(config_path)


def test_config_path_expansion():
    """Test that paths are expanded."""
    config = Config(mixxx_db=Path("~/test.sqlite"))
    config.validate()
    
    assert "~" not in str(config.mixxx_db)
```

### Subtask T022 – Create tests/unit/test_models.py

**Purpose**: Unit tests for ORM models.

**File**: `tests/unit/test_models.py`

**Implementation**:
```python
"""Unit tests for database models."""

from pathlib import Path

import pytest

from music_commander.db import get_session, Track, Playlist, Crate


def test_track_repr(sample_mixxx_db: Path):
    """Test Track string representation."""
    with get_session(sample_mixxx_db) as session:
        track = session.query(Track).first()
        assert "Track" in repr(track)
        assert "Artist1" in repr(track)


def test_track_file_path(sample_mixxx_db: Path):
    """Test Track.file_path property."""
    with get_session(sample_mixxx_db) as session:
        track = session.query(Track).first()
        assert track.file_path is not None
        assert "Track1" in track.file_path


def test_playlist_is_locked(sample_mixxx_db: Path):
    """Test Playlist.is_locked property."""
    with get_session(sample_mixxx_db) as session:
        playlist = session.query(Playlist).first()
        assert playlist.is_locked is False


def test_crate_is_visible(sample_mixxx_db: Path):
    """Test Crate.is_visible property."""
    with get_session(sample_mixxx_db) as session:
        crate = session.query(Crate).first()
        assert crate.is_visible is True
```

**Parallel**: Can proceed alongside T023.

### Subtask T023 – Create tests/unit/test_git_utils.py

**Purpose**: Unit tests for git utilities.

**File**: `tests/unit/test_git_utils.py`

**Implementation**:
```python
"""Unit tests for git utilities."""

from pathlib import Path

import pytest

from music_commander.exceptions import InvalidRevisionError, NotGitAnnexRepoError
from music_commander.utils.git import (
    check_git_annex_repo,
    get_files_from_revision,
    is_annexed,
    is_valid_revision,
)


def test_check_git_annex_repo_valid(git_annex_repo: Path):
    """Test valid git-annex repo passes check."""
    check_git_annex_repo(git_annex_repo)  # Should not raise


def test_check_git_annex_repo_invalid(temp_dir: Path):
    """Test non-annex repo raises error."""
    with pytest.raises(NotGitAnnexRepoError):
        check_git_annex_repo(temp_dir)


def test_is_valid_revision(git_annex_repo: Path):
    """Test revision validation."""
    assert is_valid_revision(git_annex_repo, "HEAD") is True
    assert is_valid_revision(git_annex_repo, "nonexistent") is False


def test_get_files_from_commit(git_annex_repo: Path):
    """Test getting files from a commit."""
    files = get_files_from_revision(git_annex_repo, "HEAD")
    assert len(files) > 0
    assert any("test.flac" in str(f) for f in files)


def test_get_files_invalid_revision(git_annex_repo: Path):
    """Test invalid revision raises error."""
    with pytest.raises(InvalidRevisionError):
        get_files_from_revision(git_annex_repo, "nonexistent-branch")


def test_is_annexed_regular_file(temp_dir: Path):
    """Test regular file is not detected as annexed."""
    regular_file = temp_dir / "regular.txt"
    regular_file.write_text("content")
    assert is_annexed(regular_file) is False
```

**Parallel**: Can proceed alongside T022.

### Subtask T024 – Create tests/integration/test_get_commit_files.py

**Purpose**: Integration tests for the main command.

**File**: `tests/integration/test_get_commit_files.py`

**Implementation**:
```python
"""Integration tests for get-commit-files command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from music_commander.cli import cli
from music_commander.config import Config


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


def test_help(runner: CliRunner):
    """Test --help works."""
    result = runner.invoke(cli, ["get-commit-files", "--help"])
    assert result.exit_code == 0
    assert "REVISION" in result.output


def test_dry_run(runner: CliRunner, git_annex_repo: Path, mock_config):
    """Test --dry-run shows files without fetching."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])
        
        result = runner.invoke(cli, ["get-commit-files", "--dry-run", "HEAD"])
        assert result.exit_code == 0
        assert "Would fetch" in result.output or "No annexed files" in result.output


def test_invalid_revision(runner: CliRunner, git_annex_repo: Path, mock_config):
    """Test invalid revision returns exit code 2."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])
        
        result = runner.invoke(cli, ["get-commit-files", "nonexistent-branch-xyz"])
        assert result.exit_code == 2
        assert "Invalid revision" in result.output


def test_not_annex_repo(runner: CliRunner, temp_dir: Path, mock_config):
    """Test non-annex repo returns exit code 3."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = temp_dir
        mock_load.return_value = (mock_config, [])
        
        result = runner.invoke(cli, ["get-commit-files", "HEAD"])
        assert result.exit_code == 3
```

## Definition of Done Checklist

- [ ] T019: conftest.py with all fixtures
- [ ] T020: Sample SQLite fixture with realistic data
- [ ] T021: test_config.py passes
- [ ] T022: test_models.py passes
- [ ] T023: test_git_utils.py passes
- [ ] T024: test_get_commit_files.py passes
- [ ] `nix flake check` runs all tests successfully
- [ ] Coverage report shows 80%+ on core modules
- [ ] No flaky tests (run 3x to verify)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| git-annex not in test env | Use nix flake check which includes git-annex |
| Flaky git tests | Use isolated temp directories, deterministic setup |
| Slow integration tests | Minimize git operations, reuse fixtures |

## Review Guidance

- Run `pytest -v` locally to verify all tests pass
- Check coverage with `pytest --cov=music_commander`
- Verify tests are isolated (no shared state between tests)
- Ensure fixtures clean up properly

## Activity Log

- 2026-01-06 – system – lane=planned – Prompt created.
