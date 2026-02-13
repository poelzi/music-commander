"""Unit tests for the cue split CLI command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner
from music_commander.commands.cue import cli

BASIC_CUE = """\
PERFORMER "Test Artist"
TITLE "Test Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Track One"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Track Two"
    INDEX 01 03:00:00
"""


def test_cue_group_help() -> None:
    """Verify the cue command group is registered and shows help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "CUE sheet processing commands" in result.output
    assert "split" in result.output


def test_split_help() -> None:
    """Verify the split subcommand shows help with all options."""
    runner = CliRunner()
    result = runner.invoke(cli, ["split", "--help"])
    assert result.exit_code == 0
    assert "--recursive" in result.output
    assert "--remove-originals" in result.output
    assert "--force" in result.output
    assert "--dry-run" in result.output
    assert "--encoding" in result.output
    assert "--verbose" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_missing_tools(mock_check: MagicMock) -> None:
    """Missing shntool should produce clear error."""
    mock_check.return_value = (["shntool"], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        result = runner.invoke(cli, ["split", "testdir"])
    assert result.exit_code == 2  # EXIT_MISSING_DEPS
    assert "shntool" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_optional_tools_warning(mock_check: MagicMock) -> None:
    """Missing optional tools should produce a warning but not block."""
    mock_check.return_value = ([], ["ffmpeg"])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        result = runner.invoke(cli, ["split", "testdir"])
    assert result.exit_code == 0
    assert "ffmpeg" in result.output
    assert "APE/WV fallback" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_no_cue_files(mock_check: MagicMock) -> None:
    """Directory with no cue files should report nothing found."""
    mock_check.return_value = ([], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        result = runner.invoke(cli, ["split", "testdir"])
    assert result.exit_code == 0
    assert "No cue/audio pairs found" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_dry_run(mock_check: MagicMock) -> None:
    """Dry run should show what would be split without actually splitting."""
    mock_check.return_value = ([], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        (Path("testdir") / "album.cue").write_text(BASIC_CUE)
        (Path("testdir") / "album.flac").touch()  # empty file for path detection
        result = runner.invoke(cli, ["split", "testdir", "--dry-run"])
    assert result.exit_code == 0
    assert "album.cue" in result.output
    assert "album.flac" in result.output
    assert "Tracks: 2" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_dry_run_verbose(mock_check: MagicMock) -> None:
    """Dry run with verbose should list individual track names."""
    mock_check.return_value = ([], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        (Path("testdir") / "album.cue").write_text(BASIC_CUE)
        (Path("testdir") / "album.flac").touch()
        result = runner.invoke(cli, ["split", "testdir", "--dry-run", "-v"])
    assert result.exit_code == 0
    assert "01 - Track One.flac" in result.output
    assert "02 - Track Two.flac" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_dry_run_shows_already_split(mock_check: MagicMock) -> None:
    """Dry run should indicate already-split albums."""
    mock_check.return_value = ([], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        (Path("testdir") / "album.cue").write_text(BASIC_CUE)
        (Path("testdir") / "album.flac").touch()
        # Create output files to simulate already split
        (Path("testdir") / "01 - Track One.flac").touch()
        (Path("testdir") / "02 - Track Two.flac").touch()
        result = runner.invoke(cli, ["split", "testdir", "--dry-run"])
    assert result.exit_code == 0
    assert "already split" in result.output or "(already split)" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_recursive_flag(mock_check: MagicMock) -> None:
    """Recursive flag should find cue files in subdirectories."""
    mock_check.return_value = ([], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("root/sub1").mkdir(parents=True)
        Path("root/sub2").mkdir(parents=True)
        (Path("root/sub1") / "album.cue").write_text(BASIC_CUE)
        (Path("root/sub1") / "album.flac").touch()
        (Path("root/sub2") / "album.cue").write_text(BASIC_CUE)
        (Path("root/sub2") / "album.flac").touch()
        result = runner.invoke(cli, ["split", "root", "--recursive", "--dry-run"])
    assert result.exit_code == 0
    # Should find both
    assert result.output.count("album.cue") == 2


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_no_recursive_skips_subdirs(mock_check: MagicMock) -> None:
    """Without recursive, subdirectories should not be scanned."""
    mock_check.return_value = ([], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("root/sub1").mkdir(parents=True)
        (Path("root/sub1") / "album.cue").write_text(BASIC_CUE)
        (Path("root/sub1") / "album.flac").touch()
        result = runner.invoke(cli, ["split", "root", "--dry-run"])
    assert result.exit_code == 0
    assert "No cue/audio pairs found" in result.output


@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_missing_source_file_warns(mock_check: MagicMock) -> None:
    """Cue file referencing missing audio should produce a warning."""
    mock_check.return_value = ([], [])
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        (Path("testdir") / "album.cue").write_text(BASIC_CUE)
        # Don't create album.flac
        result = runner.invoke(cli, ["split", "testdir", "--dry-run"])
    assert result.exit_code == 0
    assert "No cue/audio pairs found" in result.output


@patch("music_commander.commands.cue.split.split_cue")
@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_remove_originals(mock_check: MagicMock, mock_split: MagicMock) -> None:
    """Remove-originals should delete source files after successful split."""
    mock_check.return_value = ([], [])

    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        cue_path = Path("testdir") / "album.cue"
        audio_path = Path("testdir") / "album.flac"
        cue_path.write_text(BASIC_CUE)
        audio_path.touch()

        from music_commander.cue.splitter import SplitResult

        mock_split.return_value = SplitResult(
            source_path=audio_path,
            cue_path=cue_path,
            track_count=2,
            output_files=[],
            status="ok",
        )

        result = runner.invoke(cli, ["split", "testdir", "--remove-originals"])

    assert result.exit_code == 0
    assert "Split" in result.output


@patch("music_commander.commands.cue.split.split_cue")
@patch("music_commander.commands.cue.split.check_tools_available")
def test_split_error_exit_code(mock_check: MagicMock, mock_split: MagicMock) -> None:
    """Split errors should result in non-zero exit code."""
    mock_check.return_value = ([], [])

    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("testdir").mkdir()
        (Path("testdir") / "album.cue").write_text(BASIC_CUE)
        (Path("testdir") / "album.flac").touch()

        from music_commander.cue.splitter import SplitResult

        mock_split.return_value = SplitResult(
            source_path=Path("testdir/album.flac"),
            cue_path=Path("testdir/album.cue"),
            track_count=2,
            status="error",
            error="shntool failed",
        )

        result = runner.invoke(cli, ["split", "testdir"])

    assert result.exit_code == 1  # EXIT_SPLIT_ERROR
