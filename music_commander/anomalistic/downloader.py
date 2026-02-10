"""Download and archive extraction for the Anomalistic portal mirror.

Handles downloading ZIP/RAR archives from the portal, extracting them,
and discovering audio and artwork files in the extracted contents.
"""

from __future__ import annotations

import logging
import subprocess
import time
import zipfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

from music_commander.exceptions import AnomaListicError

logger = logging.getLogger(__name__)

_DOWNLOAD_CHUNK_SIZE = 8192
_USER_AGENT = "music-commander/0.1"
_MAX_DOWNLOAD_RETRIES = 3
_DOWNLOAD_BACKOFF_BASE = 2.0

AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".aif", ".aiff", ".ogg", ".opus"})
ARTWORK_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

# Preferred artwork filenames (in priority order)
_ARTWORK_NAMES = {"cover", "front", "folder", "artwork"}


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_archive(
    url: str,
    output_dir: Path,
    progress_callback: Callable[[int, int | None], None] | None = None,
) -> Path:
    """Download an archive file with temp file safety and retry/resume.

    Uses the ``.filename.tmp`` pattern during download, then atomically
    renames on success. Retries with exponential backoff on network errors,
    resuming partial downloads via HTTP Range when the server supports it.

    Args:
        url: Download URL for the archive.
        output_dir: Directory to save the file.
        progress_callback: Optional callback(downloaded_bytes, total_bytes).

    Returns:
        Path to the downloaded archive file.

    Raises:
        AnomaListicError: If download fails after all retries.
    """
    # Derive filename from URL
    parsed = urlparse(url)
    filename = unquote(parsed.path.rsplit("/", 1)[-1])
    if not filename:
        filename = "download.zip"

    final_path = output_dir / filename
    tmp_path = output_dir / f".{filename}.tmp"

    # Skip if already downloaded
    if final_path.exists():
        logger.info("Already exists, skipping: %s", final_path)
        return final_path

    output_dir.mkdir(parents=True, exist_ok=True)

    for attempt in range(_MAX_DOWNLOAD_RETRIES):
        try:
            # Check for partial download from a previous attempt
            downloaded = tmp_path.stat().st_size if tmp_path.exists() else 0
            headers: dict[str, str] = {"User-Agent": _USER_AGENT}
            if downloaded > 0:
                headers["Range"] = f"bytes={downloaded}-"
                logger.info("Resuming download from byte %d", downloaded)

            resp = requests.get(
                url,
                stream=True,
                timeout=(60, 120),
                headers=headers,
            )
            resp.raise_for_status()

            if resp.status_code == 206:
                # Server supports resume — append to existing temp file
                content_range = resp.headers.get("Content-Range", "")
                # Content-Range: bytes <start>-<end>/<total>
                total_size: int | None = None
                if "/" in content_range:
                    try:
                        total_size = int(content_range.rsplit("/", 1)[1])
                    except ValueError:
                        total_size = None
                mode = "ab"
            else:
                # Server returned full response — start from scratch
                downloaded = 0
                total_size = int(resp.headers.get("content-length", 0)) or None
                mode = "wb"

            with open(tmp_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback is not None:
                            progress_callback(downloaded, total_size)

            # Atomic rename
            tmp_path.replace(final_path)
            logger.info("Downloaded: %s (%d bytes)", final_path, downloaded)
            return final_path

        except KeyboardInterrupt:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        except requests.RequestException as e:
            if attempt == _MAX_DOWNLOAD_RETRIES - 1:
                if tmp_path.exists():
                    tmp_path.unlink()
                raise AnomaListicError(f"Download failed for {url}: {e}") from e
            wait = _DOWNLOAD_BACKOFF_BASE * (2**attempt)
            logger.warning(
                "Download failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                _MAX_DOWNLOAD_RETRIES,
                wait,
                e,
            )
            time.sleep(wait)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    # Should not be reached, but satisfy type checker
    raise AnomaListicError(f"Download failed for {url} after {_MAX_DOWNLOAD_RETRIES} attempts")


# ---------------------------------------------------------------------------
# Archive format detection
# ---------------------------------------------------------------------------


def detect_archive_format(file_path: Path) -> str:
    """Detect whether a file is a ZIP or RAR archive.

    Checks file extension first, then falls back to ``zipfile.is_zipfile()``.

    Args:
        file_path: Path to the archive file.

    Returns:
        ``"zip"`` or ``"rar"``.

    Raises:
        AnomaListicError: If format cannot be determined.
    """
    suffix = file_path.suffix.lower()
    if suffix == ".rar":
        return "rar"
    if suffix == ".zip":
        return "zip"
    # Fallback: check magic bytes
    if zipfile.is_zipfile(file_path):
        return "zip"
    raise AnomaListicError(f"Unknown archive format: {file_path}")


# ---------------------------------------------------------------------------
# ZIP extraction
# ---------------------------------------------------------------------------


def extract_zip(archive_path: Path, output_dir: Path) -> Path:
    """Extract a ZIP archive to the output directory.

    If the ZIP contains a single top-level directory, its contents are
    extracted directly into ``output_dir`` to avoid unnecessary nesting.

    Args:
        archive_path: Path to the ZIP file.
        output_dir: Directory to extract into.

    Returns:
        Path to the directory containing extracted files.

    Raises:
        AnomaListicError: If the ZIP file is corrupt or cannot be extracted.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(output_dir)
    except zipfile.BadZipFile as e:
        raise AnomaListicError(f"Corrupt ZIP archive: {archive_path}: {e}") from e

    archive_path.unlink()

    # Flatten if single top-level directory
    _flatten_single_dir(output_dir)

    return output_dir


# ---------------------------------------------------------------------------
# RAR extraction
# ---------------------------------------------------------------------------


def extract_rar(archive_path: Path, output_dir: Path) -> Path:
    """Extract a RAR archive using the ``unrar`` binary.

    Args:
        archive_path: Path to the RAR file.
        output_dir: Directory to extract into.

    Returns:
        Path to the directory containing extracted files.

    Raises:
        AnomaListicError: If ``unrar`` is not installed or extraction fails.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["unrar", "x", "-o+", str(archive_path), str(output_dir) + "/"],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise AnomaListicError(
            "unrar not found. Install unrar-free: nix develop or apt install unrar-free"
        )
    except subprocess.CalledProcessError as e:
        raise AnomaListicError(f"RAR extraction failed: {e.stderr}")

    archive_path.unlink()

    # Flatten if single top-level directory
    _flatten_single_dir(output_dir)

    return output_dir


# ---------------------------------------------------------------------------
# Extract dispatcher
# ---------------------------------------------------------------------------


def extract_archive(archive_path: Path, output_dir: Path) -> Path:
    """Detect archive format and extract accordingly.

    Args:
        archive_path: Path to the archive file.
        output_dir: Directory to extract into.

    Returns:
        Path to the directory containing extracted files.
    """
    fmt = detect_archive_format(archive_path)
    if fmt == "zip":
        return extract_zip(archive_path, output_dir)
    else:
        return extract_rar(archive_path, output_dir)


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def discover_audio_files(directory: Path) -> list[Path]:
    """Find audio files in an extracted directory.

    Args:
        directory: Path to search for audio files.

    Returns:
        Sorted list of audio file paths.
    """
    audio_files = []
    for f in sorted(directory.rglob("*")):
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in AUDIO_EXTENSIONS:
            audio_files.append(f)
    return audio_files


def discover_artwork(directory: Path) -> list[Path]:
    """Find artwork images in an extracted directory.

    Returns all artwork files, ordered with preferred names first
    (``cover.*``, ``front.*``, ``folder.*``, ``artwork.*``), then
    remaining files sorted by size (largest first).

    Args:
        directory: Path to search for artwork.

    Returns:
        List of artwork file paths, ordered by preference. Empty if none found.
    """
    candidates: list[Path] = []
    for f in directory.rglob("*"):
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in ARTWORK_EXTENSIONS:
            candidates.append(f)

    if not candidates:
        return []

    # Partition into preferred and other
    preferred: list[Path] = []
    other: list[Path] = []
    for candidate in candidates:
        stem = candidate.stem.lower()
        if stem in _ARTWORK_NAMES:
            preferred.append(candidate)
        else:
            other.append(candidate)

    # Sort other by file size (largest first)
    other.sort(key=lambda f: f.stat().st_size, reverse=True)

    return preferred + other


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten_single_dir(directory: Path) -> None:
    """If directory contains a single subdirectory (and nothing else), move its contents up.

    This handles the common case where a ZIP contains a wrapper directory
    like ``Artist - Album/track1.wav``.  Applies recursively to handle
    nested wrappers (e.g. ``Album/Album/tracks``).
    """
    while True:
        entries = list(directory.iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            break
        subdir = entries[0]
        # Rename subdir to a temp name first to avoid conflicts when
        # a child item has the same name as the subdir itself
        tmp_name = directory / (subdir.name + ".__flatten_tmp__")
        subdir.rename(tmp_name)
        for item in tmp_name.iterdir():
            item.rename(directory / item.name)
        tmp_name.rmdir()
