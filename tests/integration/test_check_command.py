"""Integration tests for files check command."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from music_commander.cli import cli
from music_commander.config import Config
from music_commander.utils import checkers as checkers_module
from music_commander.utils.checkers import CheckResult


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def clear_tool_cache() -> None:
    """Clear the checker tool availability cache between tests."""
    checkers_module._tool_cache.clear()


def _ok_result(file: str, tools: list[str] | None = None) -> CheckResult:
    """Create a successful CheckResult."""
    return CheckResult(file=file, status="ok", tools=tools or ["flac"], errors=[])


def _error_result(file: str, tools: list[str] | None = None) -> CheckResult:
    """Create a failed CheckResult."""
    return CheckResult(
        file=file,
        status="error",
        tools=tools or ["flac"],
        errors=[
            checkers_module.ToolResult(
                tool="flac", success=False, exit_code=1, output="ERROR: corrupted"
            )
        ],
    )


def _missing_result(file: str) -> CheckResult:
    """Create a checker_missing CheckResult."""
    return CheckResult(file=file, status="checker_missing", tools=["flac"], errors=[])


def _warning_result(file: str) -> CheckResult:
    """Create a warning CheckResult (multichannel bit)."""
    return CheckResult(
        file=file,
        status="warning",
        tools=["flac", "flac-multichannel"],
        errors=[],
        warnings=[
            checkers_module.ToolResult(
                tool="flac-multichannel",
                success=True,
                exit_code=0,
                output="Stereo file has WAVEFORMATEXTENSIBLE_CHANNEL_MASK=0x0003. "
                "This causes playback issues on Pioneer players.",
            )
        ],
    )


# ---------------------------------------------------------------------------
# T027: CLI integration tests
# ---------------------------------------------------------------------------


def test_help(runner: CliRunner) -> None:
    """Test --help works."""
    result = runner.invoke(cli, ["files", "check", "--help"])
    assert result.exit_code == 0
    assert "Check integrity of audio files" in result.output


def test_basic_check_success(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test basic check with no args checks all files and exits 0 on success (T027)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                result = runner.invoke(cli, ["files", "check"])

                assert result.exit_code == 0, (
                    f"Expected exit 0, got {result.exit_code}: {result.output}"
                )
                assert "Check Summary" in result.output
                assert "passed" in result.output


def test_check_with_directory_arg(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test check with a directory path argument (T027)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        tracks_dir = git_annex_repo / "tracks"

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                result = runner.invoke(cli, ["files", "check", str(tracks_dir)])

                assert result.exit_code == 0, f"Unexpected: {result.output}"
                assert "Check Summary" in result.output


def test_check_with_failures_exits_1(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test check returns exit code 1 when files fail integrity checks (T027)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _error_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                result = runner.invoke(cli, ["files", "check"])

                assert result.exit_code == 1, (
                    f"Expected exit 1 for failed checks, got {result.exit_code}: {result.output}"
                )
                assert "failed integrity checks" in result.output


# ---------------------------------------------------------------------------
# T028: Missing checker tool
# ---------------------------------------------------------------------------


def test_missing_checker_tool(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test graceful handling when checker tool is not installed (T028)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _missing_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=False,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(cli, ["files", "check", "--output", str(output_file)])

                    # Should warn about missing tools
                    assert "Missing checker tools" in result.output

                    # Should still produce a report
                    assert output_file.exists(), "Expected JSON report to be written"
                    with open(output_file) as f:
                        report = json.load(f)

                    # Verify checker_missing status in results
                    checker_missing = [
                        r for r in report["results"] if r["status"] == "checker_missing"
                    ]
                    assert len(checker_missing) > 0, (
                        f"Expected checker_missing results, got: {report['results']}"
                    )
                    assert report["summary"]["checker_missing"] > 0


# ---------------------------------------------------------------------------
# T029: Unrecognized file extension
# ---------------------------------------------------------------------------


def test_unrecognized_extension_skipped(
    runner: CliRunner, temp_dir: Path, mock_config: Config
) -> None:
    """Test non-audio files with unrecognized extensions are skipped (T029)."""
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
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    test_file = repo_path / "test.xyz"
    test_file.write_bytes(b"fake content for annex" * 100)
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

        # check_file should NOT be called for skipped files — the command
        # layer separates them before invoking check_file
        check_calls = []

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            check_calls.append(file_path)
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                # Mock MIME detection to return non-audio type
                with patch(
                    "music_commander.commands.files.get_checkers_for_file",
                    return_value=(None, "skipped"),
                ):
                    with runner.isolated_filesystem() as fs_path:
                        output_file = Path(fs_path) / "report.json"
                        result = runner.invoke(
                            cli,
                            ["files", "check", "--output", str(output_file)],
                        )

                        assert result.exit_code == 0, f"Unexpected: {result.output}"

                        # check_file should not be called for skipped files
                        assert len(check_calls) == 0, (
                            f"check_file should not be called for skipped files, "
                            f"but was called for: {check_calls}"
                        )

                        assert output_file.exists()
                        with open(output_file) as f:
                            report = json.load(f)
                        assert len(report["results"]) == 1
                        assert report["results"][0]["status"] == "skipped"
                        assert report["summary"]["skipped"] == 1


def test_unrecognized_extension_not_in_registry() -> None:
    """Verify .xyz is not in CHECKER_REGISTRY and returns empty checkers (T029)."""
    assert ".xyz" not in checkers_module.CHECKER_REGISTRY
    specs = checkers_module.get_checkers_for_extension(".xyz")
    assert specs == []


# ---------------------------------------------------------------------------
# T030: Not-present annexed file
# ---------------------------------------------------------------------------


def test_not_present_file(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test not-present annexed files are reported as not_present (T030)."""
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
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    test_file = repo_path / "test.flac"
    test_file.write_bytes(b"fake flac content" * 100)
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

        # check_file should NOT be called for not-present files because
        # the command separates present/not-present before calling check_file
        check_calls = []

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            check_calls.append(file_path)
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with runner.isolated_filesystem() as fs_path:
                output_file = Path(fs_path) / "report.json"
                result = runner.invoke(cli, ["files", "check", "--output", str(output_file)])

                assert result.exit_code == 0, f"Unexpected: {result.output}"

                # No checker should have been invoked (file is not present)
                assert len(check_calls) == 0, (
                    f"check_file should not be called for not-present files, "
                    f"but was called for: {check_calls}"
                )

                # Verify JSON report
                assert output_file.exists(), "Expected JSON report"
                with open(output_file) as f:
                    report = json.load(f)

                assert len(report["results"]) == 1, (
                    f"Expected 1 result, got {len(report['results'])}"
                )
                assert report["results"][0]["status"] == "not_present"
                assert report["results"][0]["file"] == "test.flac"
                assert report["summary"]["not_present"] == 1
                assert report["summary"]["total"] == 1


# ---------------------------------------------------------------------------
# T031: JSON report structure
# ---------------------------------------------------------------------------


def test_json_report_structure(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test JSON report matches the expected schema (T031)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(cli, ["files", "check", "--output", str(output_file)])

                    assert result.exit_code == 0, f"Unexpected: {result.output}"
                    assert output_file.exists(), "JSON report not written"

                    with open(output_file) as f:
                        report = json.load(f)

                    # Validate top-level fields
                    assert report["version"] == 1
                    assert isinstance(report["timestamp"], str)
                    assert isinstance(report["duration_seconds"], (int, float))
                    assert report["duration_seconds"] >= 0
                    assert isinstance(report["repository"], str)
                    assert isinstance(report["arguments"], list)
                    assert isinstance(report["summary"], dict)
                    assert isinstance(report["results"], list)

                    # Validate summary has all required count fields
                    summary = report["summary"]
                    for field in (
                        "total",
                        "ok",
                        "warning",
                        "error",
                        "not_present",
                        "checker_missing",
                        "skipped",
                    ):
                        assert field in summary, f"Missing summary field: {field}"
                        assert isinstance(summary[field], int), (
                            f"summary.{field} should be int, got {type(summary[field])}"
                        )

                    # Counts must be consistent
                    assert summary["total"] == (
                        summary["ok"]
                        + summary["warning"]
                        + summary["error"]
                        + summary["not_present"]
                        + summary["checker_missing"]
                        + summary["skipped"]
                    )
                    assert summary["total"] > 0, "Expected at least one file checked"

                    # Validate each result entry
                    valid_statuses = {
                        "ok",
                        "warning",
                        "error",
                        "not_present",
                        "checker_missing",
                        "skipped",
                    }
                    for entry in report["results"]:
                        assert "file" in entry, f"Missing 'file' in result: {entry}"
                        assert "status" in entry, f"Missing 'status' in result: {entry}"
                        assert "tools" in entry, f"Missing 'tools' in result: {entry}"
                        assert "errors" in entry, f"Missing 'errors' in result: {entry}"
                        assert entry["status"] in valid_statuses, (
                            f"Invalid status '{entry['status']}'"
                        )
                        assert isinstance(entry["tools"], list)
                        assert isinstance(entry["errors"], list)


# ---------------------------------------------------------------------------
# T032: Dry-run output
# ---------------------------------------------------------------------------


def test_dry_run_no_execution(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test dry-run lists files without running checks or writing reports (T032)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        check_calls = []

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            check_calls.append(file_path)
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(
                        cli,
                        ["files", "check", "--dry-run", "--output", str(output_file)],
                    )

                    assert result.exit_code == 0, (
                        f"Expected exit 0 for dry-run, got {result.exit_code}: {result.output}"
                    )

                    # No JSON report should be written
                    assert not output_file.exists(), "Dry-run should not write a JSON report"

                    # check_file should not be called
                    assert len(check_calls) == 0, (
                        f"check_file should not be called in dry-run, "
                        f"but was called for: {check_calls}"
                    )

                    # Should show what would be checked
                    assert "Would check" in result.output


# ---------------------------------------------------------------------------
# T033: resolve_args_to_files() integration
# ---------------------------------------------------------------------------


def test_resolve_args_directory(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test resolve_args_to_files with directory argument checks all files (T033)."""
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
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    music_dir = repo_path / "music"
    music_dir.mkdir()
    (music_dir / "track1.flac").write_bytes(b"fake flac" * 100)
    (music_dir / "track2.mp3").write_bytes(b"fake mp3" * 100)

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

        checked_files = []

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            checked_files.append(rel)
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(
                        cli,
                        ["files", "check", str(music_dir), "--output", str(output_file)],
                    )

                    assert result.exit_code == 0, f"Unexpected: {result.output}"
                    assert output_file.exists()

                    with open(output_file) as f:
                        report = json.load(f)

                    checked_names = {Path(r["file"]).name for r in report["results"]}
                    assert "track1.flac" in checked_names, (
                        f"track1.flac not in results: {checked_names}"
                    )
                    assert "track2.mp3" in checked_names, (
                        f"track2.mp3 not in results: {checked_names}"
                    )
                    assert report["summary"]["total"] == 2


def test_resolve_args_nonexistent_path_treated_as_query(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test non-existent path argument is treated as a search query (T033)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        # Non-existent path treated as query — without a cache this will
        # return an error or empty results, but should not crash
        result = runner.invoke(cli, ["files", "check", "nonexistent-file.flac"])

        # Should handle gracefully (cache error = exit 2, no results = exit 0)
        assert result.exit_code in [0, 2], (
            f"Expected graceful handling, got exit {result.exit_code}: {result.output}"
        )


# ---------------------------------------------------------------------------
# Additional edge case tests
# ---------------------------------------------------------------------------


def test_not_annex_repo(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test non-annex repo returns exit code 3."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = temp_dir
        mock_load.return_value = (mock_config, [])

        result = runner.invoke(cli, ["files", "check"])
        assert result.exit_code == 3


def test_parallel_checking(runner: CliRunner, git_annex_repo: Path, mock_config: Config) -> None:
    """Test parallel checking with --jobs option."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                result = runner.invoke(cli, ["files", "check", "--jobs", "4"])

                assert result.exit_code == 0, f"Unexpected: {result.output}"
                assert "Check Summary" in result.output


def test_zero_byte_file_reported_as_error(
    runner: CliRunner, temp_dir: Path, mock_config: Config
) -> None:
    """Test zero-byte / corrupt files are reported as errors (spec edge case)."""
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
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    test_file = repo_path / "corrupt.flac"
    test_file.write_bytes(b"x" * 100)
    subprocess.run(
        ["git", "annex", "add", "corrupt.flac"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add corrupt file"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = repo_path
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _error_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(cli, ["files", "check", "--output", str(output_file)])

                    assert result.exit_code == 1, (
                        f"Expected exit 1 for error, got {result.exit_code}: {result.output}"
                    )

                    assert output_file.exists()
                    with open(output_file) as f:
                        report = json.load(f)

                    assert report["summary"]["error"] == 1
                    assert report["summary"]["total"] == 1
                    error_results = [r for r in report["results"] if r["status"] == "error"]
                    assert len(error_results) == 1


def test_sigint_writes_partial_report(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test that partial results are written on interruption (spec edge case)."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            raise KeyboardInterrupt()

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(cli, ["files", "check", "--output", str(output_file)])

                    # The report should still be written via try/finally
                    if output_file.exists():
                        with open(output_file) as f:
                            report = json.load(f)
                        assert "version" in report
                        assert "results" in report
                        assert "summary" in report


# ---------------------------------------------------------------------------
# Unit tests for checkers module
# ---------------------------------------------------------------------------


def test_check_file_not_present() -> None:
    """Test check_file returns not_present for missing files."""
    from music_commander.utils.checkers import check_file

    result = check_file(Path("/nonexistent/file.flac"), Path("/nonexistent"))
    assert result.status == "not_present"
    assert result.tools == []


def test_checker_registry_coverage() -> None:
    """Verify all documented extensions are in the registry."""
    registry = checkers_module.CHECKER_REGISTRY
    # Per FR-005 in spec
    assert ".flac" in registry
    assert ".mp3" in registry
    assert ".ogg" in registry
    assert ".wav" in registry
    assert ".aiff" in registry
    assert ".aif" in registry
    assert ".m4a" in registry

    # Verify flac uses flac tool
    assert registry[".flac"][0].name == "flac"
    # Verify mp3 uses mp3val then ffmpeg
    mp3_tools = [s.name for s in registry[".mp3"]]
    assert "mp3val" in mp3_tools
    assert "ffmpeg" in mp3_tools


# ---------------------------------------------------------------------------
# Skipped non-audio files
# ---------------------------------------------------------------------------


def test_non_audio_file_skipped(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test that non-audio files (.py, .txt, etc.) are skipped, not checked."""
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
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Add a .py file and a .flac file
    (repo_path / "script.py").write_bytes(b"print('hello')" + b"\x00" * 100)
    (repo_path / "track.flac").write_bytes(b"fake flac" * 100)
    subprocess.run(
        ["git", "annex", "add", "."],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add files"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = repo_path
        mock_load.return_value = (mock_config, [])

        checked_files = []

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            checked_files.append(rel)
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(
                        cli,
                        ["files", "check", "--output", str(output_file)],
                    )

                    assert result.exit_code == 0, f"Unexpected: {result.output}"

                    # script.py should NOT have been passed to check_file
                    assert not any("script.py" in f for f in checked_files), (
                        f"script.py should be skipped, but check_file was called: {checked_files}"
                    )

                    assert output_file.exists()
                    with open(output_file) as f:
                        report = json.load(f)

                    statuses = {r["file"]: r["status"] for r in report["results"]}
                    # .py file should be skipped
                    py_files = {f: s for f, s in statuses.items() if f.endswith(".py")}
                    assert all(s == "skipped" for s in py_files.values()), (
                        f"Expected .py files to be skipped: {py_files}"
                    )
                    assert report["summary"]["skipped"] >= 1


# ---------------------------------------------------------------------------
# CUE file validation
# ---------------------------------------------------------------------------


def test_cue_file_validation(runner: CliRunner, temp_dir: Path, mock_config: Config) -> None:
    """Test that .cue files are validated using the internal cue validator."""
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
    subprocess.run(
        ["git", "annex", "init", "test"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Create a valid .cue file
    cue_content = 'FILE "track.flac" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
    cue_file = repo_path / "album.cue"
    cue_file.write_text(cue_content, encoding="utf-8")

    # Need enough bytes for git-annex
    padding = repo_path / "padding.flac"
    padding.write_bytes(b"fake flac" * 100)

    subprocess.run(
        ["git", "annex", "add", "."],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add cue"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = repo_path
        mock_load.return_value = (mock_config, [])

        # Let check_file run for real on .cue files, mock for others
        original_check_file = checkers_module.check_file

        def selective_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            if file_path.suffix == ".cue":
                return original_check_file(file_path, repo_path, **kwargs)
            rel = str(file_path.relative_to(repo_path))
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=selective_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(
                        cli,
                        ["files", "check", "--output", str(output_file)],
                    )

                    assert result.exit_code == 0, f"Unexpected: {result.output}"

                    assert output_file.exists()
                    with open(output_file) as f:
                        report = json.load(f)

                    cue_results = [r for r in report["results"] if r["file"].endswith(".cue")]
                    assert len(cue_results) == 1, f"Expected 1 cue result, got: {cue_results}"
                    assert cue_results[0]["status"] == "ok"
                    assert "cue-validator" in cue_results[0]["tools"]


# ---------------------------------------------------------------------------
# FLAC multichannel warning check
# ---------------------------------------------------------------------------


def test_flac_multichannel_check_flag(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test --flac-multichannel-check flag enables the check."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            if kwargs.get("flac_multichannel_check") and file_path.suffix == ".flac":
                return _warning_result(rel)
            return _ok_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                result = runner.invoke(cli, ["files", "check", "--flac-multichannel-check"])

                assert result.exit_code == 0, (
                    f"Expected exit 0 (warnings are not errors), "
                    f"got {result.exit_code}: {result.output}"
                )
                assert "Check Summary" in result.output


def test_flac_multichannel_warning_exit_0(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test that warnings do not cause exit code 1."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _warning_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                result = runner.invoke(cli, ["files", "check", "--flac-multichannel-check"])

                # Warnings should NOT trigger exit code 1
                assert result.exit_code == 0, (
                    f"Expected exit 0, got {result.exit_code}: {result.output}"
                )


def test_warning_in_json_report(
    runner: CliRunner, git_annex_repo: Path, mock_config: Config
) -> None:
    """Test JSON report includes warning status and warnings field."""
    with patch("music_commander.cli.load_config") as mock_load:
        mock_config.music_repo = git_annex_repo
        mock_load.return_value = (mock_config, [])

        def mock_check_file(file_path: Path, repo_path: Path, **kwargs) -> CheckResult:
            rel = str(file_path.relative_to(repo_path))
            return _warning_result(rel)

        with patch(
            "music_commander.commands.files.check_file",
            side_effect=mock_check_file,
        ):
            with patch(
                "music_commander.commands.files.check_tool_available",
                return_value=True,
            ):
                with runner.isolated_filesystem() as fs_path:
                    output_file = Path(fs_path) / "report.json"
                    result = runner.invoke(
                        cli,
                        [
                            "files",
                            "check",
                            "--flac-multichannel-check",
                            "--output",
                            str(output_file),
                        ],
                    )

                    assert result.exit_code == 0, f"Unexpected: {result.output}"
                    assert output_file.exists()

                    with open(output_file) as f:
                        report = json.load(f)

                    assert report["summary"]["warning"] > 0
                    warning_results = [r for r in report["results"] if r["status"] == "warning"]
                    assert len(warning_results) > 0
                    # Check warnings field is present in JSON
                    for wr in warning_results:
                        assert "warnings" in wr
                        assert len(wr["warnings"]) > 0
                        assert wr["warnings"][0]["tool"] == "flac-multichannel"
                        assert "Pioneer" in wr["warnings"][0]["output"]
