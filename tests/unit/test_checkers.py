"""Unit tests for music_commander.utils.checkers module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from music_commander.utils.checkers import (
    CHECKER_REGISTRY,
    FFMPEG_FALLBACK,
    CheckerSpec,
    CheckReport,
    CheckResult,
    ToolResult,
    _parse_ffmpeg_result,
    _parse_flac_result,
    _parse_mp3val_result,
    _parse_ogginfo_result,
    _parse_shntool_result,
    _parse_sox_result,
    check_file,
    check_tool_available,
    write_report,
)


class TestDataClasses:
    """Test dataclass structure and creation."""

    def test_tool_result_creation(self):
        result = ToolResult(
            tool="flac",
            success=True,
            exit_code=0,
            output="test output",
        )
        assert result.tool == "flac"
        assert result.success is True
        assert result.exit_code == 0
        assert result.output == "test output"

    def test_check_result_creation(self):
        result = CheckResult(
            file="test.flac",
            status="ok",
            tools=["flac"],
            errors=[],
        )
        assert result.file == "test.flac"
        assert result.status == "ok"
        assert result.tools == ["flac"]
        assert result.errors == []

    def test_check_report_creation(self):
        report = CheckReport(
            version=1,
            timestamp="2026-01-30T12:00:00Z",
            duration_seconds=1.5,
            repository="/test/repo",
            arguments=["test.flac"],
            summary={"total": 1, "ok": 1, "error": 0},
            results=[],
        )
        assert report.version == 1
        assert report.duration_seconds == 1.5


class TestToolParsers:
    """Test individual tool result parsers."""

    def test_parse_flac_success(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stderr = "test.flac: ok"
        result = _parse_flac_result(proc)
        assert result.success is True
        assert result.exit_code == 0
        assert result.tool == "flac"

    def test_parse_flac_failure(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 1
        proc.stderr = "ERROR: bad file"
        result = _parse_flac_result(proc)
        assert result.success is False
        assert result.exit_code == 1

    def test_parse_mp3val_success(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stdout = "INFO: file is valid\nDone!"
        result = _parse_mp3val_result(proc)
        assert result.success is True
        assert result.tool == "mp3val"

    def test_parse_mp3val_warning(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0  # mp3val always returns 0
        proc.stdout = "WARNING: padding detected\nINFO: file checked"
        result = _parse_mp3val_result(proc)
        assert result.success is False

    def test_parse_mp3val_problem(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stdout = "PROBLEM: corrupted frame\nINFO: file checked"
        result = _parse_mp3val_result(proc)
        assert result.success is False

    def test_parse_ffmpeg_success(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stderr = ""
        result = _parse_ffmpeg_result(proc)
        assert result.success is True
        assert result.tool == "ffmpeg"

    def test_parse_ffmpeg_failure_exit_code(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 1
        proc.stderr = "Error opening file"
        result = _parse_ffmpeg_result(proc)
        assert result.success is False

    def test_parse_ffmpeg_failure_stderr(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stderr = "Invalid data found when processing input"
        result = _parse_ffmpeg_result(proc)
        assert result.success is False

    def test_parse_shntool_success(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stdout = """length   expanded size   cdr  WAVE problems  fmt   ratio  filename
---
  5:30.00  35820000  -  -  -  fmt16  1.000  test.wav"""
        result = _parse_shntool_result(proc)
        assert result.success is True
        assert result.tool == "shntool"

    def test_parse_shntool_truncated(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stdout = """length   expanded size   cdr  WAVE problems  fmt   ratio  filename
---
  5:30.00  35820000  -  -  t  fmt16  1.000  test.wav"""
        result = _parse_shntool_result(proc)
        assert result.success is False

    def test_parse_sox_success(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stderr = "Samples read: 12345\nLength: 1.234"
        result = _parse_sox_result(proc)
        assert result.success is True
        assert result.tool == "sox"

    def test_parse_sox_failure(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 1
        proc.stderr = "sox FAIL: invalid header"
        result = _parse_sox_result(proc)
        assert result.success is False

    def test_parse_ogginfo_success(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 0
        proc.stdout = "Vorbis stream 1:\nRate: 44100"
        proc.stderr = ""
        result = _parse_ogginfo_result(proc)
        assert result.success is True
        assert result.tool == "ogginfo"

    def test_parse_ogginfo_failure(self):
        proc = Mock(spec=subprocess.CompletedProcess)
        proc.returncode = 1
        proc.stdout = ""
        proc.stderr = "Error opening file"
        result = _parse_ogginfo_result(proc)
        assert result.success is False


class TestCheckerRegistry:
    """Test checker registry lookups."""

    def test_flac_checker(self):
        checkers = CHECKER_REGISTRY[".flac"]
        assert len(checkers) == 1
        assert checkers[0].name == "flac"
        assert checkers[0].command == ["flac", "-t", "-s", "-w"]

    def test_mp3_checkers(self):
        checkers = CHECKER_REGISTRY[".mp3"]
        assert len(checkers) == 2
        assert checkers[0].name == "mp3val"
        assert checkers[1].name == "ffmpeg"

    def test_ogg_checkers(self):
        checkers = CHECKER_REGISTRY[".ogg"]
        assert len(checkers) == 2
        assert checkers[0].name == "ogginfo"
        assert checkers[1].name == "ffmpeg"

    def test_wav_checkers(self):
        checkers = CHECKER_REGISTRY[".wav"]
        assert len(checkers) == 2
        assert checkers[0].name == "shntool"
        assert checkers[1].name == "sox"

    def test_aiff_checker(self):
        checkers = CHECKER_REGISTRY[".aiff"]
        assert len(checkers) == 1
        assert checkers[0].name == "sox"

    def test_m4a_checker(self):
        checkers = CHECKER_REGISTRY[".m4a"]
        assert len(checkers) == 1
        assert checkers[0].name == "ffmpeg"

    def test_ffmpeg_fallback(self):
        assert FFMPEG_FALLBACK.name == "ffmpeg"
        assert FFMPEG_FALLBACK.file_arg_position == "middle"


class TestCheckToolAvailable:
    """Test tool availability checking."""

    @patch("music_commander.utils.checkers.shutil.which")
    def test_tool_available(self, mock_which):
        mock_which.return_value = "/usr/bin/flac"
        # Clear cache
        from music_commander.utils.checkers import _tool_cache

        _tool_cache.clear()

        result = check_tool_available("flac")
        assert result is True
        mock_which.assert_called_once_with("flac")

    @patch("music_commander.utils.checkers.shutil.which")
    def test_tool_not_available(self, mock_which):
        mock_which.return_value = None
        # Clear cache
        from music_commander.utils.checkers import _tool_cache

        _tool_cache.clear()

        result = check_tool_available("nonexistent")
        assert result is False

    @patch("music_commander.utils.checkers.shutil.which")
    def test_tool_caching(self, mock_which):
        mock_which.return_value = "/usr/bin/flac"
        # Clear cache
        from music_commander.utils.checkers import _tool_cache

        _tool_cache.clear()

        # First call
        check_tool_available("flac")
        # Second call should use cache
        check_tool_available("flac")
        # which should only be called once
        assert mock_which.call_count == 1


class TestCheckFile:
    """Test the main check_file function."""

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_success(self, mock_run, mock_tool_available, tmp_path):
        # Setup
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")
        repo_path = tmp_path

        mock_tool_available.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stderr = "test.flac: ok"
        mock_run.return_value = mock_proc

        # Execute
        result = check_file(test_file, repo_path)

        # Assert
        assert result.status == "ok"
        assert result.file == "test.flac"
        assert "flac" in result.tools
        assert result.errors == []

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_failure(self, mock_run, mock_tool_available, tmp_path):
        # Setup
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")
        repo_path = tmp_path

        mock_tool_available.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 1
        mock_proc.stderr = "ERROR: bad file"
        mock_run.return_value = mock_proc

        # Execute
        result = check_file(test_file, repo_path)

        # Assert
        assert result.status == "error"
        assert len(result.errors) == 1
        assert result.errors[0].tool == "flac"
        assert result.errors[0].success is False

    def test_check_file_not_present(self, tmp_path):
        # Setup
        test_file = tmp_path / "nonexistent.flac"
        repo_path = tmp_path

        # Execute
        result = check_file(test_file, repo_path)

        # Assert
        assert result.status == "not_present"
        assert result.tools == []
        assert result.errors == []

    @patch("music_commander.utils.checkers.check_tool_available")
    def test_check_file_checker_missing(self, mock_tool_available, tmp_path):
        # Setup
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")
        repo_path = tmp_path

        mock_tool_available.return_value = False

        # Execute
        result = check_file(test_file, repo_path)

        # Assert
        assert result.status == "checker_missing"
        assert "flac" in result.tools

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_ffmpeg_fallback(self, mock_run, mock_tool_available, tmp_path):
        # Setup - unknown extension
        test_file = tmp_path / "test.xyz"
        test_file.write_text("fake content")
        repo_path = tmp_path

        mock_tool_available.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        # Execute
        result = check_file(test_file, repo_path)

        # Assert - should use ffmpeg fallback
        assert result.status == "ok"
        assert "ffmpeg" in result.tools

        # Verify command construction for ffmpeg (middle insertion)
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-i" in call_args
        assert str(test_file) in call_args
        assert "-f" in call_args
        assert "null" in call_args

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_mp3_multiple_checkers(self, mock_run, mock_tool_available, tmp_path):
        # Setup
        test_file = tmp_path / "test.mp3"
        test_file.write_text("fake mp3 content")
        repo_path = tmp_path

        mock_tool_available.return_value = True

        # First call (mp3val) - success
        mock_proc1 = Mock(spec=subprocess.CompletedProcess)
        mock_proc1.returncode = 0
        mock_proc1.stdout = "INFO: file is valid"

        # Second call (ffmpeg) - success
        mock_proc2 = Mock(spec=subprocess.CompletedProcess)
        mock_proc2.returncode = 0
        mock_proc2.stderr = ""

        mock_run.side_effect = [mock_proc1, mock_proc2]

        # Execute
        result = check_file(test_file, repo_path)

        # Assert
        assert result.status == "ok"
        assert "mp3val" in result.tools
        assert "ffmpeg" in result.tools
        assert result.errors == []

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_mp3_one_fails(self, mock_run, mock_tool_available, tmp_path):
        # Setup
        test_file = tmp_path / "test.mp3"
        test_file.write_text("fake mp3 content")
        repo_path = tmp_path

        mock_tool_available.return_value = True

        # First call (mp3val) - failure
        mock_proc1 = Mock(spec=subprocess.CompletedProcess)
        mock_proc1.returncode = 0
        mock_proc1.stdout = "WARNING: padding issue"

        # Second call (ffmpeg) - success
        mock_proc2 = Mock(spec=subprocess.CompletedProcess)
        mock_proc2.returncode = 0
        mock_proc2.stderr = ""

        mock_run.side_effect = [mock_proc1, mock_proc2]

        # Execute
        result = check_file(test_file, repo_path)

        # Assert - ANY failure means overall error status
        assert result.status == "error"
        assert len(result.errors) == 1
        assert result.errors[0].tool == "mp3val"

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_timeout(self, mock_run, mock_tool_available, tmp_path):
        # Setup
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")
        repo_path = tmp_path

        mock_tool_available.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["flac"], timeout=300)

        # Execute
        result = check_file(test_file, repo_path)

        # Assert
        assert result.status == "error"
        assert len(result.errors) == 1
        assert "timed out" in result.errors[0].output.lower()


class TestWriteReport:
    """Test report writing."""

    def test_write_report_basic(self, tmp_path):
        # Setup
        report = CheckReport(
            version=1,
            timestamp="2026-01-30T12:00:00Z",
            duration_seconds=1.5,
            repository="/test/repo",
            arguments=["test.flac"],
            summary={"total": 1, "ok": 1, "error": 0},
            results=[
                CheckResult(
                    file="test.flac",
                    status="ok",
                    tools=["flac"],
                    errors=[],
                )
            ],
        )
        output_file = tmp_path / "report.json"

        # Execute
        write_report(report, output_file)

        # Assert
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["version"] == 1
        assert data["repository"] == "/test/repo"
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "ok"

    def test_write_report_atomic(self, tmp_path):
        """Test that write is atomic (temp file + rename)."""
        report = CheckReport(
            version=1,
            timestamp="2026-01-30T12:00:00Z",
            duration_seconds=1.0,
            repository="/test/repo",
            arguments=[],
            summary={"total": 0},
            results=[],
        )
        output_file = tmp_path / "report.json"

        # Execute
        write_report(report, output_file)

        # Assert - no temp files left behind
        temp_files = list(tmp_path.glob(".tmp_*"))
        assert len(temp_files) == 0
        assert output_file.exists()

    def test_write_report_creates_directory(self, tmp_path):
        """Test that parent directory is created if it doesn't exist."""
        report = CheckReport(
            version=1,
            timestamp="2026-01-30T12:00:00Z",
            duration_seconds=1.0,
            repository="/test/repo",
            arguments=[],
            summary={"total": 0},
            results=[],
        )
        output_file = tmp_path / "subdir" / "nested" / "report.json"

        # Execute
        write_report(report, output_file)

        # Assert
        assert output_file.exists()
        assert output_file.parent.exists()
