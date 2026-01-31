"""Unit tests for resolve_args_to_files and related utilities."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_commander.cli import Context
from music_commander.config import Config
from music_commander.utils.search_ops import (
    _list_all_annexed_files,
    _scan_directory_files,
    resolve_args_to_files,
)


@pytest.fixture
def mock_context() -> Context:
    """Create a mock CLI context."""
    ctx = Context()
    ctx.quiet = False
    ctx.verbose = False
    ctx.debug = False
    return ctx


@pytest.fixture
def mock_config(temp_dir: Path) -> Config:
    """Create a mock config with temp directory as repo."""
    return Config(
        music_repo=temp_dir,
        colored_output=False,
    )


def test_list_all_annexed_files_success(mock_config: Config) -> None:
    """Test listing all annexed files via git-annex find."""
    mock_output = "tracks/artist1/song1.flac\ntracks/artist2/song2.mp3\n"

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=mock_output,
            stderr="",
        )

        result = _list_all_annexed_files(mock_config, verbose=False)

        assert result is not None
        assert len(result) == 2
        assert result[0] == mock_config.music_repo / "tracks/artist1/song1.flac"
        assert result[1] == mock_config.music_repo / "tracks/artist2/song2.mp3"

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0:3] == ["git", "annex", "find"]


def test_list_all_annexed_files_error(mock_config: Config) -> None:
    """Test error handling when git-annex find fails."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["git", "annex", "find"],
            stderr="fatal: not a git repository",
        )

        result = _list_all_annexed_files(mock_config, verbose=False)

        assert result is None


def test_scan_directory_files(temp_dir: Path) -> None:
    """Test recursive directory scanning."""
    # Create test directory structure
    subdir = temp_dir / "music" / "artist"
    subdir.mkdir(parents=True)

    file1 = temp_dir / "music" / "track1.flac"
    file2 = subdir / "track2.mp3"
    file3 = subdir / "track3.wav"

    file1.write_text("content1")
    file2.write_text("content2")
    file3.write_text("content3")

    # Also create a subdirectory (should be ignored)
    another_subdir = subdir / "subdir"
    another_subdir.mkdir()

    result = _scan_directory_files(temp_dir / "music", temp_dir, verbose=False)

    assert len(result) == 3
    assert file1 in result
    assert file2 in result
    assert file3 in result


def test_scan_directory_files_outside_repo(temp_dir: Path) -> None:
    """Test that files outside repo are excluded."""
    music_dir = temp_dir / "music"
    music_dir.mkdir()

    file1 = music_dir / "track1.flac"
    file1.write_text("content1")

    # Scan with a different repo path - file should be excluded
    fake_repo = temp_dir / "fake_repo"
    fake_repo.mkdir()

    result = _scan_directory_files(music_dir, fake_repo, verbose=False)

    # File is outside fake_repo, so should be excluded
    assert len(result) == 0


def test_resolve_args_to_files_single_file(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test resolving a single file path argument."""
    test_file = temp_dir / "track.flac"
    test_file.write_text("content")

    result = resolve_args_to_files(
        ctx=mock_context,
        args=(str(test_file),),
        config=mock_config,
        require_present=True,
        verbose=False,
    )

    assert result is not None
    assert len(result) == 1
    assert result[0] == test_file


def test_resolve_args_to_files_directory(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test resolving a directory argument."""
    music_dir = temp_dir / "music"
    music_dir.mkdir()

    file1 = music_dir / "track1.flac"
    file2 = music_dir / "track2.mp3"
    file1.write_text("content1")
    file2.write_text("content2")

    result = resolve_args_to_files(
        ctx=mock_context,
        args=(str(music_dir),),
        config=mock_config,
        require_present=True,
        verbose=False,
    )

    assert result is not None
    assert len(result) == 2
    assert file1 in result
    assert file2 in result


def test_resolve_args_to_files_search_query(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test resolving search query arguments."""
    with patch("music_commander.utils.search_ops.execute_search_files") as mock_search:
        # Create the file on disk so require_present filter passes
        mock_file = temp_dir / "result.flac"
        mock_file.write_text("content")
        mock_search.return_value = [mock_file]

        result = resolve_args_to_files(
            ctx=mock_context,
            args=("artist:Techno", "bpm:>140"),
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        assert result is not None
        assert len(result) == 1
        assert result[0] == mock_file

        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[1]["query"] == ("artist:Techno", "bpm:>140")


def test_resolve_args_to_files_mixed(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test resolving mixed path and query arguments."""
    # Create a real file
    test_file = temp_dir / "track.flac"
    test_file.write_text("content")

    with patch("music_commander.utils.search_ops.execute_search_files") as mock_search:
        # Create the search result file on disk so require_present filter passes
        mock_file = temp_dir / "search_result.flac"
        mock_file.write_text("content")
        mock_search.return_value = [mock_file]

        result = resolve_args_to_files(
            ctx=mock_context,
            args=(str(test_file), "artist:Techno"),
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        assert result is not None
        assert len(result) == 2
        assert test_file in result
        assert mock_file in result

        # Verify search was called with only the query term
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[1]["query"] == ("artist:Techno",)


def test_resolve_args_to_files_empty_args(
    mock_context: Context,
    mock_config: Config,
) -> None:
    """Test resolving empty arguments (should list all annexed files)."""
    with patch("music_commander.utils.search_ops._list_all_annexed_files") as mock_list:
        mock_list.return_value = [Path("/music/file1.flac"), Path("/music/file2.mp3")]

        result = resolve_args_to_files(
            ctx=mock_context,
            args=(),
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        assert result is not None
        assert len(result) == 2
        mock_list.assert_called_once_with(mock_config, verbose=False)


def test_resolve_args_to_files_nonexistent_path_as_query(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test that non-existent paths are treated as query terms."""
    with patch("music_commander.utils.search_ops.execute_search_files") as mock_search:
        mock_file = temp_dir / "result.flac"
        mock_search.return_value = [mock_file]

        result = resolve_args_to_files(
            ctx=mock_context,
            args=("nonexistent/path.flac",),
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        assert result is not None
        # Should have called search with the "path" as a query term
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        assert call_args[1]["query"] == ("nonexistent/path.flac",)


def test_resolve_args_to_files_deduplication(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test that duplicate files are removed."""
    test_file = temp_dir / "track.flac"
    test_file.write_text("content")

    with patch("music_commander.utils.search_ops.execute_search_files") as mock_search:
        # Search returns the same file that was also specified as path
        mock_search.return_value = [test_file]

        result = resolve_args_to_files(
            ctx=mock_context,
            args=(str(test_file), "title:Track"),
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        assert result is not None
        # Should only have one entry despite appearing in both path and search results
        assert len(result) == 1
        assert result[0] == test_file


def test_resolve_args_to_files_path_relative_to_cwd(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test path resolution relative to CWD."""
    test_file = temp_dir / "track.flac"
    test_file.write_text("content")

    # Change to temp_dir
    import os

    old_cwd = os.getcwd()
    try:
        os.chdir(temp_dir)

        result = resolve_args_to_files(
            ctx=mock_context,
            args=("track.flac",),  # Relative path
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        assert result is not None
        assert len(result) == 1
        assert result[0] == test_file

    finally:
        os.chdir(old_cwd)


def test_resolve_args_to_files_path_relative_to_repo(
    mock_context: Context,
    temp_dir: Path,
) -> None:
    """Test path resolution relative to repo root."""
    music_dir = temp_dir / "music"
    music_dir.mkdir()
    test_file = music_dir / "track.flac"
    test_file.write_text("content")

    config = Config(music_repo=temp_dir, colored_output=False)

    result = resolve_args_to_files(
        ctx=mock_context,
        args=("music/track.flac",),  # Relative to repo
        config=config,
        require_present=True,
        verbose=False,
    )

    assert result is not None
    assert len(result) == 1
    assert result[0] == test_file


def test_resolve_args_to_files_require_present_filter(
    mock_context: Context,
    mock_config: Config,
    temp_dir: Path,
) -> None:
    """Test that require_present filters out non-present files."""
    # Create a file then delete it (to simulate annexed but not present)
    test_file = temp_dir / "track.flac"
    test_file.write_text("content")
    file_path = test_file  # Save path
    test_file.unlink()  # Delete the file

    # The deleted path won't resolve as a file, so it's treated as a query term.
    # Mock execute_search_files to return empty (no matches).
    with patch("music_commander.utils.search_ops.execute_search_files") as mock_search:
        mock_search.return_value = []

        result = resolve_args_to_files(
            ctx=mock_context,
            args=(str(file_path),),
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        # No files exist, so result should be empty
        assert result is not None
        assert len(result) == 0


def test_resolve_args_to_files_search_error(
    mock_context: Context,
    mock_config: Config,
) -> None:
    """Test error handling when search fails."""
    with patch("music_commander.utils.search_ops.execute_search_files") as mock_search:
        mock_search.return_value = None  # Simulates search error

        result = resolve_args_to_files(
            ctx=mock_context,
            args=("artist:Invalid",),
            config=mock_config,
            require_present=True,
            verbose=False,
        )

        assert result is None
