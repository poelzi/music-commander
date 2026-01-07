"""Integration tests for get-commit-files command."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from music_commander.cli import cli
from music_commander.config import Config


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


def test_help(runner: CliRunner) -> None:
    """Test --help works."""
    result = runner.invoke(cli, ["get-commit-files", "--help"])
    assert result.exit_code == 0
    assert "REVISION" in result.output


def test_dry_run(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test --dry-run shows files without fetching."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        result = runner.invoke(cli, ["get-commit-files", "--dry-run", "HEAD"])
        assert result.exit_code == 0
        # Either shows files to fetch, or indicates no files/annexed files found
        assert (
            "Would fetch" in result.output
            or "No annexed files" in result.output
            or "No files changed" in result.output
        )


def test_invalid_revision(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test invalid revision returns exit code 2."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        result = runner.invoke(cli, ["get-commit-files", "nonexistent-branch-xyz"])
        assert result.exit_code == 2
        assert "Invalid revision" in result.output


def test_not_annex_repo(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test non-annex repo returns exit code 3."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = temp_dir
        mock_load.return_value = (mock_config, [])

        result = runner.invoke(cli, ["get-commit-files", "HEAD"])
        assert result.exit_code == 3
