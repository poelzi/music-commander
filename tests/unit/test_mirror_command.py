"""Tests for the mirror CLI command group and anomalistic subcommand."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import click
from click.testing import CliRunner

from music_commander.cli import Context
from music_commander.commands.mirror import cli as mirror_cli


def _make_context(tmp_path, **config_overrides):
    """Create a real Context with a mock config."""
    config = MagicMock()
    config.music_repo = tmp_path / "repo"
    config.music_repo.mkdir(exist_ok=True)
    config.anomalistic_output_dir = tmp_path / "output"
    config.anomalistic_format = "flac"
    config.anomalistic_download_source = "wav"
    config.anomalistic_output_pattern = "{{artist}} - {{album}}"
    for k, v in config_overrides.items():
        setattr(config, k, v)
    ctx = Context()
    ctx.config = config
    return ctx


class TestMirrorGroup:
    """Tests for the mirror command group registration."""

    def test_mirror_is_click_group(self):
        assert isinstance(mirror_cli, click.Group)

    def test_mirror_group_name(self):
        assert mirror_cli.name == "mirror"

    def test_anomalistic_is_subcommand(self):
        assert "anomalistic" in mirror_cli.commands

    def test_mirror_help(self):
        runner = CliRunner()
        result = runner.invoke(mirror_cli, ["--help"])
        assert result.exit_code == 0
        assert "Mirror releases from external music portals" in result.output
        assert "anomalistic" in result.output

    def test_anomalistic_help(self):
        runner = CliRunner()
        result = runner.invoke(mirror_cli, ["anomalistic", "--help"])
        assert result.exit_code == 0
        assert "Mirror releases from the Anomalistic Dark Psy Portal" in result.output
        assert "--force" in result.output


class TestMirrorAutoDiscovery:
    """Tests for CLI auto-discovery of the mirror command."""

    def test_mirror_module_exports_cli(self):
        """The mirror __init__.py should export a 'cli' attribute."""
        from music_commander.commands import mirror

        assert hasattr(mirror, "cli")
        assert isinstance(mirror.cli, click.Group)


class TestAnomaListicCommand:
    """Tests for the anomalistic mirror command with mocked dependencies."""

    @patch("music_commander.commands.mirror.anomalistic.get_cache_session")
    @patch("music_commander.commands.mirror.anomalistic.AnomaListicClient")
    def test_no_releases(self, mock_client_cls, mock_cache, tmp_path):
        """When no releases found, should exit cleanly."""
        mock_client = MagicMock()
        mock_client.fetch_categories.return_value = []
        mock_client.iter_releases.return_value = iter([])
        mock_client_cls.return_value = mock_client

        mock_session = MagicMock()
        mock_cache.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cache.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic"],
            obj=_make_context(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Found 0 releases" in result.output

    @patch("music_commander.commands.mirror.anomalistic.get_cache_session")
    @patch("music_commander.commands.mirror.anomalistic.AnomaListicClient")
    def test_force_flag_skips_dedup(self, mock_client_cls, mock_cache, tmp_path):
        """When --force is used, dedup should not be called."""
        mock_client = MagicMock()
        mock_client.fetch_categories.return_value = []
        mock_client.iter_releases.return_value = iter([])
        mock_client_cls.return_value = mock_client

        mock_session = MagicMock()
        mock_cache.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cache.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic", "--force"],
            obj=_make_context(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0

    @patch("music_commander.commands.mirror.anomalistic.get_cache_session")
    @patch("music_commander.commands.mirror.anomalistic.load_local_albums")
    @patch("music_commander.commands.mirror.anomalistic.check_duplicate")
    @patch("music_commander.commands.mirror.anomalistic.AnomaListicClient")
    def test_skipped_release(self, mock_client_cls, mock_dedup, mock_load, mock_cache, tmp_path):
        """A release that matches dedup should be skipped."""
        mock_client = MagicMock()
        mock_client.fetch_categories.return_value = []
        post = {
            "id": 1,
            "title": {"rendered": "XianZai &#8211; Irrational Conjunction"},
            "content": {"rendered": "<p>Content</p>"},
            "date": "2023-05-09T00:00:00",
            "link": "https://portal.example.com/release-1",
            "categories": [],
        }
        mock_client.iter_releases.return_value = iter([post])
        mock_client_cls.return_value = mock_client

        mock_load.return_value = []

        from music_commander.anomalistic.dedup import DedupResult

        mock_dedup.return_value = DedupResult(should_skip=True, reason="cached")

        mock_session = MagicMock()
        mock_cache.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cache.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic"],
            obj=_make_context(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Skipped:    1" in result.output

    @patch("music_commander.commands.mirror.anomalistic.get_cache_session")
    @patch("music_commander.commands.mirror.anomalistic.load_local_albums")
    @patch("music_commander.commands.mirror.anomalistic.check_duplicate")
    @patch("music_commander.commands.mirror.anomalistic.write_meta_json")
    @patch("music_commander.commands.mirror.anomalistic.convert_release")
    @patch("music_commander.commands.mirror.anomalistic.discover_audio_files")
    @patch("music_commander.commands.mirror.anomalistic.extract_archive")
    @patch("music_commander.commands.mirror.anomalistic.download_archive")
    @patch("music_commander.commands.mirror.anomalistic.AnomaListicClient")
    def test_successful_download(
        self,
        mock_client_cls,
        mock_download,
        mock_extract,
        mock_discover,
        mock_convert,
        mock_meta,
        mock_dedup,
        mock_load,
        mock_cache,
        tmp_path,
    ):
        """Full successful download of a single release."""
        mock_client = MagicMock()
        mock_client.fetch_categories.return_value = []
        post = {
            "id": 42,
            "title": {"rendered": "XianZai &#8211; Irrational Conjunction"},
            "content": {
                "rendered": '<p><a href="https://www.anomalisticrecords.com/dl/WAV.zip">WAV</a></p>'
            },
            "date": "2023-05-09T00:00:00",
            "link": "https://portal.example.com/release-1",
            "categories": [],
        }
        mock_client.iter_releases.return_value = iter([post])
        mock_client_cls.return_value = mock_client

        mock_load.return_value = []

        from music_commander.anomalistic.dedup import DedupResult

        mock_dedup.return_value = DedupResult(should_skip=False)

        mock_download.return_value = tmp_path / "archive.zip"
        mock_extract.return_value = tmp_path / "extracted"

        audio_file = tmp_path / "track.wav"
        audio_file.write_bytes(b"fake")
        mock_discover.return_value = [audio_file]

        converted_file = tmp_path / "output" / "track.flac"
        mock_convert.return_value = [converted_file]
        mock_meta.return_value = tmp_path / "output" / "meta.json"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_cache.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cache.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic"],
            obj=_make_context(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Downloaded: 1" in result.output
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called()

    @patch("music_commander.commands.mirror.anomalistic.get_cache_session")
    @patch("music_commander.commands.mirror.anomalistic.load_local_albums")
    @patch("music_commander.commands.mirror.anomalistic.check_duplicate")
    @patch("music_commander.commands.mirror.anomalistic.write_meta_json")
    @patch("music_commander.commands.mirror.anomalistic.convert_release")
    @patch("music_commander.commands.mirror.anomalistic.discover_audio_files")
    @patch("music_commander.commands.mirror.anomalistic.extract_archive")
    @patch("music_commander.commands.mirror.anomalistic.download_archive")
    @patch("music_commander.commands.mirror.anomalistic.AnomaListicClient")
    def test_download_passes_progress_callback(
        self,
        mock_client_cls,
        mock_download,
        mock_extract,
        mock_discover,
        mock_convert,
        mock_meta,
        mock_dedup,
        mock_load,
        mock_cache,
        tmp_path,
    ):
        """download_archive should be called with a progress_callback."""
        mock_client = MagicMock()
        mock_client.fetch_categories.return_value = []
        post = {
            "id": 99,
            "title": {"rendered": "TestArtist &#8211; TestAlbum"},
            "content": {
                "rendered": '<p><a href="https://www.anomalisticrecords.com/dl/WAV.zip">WAV</a></p>'
            },
            "date": "2024-01-01T00:00:00",
            "link": "https://portal.example.com/release-99",
            "categories": [],
        }
        mock_client.iter_releases.return_value = iter([post])
        mock_client_cls.return_value = mock_client

        mock_load.return_value = []

        from music_commander.anomalistic.dedup import DedupResult

        mock_dedup.return_value = DedupResult(should_skip=False)

        mock_download.return_value = tmp_path / "archive.zip"
        mock_extract.return_value = tmp_path / "extracted"

        audio_file = tmp_path / "track.wav"
        audio_file.write_bytes(b"fake")
        mock_discover.return_value = [audio_file]
        mock_convert.return_value = [tmp_path / "output" / "track.flac"]

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_cache.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cache.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic"],
            obj=_make_context(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 0

        # Verify download_archive was called with a progress_callback
        mock_download.assert_called_once()
        call_kwargs = mock_download.call_args
        assert "progress_callback" in call_kwargs.kwargs
        assert callable(call_kwargs.kwargs["progress_callback"])

    def test_invalid_format_preset(self, tmp_path):
        """Unknown format preset should error out."""
        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic"],
            obj=_make_context(tmp_path, anomalistic_format="invalid-format"),
            catch_exceptions=False,
        )
        assert result.exit_code == 1
        assert "Unknown format preset" in result.output

    @patch("music_commander.commands.mirror.anomalistic.AnomaListicClient")
    def test_category_fetch_failure(self, mock_client_cls, tmp_path):
        """Failed category fetch should exit with error."""
        mock_client = MagicMock()
        mock_client.fetch_categories.side_effect = Exception("Connection refused")
        mock_client_cls.return_value = mock_client

        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic"],
            obj=_make_context(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 1
        assert "Failed to fetch categories" in result.output

    @patch("music_commander.commands.mirror.anomalistic.get_cache_session")
    @patch("music_commander.commands.mirror.anomalistic.load_local_albums")
    @patch("music_commander.commands.mirror.anomalistic.check_duplicate")
    @patch("music_commander.commands.mirror.anomalistic.AnomaListicClient")
    def test_no_download_url(self, mock_client_cls, mock_dedup, mock_load, mock_cache, tmp_path):
        """Release with no download URL should be counted as failed."""
        mock_client = MagicMock()
        mock_client.fetch_categories.return_value = []
        post = {
            "id": 1,
            "title": {"rendered": "Artist - Album"},
            "content": {"rendered": "<p>No links here</p>"},
            "date": "2023-01-01T00:00:00",
            "link": "https://portal.example.com/no-download",
            "categories": [],
        }
        mock_client.iter_releases.return_value = iter([post])
        mock_client_cls.return_value = mock_client

        mock_load.return_value = []

        from music_commander.anomalistic.dedup import DedupResult

        mock_dedup.return_value = DedupResult(should_skip=False)

        mock_session = MagicMock()
        mock_cache.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_cache.return_value.__exit__ = MagicMock(return_value=False)

        runner = CliRunner()
        result = runner.invoke(
            mirror_cli,
            ["anomalistic"],
            obj=_make_context(tmp_path),
            catch_exceptions=False,
        )
        assert result.exit_code == 1
        assert "Failed:     1" in result.output
