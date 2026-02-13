"""Unit tests for the check-deps command."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from music_commander.commands.check_deps import cli


def test_check_deps_help() -> None:
    """Verify the check-deps command shows help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Check availability" in result.output


@patch("music_commander.commands.check_deps.shutil.which")
def test_check_deps_all_found(mock_which: object) -> None:
    """When all tools are found, exit code should be 0."""
    from unittest.mock import MagicMock

    mock_which = MagicMock(side_effect=lambda name: f"/usr/bin/{name}")  # type: ignore[assignment]
    with patch("music_commander.commands.check_deps.shutil.which", mock_which):
        runner = CliRunner()
        result = runner.invoke(cli, [], standalone_mode=False)
    assert result.exception is None or result.exit_code == 0
    assert "All required tools" in result.output


@patch("music_commander.commands.check_deps.shutil.which")
def test_check_deps_required_missing(mock_which: object) -> None:
    """When a required tool is missing, exit code should be 1."""
    from unittest.mock import MagicMock

    def _which(name: str) -> str | None:
        if name == "git":
            return None
        return f"/usr/bin/{name}"

    mock_which = MagicMock(side_effect=_which)  # type: ignore[assignment]
    with patch("music_commander.commands.check_deps.shutil.which", mock_which):
        runner = CliRunner()
        result = runner.invoke(cli, [], standalone_mode=False)
    assert isinstance(result.exception, SystemExit)
    assert result.exception.code == 1
    assert "MISSING" in result.output or "git" in result.output


@patch("music_commander.commands.check_deps.shutil.which")
def test_check_deps_optional_missing_ok(mock_which: object) -> None:
    """When only optional tools are missing, exit code should be 0."""
    from unittest.mock import MagicMock

    # Required tools found, optional tools (firefox, unrar, etc.) missing
    required_tools = {"git", "git-annex", "ffmpeg", "ffprobe", "shntool", "metaflac"}

    def _which(name: str) -> str | None:
        if name in required_tools:
            return f"/usr/bin/{name}"
        return None

    mock_which = MagicMock(side_effect=_which)  # type: ignore[assignment]
    with patch("music_commander.commands.check_deps.shutil.which", mock_which):
        runner = CliRunner()
        result = runner.invoke(cli, [], standalone_mode=False)
    assert result.exception is None or result.exit_code == 0
    assert "All required tools" in result.output


@patch("music_commander.commands.check_deps.shutil.which")
def test_check_deps_shows_table_content(mock_which: object) -> None:
    """Output should contain tool names and categories."""
    from unittest.mock import MagicMock

    mock_which = MagicMock(return_value="/usr/bin/tool")  # type: ignore[assignment]
    with patch("music_commander.commands.check_deps.shutil.which", mock_which):
        runner = CliRunner()
        result = runner.invoke(cli, [], standalone_mode=False)
    # Check some expected tool names appear in output
    assert "git" in result.output
    assert "ffmpeg" in result.output
    assert "shntool" in result.output
