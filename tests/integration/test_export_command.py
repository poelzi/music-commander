"""Integration tests for files export command."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from music_commander.utils.encoder import ExportResult, FormatPreset, SourceInfo

from music_commander.cli import cli
from music_commander.config import Config


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


def _ok_result(source: str, output: str, preset: str = "mp3-320") -> ExportResult:
    """Create a successful ExportResult."""
    return ExportResult(
        source=source,
        output=output,
        status="ok",
        preset=preset,
        action="encode",
        duration_seconds=1.5,
    )


def _error_result(source: str, output: str, preset: str = "mp3-320") -> ExportResult:
    """Create a failed ExportResult."""
    return ExportResult(
        source=source,
        output=output,
        status="error",
        preset=preset,
        action="encode",
        duration_seconds=0.0,
        error_message="ffmpeg failed: invalid input",
    )


def _skipped_result(source: str, output: str, preset: str = "mp3-320") -> ExportResult:
    """Create a skipped ExportResult."""
    return ExportResult(
        source=source,
        output=output,
        status="skipped",
        preset=preset,
        action="skipped",
        duration_seconds=0.0,
    )


def _copied_result(source: str, output: str, preset: str = "flac") -> ExportResult:
    """Create a copied ExportResult."""
    return ExportResult(
        source=source,
        output=output,
        status="copied",
        preset=preset,
        action="copy",
        duration_seconds=0.5,
    )


# ---------------------------------------------------------------------------
# Format selection tests
# ---------------------------------------------------------------------------


def test_explicit_format_mp3_320(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test --format mp3-320 selects correct preset."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        # Create a test file
        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.flac", "output.mp3")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}",
                            "-o",
                            "/tmp/export-test",
                            "test.flac",
                        ],
                    )

                    # Verify preset was used
                    assert mock_export.called
                    call_args = mock_export.call_args
                    preset = call_args[0][2]  # Third positional arg
                    assert preset.name == "mp3-320"


def test_auto_detect_format_from_extension(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test template .flac -> flac preset auto-detection."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.mp3"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.mp3"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.mp3", "output.flac", "flac")

                    result = runner.invoke(
                        cli,
                        ["files", "export", "-p", "{{ title }}.flac", "-o", "/tmp", "test.mp3"],
                    )

                    # Should auto-detect flac preset from .flac extension
                    assert mock_export.called
                    call_args = mock_export.call_args
                    preset = call_args[0][2]
                    assert preset.name == "flac"


def test_unknown_extension_error(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test template .xyz without --format -> error."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        result = runner.invoke(
            cli,
            ["files", "export", "-p", "{{ title }}.xyz", "-o", "/tmp", "test.flac"],
        )

        assert result.exit_code != 0
        assert "Unknown extension" in result.output or "No preset" in result.output


def test_extension_conflict_warning(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test --format flac with .mp3 template -> warning printed but proceeds."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.flac", "output.mp3", "flac")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "flac",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            "/tmp",
                            "test.flac",
                        ],
                    )

                    # Should show warning about extension conflict
                    assert "Warning" in result.output or "conflict" in result.output.lower()
                    # But should still proceed with flac preset
                    assert mock_export.called


# ---------------------------------------------------------------------------
# Incremental mode tests
# ---------------------------------------------------------------------------


def test_skip_existing_file(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test output exists and is newer -> skipped."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                # Mock _should_skip to return True
                with patch("music_commander.commands.files._should_skip") as mock_skip:
                    mock_skip.return_value = True

                    with patch("music_commander.commands.files.export_file") as mock_export:
                        result = runner.invoke(
                            cli,
                            [
                                "files",
                                "export",
                                "-f",
                                "mp3-320",
                                "-p",
                                "{{ title }}.mp3",
                                "-o",
                                "/tmp",
                                "test.flac",
                            ],
                        )

                        # export_file should NOT be called for skipped files
                        assert not mock_export.called
                        assert "skipped" in result.output.lower() or "Skipped" in result.output


def test_force_re_exports_all(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test --force -> all files exported regardless."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.flac", "output.mp3")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            "/tmp",
                            "--force",
                            "test.flac",
                        ],
                    )

                    # With --force, export_file SHOULD be called
                    assert mock_export.called


# ---------------------------------------------------------------------------
# Dry-run tests
# ---------------------------------------------------------------------------


def test_dry_run_no_files_written(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test --dry-run -> no output files created."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    with patch("music_commander.commands.files.probe_source") as mock_probe:
                        mock_probe.return_value = SourceInfo(
                            codec_name="flac",
                            sample_rate=44100,
                            bit_depth=16,
                            channels=2,
                            has_cover_art=False,
                        )

                        result = runner.invoke(
                            cli,
                            [
                                "files",
                                "export",
                                "-f",
                                "mp3-320",
                                "-p",
                                "{{ title }}.mp3",
                                "-o",
                                "/tmp",
                                "--dry-run",
                                "test.flac",
                            ],
                        )

                        # export_file should NOT be called in dry-run
                        assert not mock_export.called
                        assert result.exit_code == 0


def test_dry_run_shows_preview(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test --dry-run -> table output with actions."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.probe_source") as mock_probe:
                    mock_probe.return_value = SourceInfo(
                        codec_name="flac",
                        sample_rate=44100,
                        bit_depth=16,
                        channels=2,
                        has_cover_art=False,
                    )

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            "/tmp",
                            "--dry-run",
                            "test.flac",
                        ],
                    )

                    # Should show preview table
                    assert "Export Preview" in result.output or "preview" in result.output.lower()
                    assert "encode" in result.output.lower() or "Action" in result.output


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------


def test_json_report_structure(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config, tmp_path: Path
) -> None:
    """Verify report JSON has version, timestamp, summary, results."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        output_dir = tmp_path / "export"
        output_dir.mkdir()

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.flac", "output.mp3")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            str(output_dir),
                            "test.flac",
                        ],
                    )

                    # Check report was written
                    report_path = output_dir / ".music-commander-export-report.json"
                    assert report_path.exists()

                    report_data = json.loads(report_path.read_text())
                    assert "version" in report_data
                    assert "timestamp" in report_data
                    assert "summary" in report_data
                    assert "results" in report_data
                    assert "preset" in report_data


def test_json_report_summary_counts(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config, tmp_path: Path
) -> None:
    """Summary counts match actual results."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file1 = git_annex_repo / "test1.flac"
        test_file1.write_text("")
        test_file2 = git_annex_repo / "test2.flac"
        test_file2.write_text("")

        output_dir = tmp_path / "export"
        output_dir.mkdir()

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file1, test_file2]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track1 = MagicMock()
                mock_track1.file = "test1.flac"
                mock_track1.artist = "Artist1"
                mock_track1.title = "Title1"
                mock_track1.album = "Album"
                mock_track1.genre = None
                mock_track1.bpm = None
                mock_track1.rating = None
                mock_track1.key = None
                mock_track1.year = None
                mock_track1.tracknumber = None
                mock_track1.comment = None

                mock_track2 = MagicMock()
                mock_track2.file = "test2.flac"
                mock_track2.artist = "Artist2"
                mock_track2.title = "Title2"
                mock_track2.album = "Album"
                mock_track2.genre = None
                mock_track2.bpm = None
                mock_track2.rating = None
                mock_track2.key = None
                mock_track2.year = None
                mock_track2.tracknumber = None
                mock_track2.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track1, mock_track2]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    # First succeeds, second fails
                    mock_export.side_effect = [
                        _ok_result("test1.flac", "output1.mp3"),
                        _error_result("test2.flac", "output2.mp3"),
                    ]

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            str(output_dir),
                            "test1.flac",
                            "test2.flac",
                        ],
                    )

                    report_path = output_dir / ".music-commander-export-report.json"
                    report_data = json.loads(report_path.read_text())

                    summary = report_data["summary"]
                    assert summary["total"] == 2
                    assert summary["ok"] == 1
                    assert summary["error"] == 1


# ---------------------------------------------------------------------------
# Exit code tests
# ---------------------------------------------------------------------------


def test_exit_0_on_success(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """All files exported successfully -> exit 0."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.flac", "output.mp3")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            "/tmp",
                            "test.flac",
                        ],
                    )

                    assert result.exit_code == 0


def test_exit_0_on_copies_and_skips(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Only copies and skips -> exit 0."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _copied_result("test.flac", "output.flac")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "flac",
                            "-p",
                            "{{ title }}.flac",
                            "-o",
                            "/tmp",
                            "test.flac",
                        ],
                    )

                    assert result.exit_code == 0


def test_exit_1_on_errors(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Some files errored -> exit 1."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _error_result("test.flac", "output.mp3")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            "/tmp",
                            "test.flac",
                        ],
                    )

                    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_output_directory_created(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config, tmp_path: Path
) -> None:
    """Output dir doesn't exist -> created automatically."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        output_dir = tmp_path / "new_dir" / "nested"

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            with patch("music_commander.cache.query.get_cache") as mock_cache:
                mock_track = MagicMock()
                mock_track.file = "test.flac"
                mock_track.artist = "Artist"
                mock_track.title = "Title"
                mock_track.album = "Album"
                mock_track.genre = None
                mock_track.bpm = None
                mock_track.rating = None
                mock_track.key = None
                mock_track.year = None
                mock_track.tracknumber = None
                mock_track.comment = None

                mock_cache_instance = MagicMock()
                mock_cache_instance.get_all_tracks.return_value = [mock_track]
                mock_cache.return_value = mock_cache_instance

                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.flac", "output.mp3")

                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "export",
                            "-f",
                            "mp3-320",
                            "-p",
                            "{{ title }}.mp3",
                            "-o",
                            str(output_dir),
                            "test.flac",
                        ],
                    )

                    # Directory should be created
                    assert output_dir.exists()
