"""Unit tests for encoder module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from music_commander.utils.encoder import (
    AIFF,
    AIFF_PIONEER,
    EXTENSION_TO_PRESET,
    FLAC,
    FLAC_PIONEER,
    MP3_320,
    MP3_V0,
    PRESETS,
    WAV,
    WAV_PIONEER,
    ExportReport,
    ExportResult,
    FormatPreset,
    SourceInfo,
    build_ffmpeg_command,
    can_copy,
    export_file,
    find_cover_art,
    probe_source,
    write_export_report,
)


class TestFormatPresets:
    """Tests for FormatPreset registry and definitions."""

    def test_all_presets_present(self):
        """All 8 presets should be in PRESETS registry."""
        assert len(PRESETS) == 8
        assert "mp3-320" in PRESETS
        assert "mp3-v0" in PRESETS
        assert "flac" in PRESETS
        assert "flac-pioneer" in PRESETS
        assert "aiff" in PRESETS
        assert "aiff-pioneer" in PRESETS
        assert "wav" in PRESETS
        assert "wav-pioneer" in PRESETS

    def test_preset_codec_and_container(self):
        """Each preset should have correct codec and container."""
        assert PRESETS["mp3-320"].codec == "libmp3lame"
        assert PRESETS["mp3-320"].container == ".mp3"
        assert PRESETS["flac"].codec == "flac"
        assert PRESETS["flac"].container == ".flac"
        assert PRESETS["aiff"].codec == "pcm_s16be"
        assert PRESETS["aiff"].container == ".aiff"
        assert PRESETS["wav"].codec == "pcm_s16le"
        assert PRESETS["wav"].container == ".wav"

    def test_pioneer_presets_have_constraints(self):
        """Pioneer presets should have 44.1kHz/16-bit/stereo constraints."""
        assert PRESETS["flac-pioneer"].sample_rate == 44100
        assert PRESETS["flac-pioneer"].bit_depth == 16
        assert PRESETS["flac-pioneer"].channels == 2

        assert PRESETS["aiff-pioneer"].sample_rate == 44100
        assert PRESETS["aiff-pioneer"].bit_depth == 16
        assert PRESETS["aiff-pioneer"].channels == 2

        assert PRESETS["wav-pioneer"].sample_rate == 44100
        assert PRESETS["wav-pioneer"].bit_depth == 16
        assert PRESETS["wav-pioneer"].channels == 2

    def test_flac_pioneer_has_post_commands(self):
        """flac-pioneer should have metaflac post-processing."""
        assert PRESETS["flac-pioneer"].post_commands is not None
        assert len(PRESETS["flac-pioneer"].post_commands) == 1
        assert "metaflac" in PRESETS["flac-pioneer"].post_commands[0]

    def test_wav_presets_no_cover_art(self):
        """WAV presets should not support cover art."""
        assert PRESETS["wav"].supports_cover_art is False
        assert PRESETS["wav-pioneer"].supports_cover_art is False

    def test_extension_to_preset_mapping(self):
        """Extension mappings should be correct."""
        assert EXTENSION_TO_PRESET[".mp3"] == "mp3-320"
        assert EXTENSION_TO_PRESET[".flac"] == "flac"
        assert EXTENSION_TO_PRESET[".aiff"] == "aiff"
        assert EXTENSION_TO_PRESET[".aif"] == "aiff"
        assert EXTENSION_TO_PRESET[".wav"] == "wav"

    def test_preset_frozen(self):
        """FormatPreset instances should be immutable."""
        preset = PRESETS["mp3-320"]
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            preset.codec = "something_else"


class TestProbeSource:
    """Tests for probe_source() function."""

    def test_probe_flac_16bit_44100(self):
        """Probe FLAC 16-bit 44.1kHz stereo with embedded art."""
        ffprobe_audio = {
            "streams": [
                {
                    "codec_name": "flac",
                    "sample_rate": "44100",
                    "channels": "2",
                    "bits_per_raw_sample": "16",
                    "sample_fmt": "s16",
                }
            ]
        }

        mock_proc_audio = Mock()
        mock_proc_audio.returncode = 0
        mock_proc_audio.stdout = json.dumps(ffprobe_audio)

        mock_proc_art = Mock()
        mock_proc_art.returncode = 0
        mock_proc_art.stdout = "mjpeg\n"

        with patch("subprocess.run", side_effect=[mock_proc_audio, mock_proc_art]):
            result = probe_source(Path("/fake/file.flac"))

        assert result.codec_name == "flac"
        assert result.sample_rate == 44100
        assert result.bit_depth == 16
        assert result.channels == 2
        assert result.has_cover_art is True

    def test_probe_flac_24bit_96000(self):
        """Probe FLAC 24-bit 96kHz stereo without art."""
        ffprobe_audio = {
            "streams": [
                {
                    "codec_name": "flac",
                    "sample_rate": "96000",
                    "channels": "2",
                    "bits_per_raw_sample": "24",
                    "sample_fmt": "s32",
                }
            ]
        }

        mock_proc_audio = Mock()
        mock_proc_audio.returncode = 0
        mock_proc_audio.stdout = json.dumps(ffprobe_audio)

        mock_proc_art = Mock()
        mock_proc_art.returncode = 0
        mock_proc_art.stdout = ""

        with patch("subprocess.run", side_effect=[mock_proc_audio, mock_proc_art]):
            result = probe_source(Path("/fake/file.flac"))

        assert result.codec_name == "flac"
        assert result.sample_rate == 96000
        assert result.bit_depth == 24
        assert result.channels == 2
        assert result.has_cover_art is False

    def test_probe_mp3_fallback_sample_fmt(self):
        """Probe MP3 with empty bits_per_raw_sample (use sample_fmt fallback)."""
        ffprobe_audio = {
            "streams": [
                {
                    "codec_name": "mp3",
                    "sample_rate": "44100",
                    "channels": "2",
                    "bits_per_raw_sample": "0",
                    "sample_fmt": "s16p",
                }
            ]
        }

        mock_proc_audio = Mock()
        mock_proc_audio.returncode = 0
        mock_proc_audio.stdout = json.dumps(ffprobe_audio)

        mock_proc_art = Mock()
        mock_proc_art.returncode = 0
        mock_proc_art.stdout = ""

        with patch("subprocess.run", side_effect=[mock_proc_audio, mock_proc_art]):
            result = probe_source(Path("/fake/file.mp3"))

        assert result.codec_name == "mp3"
        assert result.bit_depth == 16  # from sample_fmt s16p

    def test_probe_error(self):
        """Probe should raise RuntimeError on ffprobe failure."""
        mock_proc = Mock()
        mock_proc.returncode = 1
        mock_proc.stderr = "ffprobe error"

        with patch("subprocess.run", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="ffprobe failed"):
                probe_source(Path("/fake/file.flac"))


class TestFindCoverArt:
    """Tests for find_cover_art() function."""

    def test_cover_jpg_found(self, tmp_path):
        """Should find cover.jpg."""
        audio_file = tmp_path / "track.flac"
        audio_file.touch()
        cover = tmp_path / "cover.jpg"
        cover.touch()

        result = find_cover_art(audio_file)
        assert result == cover

    def test_folder_png_found(self, tmp_path):
        """Should find folder.png when cover.jpg doesn't exist."""
        audio_file = tmp_path / "track.flac"
        audio_file.touch()
        folder_png = tmp_path / "folder.png"
        folder_png.touch()

        result = find_cover_art(audio_file)
        assert result == folder_png

    def test_no_cover_found(self, tmp_path):
        """Should return None when no cover files exist."""
        audio_file = tmp_path / "track.flac"
        audio_file.touch()

        result = find_cover_art(audio_file)
        assert result is None

    def test_case_insensitive(self, tmp_path):
        """Should find Cover.JPG (case-insensitive)."""
        audio_file = tmp_path / "track.flac"
        audio_file.touch()
        cover = tmp_path / "Cover.JPG"
        cover.touch()

        result = find_cover_art(audio_file)
        assert result == cover

    def test_priority_order(self, tmp_path):
        """Should return cover.jpg when both cover.jpg and folder.jpg exist."""
        audio_file = tmp_path / "track.flac"
        audio_file.touch()
        cover_jpg = tmp_path / "cover.jpg"
        cover_jpg.touch()
        folder_jpg = tmp_path / "folder.jpg"
        folder_jpg.touch()

        result = find_cover_art(audio_file)
        assert result == cover_jpg


class TestCanCopy:
    """Tests for can_copy() function."""

    def test_exact_match(self):
        """Source matches preset exactly -> True."""
        source = SourceInfo(
            codec_name="flac",
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            has_cover_art=False,
        )
        preset = FLAC_PIONEER

        assert can_copy(source, preset) is True

    def test_codec_mismatch(self):
        """Source codec doesn't match -> False."""
        source = SourceInfo(
            codec_name="flac",
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            has_cover_art=False,
        )
        preset = MP3_320

        assert can_copy(source, preset) is False

    def test_sample_rate_mismatch(self):
        """Source sample rate doesn't match preset requirement -> False."""
        source = SourceInfo(
            codec_name="flac",
            sample_rate=96000,
            bit_depth=16,
            channels=2,
            has_cover_art=False,
        )
        preset = FLAC_PIONEER

        assert can_copy(source, preset) is False

    def test_preset_no_constraints(self):
        """Preset with no constraints (all None) -> True if codec matches."""
        source = SourceInfo(
            codec_name="flac",
            sample_rate=96000,
            bit_depth=24,
            channels=2,
            has_cover_art=False,
        )
        preset = FLAC

        assert can_copy(source, preset) is True

    def test_bit_depth_mismatch(self):
        """Source bit depth doesn't match -> False."""
        source = SourceInfo(
            codec_name="flac",
            sample_rate=44100,
            bit_depth=24,
            channels=2,
            has_cover_art=False,
        )
        preset = FLAC_PIONEER

        assert can_copy(source, preset) is False

    def test_channel_mismatch(self):
        """Source channels don't match -> False."""
        source = SourceInfo(
            codec_name="flac",
            sample_rate=44100,
            bit_depth=16,
            channels=1,
            has_cover_art=False,
        )
        preset = FLAC_PIONEER

        assert can_copy(source, preset) is False

    def test_mp3_codec_compat(self):
        """Source codec 'mp3' should match preset codec 'libmp3lame'."""
        source = SourceInfo(
            codec_name="mp3",
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            has_cover_art=False,
        )
        preset = MP3_320

        assert can_copy(source, preset) is True


class TestBuildFfmpegCommand:
    """Tests for build_ffmpeg_command() function."""

    def test_full_encode_mp3_320(self):
        """Full encode to MP3-320 should include correct args."""
        source = SourceInfo("flac", 44100, 16, 2, False)
        cmd = build_ffmpeg_command(
            Path("/in.flac"),
            Path("/out.mp3"),
            MP3_320,
            source,
        )

        assert "ffmpeg" in cmd
        assert "-codec:a" in cmd
        assert "libmp3lame" in cmd
        assert "-b:a" in cmd
        assert "320k" in cmd
        assert "-map_metadata" in cmd
        assert "0" in cmd

    def test_full_encode_with_cover(self):
        """Encode with external cover should map cover as attached_pic."""
        source = SourceInfo("flac", 44100, 16, 2, False)
        cmd = build_ffmpeg_command(
            Path("/in.flac"),
            Path("/out.mp3"),
            MP3_320,
            source,
            cover_path=Path("/cover.jpg"),
        )

        assert "-i" in cmd
        cover_idx = cmd.index("-i")
        # First -i is input, second -i is cover
        assert cmd.count("-i") == 2
        assert "-map" in cmd
        assert "0:a" in cmd
        assert "1:0" in cmd
        assert "-disposition:v:0" in cmd
        assert "attached_pic" in cmd

    def test_stream_copy(self):
        """Stream copy should use -codec:a copy."""
        source = SourceInfo("mp3", 44100, 16, 2, False)
        cmd = build_ffmpeg_command(
            Path("/in.mp3"),
            Path("/out.mp3"),
            MP3_320,
            source,
            stream_copy=True,
        )

        assert "-codec:a" in cmd
        assert "copy" in cmd

    def test_stream_copy_with_cover(self):
        """Stream copy with external cover."""
        source = SourceInfo("mp3", 44100, 16, 2, False)
        cmd = build_ffmpeg_command(
            Path("/in.mp3"),
            Path("/out.mp3"),
            MP3_320,
            source,
            cover_path=Path("/cover.jpg"),
            stream_copy=True,
        )

        assert "-codec:a" in cmd
        assert "copy" in cmd
        assert cmd.count("-i") == 2

    def test_preserve_embedded_art(self):
        """Source with embedded art should map 0:v."""
        source = SourceInfo("flac", 44100, 16, 2, True)
        cmd = build_ffmpeg_command(
            Path("/in.flac"),
            Path("/out.mp3"),
            MP3_320,
            source,
        )

        assert "-map" in cmd
        assert "0:a" in cmd
        assert "0:v" in cmd

    def test_flac_pioneer_args(self):
        """flac-pioneer should include -sample_fmt s16 -ar 44100 -ac 2."""
        source = SourceInfo("flac", 96000, 24, 2, False)
        cmd = build_ffmpeg_command(
            Path("/in.flac"),
            Path("/out.flac"),
            FLAC_PIONEER,
            source,
        )

        assert "-sample_fmt" in cmd
        assert "s16" in cmd
        assert "-ar" in cmd
        assert "44100" in cmd
        assert "-ac" in cmd
        assert "2" in cmd

    def test_aiff_24bit_codec_selection(self):
        """AIFF non-pioneer with 24-bit source should use pcm_s24be."""
        source = SourceInfo("pcm_s24be", 44100, 24, 2, False)
        cmd = build_ffmpeg_command(
            Path("/in.aiff"),
            Path("/out.aiff"),
            AIFF,
            source,
        )

        assert "-codec:a" in cmd
        codec_idx = cmd.index("-codec:a")
        assert cmd[codec_idx + 1] == "pcm_s24be"

    def test_wav_no_cover_art_mapping(self):
        """WAV preset should skip cover art mapping even if cover exists."""
        source = SourceInfo("pcm_s16le", 44100, 16, 2, False)
        cmd = build_ffmpeg_command(
            Path("/in.wav"),
            Path("/out.wav"),
            WAV,
            source,
            cover_path=Path("/cover.jpg"),
        )

        # Should NOT have second -i for cover
        assert cmd.count("-i") == 1
        assert "attached_pic" not in cmd


class TestExportFile:
    """Tests for export_file() function."""

    def test_export_full_encode(self, tmp_path):
        """Full encode should run ffmpeg and return ok status."""
        repo = tmp_path / "repo"
        repo.mkdir()
        source = repo / "track.flac"
        source.touch()

        output_dir = tmp_path / "output"
        output = output_dir / "track.mp3"

        # Mock probe_source
        mock_source_info = SourceInfo("flac", 44100, 16, 2, False)

        # Mock ffmpeg subprocess - create temp file so rename succeeds
        def fake_run(cmd, **kwargs):
            # ffmpeg writes to the temp file path (last arg)
            temp_file = Path(cmd[-1])
            temp_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file.touch()
            mock_proc = Mock()
            mock_proc.returncode = 0
            mock_proc.stderr = ""
            return mock_proc

        with patch("music_commander.utils.encoder.probe_source", return_value=mock_source_info):
            with patch("subprocess.run", side_effect=fake_run):
                result = export_file(source, output, MP3_320, repo)

        assert result.status == "ok"
        assert result.action == "encoded"
        assert result.preset == "mp3-320"

    def test_export_file_copy(self, tmp_path):
        """File copy should use shutil.copy2."""
        repo = tmp_path / "repo"
        repo.mkdir()
        source = repo / "track.mp3"
        source.write_text("fake audio")

        output_dir = tmp_path / "output"
        output = output_dir / "track.mp3"

        # Source matches preset exactly
        mock_source_info = SourceInfo("mp3", 44100, 16, 2, True)

        with patch("music_commander.utils.encoder.probe_source", return_value=mock_source_info):
            with patch("music_commander.utils.encoder.find_cover_art", return_value=None):
                result = export_file(source, output, MP3_320, repo)

        assert result.status == "copied"
        assert result.action == "file_copied"
        assert output.exists()

    def test_export_error(self, tmp_path):
        """ffmpeg error should return error status and clean up temp."""
        repo = tmp_path / "repo"
        repo.mkdir()
        source = repo / "track.flac"
        source.touch()

        output_dir = tmp_path / "output"
        output = output_dir / "track.mp3"

        mock_source_info = SourceInfo("flac", 44100, 16, 2, False)

        # Mock ffmpeg failure
        mock_proc = Mock()
        mock_proc.returncode = 1
        mock_proc.stderr = "ffmpeg error"

        with patch("music_commander.utils.encoder.probe_source", return_value=mock_source_info):
            with patch("subprocess.run", return_value=mock_proc):
                result = export_file(source, output, MP3_320, repo)

        assert result.status == "error"
        assert result.error_message is not None
        # Temp file should be cleaned up
        assert not (output.parent / (output.name + ".tmp")).exists()

    def test_export_not_present(self, tmp_path):
        """Non-existent source should return not_present status."""
        repo = tmp_path / "repo"
        repo.mkdir()
        source = repo / "missing.flac"  # doesn't exist

        output_dir = tmp_path / "output"
        output = output_dir / "track.mp3"

        result = export_file(source, output, MP3_320, repo)

        assert result.status == "not_present"

    def test_export_post_processing(self, tmp_path):
        """flac-pioneer should run metaflac post-processing."""
        repo = tmp_path / "repo"
        repo.mkdir()
        source = repo / "track.flac"
        source.touch()

        output_dir = tmp_path / "output"
        output = output_dir / "track.flac"

        mock_source_info = SourceInfo("flac", 96000, 24, 2, False)

        call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # ffmpeg call - create temp file
                temp_file = Path(cmd[-1])
                temp_file.parent.mkdir(parents=True, exist_ok=True)
                temp_file.touch()
            mock_proc = Mock()
            mock_proc.returncode = 0
            mock_proc.stderr = ""
            return mock_proc

        with patch("music_commander.utils.encoder.probe_source", return_value=mock_source_info):
            with patch("subprocess.run", side_effect=fake_run):
                result = export_file(source, output, FLAC_PIONEER, repo)

        assert result.status == "ok"
        # Should have called both ffmpeg and metaflac
        assert call_count == 2


class TestExportReport:
    """Tests for export report dataclasses."""

    def test_export_result_dataclass(self):
        """ExportResult should be creatable with all fields."""
        result = ExportResult(
            source="track.flac",
            output="track.mp3",
            status="ok",
            preset="mp3-320",
            action="encoded",
            duration_seconds=5.2,
            error_message=None,
        )

        assert result.source == "track.flac"
        assert result.status == "ok"

    def test_export_report_dataclass(self):
        """ExportReport should be creatable with all fields."""
        report = ExportReport(
            version=1,
            timestamp="2026-01-31T12:00:00Z",
            duration_seconds=10.5,
            repository="/repo",
            output_dir="/output",
            preset="mp3-320",
            arguments=["query"],
            summary={"total": 1, "ok": 1},
            results=[],
        )

        assert report.version == 1
        assert report.preset == "mp3-320"

    def test_write_export_report(self, tmp_path):
        """write_export_report should create JSON file."""
        report = ExportReport(
            version=1,
            timestamp="2026-01-31T12:00:00Z",
            duration_seconds=10.5,
            repository="/repo",
            output_dir="/output",
            preset="mp3-320",
            arguments=["query"],
            summary={"total": 1, "ok": 1},
            results=[],
        )

        output_path = tmp_path / "report.json"
        write_export_report(report, output_path)

        assert output_path.exists()
        with output_path.open() as f:
            data = json.load(f)

        assert data["version"] == 1
        assert data["preset"] == "mp3-320"
