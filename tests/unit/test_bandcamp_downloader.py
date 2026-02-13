"""Unit tests for the Bandcamp downloader module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_commander.bandcamp.downloader import (
    _sanitize_filename,
    download_release,
    format_extension,
    resolve_format,
)
from music_commander.exceptions import BandcampError


# ---------------------------------------------------------------------------
# resolve_format
# ---------------------------------------------------------------------------


class TestResolveFormat:
    def test_valid_flac(self) -> None:
        assert resolve_format("flac", ["flac", "mp3-320"]) == "flac"

    def test_valid_mp3_alias(self) -> None:
        assert resolve_format("mp3", ["flac", "mp3-320"]) == "mp3-320"

    def test_valid_ogg_alias(self) -> None:
        assert resolve_format("ogg", ["vorbis", "flac"]) == "vorbis"

    def test_case_insensitive(self) -> None:
        assert resolve_format("FLAC", ["flac"]) == "flac"

    def test_unknown_format_raises(self) -> None:
        with pytest.raises(BandcampError, match="Unknown format"):
            resolve_format("invalid", ["flac"])

    def test_unavailable_format_raises(self) -> None:
        with pytest.raises(BandcampError, match="not available"):
            resolve_format("wav", ["flac", "mp3-320"])


# ---------------------------------------------------------------------------
# format_extension
# ---------------------------------------------------------------------------


class TestFormatExtension:
    def test_all_known_encodings_return_zip(self) -> None:
        for enc in ("flac", "mp3-320", "mp3-v0", "aac-hi", "alac", "wav", "vorbis", "aiff-lossless"):
            assert format_extension(enc) == "zip"

    def test_unknown_encoding_defaults_to_zip(self) -> None:
        assert format_extension("unknown") == "zip"


# ---------------------------------------------------------------------------
# _sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    def test_removes_unsafe_chars(self) -> None:
        assert _sanitize_filename('a<b>c:d"e') == "a_b_c_d_e"

    def test_strips_dots_and_spaces(self) -> None:
        assert _sanitize_filename("...name...") == "name"

    def test_empty_returns_download(self) -> None:
        assert _sanitize_filename("") == "download"

    def test_only_unsafe_chars_returns_download(self) -> None:
        assert _sanitize_filename("...") == "download"

    def test_normal_name_unchanged(self) -> None:
        assert _sanitize_filename("Artist - Album") == "Artist - Album"


# ---------------------------------------------------------------------------
# download_release
# ---------------------------------------------------------------------------


def _make_release(
    band_name: str = "Test Artist",
    album_title: str = "Test Album",
    redownload_url: str = "https://bandcamp.com/download?id=123",
) -> MagicMock:
    """Create a mock BandcampRelease."""
    release = MagicMock()
    release.band_name = band_name
    release.album_title = album_title
    release.redownload_url = redownload_url
    return release


class TestDownloadRelease:
    def test_no_redownload_url_raises(self, tmp_path: Path) -> None:
        client = MagicMock()
        release = _make_release(redownload_url="")
        with pytest.raises(BandcampError, match="No redownload URL"):
            download_release(client, release, "flac", tmp_path)

    def test_skips_existing_file(self, tmp_path: Path) -> None:
        client = MagicMock()
        release = _make_release()
        # Pre-create the output file
        expected = tmp_path / "Test Artist - Test Album.zip"
        expected.write_text("existing")
        result = download_release(client, release, "flac", tmp_path)
        assert result == expected
        # stream_get should not have been called
        client.stream_get.assert_not_called()

    def test_calls_stream_get(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.resolve_download_url.return_value = "https://download.bandcamp.com/file.zip"

        # Mock streaming response
        mock_resp = MagicMock()
        mock_resp.headers = {"content-length": "4"}
        mock_resp.iter_content.return_value = [b"data"]
        client.stream_get.return_value = mock_resp

        release = _make_release()
        result = download_release(client, release, "flac", tmp_path)

        client.stream_get.assert_called_once_with(
            "https://download.bandcamp.com/file.zip", timeout=60
        )
        client.resolve_download_url.assert_called_once()
        # Result should be a path (file or directory)
        assert result is not None

    def test_cleans_up_on_error(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.resolve_download_url.return_value = "https://download.bandcamp.com/file.zip"
        client.stream_get.side_effect = ConnectionError("network error")

        release = _make_release()
        with pytest.raises(ConnectionError):
            download_release(client, release, "flac", tmp_path)

        # Temp file should be cleaned up
        tmp_files = list(tmp_path.glob(".*tmp"))
        assert len(tmp_files) == 0
