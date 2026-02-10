"""Tests for the Anomalistic portal conversion pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_commander.anomalistic.converter import (
    _get_stream_copy_preset,
    _is_lossless_target,
    _is_lossy_source,
    convert_file,
    convert_release,
    download_cover_art,
    render_output_path,
    write_meta_json,
)
from music_commander.utils.encoder import (
    FLAC,
    MP3_320,
    PRESETS,
    WAV,
    FormatPreset,
    SourceInfo,
    build_ffmpeg_command,
)

# ---------------------------------------------------------------------------
# render_output_path tests
# ---------------------------------------------------------------------------


class TestRenderOutputPath:
    """Tests for Jinja2 folder pattern rendering."""

    def test_basic_pattern(self):
        result = render_output_path(
            "{{artist}} - {{album}}",
            artist="XianZai",
            album="Irrational Conjunction",
        )
        assert result == Path("XianZai - Irrational Conjunction")

    def test_pattern_with_all_variables(self):
        result = render_output_path(
            "{{genre}}/{{label}}/{{artist}} - {{album}} ({{year}})",
            genre="DarkPsy",
            label="Anomalistic Records",
            artist="XianZai",
            album="Irrational Conjunction",
            year="2023",
        )
        assert result == Path("DarkPsy/Anomalistic Records/XianZai - Irrational Conjunction (2023)")

    def test_pattern_with_subdirectories(self):
        result = render_output_path(
            "{{genre}}/{{artist}}/{{album}}",
            genre="DarkPsy",
            artist="XianZai",
            album="Irrational Conjunction",
        )
        assert result == Path("DarkPsy") / "XianZai" / "Irrational Conjunction"

    def test_unsafe_characters_removed(self):
        result = render_output_path(
            "{{artist}} - {{album}}",
            artist="Art:ist<>",
            album='Al"bum?*',
        )
        # Unsafe chars stripped
        assert "<" not in str(result)
        assert ">" not in str(result)
        assert '"' not in str(result)
        assert "?" not in str(result)
        assert "*" not in str(result)
        assert ":" not in str(result)

    def test_empty_pattern_fallback(self):
        # Invalid template syntax falls back to "artist - album"
        result = render_output_path(
            "{{",
            artist="XianZai",
            album="Irrational Conjunction",
        )
        assert "XianZai" in str(result)

    def test_undefined_variable_fallback(self):
        result = render_output_path(
            "{{nonexistent}}",
            artist="XianZai",
            album="Test",
        )
        # Should fall back to artist - album
        assert result == Path("XianZai - Test")

    def test_empty_result_returns_unknown(self):
        result = render_output_path(
            "{{artist}}",
            artist="",
        )
        assert result == Path("Unknown")

    def test_conditional_pattern(self):
        result = render_output_path(
            "{% if genre %}{{genre}}/{% endif %}{{artist}} - {{album}}",
            genre="DarkPsy",
            artist="XianZai",
            album="Test",
        )
        assert result == Path("DarkPsy") / "XianZai - Test"

    def test_conditional_pattern_empty_genre(self):
        result = render_output_path(
            "{% if genre %}{{genre}}/{% endif %}{{artist}} - {{album}}",
            genre="",
            artist="XianZai",
            album="Test",
        )
        assert result == Path("XianZai - Test")

    def test_dots_stripped_from_path_components(self):
        result = render_output_path(
            "{{artist}}",
            artist="...test...",
        )
        assert str(result) == "test"

    def test_spaces_stripped_from_path_components(self):
        result = render_output_path(
            "{{artist}}",
            artist="  test  ",
        )
        assert str(result) == "test"


# ---------------------------------------------------------------------------
# write_meta_json tests
# ---------------------------------------------------------------------------


class TestWriteMetaJson:
    """Tests for meta.json generation."""

    def test_basic_meta_json(self, tmp_path):
        tracks = [{"number": 1, "title": "Track 1", "artist": None, "bpm": None}]
        result = write_meta_json(
            tmp_path,
            artist="XianZai",
            album="Irrational Conjunction",
            release_url="https://example.com/release",
            genres=["DarkPsy"],
            labels=["Anomalistic Records"],
            release_date="2023-05-09",
            cover_art_url="https://example.com/cover.jpg",
            credits="Mastered at Studio",
            download_source="wav",
            download_url="https://example.com/download.zip",
            tracks=tracks,
        )
        assert result == tmp_path / "meta.json"
        assert result.exists()

        data = json.loads(result.read_text())
        assert data["artist"] == "XianZai"
        assert data["album"] == "Irrational Conjunction"
        assert data["url"] == "https://example.com/release"
        assert data["genres"] == ["DarkPsy"]
        assert data["labels"] == ["Anomalistic Records"]
        assert data["release_date"] == "2023-05-09"
        assert data["cover_art_url"] == "https://example.com/cover.jpg"
        assert data["credits"] == "Mastered at Studio"
        assert data["download_source"] == "wav"
        assert data["download_url"] == "https://example.com/download.zip"
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["title"] == "Track 1"
        assert "mirrored_at" in data

    def test_meta_json_none_fields(self, tmp_path):
        result = write_meta_json(
            tmp_path,
            artist="Test",
            album="Test",
            release_url="https://example.com",
            genres=[],
            labels=[],
        )
        data = json.loads(result.read_text())
        assert data["release_date"] is None
        assert data["cover_art_url"] is None
        assert data["credits"] is None
        assert data["tracks"] == []

    def test_meta_json_creates_directory(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        result = write_meta_json(
            nested,
            artist="Test",
            album="Test",
            release_url="https://example.com",
            genres=[],
            labels=[],
        )
        assert result.exists()

    def test_meta_json_unicode(self, tmp_path):
        result = write_meta_json(
            tmp_path,
            artist="Тест",
            album="日本語テスト",
            release_url="https://example.com",
            genres=["Ψ-Trance"],
            labels=[],
        )
        data = json.loads(result.read_text())
        assert data["artist"] == "Тест"
        assert data["album"] == "日本語テスト"
        assert data["genres"] == ["Ψ-Trance"]


# ---------------------------------------------------------------------------
# build_ffmpeg_command extra_metadata tests
# ---------------------------------------------------------------------------


class TestBuildFfmpegCommandExtraMetadata:
    """Tests for the extra_metadata parameter on build_ffmpeg_command."""

    def _make_source_info(self, codec="flac"):
        return SourceInfo(
            codec_name=codec,
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            has_cover_art=False,
        )

    def test_extra_metadata_none_no_change(self):
        cmd = build_ffmpeg_command(
            Path("/in.wav"),
            Path("/out.flac"),
            FLAC,
            self._make_source_info("pcm_s16le"),
            extra_metadata=None,
        )
        assert "-metadata" not in cmd

    def test_extra_metadata_comment(self):
        cmd = build_ffmpeg_command(
            Path("/in.wav"),
            Path("/out.flac"),
            FLAC,
            self._make_source_info("pcm_s16le"),
            extra_metadata={"comment": "https://example.com/release"},
        )
        idx = cmd.index("-metadata")
        assert cmd[idx + 1] == "comment=https://example.com/release"

    def test_extra_metadata_multiple_keys(self):
        cmd = build_ffmpeg_command(
            Path("/in.wav"),
            Path("/out.flac"),
            FLAC,
            self._make_source_info("pcm_s16le"),
            extra_metadata={"comment": "URL", "genre": "DarkPsy"},
        )
        metadata_pairs = []
        for i, arg in enumerate(cmd):
            if arg == "-metadata" and i + 1 < len(cmd):
                metadata_pairs.append(cmd[i + 1])
        assert "comment=URL" in metadata_pairs
        assert "genre=DarkPsy" in metadata_pairs

    def test_extra_metadata_with_stream_copy(self):
        cmd = build_ffmpeg_command(
            Path("/in.flac"),
            Path("/out.flac"),
            FLAC,
            self._make_source_info("flac"),
            stream_copy=True,
            extra_metadata={"comment": "test"},
        )
        assert "-codec:a" in cmd
        assert "copy" in cmd
        idx = cmd.index("-metadata")
        assert cmd[idx + 1] == "comment=test"

    def test_backward_compatible_no_extra_metadata(self):
        """Ensure existing callers without extra_metadata still work."""
        cmd = build_ffmpeg_command(
            Path("/in.wav"),
            Path("/out.flac"),
            FLAC,
            self._make_source_info("pcm_s16le"),
        )
        # Should not have -metadata flags (only -map_metadata)
        for i, arg in enumerate(cmd):
            if arg == "-metadata":
                pytest.fail("Found -metadata flag without extra_metadata parameter")


# ---------------------------------------------------------------------------
# download_cover_art tests
# ---------------------------------------------------------------------------


class TestDownloadCoverArt:
    """Tests for cover art download."""

    def test_none_url_returns_none(self, tmp_path):
        assert download_cover_art(None, tmp_path) is None

    @patch("music_commander.anomalistic.converter.requests.get")
    def test_successful_download(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.content = b"\xff\xd8\xff\xe0fake-jpeg"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = download_cover_art("https://example.com/image.jpg", tmp_path)
        assert result is not None
        assert result.name == "cover.jpg"
        assert result.exists()
        assert result.read_bytes() == b"\xff\xd8\xff\xe0fake-jpeg"

    @patch("music_commander.anomalistic.converter.requests.get")
    def test_download_png_extension(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.content = b"fake-png"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = download_cover_art("https://example.com/cover.png", tmp_path)
        assert result is not None
        assert result.name == "cover.png"

    @patch("music_commander.anomalistic.converter.requests.get")
    def test_download_unknown_extension_defaults_jpg(self, mock_get, tmp_path):
        mock_resp = MagicMock()
        mock_resp.content = b"fake-image"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = download_cover_art("https://example.com/image.bmp", tmp_path)
        assert result is not None
        assert result.name == "cover.jpg"

    @patch("music_commander.anomalistic.converter.requests.get")
    def test_download_failure_returns_none(self, mock_get, tmp_path):
        import requests as req

        mock_get.side_effect = req.RequestException("Connection failed")
        result = download_cover_art("https://example.com/cover.jpg", tmp_path)
        assert result is None


# ---------------------------------------------------------------------------
# Lossy/lossless detection tests
# ---------------------------------------------------------------------------


class TestLossyLosslessDetection:
    """Tests for lossy/lossless edge case helpers."""

    def _source(self, codec="mp3"):
        return SourceInfo(
            codec_name=codec,
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            has_cover_art=False,
        )

    def test_mp3_is_lossy(self):
        assert _is_lossy_source(self._source("mp3")) is True

    def test_flac_is_not_lossy(self):
        assert _is_lossy_source(self._source("flac")) is False

    def test_pcm_is_not_lossy(self):
        assert _is_lossy_source(self._source("pcm_s16le")) is False

    def test_flac_is_lossless_target(self):
        assert _is_lossless_target(FLAC) is True

    def test_mp3_is_not_lossless_target(self):
        assert _is_lossless_target(MP3_320) is False

    def test_wav_is_lossless_target(self):
        assert _is_lossless_target(WAV) is True

    def test_stream_copy_preset_for_mp3(self):
        result = _get_stream_copy_preset(self._source("mp3"))
        assert result is not None
        assert result.name == "mp3-320"

    def test_stream_copy_preset_for_flac(self):
        result = _get_stream_copy_preset(self._source("flac"))
        assert result is not None
        assert result.name == "flac"

    def test_stream_copy_preset_unknown_returns_none(self):
        result = _get_stream_copy_preset(self._source("pcm_s16le"))
        assert result is None


# ---------------------------------------------------------------------------
# convert_file tests
# ---------------------------------------------------------------------------


class TestConvertFile:
    """Tests for single file conversion with mocked ffmpeg."""

    def _source_info(self, codec="pcm_s16le"):
        return SourceInfo(
            codec_name=codec,
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            has_cover_art=False,
        )

    @patch("music_commander.anomalistic.converter.subprocess.run")
    @patch("music_commander.anomalistic.converter.probe_source")
    def test_basic_conversion(self, mock_probe, mock_run, tmp_path):
        mock_probe.return_value = self._source_info()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake audio")
        output_dir = tmp_path / "output"

        # The temp file needs to exist for rename to work
        def side_effect(*args, **kwargs):
            # Create the temp output file when ffmpeg "runs"
            cmd = args[0]
            # Find the output path (last arg)
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"converted")
            return mock_proc

        mock_run.side_effect = side_effect

        result = convert_file(input_file, output_dir, FLAC, "https://example.com/release")
        assert result is not None
        assert result.suffix == ".flac"
        assert result.exists()

    @patch("music_commander.anomalistic.converter.probe_source")
    def test_probe_failure_returns_none(self, mock_probe, tmp_path):
        mock_probe.side_effect = RuntimeError("probe failed")

        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake")

        result = convert_file(input_file, tmp_path / "output", FLAC, "https://example.com")
        assert result is None

    @patch("music_commander.anomalistic.converter.subprocess.run")
    @patch("music_commander.anomalistic.converter.probe_source")
    def test_ffmpeg_failure_returns_none(self, mock_probe, mock_run, tmp_path):
        mock_probe.return_value = self._source_info()
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "error"
        mock_run.return_value = mock_proc

        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake")
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        result = convert_file(input_file, output_dir, FLAC, "https://example.com")
        assert result is None

    @patch("music_commander.anomalistic.converter.subprocess.run")
    @patch("music_commander.anomalistic.converter.probe_source")
    def test_lossy_to_lossless_uses_stream_copy(self, mock_probe, mock_run, tmp_path):
        """MP3 source with FLAC target should stream copy as MP3."""
        mock_probe.return_value = self._source_info("mp3")
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        input_file = tmp_path / "input.mp3"
        input_file.write_bytes(b"fake mp3")
        output_dir = tmp_path / "output"

        def side_effect(*args, **kwargs):
            cmd = args[0]
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"tagged mp3")
            return mock_proc

        mock_run.side_effect = side_effect

        result = convert_file(input_file, output_dir, FLAC, "https://example.com")
        assert result is not None
        # Should output as .mp3, not .flac
        assert result.suffix == ".mp3"

        # Verify stream copy was used
        cmd = mock_run.call_args[0][0]
        assert "-codec:a" in cmd
        assert "copy" in cmd

    @patch("music_commander.anomalistic.converter.subprocess.run")
    @patch("music_commander.anomalistic.converter.probe_source")
    def test_format_match_uses_stream_copy(self, mock_probe, mock_run, tmp_path):
        """FLAC source with FLAC target should stream copy + tag."""
        mock_probe.return_value = self._source_info("flac")
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        input_file = tmp_path / "input.flac"
        input_file.write_bytes(b"fake flac")
        output_dir = tmp_path / "output"

        def side_effect(*args, **kwargs):
            cmd = args[0]
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"tagged flac")
            return mock_proc

        mock_run.side_effect = side_effect

        result = convert_file(input_file, output_dir, FLAC, "https://example.com")
        assert result is not None
        assert result.suffix == ".flac"

        cmd = mock_run.call_args[0][0]
        assert "-codec:a" in cmd
        assert "copy" in cmd
        # Should have comment metadata
        assert "-metadata" in cmd
        meta_idx = cmd.index("-metadata")
        assert "comment=" in cmd[meta_idx + 1]

    @patch("music_commander.anomalistic.converter.subprocess.run")
    @patch("music_commander.anomalistic.converter.probe_source")
    def test_non_utf8_ffmpeg_output(self, mock_probe, mock_run, tmp_path):
        """ffmpeg stderr with non-UTF-8 bytes (e.g. Latin-1 metadata) should not crash."""
        mock_probe.return_value = self._source_info()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake audio")
        output_dir = tmp_path / "output"

        def side_effect(*args, **kwargs):
            cmd = args[0]
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"converted")
            return mock_proc

        mock_run.side_effect = side_effect

        result = convert_file(input_file, output_dir, FLAC, "https://example.com/release")
        assert result is not None

        # Verify encoding="utf-8" and errors="replace" are used instead of text=True
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs.get("encoding") == "utf-8"
        assert call_kwargs.get("errors") == "replace"
        assert "text" not in call_kwargs

    @patch("music_commander.anomalistic.converter.subprocess.run")
    @patch("music_commander.anomalistic.converter.probe_source")
    def test_comment_metadata_always_present(self, mock_probe, mock_run, tmp_path):
        """Every conversion should include the release URL as comment."""
        mock_probe.return_value = self._source_info()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        input_file = tmp_path / "input.wav"
        input_file.write_bytes(b"fake")
        output_dir = tmp_path / "output"

        def side_effect(*args, **kwargs):
            cmd = args[0]
            out = Path(cmd[-1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"result")
            return mock_proc

        mock_run.side_effect = side_effect

        convert_file(input_file, output_dir, FLAC, "https://portal.example.com/release")
        cmd = mock_run.call_args[0][0]
        assert "-metadata" in cmd
        meta_idx = cmd.index("-metadata")
        assert cmd[meta_idx + 1] == "comment=https://portal.example.com/release"


# ---------------------------------------------------------------------------
# convert_release tests
# ---------------------------------------------------------------------------


class TestConvertRelease:
    """Tests for release-level conversion orchestration."""

    @patch("music_commander.anomalistic.converter.convert_file")
    @patch("music_commander.anomalistic.converter.discover_artwork")
    def test_uses_archive_artwork_first(self, mock_artwork, mock_convert, tmp_path):
        cover = tmp_path / "extract" / "cover.jpg"
        cover.parent.mkdir(parents=True)
        cover.write_bytes(b"jpeg")
        mock_artwork.return_value = [cover]
        mock_convert.return_value = tmp_path / "output" / "track.flac"

        audio = [tmp_path / "extract" / "track.wav"]
        audio[0].parent.mkdir(parents=True, exist_ok=True)
        audio[0].write_bytes(b"wav")

        convert_release(
            audio,
            tmp_path / "output",
            FLAC,
            "https://example.com",
            cover_art_url="https://example.com/cover.jpg",
            extract_dir=tmp_path / "extract",
        )

        # convert_file should be called with the archive cover, not downloaded
        call_args = mock_convert.call_args
        assert call_args[0][4] == cover  # cover_path argument

    @patch("music_commander.anomalistic.converter.convert_file")
    @patch("music_commander.anomalistic.converter.download_cover_art")
    @patch("music_commander.anomalistic.converter.discover_artwork")
    def test_falls_back_to_download(self, mock_artwork, mock_download, mock_convert, tmp_path):
        mock_artwork.return_value = []
        downloaded_cover = tmp_path / "output" / "cover.jpg"
        mock_download.return_value = downloaded_cover
        mock_convert.return_value = tmp_path / "output" / "track.flac"

        audio = [tmp_path / "track.wav"]
        audio[0].write_bytes(b"wav")

        convert_release(
            audio,
            tmp_path / "output",
            FLAC,
            "https://example.com",
            cover_art_url="https://example.com/cover.jpg",
            extract_dir=tmp_path / "extract",
        )

        mock_download.assert_called_once()
        call_args = mock_convert.call_args
        assert call_args[0][4] == downloaded_cover

    @patch("music_commander.anomalistic.converter.convert_file")
    @patch("music_commander.anomalistic.converter.discover_artwork")
    def test_no_cover_art_available(self, mock_artwork, mock_convert, tmp_path):
        mock_artwork.return_value = []
        mock_convert.return_value = tmp_path / "output" / "track.flac"

        audio = [tmp_path / "track.wav"]
        audio[0].write_bytes(b"wav")

        convert_release(
            audio,
            tmp_path / "output",
            FLAC,
            "https://example.com",
            cover_art_url=None,
            extract_dir=tmp_path / "extract",
        )

        call_args = mock_convert.call_args
        assert call_args[0][4] is None  # No cover path

    @patch("music_commander.anomalistic.converter.convert_file")
    @patch("music_commander.anomalistic.converter.discover_artwork")
    def test_failed_conversions_excluded(self, mock_artwork, mock_convert, tmp_path):
        mock_artwork.return_value = []
        # First file succeeds, second fails
        mock_convert.side_effect = [
            tmp_path / "output" / "track1.flac",
            None,
        ]

        audio = [tmp_path / "t1.wav", tmp_path / "t2.wav"]
        for f in audio:
            f.write_bytes(b"wav")

        results = convert_release(
            audio,
            tmp_path / "output",
            FLAC,
            "https://example.com",
            extract_dir=tmp_path,
        )

        assert len(results) == 1
