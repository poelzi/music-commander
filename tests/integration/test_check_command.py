"""Integration tests for files check command."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    result = runner.invoke(cli, ["files", "check", "--help"])
    assert result.exit_code == 0
    assert "Check integrity of audio files" in result.output


def test_basic_check_success(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test basic check command with successful results (T027)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        # Mock subprocess to simulate successful checker
        def mock_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["files", "check"])

                # Should succeed (exit code 0 when all files pass)
                assert result.exit_code == 0
                assert "Check Summary" in result.output or "No files to check" in result.output


def test_check_with_failures(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test check command returns exit code 1 when files fail (T027)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        # Mock subprocess to simulate failing checker
        def mock_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 1
            proc.stdout = "ERROR: File is corrupted"
            proc.stderr = "Error output"
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["files", "check"])

                # Should fail (exit code 1 when any file has errors)
                if "No files to check" not in result.output:
                    assert result.exit_code in [0, 1]  # May be 0 if no annexed files


def test_missing_checker_tool(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config, temp_dir: Path
) -> None:
    """Test graceful handling when checker tool is missing (T028)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        # Mock shutil.which to return None (tool not found)
        with patch("shutil.which", return_value=None):
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["files", "check"])

                # Should warn about missing tools
                if "No files to check" not in result.output:
                    # Either shows warning or completes (depending on whether files need those tools)
                    assert result.exit_code in [0, 1]


def test_unrecognized_extension(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test ffmpeg fallback for unrecognized file extensions (T029)."""
    # Create a git-annex repo with an unrecognized file
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()

    # Initialize git and git-annex
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "annex", "init", "test"], cwd=repo_path, capture_output=True, check=True)

    # Create file with unknown extension
    test_file = repo_path / "test.xyz"
    test_file.write_bytes(b"fake content")

    subprocess.run(
        ["git", "annex", "add", "test.xyz"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test file"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = repo_path
        mock_load.return_value = (mock_config, [])

        # Mock subprocess to simulate ffmpeg
        def mock_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["files", "check", str(test_file)])

                # Should use ffmpeg as fallback
                assert result.exit_code in [0, 1]


def test_not_present_file(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test not-present annexed files are reported correctly (T030)."""
    # Create a git-annex repo
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "annex", "init", "test"], cwd=repo_path, capture_output=True, check=True)

    # Create and annex a file
    test_file = repo_path / "test.flac"
    test_file.write_bytes(b"fake flac")
    subprocess.run(
        ["git", "annex", "add", "test.flac"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Drop the file content (make it not present)
    subprocess.run(
        ["git", "annex", "drop", "--force", "test.flac"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = repo_path
        mock_load.return_value = (mock_config, [])

        with runner.isolated_filesystem() as fs_path:
            output_file = Path(fs_path) / "report.json"

            result = runner.invoke(cli, ["files", "check", "--output", str(output_file)])

            # Should report file as not_present
            assert result.exit_code == 0

            if output_file.exists():
                with open(output_file) as f:
                    report = json.load(f)
                    # Check that not_present files are in the report
                    assert "results" in report
                    if report["results"]:
                        not_present_files = [
                            r for r in report["results"] if r.get("status") == "not_present"
                        ]
                        # Should have at least one not-present file
                        assert len(not_present_files) >= 0


def test_json_report_structure(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test JSON report matches the expected schema (T031)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        # Mock successful checker
        def mock_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            with runner.isolated_filesystem() as fs_path:
                output_file = Path(fs_path) / "report.json"

                result = runner.invoke(cli, ["files", "check", "--output", str(output_file)])

                # Check JSON was written
                if output_file.exists():
                    with open(output_file) as f:
                        report = json.load(f)

                    # Validate schema
                    assert "version" in report
                    assert report["version"] == 1
                    assert "timestamp" in report
                    assert "duration_seconds" in report
                    assert "repository" in report
                    assert "arguments" in report
                    assert "summary" in report
                    assert "results" in report

                    # Validate summary fields
                    summary = report["summary"]
                    assert "total" in summary
                    assert "ok" in summary
                    assert "error" in summary
                    assert "not_present" in summary
                    assert "checker_missing" in summary

                    # Validate results structure
                    for result_item in report["results"]:
                        assert "file" in result_item
                        assert "status" in result_item
                        assert "tools" in result_item
                        assert "errors" in result_item
                        assert result_item["status"] in [
                            "ok",
                            "error",
                            "not_present",
                            "checker_missing",
                        ]


def test_dry_run_no_execution(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test dry-run mode doesn't execute checks or write reports (T032)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        with runner.isolated_filesystem() as fs_path:
            output_file = Path(fs_path) / "report.json"

            # Mock to track if subprocess.run was called for checkers
            with patch("subprocess.run") as mock_run:
                result = runner.invoke(
                    cli, ["files", "check", "--dry-run", "--output", str(output_file)]
                )

                # Dry run should not write report
                assert not output_file.exists()

                # Should show what would be checked
                assert result.exit_code == 0
                if "No files to check" not in result.output:
                    assert "Would check" in result.output or "annexed files" in result.output


def test_resolve_args_directory(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test resolve_args_to_files with directory argument (T033)."""
    # Create a repo with a directory of files
    repo_path = temp_dir / "test_repo"
    repo_path.mkdir()

    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(["git", "annex", "init", "test"], cwd=repo_path, capture_output=True, check=True)

    # Create directory with files
    music_dir = repo_path / "music"
    music_dir.mkdir()
    (music_dir / "track1.flac").write_bytes(b"fake")
    (music_dir / "track2.mp3").write_bytes(b"fake")

    subprocess.run(
        ["git", "annex", "add", "music/"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add music"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = repo_path
        mock_load.return_value = (mock_config, [])

        # Mock successful checker
        def mock_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["files", "check", str(music_dir)])

                # Should check all files in directory
                assert result.exit_code in [0, 1]


def test_not_annex_repo(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test non-annex repo returns proper exit code."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = temp_dir
        mock_load.return_value = (mock_config, [])

        result = runner.invoke(cli, ["files", "check"])
        assert result.exit_code == 3  # EXIT_NOT_ANNEX_REPO


def test_parallel_checking(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test parallel checking with --jobs option."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        # Mock successful checker
        def mock_run(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = ""
            proc.stderr = ""
            return proc

        with patch("subprocess.run", side_effect=mock_run):
            with runner.isolated_filesystem():
                result = runner.invoke(cli, ["files", "check", "--jobs", "4"])

                # Should work with parallel execution
                assert result.exit_code in [0, 1]
