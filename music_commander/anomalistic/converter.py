"""Conversion pipeline and comment tagging for the Anomalistic portal mirror.

Converts extracted audio files to the target format, embeds release URL as
a comment tag, renders output folder patterns via Jinja2, and writes
per-release meta.json files.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from jinja2 import Environment, StrictUndefined, TemplateSyntaxError, UndefinedError

from music_commander.anomalistic.downloader import discover_artwork
from music_commander.utils.encoder import (
    PRESETS,
    FormatPreset,
    SourceInfo,
    build_ffmpeg_command,
    can_copy,
    probe_source,
)

logger = logging.getLogger(__name__)

# Characters unsafe for filesystem paths
_UNSAFE_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')

# Lossy codecs that should not be upscaled to lossless
_LOSSY_CODECS = frozenset({"mp3", "aac", "vorbis", "opus", "wmav2"})

# Lossless target codecs
_LOSSLESS_CODECS = frozenset({"flac", "pcm_s16be", "pcm_s16le", "pcm_s24be", "pcm_s24le"})


# ---------------------------------------------------------------------------
# Cover art download
# ---------------------------------------------------------------------------


def download_cover_art(cover_art_url: str | None, output_dir: Path) -> Path | None:
    """Download cover art image from URL.

    Args:
        cover_art_url: URL to the cover art image, or None.
        output_dir: Directory to save the image.

    Returns:
        Path to the saved image, or None if unavailable.
    """
    if not cover_art_url:
        return None

    try:
        resp = requests.get(cover_art_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("Failed to download cover art from %s: %s", cover_art_url, e)
        return None

    # Derive extension from URL or Content-Type
    ext = Path(urlparse(cover_art_url).path).suffix
    if ext.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"

    output_dir.mkdir(parents=True, exist_ok=True)
    cover_path = output_dir / f"cover{ext}"
    cover_path.write_bytes(resp.content)
    return cover_path


# ---------------------------------------------------------------------------
# Folder pattern rendering
# ---------------------------------------------------------------------------


def render_output_path(
    pattern: str,
    *,
    genre: str = "",
    label: str = "",
    artist: str = "",
    album: str = "",
    year: str = "",
) -> Path:
    """Render a Jinja2 output pattern into a filesystem path.

    Args:
        pattern: Jinja2 template string for the output path.
        genre: Primary genre name.
        label: Label name.
        artist: Artist name.
        album: Album title.
        year: Release year.

    Returns:
        Sanitized relative Path.
    """
    env = Environment(undefined=StrictUndefined)
    try:
        template = env.from_string(pattern)
        rendered = template.render(
            genre=genre,
            label=label,
            artist=artist,
            album=album,
            year=year,
        )
    except (TemplateSyntaxError, UndefinedError) as e:
        logger.warning("Template rendering failed for pattern %r: %s", pattern, e)
        rendered = f"{artist} - {album}" if artist and album else "Unknown"

    # Sanitize each path component
    parts = []
    for part in Path(rendered).parts:
        clean = _UNSAFE_CHARS.sub("", part).strip(". ")
        if clean:
            parts.append(clean)

    return Path(*parts) if parts else Path("Unknown")


# ---------------------------------------------------------------------------
# meta.json generation
# ---------------------------------------------------------------------------


def write_meta_json(
    output_dir: Path,
    *,
    artist: str,
    album: str,
    release_url: str,
    genres: list[str],
    labels: list[str],
    release_date: str | None = None,
    cover_art_url: str | None = None,
    credits: str | None = None,
    download_source: str = "",
    download_url: str = "",
    tracks: list[dict] | None = None,
) -> Path:
    """Write release metadata to a JSON file.

    Args:
        output_dir: Directory to write meta.json into.
        artist: Artist name.
        album: Album title.
        release_url: Portal release URL.
        genres: List of genre names.
        labels: List of label names.
        release_date: ISO date string or None.
        cover_art_url: Cover art URL or None.
        credits: Credits string or None.
        download_source: Source format used for download (e.g., "wav").
        download_url: URL the archive was downloaded from.
        tracks: List of track dicts with number, title, artist, bpm.

    Returns:
        Path to the written meta.json file.
    """
    meta = {
        "artist": artist,
        "album": album,
        "url": release_url,
        "genres": genres,
        "labels": labels,
        "release_date": release_date,
        "cover_art_url": cover_art_url,
        "credits": credits,
        "download_source": download_source,
        "download_url": download_url,
        "tracks": tracks or [],
        "mirrored_at": datetime.now(timezone.utc).isoformat(),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    meta_path = output_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return meta_path


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------


def _is_lossy_source(source_info: SourceInfo) -> bool:
    """Check if the source codec is lossy."""
    return source_info.codec_name in _LOSSY_CODECS


def _is_lossless_target(preset: FormatPreset) -> bool:
    """Check if the target preset uses a lossless codec."""
    return preset.codec in _LOSSLESS_CODECS


def _get_stream_copy_preset(source_info: SourceInfo) -> FormatPreset | None:
    """Get a preset that matches the source codec for stream copying with tags."""
    if source_info.codec_name == "mp3":
        return PRESETS["mp3-320"]
    if source_info.codec_name == "flac":
        return PRESETS["flac"]
    return None


# ---------------------------------------------------------------------------
# Single-file conversion
# ---------------------------------------------------------------------------


def convert_file(
    input_path: Path,
    output_dir: Path,
    preset: FormatPreset,
    release_url: str,
    cover_path: Path | None = None,
    *,
    verbose: bool = False,
) -> Path | None:
    """Convert a single audio file to the target format with comment tagging.

    Handles edge cases:
    - Format match: stream copy + tag instead of re-encoding.
    - Lossy→lossless: keep lossy format, stream copy + tag, warn.

    Args:
        input_path: Source audio file.
        output_dir: Directory for the converted file.
        preset: Target format preset.
        release_url: URL to embed as comment metadata.
        cover_path: Optional cover art to embed.
        verbose: If True, log commands.

    Returns:
        Path to the converted file, or None on failure.
    """
    try:
        source_info = probe_source(input_path)
    except RuntimeError as e:
        logger.error("Failed to probe %s: %s", input_path, e)
        return None

    actual_preset = preset
    stream_copy = False
    extra_metadata = {"comment": release_url}

    # Edge case: lossy source with lossless target
    if _is_lossy_source(source_info) and _is_lossless_target(preset):
        logger.warning(
            "Source is %s (lossy), keeping as %s instead of converting to %s: %s",
            source_info.codec_name,
            source_info.codec_name.upper(),
            preset.name,
            input_path.name,
        )
        fallback = _get_stream_copy_preset(source_info)
        if fallback:
            actual_preset = fallback
            stream_copy = True
        else:
            # Unknown lossy codec — just stream copy with original container
            actual_preset = preset
            stream_copy = True

    # Edge case: source format matches target — stream copy + tag
    elif can_copy(source_info, preset):
        stream_copy = True

    output_name = input_path.stem + actual_preset.container
    output_path = output_dir / output_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use temp file for atomic write
    temp_path = output_path.with_stem(output_path.stem + ".tmp")

    try:
        cmd = build_ffmpeg_command(
            input_path,
            temp_path,
            actual_preset,
            source_info,
            cover_path,
            stream_copy=stream_copy,
            extra_metadata=extra_metadata,
        )

        if verbose:
            logger.info("Running: %s", " ".join(cmd))

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if proc.returncode != 0:
            logger.error("ffmpeg failed for %s: %s", input_path.name, proc.stderr[:500])
            if temp_path.exists():
                temp_path.unlink()
            return None

        temp_path.rename(output_path)
        return output_path

    except Exception as e:
        logger.error("Conversion error for %s: %s", input_path.name, e)
        if temp_path.exists():
            temp_path.unlink()
        return None


# ---------------------------------------------------------------------------
# Release conversion orchestration
# ---------------------------------------------------------------------------


def convert_release(
    audio_files: list[Path],
    output_dir: Path,
    preset: FormatPreset,
    release_url: str,
    cover_art_url: str | None = None,
    extract_dir: Path | None = None,
    *,
    verbose: bool = False,
) -> list[Path]:
    """Convert all audio files for a release.

    Resolves cover art (archive artwork > downloaded > none), converts
    each file, and copies cover art to the output directory.

    Args:
        audio_files: List of source audio file paths.
        output_dir: Target directory for converted files.
        preset: Target format preset.
        release_url: URL to embed as comment metadata.
        cover_art_url: Portal cover art URL for fallback download.
        extract_dir: Directory where archive was extracted (for artwork discovery).
        verbose: If True, log commands.

    Returns:
        List of paths to successfully converted files.
    """
    # Resolve cover art: archive > download > none
    cover_path: Path | None = None
    if extract_dir:
        artwork_files = discover_artwork(extract_dir)
        if artwork_files:
            cover_path = artwork_files[0]

    if cover_path is None:
        cover_path = download_cover_art(cover_art_url, output_dir)

    converted: list[Path] = []
    for audio_file in audio_files:
        result = convert_file(
            audio_file,
            output_dir,
            preset,
            release_url,
            cover_path,
            verbose=verbose,
        )
        if result:
            converted.append(result)

    # Copy cover art to output directory alongside tracks
    if cover_path and cover_path.parent != output_dir:
        dest_cover = output_dir / cover_path.name
        if not dest_cover.exists():
            output_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cover_path, dest_cover)

    return converted
