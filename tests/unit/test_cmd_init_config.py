"""Unit tests for the init-config command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from music_commander.commands.init_config import _load_example_config, cli


class TestLoadExampleConfig:
    def test_loads_non_empty_content(self) -> None:
        content = _load_example_config()
        assert len(content) > 0

    def test_contains_all_sections(self) -> None:
        content = _load_example_config()
        for section in (
            "[paths]",
            "[display]",
            "[git_annex]",
            "[checks]",
            "[editors]",
            "[bandcamp]",
            "[anomalistic]",
        ):
            assert section in content, f"Missing section {section}"

    def test_documentation_url_correct(self) -> None:
        content = _load_example_config()
        assert "https://github.com/poelzi/music-commander" in content
        # Ensure the old incorrect URL is not present
        assert "musicCommander" not in content


class TestInitConfigCommand:
    def test_creates_config_file(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["--output", "test-config.toml"], standalone_mode=False)
            assert result.exit_code == 0 or result.exception is None
            assert Path("test-config.toml").exists()
            content = Path("test-config.toml").read_text()
            assert "[paths]" in content

    def test_created_file_matches_example(self) -> None:
        example = _load_example_config()
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["--output", "test-config.toml"], standalone_mode=False)
            content = Path("test-config.toml").read_text()
            assert content == example

    def test_fails_if_exists_without_force(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("test-config.toml").write_text("existing")
            result = runner.invoke(cli, ["--output", "test-config.toml"], standalone_mode=False)
            # Should fail with SystemExit(1)
            assert isinstance(result.exception, SystemExit)
            assert result.exception.code == 1
            # Original content should be preserved
            assert Path("test-config.toml").read_text() == "existing"

    def test_force_overwrites_existing(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            Path("test-config.toml").write_text("old content")
            result = runner.invoke(
                cli, ["--output", "test-config.toml", "--force"], standalone_mode=False
            )
            assert result.exception is None or result.exit_code == 0
            content = Path("test-config.toml").read_text()
            assert "[paths]" in content
            assert "old content" not in content

    def test_creates_parent_directories(self) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["--output", "deep/nested/dir/config.toml"], standalone_mode=False
            )
            assert result.exception is None or result.exit_code == 0
            assert Path("deep/nested/dir/config.toml").exists()

    @patch("music_commander.commands.init_config.get_default_config_path")
    def test_default_path_used_when_no_output(self, mock_path: object) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            from unittest.mock import MagicMock

            mock_path = MagicMock(return_value=Path("default-config.toml"))  # type: ignore[assignment]
            with patch(
                "music_commander.commands.init_config.get_default_config_path", mock_path
            ):
                result = runner.invoke(cli, [], standalone_mode=False)
                assert result.exception is None or result.exit_code == 0
                assert Path("default-config.toml").exists()
