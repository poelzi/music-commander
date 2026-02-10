"""Unit tests for Anomalistic portal downloader and archive extraction."""

from __future__ import annotations

import io
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from music_commander.anomalistic.downloader import (
    ARTWORK_EXTENSIONS,
    AUDIO_EXTENSIONS,
    detect_archive_format,
    discover_artwork,
    discover_audio_files,
    download_archive,
    extract_archive,
    extract_rar,
    extract_zip,
)
from music_commander.exceptions import AnomaListicError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_zip(temp_dir: Path, files: dict[str, bytes]) -> Path:
    """Create a ZIP archive with the given files."""
    zip_path = temp_dir / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return zip_path


def _create_zip_with_dir(temp_dir: Path, dirname: str, files: dict[str, bytes]) -> Path:
    """Create a ZIP archive with files inside a subdirectory."""
    zip_path = temp_dir / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in files.items():
            zf.writestr(f"{dirname}/{name}", content)
    return zip_path


# ---------------------------------------------------------------------------
# Download tests
# ---------------------------------------------------------------------------


class TestDownloadArchive:
    """Tests for download_archive()."""

    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_successful_download(self, mock_get, temp_dir: Path):
        content = b"fake zip content"
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-length": str(len(content))}
        resp.iter_content.return_value = [content]
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        result = download_archive(
            "https://www.anomalisticrecords.com/test/Artist%20-%20Album%20-%20WAV.zip",
            temp_dir,
        )

        assert result.name == "Artist - Album - WAV.zip"
        assert result.exists()
        assert result.read_bytes() == content

    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_temp_file_cleaned_on_error(self, mock_get, temp_dir: Path):
        mock_get.side_effect = requests.ConnectionError("fail")

        with pytest.raises(AnomaListicError):
            download_archive("https://example.com/test.zip", temp_dir)

        # No temp files left
        assert list(temp_dir.glob(".*")) == []

    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_skip_existing(self, mock_get, temp_dir: Path):
        # Pre-create the file
        existing = temp_dir / "test.zip"
        existing.write_bytes(b"existing")

        result = download_archive("https://example.com/path/test.zip", temp_dir)

        assert result == existing
        mock_get.assert_not_called()

    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_progress_callback(self, mock_get, temp_dir: Path):
        content = b"chunk1chunk2"
        resp = MagicMock()
        resp.headers = {"content-length": str(len(content))}
        resp.status_code = 200
        resp.iter_content.return_value = [b"chunk1", b"chunk2"]
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        calls = []
        download_archive(
            "https://example.com/path/test.zip",
            temp_dir,
            progress_callback=lambda downloaded, total: calls.append((downloaded, total)),
        )

        assert len(calls) == 2
        assert calls[0] == (6, 12)
        assert calls[1] == (12, 12)

    @patch("music_commander.anomalistic.downloader.time.sleep")
    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_retry_on_connection_error(self, mock_get, mock_sleep, temp_dir: Path):
        """Retry succeeds on second attempt after connection error."""
        content = b"full content"
        good_resp = MagicMock()
        good_resp.status_code = 200
        good_resp.headers = {"content-length": str(len(content))}
        good_resp.iter_content.return_value = [content]
        good_resp.raise_for_status = MagicMock()

        mock_get.side_effect = [
            requests.ConnectionError("connection reset"),
            good_resp,
        ]

        result = download_archive("https://example.com/test.zip", temp_dir)

        assert result.exists()
        assert result.read_bytes() == content
        assert mock_get.call_count == 2
        mock_sleep.assert_called_once()

    @patch("music_commander.anomalistic.downloader.time.sleep")
    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_retry_exhausted(self, mock_get, mock_sleep, temp_dir: Path):
        """All retries fail — raises AnomaListicError and cleans up temp file."""
        mock_get.side_effect = requests.ConnectionError("fail")

        with pytest.raises(AnomaListicError, match="Download failed"):
            download_archive("https://example.com/test.zip", temp_dir)

        assert mock_get.call_count == 3
        # No temp files left behind
        assert list(temp_dir.glob(".*")) == []

    @patch("music_commander.anomalistic.downloader.time.sleep")
    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_resume_partial_download(self, mock_get, mock_sleep, temp_dir: Path):
        """Resumes partial download using Range header on retry."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        # Simulate a partial temp file from a failed first attempt
        tmp_file = temp_dir / ".test.zip.tmp"
        partial = b"partial"
        tmp_file.write_bytes(partial)

        remaining = b" content"
        resp = MagicMock()
        resp.status_code = 206
        resp.headers = {
            "Content-Range": f"bytes {len(partial)}-{len(partial) + len(remaining) - 1}/{len(partial) + len(remaining)}",
        }
        resp.iter_content.return_value = [remaining]
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        result = download_archive("https://example.com/test.zip", temp_dir)

        assert result.exists()
        assert result.read_bytes() == partial + remaining
        # Verify Range header was sent
        call_headers = mock_get.call_args[1].get("headers") or mock_get.call_args.kwargs.get(
            "headers", {}
        )
        assert call_headers.get("Range") == f"bytes={len(partial)}-"

    @patch("music_commander.anomalistic.downloader.time.sleep")
    @patch("music_commander.anomalistic.downloader.requests.get")
    def test_resume_fallback_to_full(self, mock_get, mock_sleep, temp_dir: Path):
        """Server ignores Range header and returns 200 — restarts from scratch."""
        temp_dir.mkdir(parents=True, exist_ok=True)
        tmp_file = temp_dir / ".test.zip.tmp"
        tmp_file.write_bytes(b"stale partial data")

        full_content = b"complete file"
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-length": str(len(full_content))}
        resp.iter_content.return_value = [full_content]
        resp.raise_for_status = MagicMock()
        mock_get.return_value = resp

        result = download_archive("https://example.com/test.zip", temp_dir)

        assert result.exists()
        # Should contain only the full content, not stale partial + full
        assert result.read_bytes() == full_content


# ---------------------------------------------------------------------------
# Archive format detection tests
# ---------------------------------------------------------------------------


class TestDetectArchiveFormat:
    """Tests for detect_archive_format()."""

    def test_zip_extension(self, temp_dir: Path):
        f = temp_dir / "test.zip"
        f.write_bytes(b"not actually a zip")
        assert detect_archive_format(f) == "zip"

    def test_rar_extension(self, temp_dir: Path):
        f = temp_dir / "test.rar"
        f.write_bytes(b"not actually a rar")
        assert detect_archive_format(f) == "rar"

    def test_zip_by_magic(self, temp_dir: Path):
        f = temp_dir / "archive.dat"
        # Create a real ZIP to test magic detection
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("test.txt", "hello")
        assert detect_archive_format(f) == "zip"

    def test_unknown_format(self, temp_dir: Path):
        f = temp_dir / "test.dat"
        f.write_bytes(b"unknown format")
        with pytest.raises(AnomaListicError, match="Unknown archive format"):
            detect_archive_format(f)


# ---------------------------------------------------------------------------
# ZIP extraction tests
# ---------------------------------------------------------------------------


class TestExtractZip:
    """Tests for extract_zip()."""

    def test_basic_extraction(self, temp_dir: Path):
        zip_path = _create_zip(
            temp_dir,
            {
                "track1.wav": b"audio1",
                "track2.wav": b"audio2",
            },
        )
        output = temp_dir / "output"

        result = extract_zip(zip_path, output)

        assert result == output
        assert (output / "track1.wav").exists()
        assert (output / "track2.wav").exists()
        assert not zip_path.exists()  # Archive removed

    def test_flatten_single_directory(self, temp_dir: Path):
        zip_path = _create_zip_with_dir(
            temp_dir,
            "Artist - Album",
            {
                "track1.wav": b"audio1",
                "track2.wav": b"audio2",
            },
        )
        output = temp_dir / "output"

        extract_zip(zip_path, output)

        # Files should be at top level, not in subdirectory
        assert (output / "track1.wav").exists()
        assert not (output / "Artist - Album").exists()

    def test_flatten_nested_same_name_directory(self, temp_dir: Path):
        """Nested dirs with same name: Album/Album/tracks should flatten."""
        zip_path = temp_dir / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("VA - Album - WAV/VA - Album - WAV/track1.wav", b"audio1")
            zf.writestr("VA - Album - WAV/VA - Album - WAV/track2.wav", b"audio2")
        output = temp_dir / "output"

        extract_zip(zip_path, output)

        assert (output / "track1.wav").exists()
        assert (output / "track2.wav").exists()
        assert not (output / "VA - Album - WAV").exists()

    def test_no_flatten_multiple_entries(self, temp_dir: Path):
        zip_path = _create_zip(
            temp_dir,
            {
                "dir1/track1.wav": b"audio1",
                "dir2/track2.wav": b"audio2",
            },
        )
        output = temp_dir / "output"

        extract_zip(zip_path, output)

        assert (output / "dir1" / "track1.wav").exists()
        assert (output / "dir2" / "track2.wav").exists()

    def test_corrupt_zip(self, temp_dir: Path):
        corrupt = temp_dir / "corrupt.zip"
        corrupt.write_bytes(b"not a zip file at all")
        output = temp_dir / "output"

        with pytest.raises(AnomaListicError, match="Corrupt ZIP"):
            extract_zip(corrupt, output)


# ---------------------------------------------------------------------------
# RAR extraction tests
# ---------------------------------------------------------------------------


class TestExtractRar:
    """Tests for extract_rar()."""

    @patch("music_commander.anomalistic.downloader.subprocess.run")
    def test_successful_extraction(self, mock_run, temp_dir: Path):
        rar_path = temp_dir / "test.rar"
        rar_path.write_bytes(b"fake rar")
        output = temp_dir / "output"

        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        extract_rar(rar_path, output)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "unrar"
        assert args[1] == "x"
        assert str(rar_path) in args

    @patch("music_commander.anomalistic.downloader.subprocess.run")
    def test_missing_unrar(self, mock_run, temp_dir: Path):
        rar_path = temp_dir / "test.rar"
        rar_path.write_bytes(b"fake rar")
        output = temp_dir / "output"

        mock_run.side_effect = FileNotFoundError()

        with pytest.raises(AnomaListicError, match="unrar not found"):
            extract_rar(rar_path, output)

    @patch("music_commander.anomalistic.downloader.subprocess.run")
    def test_extraction_failure(self, mock_run, temp_dir: Path):
        rar_path = temp_dir / "test.rar"
        rar_path.write_bytes(b"fake rar")
        output = temp_dir / "output"

        mock_run.side_effect = subprocess.CalledProcessError(1, "unrar", stderr="corrupt archive")

        with pytest.raises(AnomaListicError, match="RAR extraction failed"):
            extract_rar(rar_path, output)


# ---------------------------------------------------------------------------
# extract_archive dispatcher tests
# ---------------------------------------------------------------------------


class TestExtractArchive:
    """Tests for extract_archive() dispatcher."""

    def test_dispatches_zip(self, temp_dir: Path):
        zip_path = _create_zip(temp_dir, {"track.wav": b"audio"})
        output = temp_dir / "output"

        result = extract_archive(zip_path, output)
        assert (output / "track.wav").exists()


# ---------------------------------------------------------------------------
# Audio file discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverAudioFiles:
    """Tests for discover_audio_files()."""

    def test_finds_audio_files(self, temp_dir: Path):
        (temp_dir / "track1.wav").write_bytes(b"a")
        (temp_dir / "track2.flac").write_bytes(b"b")
        (temp_dir / "cover.jpg").write_bytes(b"c")
        (temp_dir / "readme.txt").write_bytes(b"d")

        result = discover_audio_files(temp_dir)
        names = [f.name for f in result]

        assert "track1.wav" in names
        assert "track2.flac" in names
        assert "cover.jpg" not in names
        assert "readme.txt" not in names

    def test_sorted_by_name(self, temp_dir: Path):
        (temp_dir / "02-track.wav").write_bytes(b"a")
        (temp_dir / "01-track.wav").write_bytes(b"b")

        result = discover_audio_files(temp_dir)
        assert result[0].name == "01-track.wav"
        assert result[1].name == "02-track.wav"

    def test_ignores_hidden_files(self, temp_dir: Path):
        (temp_dir / ".DS_Store").write_bytes(b"a")
        (temp_dir / "._track.wav").write_bytes(b"b")
        (temp_dir / "track.wav").write_bytes(b"c")

        result = discover_audio_files(temp_dir)
        assert len(result) == 1
        assert result[0].name == "track.wav"

    def test_recursive(self, temp_dir: Path):
        subdir = temp_dir / "subdir"
        subdir.mkdir()
        (subdir / "track.wav").write_bytes(b"a")

        result = discover_audio_files(temp_dir)
        assert len(result) == 1

    def test_empty_directory(self, temp_dir: Path):
        result = discover_audio_files(temp_dir)
        assert result == []

    def test_all_audio_extensions(self, temp_dir: Path):
        for ext in AUDIO_EXTENSIONS:
            (temp_dir / f"test{ext}").write_bytes(b"a")

        result = discover_audio_files(temp_dir)
        assert len(result) == len(AUDIO_EXTENSIONS)


# ---------------------------------------------------------------------------
# Artwork discovery tests
# ---------------------------------------------------------------------------


class TestDiscoverArtwork:
    """Tests for discover_artwork()."""

    def test_prefers_cover_name(self, temp_dir: Path):
        (temp_dir / "cover.jpg").write_bytes(b"small")
        (temp_dir / "random.png").write_bytes(b"x" * 1000)

        result = discover_artwork(temp_dir)
        assert len(result) == 2
        assert result[0].name == "cover.jpg"

    def test_prefers_front_name(self, temp_dir: Path):
        (temp_dir / "front.jpg").write_bytes(b"art")
        (temp_dir / "back.jpg").write_bytes(b"x" * 1000)

        result = discover_artwork(temp_dir)
        assert len(result) == 2
        assert result[0].name == "front.jpg"

    def test_falls_back_to_largest(self, temp_dir: Path):
        (temp_dir / "small.jpg").write_bytes(b"x")
        (temp_dir / "large.png").write_bytes(b"x" * 1000)

        result = discover_artwork(temp_dir)
        assert len(result) == 2
        assert result[0].name == "large.png"

    def test_no_artwork(self, temp_dir: Path):
        (temp_dir / "track.wav").write_bytes(b"audio")

        result = discover_artwork(temp_dir)
        assert result == []

    def test_ignores_hidden_files(self, temp_dir: Path):
        (temp_dir / ".hidden.jpg").write_bytes(b"x")
        (temp_dir / "cover.jpg").write_bytes(b"y")

        result = discover_artwork(temp_dir)
        assert len(result) == 1
        assert result[0].name == "cover.jpg"

    def test_recursive_search(self, temp_dir: Path):
        subdir = temp_dir / "artwork"
        subdir.mkdir()
        (subdir / "cover.jpg").write_bytes(b"art")

        result = discover_artwork(temp_dir)
        assert len(result) == 1
        assert result[0].name == "cover.jpg"

    def test_returns_all_artwork(self, temp_dir: Path):
        (temp_dir / "cover.jpg").write_bytes(b"small")
        (temp_dir / "back.jpg").write_bytes(b"x" * 500)
        (temp_dir / "inlay.png").write_bytes(b"x" * 1000)

        result = discover_artwork(temp_dir)
        assert len(result) == 3
        # cover.jpg is preferred name, should be first
        assert result[0].name == "cover.jpg"
        # Others sorted by size descending
        assert result[1].name == "inlay.png"
        assert result[2].name == "back.jpg"
