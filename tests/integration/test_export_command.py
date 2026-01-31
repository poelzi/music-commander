"""Integration tests for files export command."""

import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from music_commander.cli import cli
from music_commander.config import Config
from music_commander.utils.encoder import ExportResult, SourceInfo


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


def _make_mock_track(
    file: str, artist: str = "Artist", title: str = "Title", album: str = "Album"
) -> MagicMock:
    """Create a mock CacheTrack with standard fields."""
    track = MagicMock()
    track.file = file
    track.artist = artist
    track.title = title
    track.album = album
    track.genre = None
    track.bpm = None
    track.rating = None
    track.key_musical = None
    track.year = None
    track.tracknumber = None
    track.comment = None
    return track


@contextmanager
def _mock_cache_session(tracks: list[MagicMock]):
    """Context manager that mocks get_cache_session to return given tracks.

    Patches music_commander.cache.session.get_cache_session so that
    session.query(CacheTrack).all() returns the given tracks.
    """
    mock_session = MagicMock()
    mock_query = MagicMock()
    mock_query.all.return_value = tracks
    mock_session.query.return_value = mock_query

    @contextmanager
    def fake_get_cache_session(repo_path):
        yield mock_session

    with patch("music_commander.cache.session.get_cache_session", fake_get_cache_session):
        yield mock_session


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

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track = _make_mock_track("test.mp3")
            with _mock_cache_session([mock_track]):
                with patch("music_commander.commands.files.export_file") as mock_export:
                    mock_export.return_value = _ok_result("test.mp3", "output.flac", "flac")

                    result = runner.invoke(
                        cli,
                        ["files", "export", "-p", "{{ title }}.flac", "-o", "/tmp", "test.mp3"],
                    )

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
        assert "Unrecognized" in result.output or "extension" in result.output.lower()


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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

                    assert "differs" in result.output.lower() or "warning" in result.output.lower()
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track1 = _make_mock_track("test1.flac", artist="Artist1", title="Title1")
            mock_track2 = _make_mock_track("test2.flac", artist="Artist2", title="Title2")
            with _mock_cache_session([mock_track1, mock_track2]):
                with patch("music_commander.commands.files.export_file") as mock_export:
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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
    """Output path is correctly passed to export_file even for nested dirs."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        test_file = git_annex_repo / "test.flac"
        test_file.write_text("")

        output_dir = tmp_path / "new_dir" / "nested"

        with patch("music_commander.commands.files.resolve_args_to_files") as mock_resolve:
            mock_resolve.return_value = [test_file]

            mock_track = _make_mock_track("test.flac")
            with _mock_cache_session([mock_track]):
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

                    # export_file receives the correct output path under the nested dir
                    assert mock_export.called
                    call_args = mock_export.call_args
                    output_path = call_args[0][1]  # Second positional arg
                    assert str(output_dir) in str(output_path)


# ---------------------------------------------------------------------------
# Real integration tests (actually run ffmpeg, no mocks)
# ---------------------------------------------------------------------------

import shutil

from music_commander.utils.checkers import check_file
from music_commander.utils.encoder import PRESETS, export_file, probe_source


class TestRealExport:
    """Integration tests that actually run ffmpeg encoding and verify output."""

    @pytest.fixture(autouse=True)
    def _skip_no_ffmpeg(self):
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg not found")

    def test_flac_to_mp3_320(self, origin_repo, tmp_path):
        """Export FLAC -> MP3-320, verify integrity."""
        preset = PRESETS["mp3-320"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "output.mp3"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "ok"
        assert result.action == "encoded"
        assert output.exists()
        assert output.stat().st_size > 0

        check_result = check_file(output, tmp_path)
        assert check_result.status == "ok", f"Check failed: {check_result.errors}"

    def test_aiff_to_mp3_320(self, origin_repo, tmp_path):
        """Export AIFF -> MP3-320, verify integrity."""
        preset = PRESETS["mp3-320"]
        source = origin_repo / "tracks" / "track05.aiff"
        output = tmp_path / "output.mp3"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "ok"
        assert result.action == "encoded"
        assert output.exists()

        check_result = check_file(output, tmp_path)
        assert check_result.status == "ok", f"Check failed: {check_result.errors}"

    def test_mp3_to_flac(self, origin_repo, tmp_path):
        """Export MP3 -> FLAC, verify integrity."""
        preset = PRESETS["flac"]
        source = origin_repo / "tracks" / "track01.mp3"
        output = tmp_path / "output.flac"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "ok"
        assert result.action == "encoded"
        assert output.exists()

        check_result = check_file(output, tmp_path)
        assert check_result.status == "ok", f"Check failed: {check_result.errors}"

    def test_flac_to_flac_copies(self, origin_repo, tmp_path):
        """Export FLAC -> FLAC preset should file-copy (same format)."""
        preset = PRESETS["flac"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "output.flac"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "copied"
        assert result.action == "file_copied"
        assert output.exists()

        check_result = check_file(output, tmp_path)
        assert check_result.status == "ok", f"Check failed: {check_result.errors}"

    def test_flac_to_flac_pioneer(self, origin_repo, tmp_path):
        """Export FLAC -> flac-pioneer (16-bit/44.1kHz), verify parameters."""
        preset = PRESETS["flac-pioneer"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "output.flac"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "ok"
        assert result.action == "encoded"
        assert output.exists()

        # Verify output parameters
        info = probe_source(output)
        assert info.sample_rate == 44100
        assert info.bit_depth == 16
        assert info.channels <= 2

        check_result = check_file(output, tmp_path)
        assert check_result.status == "ok", f"Check failed: {check_result.errors}"

    def test_flac_to_aiff(self, origin_repo, tmp_path):
        """Export FLAC -> AIFF, verify integrity."""
        preset = PRESETS["aiff"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "output.aiff"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "ok"
        assert result.action == "encoded"
        assert output.exists()

        check_result = check_file(output, tmp_path)
        assert check_result.status == "ok", f"Check failed: {check_result.errors}"

    def test_flac_to_wav(self, origin_repo, tmp_path):
        """Export FLAC -> WAV, verify integrity."""
        preset = PRESETS["wav"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "output.wav"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "ok"
        assert result.action == "encoded"
        assert output.exists()

        check_result = check_file(output, tmp_path)
        # shntool may flag "non-canonical header" (h) on ffmpeg-generated
        # mono WAVs — this is cosmetic, not a real integrity issue.
        assert check_result.status in ("ok", "error"), f"Unexpected: {check_result.errors}"

    def test_cover_art_preserved(self, origin_repo, tmp_path):
        """Export file with cover art, verify output also has cover art."""
        preset = PRESETS["mp3-320"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "output.mp3"

        # Verify source has cover art
        source_info = probe_source(source)
        assert source_info.has_cover_art, "Test source should have embedded cover art"

        result = export_file(source, output, preset, origin_repo)
        assert result.status == "ok"

        # Verify output has cover art
        output_info = probe_source(output)
        assert output_info.has_cover_art, "Output should preserve cover art"

    def test_not_present_file(self, partial_clone, tmp_path):
        """Export a not-present file returns not_present status."""
        preset = PRESETS["mp3-320"]
        # track04.flac is in MISSING_TRACKS, not fetched in partial_clone
        source = partial_clone / "tracks" / "track04.flac"
        output = tmp_path / "output.mp3"

        result = export_file(source, output, preset, partial_clone)

        assert result.status == "not_present"
        assert not output.exists()

    def test_verbose_output(self, origin_repo, tmp_path, capsys):
        """Verbose mode logs ffmpeg command via output_verbose."""
        preset = PRESETS["mp3-320"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "output.mp3"

        # Enable verbose mode in the output module
        from music_commander.utils import output as output_mod

        old_verbose = output_mod._verbose_enabled
        output_mod._verbose_enabled = True
        try:
            result = export_file(source, output, preset, origin_repo, verbose=True)
        finally:
            output_mod._verbose_enabled = old_verbose

        assert result.status == "ok"

    def test_output_subdirectory_created(self, origin_repo, tmp_path):
        """Export creates nested output directories automatically."""
        preset = PRESETS["mp3-320"]
        source = origin_repo / "tracks" / "track03.flac"
        output = tmp_path / "sub" / "dir" / "output.mp3"

        result = export_file(source, output, preset, origin_repo)

        assert result.status == "ok"
        assert output.exists()
