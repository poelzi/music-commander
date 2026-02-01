"""Download engine for Bandcamp releases.

Handles format resolution, streaming downloads with progress,
and cleanup of interrupted transfers.
"""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path

import requests
from rich.progress import Progress

from music_commander.bandcamp.client import BandcampClient
from music_commander.cache.models import BandcampRelease
from music_commander.exceptions import BandcampError

logger = logging.getLogger(__name__)

# User-friendly name → Bandcamp encoding key
_FORMAT_MAP: dict[str, str] = {
    "flac": "flac",
    "mp3": "mp3-320",
    "mp3-320": "mp3-320",
    "mp3-v0": "mp3-v0",
    "mp3v0": "mp3-v0",
    "aac": "aac-hi",
    "aac-hi": "aac-hi",
    "alac": "alac",
    "wav": "wav",
    "ogg": "vorbis",
    "vorbis": "vorbis",
    "aiff": "aiff-lossless",
    "aiff-lossless": "aiff-lossless",
}

# Bandcamp encoding key → file extension
_EXTENSION_MAP: dict[str, str] = {
    "flac": "zip",
    "mp3-320": "zip",
    "mp3-v0": "zip",
    "aac-hi": "zip",
    "alac": "zip",
    "wav": "zip",
    "vorbis": "zip",
    "aiff-lossless": "zip",
}

_DOWNLOAD_CHUNK_SIZE = 8192


def resolve_format(requested: str, available: list[str]) -> str:
    """Resolve a user-friendly format name to a Bandcamp encoding key.

    Args:
        requested: User-provided format name (e.g., "flac", "mp3").
        available: List of available Bandcamp encoding keys.

    Returns:
        The Bandcamp encoding key.

    Raises:
        BandcampError: If the format is not recognized or not available.
    """
    encoding = _FORMAT_MAP.get(requested.lower())
    if encoding is None:
        valid = ", ".join(sorted(_FORMAT_MAP.keys()))
        raise BandcampError(f"Unknown format '{requested}'. Valid formats: {valid}")

    if encoding not in available:
        available_friendly = ", ".join(sorted(available))
        raise BandcampError(
            f"Format '{requested}' ({encoding}) is not available for this release. "
            f"Available: {available_friendly}"
        )

    return encoding


def format_extension(encoding: str) -> str:
    """Map a Bandcamp encoding key to a file extension."""
    return _EXTENSION_MAP.get(encoding, "zip")


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters unsafe for filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = name.strip(". ")
    return name or "download"


def download_release(
    client: BandcampClient,
    release: BandcampRelease,
    encoding: str,
    output_dir: Path,
    progress: Progress | None = None,
    task_id: int | None = None,
) -> Path:
    """Download a release in the specified format.

    Args:
        client: Authenticated Bandcamp API client.
        release: The release to download.
        encoding: Bandcamp encoding key (e.g., "flac", "mp3-320").
        output_dir: Directory to save the downloaded file.
        progress: Optional Rich Progress instance for progress display.
        task_id: Optional Rich task ID for progress updates.

    Returns:
        Path to the downloaded file.

    Raises:
        BandcampError: If download fails or release has no redownload URL.
    """
    if not release.redownload_url:
        raise BandcampError(f"No redownload URL for {release.band_name} - {release.album_title}")

    # Resolve the format-specific download URL
    download_url = client.resolve_download_url(release.redownload_url, encoding)

    ext = format_extension(encoding)
    artist = _sanitize_filename(release.band_name)
    album = _sanitize_filename(release.album_title)
    filename = f"{artist} - {album}.{ext}"
    final_path = output_dir / filename
    tmp_path = output_dir / f".{filename}.tmp"

    # Skip if already downloaded
    if final_path.exists():
        logger.info("Already exists, skipping: %s", final_path)
        if progress and task_id is not None:
            progress.update(task_id, description=f"[dim]Skipped (exists): {filename}[/dim]")
        return final_path

    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        resp = requests.get(
            download_url,
            stream=True,
            timeout=60,
            headers={"User-Agent": "music-commander/0.1"},
        )
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0)) or None

        if progress and task_id is not None and total_size:
            progress.update(task_id, total=total_size)

        downloaded = 0
        with open(tmp_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress and task_id is not None:
                        progress.update(task_id, completed=downloaded)

        # Rename to final path
        tmp_path.replace(final_path)

        # Extract ZIP files into a subdirectory
        if ext == "zip" and zipfile.is_zipfile(final_path):
            extract_dir = output_dir / f"{artist} - {album}"
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(final_path, "r") as zf:
                zf.extractall(extract_dir)
            final_path.unlink()
            logger.info("Extracted ZIP to %s", extract_dir)
            if progress and task_id is not None:
                progress.update(
                    task_id, description=f"[green]Extracted: {extract_dir.name}[/green]"
                )
            return extract_dir

        return final_path

    except KeyboardInterrupt:
        # Clean up partial download
        tmp_path.unlink(missing_ok=True)
        raise
    except Exception:
        # Clean up partial download on any error
        tmp_path.unlink(missing_ok=True)
        raise
