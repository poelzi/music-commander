"""Unit tests for music_commander.utils.checkers module."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from music_commander.utils.checkers import (
    _FFMPEG_CHECKER,
    _SOX_CHECKER,
    AUDIO_FALLBACK_GROUP,
    CHECKER_GROUPS,
    CHECKER_REGISTRY,
    CheckerGroup,
    CheckerSpec,
    CheckReport,
    CheckResult,
    ToolResult,
    _check_flac_multichannel,
    _parse_ffmpeg_result,
    _parse_flac_result,
    _parse_mp3val_result,
    _parse_ogginfo_result,
    _parse_shntool_result,
    _parse_sox_result,
    _validate_cue_file,
    check_file,
    check_tool_available,
    get_checkers_for_extension,
    get_checkers_for_file,
    write_report,
)


@pytest.fixture(autouse=True)
def _clear_tool_cache():
    """Clear tool availability cache before each test."""
    from music_commander.utils.checkers import _tool_cache

    _tool_cache.clear()


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

    def test_check_result_skipped_status(self):
        result = CheckResult(
            file="script.py",
            status="skipped",
            tools=[],
            errors=[],
        )
        assert result.status == "skipped"

    def test_check_result_warning_status(self):
        warning = ToolResult(
            tool="flac-multichannel",
            success=True,
            exit_code=0,
            output="multichannel bit set",
        )
        result = CheckResult(
            file="test.flac",
            status="warning",
            tools=["flac", "flac-multichannel"],
            errors=[],
            warnings=[warning],
        )
        assert result.status == "warning"
        assert len(result.warnings) == 1
        assert result.errors == []

    def test_check_result_warnings_default_empty(self):
        result = CheckResult(
            file="test.flac",
            status="ok",
            tools=["flac"],
            errors=[],
        )
        assert result.warnings == []

    def test_check_report_creation(self):
        report = CheckReport(
            version=1,
            timestamp="2026-01-30T12:00:00Z",
            duration_seconds=1.5,
            repository="/test/repo",
            arguments=["test.flac"],
            summary={"total": 1, "ok": 1, "error": 0, "skipped": 0},
            results=[],
        )
        assert report.version == 1
        assert report.duration_seconds == 1.5

    def test_checker_group_frozen(self):
        group = CheckerGroup(
            extensions=frozenset({".flac"}),
            mimetypes=frozenset({"audio/flac"}),
            checkers=[],
        )
        assert ".flac" in group.extensions
        assert "audio/flac" in group.mimetypes


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
        proc.returncode = 0
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
    """Test checker group registry and lookups."""

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

    def test_aiff_and_aif_share_sox(self):
        """Both .aiff and .aif should use the same sox checker (DRY)."""
        aiff_checkers = CHECKER_REGISTRY[".aiff"]
        aif_checkers = CHECKER_REGISTRY[".aif"]
        assert len(aiff_checkers) == 1
        assert len(aif_checkers) == 1
        assert aiff_checkers[0].name == "sox"
        assert aif_checkers[0].name == "sox"
        # They should be the exact same object (shared constant)
        assert aiff_checkers[0] is aif_checkers[0]

    def test_m4a_checker(self):
        checkers = CHECKER_REGISTRY[".m4a"]
        assert len(checkers) == 1
        assert checkers[0].name == "ffmpeg"

    def test_cue_in_registry(self):
        """CUE files should be in the registry with no external checkers."""
        checkers = CHECKER_REGISTRY.get(".cue", None)
        assert checkers is not None
        assert checkers == []

    def test_audio_fallback_group(self):
        assert _FFMPEG_CHECKER in AUDIO_FALLBACK_GROUP.checkers
        assert "audio/*" in AUDIO_FALLBACK_GROUP.mimetypes

    def test_checker_groups_have_extensions(self):
        """Every group should have at least one extension or mimetype."""
        for group in CHECKER_GROUPS:
            assert group.extensions or group.mimetypes

    def test_shared_constants_are_reused(self):
        """Shared checker specs should be the same object across groups."""
        ffmpeg_groups = [g for g in CHECKER_GROUPS if _FFMPEG_CHECKER in g.checkers]
        assert len(ffmpeg_groups) >= 3  # mp3, ogg, m4a at minimum

    def test_unknown_extension_returns_empty(self):
        """get_checkers_for_extension should return empty for unknown extensions."""
        checkers = get_checkers_for_extension(".xyz")
        assert checkers == []


class TestGetCheckersForFile:
    """Test the file-based checker lookup with MIME support."""

    def test_known_extension_no_magic_needed(self, tmp_path):
        """Known extensions should match without MIME detection."""
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake")
        group, hint = get_checkers_for_file(test_file)
        assert hint == "check"
        assert group is not None
        assert any(c.name == "flac" for c in group.checkers)

    @patch("music_commander.utils.checkers._detect_mimetype")
    def test_unknown_ext_audio_mime_uses_fallback(self, mock_mime, tmp_path):
        """Unknown extension with audio/* MIME should use ffmpeg fallback."""
        test_file = tmp_path / "track.audio"
        test_file.write_text("fake audio")
        mock_mime.return_value = "audio/x-custom"

        group, hint = get_checkers_for_file(test_file)
        assert hint == "check"
        assert group is AUDIO_FALLBACK_GROUP

    @patch("music_commander.utils.checkers._detect_mimetype")
    def test_unknown_ext_non_audio_mime_skipped(self, mock_mime, tmp_path):
        """Unknown extension with non-audio MIME should be skipped."""
        test_file = tmp_path / "script.py"
        test_file.write_text("print('hello')")
        mock_mime.return_value = "text/x-python"

        group, hint = get_checkers_for_file(test_file)
        assert hint == "skipped"
        assert group is None

    @patch("music_commander.utils.checkers._detect_mimetype")
    def test_unknown_ext_exact_mime_match(self, mock_mime, tmp_path):
        """Unknown extension but exact MIME match should find the right group."""
        test_file = tmp_path / "track.unknown"
        test_file.write_text("fake")
        mock_mime.return_value = "audio/flac"

        group, hint = get_checkers_for_file(test_file)
        assert hint == "check"
        assert group is not None
        assert any(c.name == "flac" for c in group.checkers)

    @patch("music_commander.utils.checkers._detect_mimetype")
    def test_unknown_ext_mime_detection_fails(self, mock_mime, tmp_path):
        """If MIME detection returns None, file should be skipped."""
        test_file = tmp_path / "data.bin"
        test_file.write_text("binary data")
        mock_mime.return_value = None

        group, hint = get_checkers_for_file(test_file)
        assert hint == "skipped"

    def test_cue_extension_matches(self, tmp_path):
        """CUE files should match by extension."""
        test_file = tmp_path / "album.cue"
        test_file.write_text("FILE track.wav WAVE\nTRACK 01 AUDIO")
        group, hint = get_checkers_for_file(test_file)
        assert hint == "check"
        assert group is not None
        assert group.internal_validator == "cue"


class TestCueValidator:
    """Test CUE sheet validation."""

    def test_valid_cue_file(self, tmp_path):
        test_file = tmp_path / "album.cue"
        test_file.write_text('FILE "track01.wav" WAVE\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n')
        result = _validate_cue_file(test_file, "album.cue")
        assert result.status == "ok"
        assert result.tools == ["cue-validator"]

    def test_missing_file_directive(self, tmp_path):
        test_file = tmp_path / "bad.cue"
        test_file.write_text("TRACK 01 AUDIO\n  INDEX 01 00:00:00\n")
        result = _validate_cue_file(test_file, "bad.cue")
        assert result.status == "error"
        assert "FILE" in result.errors[0].output

    def test_missing_track_directive(self, tmp_path):
        test_file = tmp_path / "bad.cue"
        test_file.write_text('FILE "track.wav" WAVE\n')
        result = _validate_cue_file(test_file, "bad.cue")
        assert result.status == "error"
        assert "TRACK" in result.errors[0].output

    def test_missing_both_directives(self, tmp_path):
        test_file = tmp_path / "bad.cue"
        test_file.write_text("PERFORMER Artist\nTITLE Album\n")
        result = _validate_cue_file(test_file, "bad.cue")
        assert result.status == "error"
        assert "FILE" in result.errors[0].output
        assert "TRACK" in result.errors[0].output

    def test_latin1_encoded_cue(self, tmp_path):
        test_file = tmp_path / "latin.cue"
        content = 'PERFORMER "K\xf6nig"\nFILE "track.wav" WAVE\nTRACK 01 AUDIO\n'
        test_file.write_bytes(content.encode("latin-1"))
        result = _validate_cue_file(test_file, "latin.cue")
        assert result.status == "ok"

    def test_binary_file_as_cue(self, tmp_path):
        test_file = tmp_path / "fake.cue"
        test_file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd" * 100)
        result = _validate_cue_file(test_file, "fake.cue")
        # Binary garbage should either decode as latin-1 (then fail directives)
        # or be reported as error
        assert result.status == "error"


class TestCheckToolAvailable:
    """Test tool availability checking."""

    @patch("music_commander.utils.checkers.shutil.which")
    def test_tool_available(self, mock_which):
        mock_which.return_value = "/usr/bin/flac"
        result = check_tool_available("flac")
        assert result is True
        mock_which.assert_called_once_with("flac")

    @patch("music_commander.utils.checkers.shutil.which")
    def test_tool_not_available(self, mock_which):
        mock_which.return_value = None
        result = check_tool_available("nonexistent")
        assert result is False

    @patch("music_commander.utils.checkers.shutil.which")
    def test_tool_caching(self, mock_which):
        mock_which.return_value = "/usr/bin/flac"
        check_tool_available("flac")
        check_tool_available("flac")
        assert mock_which.call_count == 1


class TestCheckFile:
    """Test the main check_file function."""

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_success(self, mock_run, mock_tool_available, tmp_path):
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool_available.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stderr = "test.flac: ok"
        mock_run.return_value = mock_proc

        result = check_file(test_file, tmp_path, verbose_output=True)
        assert result.status == "ok"
        assert result.file == "test.flac"
        assert "flac" in result.tools
        assert result.errors == []

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_failure(self, mock_run, mock_tool_available, tmp_path):
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool_available.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 1
        mock_proc.stderr = "ERROR: bad file"
        mock_run.return_value = mock_proc

        result = check_file(test_file, tmp_path, verbose_output=True)
        assert result.status == "error"
        assert len(result.errors) == 1
        assert result.errors[0].tool == "flac"

    def test_check_file_not_present(self, tmp_path):
        test_file = tmp_path / "nonexistent.flac"
        result = check_file(test_file, tmp_path)
        assert result.status == "not_present"
        assert result.tools == []

    @patch("music_commander.utils.checkers.check_tool_available")
    def test_check_file_checker_missing(self, mock_tool_available, tmp_path):
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool_available.return_value = False

        result = check_file(test_file, tmp_path)
        assert result.status == "checker_missing"
        assert "flac" in result.tools

    @patch("music_commander.utils.checkers._detect_mimetype")
    def test_check_file_non_audio_skipped(self, mock_mime, tmp_path):
        """Non-audio files should be skipped, not checked with ffmpeg."""
        test_file = tmp_path / "script.py"
        test_file.write_text("print('hello')")
        mock_mime.return_value = "text/x-python"

        result = check_file(test_file, tmp_path)
        assert result.status == "skipped"
        assert result.tools == []
        assert result.errors == []

    @patch("music_commander.utils.checkers._detect_mimetype")
    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_unknown_ext_audio_mime(self, mock_run, mock_tool, mock_mime, tmp_path):
        """Unknown extension with audio MIME should use ffmpeg fallback."""
        test_file = tmp_path / "track.audio"
        test_file.write_text("fake audio content")
        mock_mime.return_value = "audio/x-custom"
        mock_tool.return_value = True

        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = check_file(test_file, tmp_path)
        assert result.status == "ok"
        assert "ffmpeg" in result.tools

    def test_check_file_cue_valid(self, tmp_path):
        """CUE files should use internal validator."""
        test_file = tmp_path / "album.cue"
        test_file.write_text('FILE "track.wav" WAVE\nTRACK 01 AUDIO\n  INDEX 01 00:00:00\n')

        result = check_file(test_file, tmp_path)
        assert result.status == "ok"
        assert "cue-validator" in result.tools

    def test_check_file_cue_invalid(self, tmp_path):
        """Invalid CUE files should report error."""
        test_file = tmp_path / "bad.cue"
        test_file.write_text("PERFORMER Artist\nTITLE Album\n")

        result = check_file(test_file, tmp_path)
        assert result.status == "error"
        assert "cue-validator" in result.tools

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_mp3_multiple_checkers(self, mock_run, mock_tool_available, tmp_path):
        test_file = tmp_path / "test.mp3"
        test_file.write_text("fake mp3 content")

        mock_tool_available.return_value = True

        mock_proc1 = Mock(spec=subprocess.CompletedProcess)
        mock_proc1.returncode = 0
        mock_proc1.stdout = "INFO: file is valid"

        mock_proc2 = Mock(spec=subprocess.CompletedProcess)
        mock_proc2.returncode = 0
        mock_proc2.stderr = ""

        mock_run.side_effect = [mock_proc1, mock_proc2]

        result = check_file(test_file, tmp_path)
        assert result.status == "ok"
        assert "mp3val" in result.tools
        assert "ffmpeg" in result.tools

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_mp3_one_fails(self, mock_run, mock_tool_available, tmp_path):
        test_file = tmp_path / "test.mp3"
        test_file.write_text("fake mp3 content")

        mock_tool_available.return_value = True

        mock_proc1 = Mock(spec=subprocess.CompletedProcess)
        mock_proc1.returncode = 0
        mock_proc1.stdout = "WARNING: padding issue"

        mock_proc2 = Mock(spec=subprocess.CompletedProcess)
        mock_proc2.returncode = 0
        mock_proc2.stderr = ""

        mock_run.side_effect = [mock_proc1, mock_proc2]

        result = check_file(test_file, tmp_path)
        assert result.status == "error"
        assert len(result.errors) == 1
        assert result.errors[0].tool == "mp3val"

    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_check_file_timeout(self, mock_run, mock_tool_available, tmp_path):
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool_available.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["flac"], timeout=300)

        result = check_file(test_file, tmp_path)
        assert result.status == "error"
        assert len(result.errors) == 1
        assert "timed out" in result.errors[0].output.lower()


class TestWriteReport:
    """Test report writing."""

    def test_write_report_basic(self, tmp_path):
        report = CheckReport(
            version=1,
            timestamp="2026-01-30T12:00:00Z",
            duration_seconds=1.5,
            repository="/test/repo",
            arguments=["test.flac"],
            summary={"total": 1, "ok": 1, "error": 0, "skipped": 0},
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
        write_report(report, output_file)

        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["version"] == 1
        assert data["repository"] == "/test/repo"
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "ok"

    def test_write_report_atomic(self, tmp_path):
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
        write_report(report, output_file)

        temp_files = list(tmp_path.glob(".tmp_*"))
        assert len(temp_files) == 0
        assert output_file.exists()

    def test_write_report_creates_directory(self, tmp_path):
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
        write_report(report, output_file)

        assert output_file.exists()
        assert output_file.parent.exists()


class TestFlacMultichannelCheck:
    """Test FLAC multichannel bit detection."""

    @patch("music_commander.utils.checkers.check_tool_available")
    def test_metaflac_not_available(self, mock_tool, tmp_path):
        """Returns None when metaflac is not installed."""
        mock_tool.return_value = False
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake")
        result = _check_flac_multichannel(test_file)
        assert result is None

    @patch("music_commander.utils.checkers.subprocess.run")
    @patch("music_commander.utils.checkers.check_tool_available")
    def test_stereo_with_multichannel_mask(self, mock_tool, mock_run, tmp_path):
        """Detects stereo file with WAVEFORMATEXTENSIBLE_CHANNEL_MASK tag."""
        mock_tool.return_value = True
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake")

        # First call: --show-channels returns 2
        proc_channels = Mock(spec=subprocess.CompletedProcess)
        proc_channels.returncode = 0
        proc_channels.stdout = "2\n"

        # Second call: --show-tag returns the mask
        proc_tag = Mock(spec=subprocess.CompletedProcess)
        proc_tag.returncode = 0
        proc_tag.stdout = "WAVEFORMATEXTENSIBLE_CHANNEL_MASK=0x0003\n"

        mock_run.side_effect = [proc_channels, proc_tag]

        result = _check_flac_multichannel(test_file)
        assert result is not None
        assert result.tool == "flac-multichannel"
        assert "0x0003" in result.output
        assert "Pioneer" in result.output

    @patch("music_commander.utils.checkers.subprocess.run")
    @patch("music_commander.utils.checkers.check_tool_available")
    def test_stereo_without_mask(self, mock_tool, mock_run, tmp_path):
        """No warning when stereo file has no WAVEFORMATEXTENSIBLE_CHANNEL_MASK."""
        mock_tool.return_value = True
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake")

        proc_channels = Mock(spec=subprocess.CompletedProcess)
        proc_channels.returncode = 0
        proc_channels.stdout = "2\n"

        proc_tag = Mock(spec=subprocess.CompletedProcess)
        proc_tag.returncode = 0
        proc_tag.stdout = "\n"  # Empty — no tag

        mock_run.side_effect = [proc_channels, proc_tag]

        result = _check_flac_multichannel(test_file)
        assert result is None

    @patch("music_commander.utils.checkers.subprocess.run")
    @patch("music_commander.utils.checkers.check_tool_available")
    def test_mono_file_ignored(self, mock_tool, mock_run, tmp_path):
        """Mono files are not flagged (only stereo is checked)."""
        mock_tool.return_value = True
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake")

        proc_channels = Mock(spec=subprocess.CompletedProcess)
        proc_channels.returncode = 0
        proc_channels.stdout = "1\n"

        mock_run.return_value = proc_channels

        result = _check_flac_multichannel(test_file)
        assert result is None

    @patch("music_commander.utils.checkers.subprocess.run")
    @patch("music_commander.utils.checkers.check_tool_available")
    def test_multichannel_file_ignored(self, mock_tool, mock_run, tmp_path):
        """Files with >2 channels are not flagged."""
        mock_tool.return_value = True
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake")

        proc_channels = Mock(spec=subprocess.CompletedProcess)
        proc_channels.returncode = 0
        proc_channels.stdout = "6\n"

        mock_run.return_value = proc_channels

        result = _check_flac_multichannel(test_file)
        assert result is None

    @patch("music_commander.utils.checkers.subprocess.run")
    @patch("music_commander.utils.checkers.check_tool_available")
    def test_metaflac_error_returns_none(self, mock_tool, mock_run, tmp_path):
        """Returns None when metaflac fails."""
        mock_tool.return_value = True
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake")

        proc_channels = Mock(spec=subprocess.CompletedProcess)
        proc_channels.returncode = 1
        proc_channels.stdout = ""

        mock_run.return_value = proc_channels

        result = _check_flac_multichannel(test_file)
        assert result is None


class TestCheckFileMultichannel:
    """Test check_file integration with flac_multichannel_check flag."""

    @patch("music_commander.utils.checkers._check_flac_multichannel")
    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_warning_when_enabled(self, mock_run, mock_tool, mock_mc, tmp_path):
        """check_file returns warning status when multichannel check detects issue."""
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stderr = "test.flac: ok"
        mock_run.return_value = mock_proc

        mock_mc.return_value = ToolResult(
            tool="flac-multichannel",
            success=True,
            exit_code=0,
            output="Stereo file has WAVEFORMATEXTENSIBLE_CHANNEL_MASK=0x0003.",
        )

        result = check_file(test_file, tmp_path, flac_multichannel_check=True)
        assert result.status == "warning"
        assert len(result.warnings) == 1
        assert result.warnings[0].tool == "flac-multichannel"
        assert result.errors == []
        assert "flac-multichannel" in result.tools

    @patch("music_commander.utils.checkers._check_flac_multichannel")
    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_no_warning_when_disabled(self, mock_run, mock_tool, mock_mc, tmp_path):
        """check_file does not run multichannel check when flag is off."""
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stderr = "test.flac: ok"
        mock_run.return_value = mock_proc

        result = check_file(test_file, tmp_path, flac_multichannel_check=False)
        assert result.status == "ok"
        assert result.warnings == []
        mock_mc.assert_not_called()

    @patch("music_commander.utils.checkers._check_flac_multichannel")
    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_no_warning_on_error(self, mock_run, mock_tool, mock_mc, tmp_path):
        """Multichannel check is skipped when integrity check fails."""
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 1
        mock_proc.stderr = "ERROR: corrupted"
        mock_run.return_value = mock_proc

        result = check_file(test_file, tmp_path, flac_multichannel_check=True)
        assert result.status == "error"
        mock_mc.assert_not_called()

    @patch("music_commander.utils.checkers._check_flac_multichannel")
    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_no_warning_on_non_flac(self, mock_run, mock_tool, mock_mc, tmp_path):
        """Multichannel check only applies to .flac files."""
        test_file = tmp_path / "test.mp3"
        test_file.write_text("fake mp3 content")

        mock_tool.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stdout = "INFO: file is valid"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        result = check_file(test_file, tmp_path, flac_multichannel_check=True)
        assert result.status == "ok"
        mock_mc.assert_not_called()

    @patch("music_commander.utils.checkers._check_flac_multichannel")
    @patch("music_commander.utils.checkers.check_tool_available")
    @patch("music_commander.utils.checkers.subprocess.run")
    def test_no_issue_detected(self, mock_run, mock_tool, mock_mc, tmp_path):
        """check_file returns ok when multichannel check finds no issue."""
        test_file = tmp_path / "test.flac"
        test_file.write_text("fake flac content")

        mock_tool.return_value = True
        mock_proc = Mock(spec=subprocess.CompletedProcess)
        mock_proc.returncode = 0
        mock_proc.stderr = "test.flac: ok"
        mock_run.return_value = mock_proc

        mock_mc.return_value = None  # No issue found

        result = check_file(test_file, tmp_path, flac_multichannel_check=True)
        assert result.status == "ok"
        assert result.warnings == []
