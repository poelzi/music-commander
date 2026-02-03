"""CUE sheet splitting engine.

Splits single-file CD rips into individual FLAC tracks using shntool
(primary) with ffmpeg as fallback. Handles tagging via metaflac and
cover art embedding.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from music_commander.cue.parser import CueSheet, CueTrack, sanitize_filename

logger = logging.getLogger(__name__)

# FLAC picture types per ID3v2 APIC spec
PICTURE_TYPE_FRONT_COVER = 3
PICTURE_TYPE_BACK_COVER = 4

# Patterns for cover art filename matching (case-insensitive)
_FRONT_COVER_PATTERN = re.compile(r".*(front|cover).*", re.IGNORECASE)
_BACK_COVER_PATTERN = re.compile(r".*back.*", re.IGNORECASE)

# Supported source audio extensions
SUPPORTED_EXTENSIONS = {".flac", ".wav", ".ape", ".wv"}

# Extensions where shntool is expected to work directly
SHNTOOL_EXTENSIONS = {".flac", ".wav"}

# Tag mapping: CueTrack field name -> FLAC tag name
TAG_MAPPING: dict[str, str] = {
    "performer": "ARTIST",
    "album": "ALBUM",
    "title": "TITLE",
    "track_num": "TRACKNUMBER",
    "genre": "GENRE",
    "date": "DATE",
    "songwriter": "SONGWRITER",
    "isrc": "ISRC",
    "disc_id": "DISCID",
}


@dataclass
class SplitResult:
    """Outcome of processing one cue/file pair."""

    source_path: Path
    cue_path: Path
    track_count: int = 0
    output_files: list[Path] = field(default_factory=list)
    status: str = "ok"  # ok, skipped, error
    error: str | None = None


def check_tools_available() -> list[str]:
    """Check that required external tools are available.

    Returns:
        List of missing tool names (empty if all present).
    """
    missing = []
    for tool in ("shntool", "metaflac"):
        if shutil.which(tool) is None:
            missing.append(tool)
    return missing


def track_output_filename(track: CueTrack) -> str:
    """Generate the output filename for a split track.

    Format: {tracknum:02d} - {sanitized_title}.flac
    Falls back to "Track {num}" if title is empty.
    """
    title = track.title if track.title else f"Track {track.track_num}"
    safe_title = sanitize_filename(title)
    return f"{track.track_num:02d} - {safe_title}.flac"


def check_already_split(cue_sheet: CueSheet, output_dir: Path) -> bool:
    """Check if all expected output files already exist.

    Returns:
        True if ALL expected output files exist (fully split).
    """
    for track in cue_sheet.tracks:
        expected = output_dir / track_output_filename(track)
        if not expected.exists():
            return False
    return True


def find_cover_art(directory: Path) -> list[tuple[Path, int]]:
    """Find image files in a directory and classify them by type.

    Returns:
        List of (path, picture_type) tuples. Picture types:
        - 3: front cover
        - 4: back cover
    """
    image_extensions = {".jpg", ".jpeg", ".png"}
    images = [
        f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in image_extensions
    ]

    if not images:
        return []

    # Single image: use as front cover
    if len(images) == 1:
        return [(images[0], PICTURE_TYPE_FRONT_COVER)]

    # Multiple images: classify by filename
    covers: list[tuple[Path, int]] = []
    for img in images:
        name = img.stem
        if _FRONT_COVER_PATTERN.match(name):
            covers.append((img, PICTURE_TYPE_FRONT_COVER))
        elif _BACK_COVER_PATTERN.match(name):
            covers.append((img, PICTURE_TYPE_BACK_COVER))
        # Skip unmatched images (booklet pages, etc.)

    return covers


def build_tag_args(track: CueTrack) -> list[str]:
    """Build metaflac arguments for tagging a track.

    Returns:
        List of metaflac arguments (without the filename).
    """
    args: list[str] = []
    for attr, tag_name in TAG_MAPPING.items():
        value = getattr(track, attr, None)
        if value is None:
            continue
        # Convert track_num to string
        str_value = str(value)
        if not str_value:
            continue
        args.append(f"--remove-tag={tag_name}")
        args.append(f"--set-tag={tag_name}={str_value}")
    return args


def tag_track(track: CueTrack, file_path: Path) -> None:
    """Tag a FLAC file with metadata from a CueTrack."""
    tag_args = build_tag_args(track)
    if not tag_args:
        return

    cmd = ["metaflac"] + tag_args + [str(file_path)]
    logger.debug("Tagging: %s", cmd)
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def add_replay_gain(file_paths: list[Path]) -> None:
    """Add ReplayGain tags to a set of FLAC files (album-level)."""
    if not file_paths:
        return
    cmd = ["metaflac", "--add-replay-gain"] + [str(f) for f in file_paths]
    logger.debug("ReplayGain: %s", cmd)
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def embed_cover_art(file_path: Path, covers: list[tuple[Path, int]]) -> None:
    """Embed cover art images into a FLAC file."""
    if not covers:
        return

    cmd = ["metaflac"]
    for img_path, picture_type in covers:
        cmd.append(f"--import-picture-from={picture_type}||||{img_path}")
    cmd.append(str(file_path))

    logger.debug("Cover art: %s", cmd)
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def split_with_shntool(
    cue_path: Path,
    source_path: Path,
    output_dir: Path,
) -> list[Path]:
    """Split a source file using shntool.

    Args:
        cue_path: Path to the .cue file.
        source_path: Path to the source audio file.
        output_dir: Directory for output files.

    Returns:
        List of output file paths created by shntool.

    Raises:
        subprocess.CalledProcessError: If shntool fails.
    """
    cmd = [
        "shntool",
        "split",
        "-t",
        "%n - %t",
        "-o",
        "flac",
        "-f",
        str(cue_path),
        "-d",
        str(output_dir),
        "-O",
        "never",
        str(source_path),
    ]
    logger.debug("shntool: %s", cmd)
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    # Collect output files (shntool creates them in output_dir)
    output_files = sorted(output_dir.glob("*.flac"))
    # Filter out the original source if it's in the same directory
    output_files = [f for f in output_files if f != source_path]
    return output_files


def split_with_ffmpeg(
    cue_sheet: CueSheet,
    source_path: Path,
    output_dir: Path,
    tracks: list[CueTrack] | None = None,
) -> list[Path]:
    """Split a source file using ffmpeg (fallback for APE/WV).

    Args:
        cue_sheet: Parsed cue sheet.
        source_path: Path to the source audio file.
        output_dir: Directory for output files.
        tracks: Specific tracks to split (defaults to all tracks in cue_sheet).

    Returns:
        List of output file paths.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    target_tracks = tracks if tracks is not None else cue_sheet.tracks
    output_files: list[Path] = []

    for track in target_tracks:
        output_name = track_output_filename(track)
        output_path = output_dir / output_name

        start_sec = track.start_samples / 44100.0
        cmd = [
            "ffmpeg",
            "-i",
            str(source_path),
            "-ss",
            f"{start_sec:.6f}",
        ]
        if track.end_samples is not None:
            end_sec = track.end_samples / 44100.0
            cmd.extend(["-to", f"{end_sec:.6f}"])
        cmd.extend(
            [
                "-c:a",
                "flac",
                "-n",  # don't overwrite
                str(output_path),
            ]
        )

        logger.debug("ffmpeg: %s", cmd)
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        output_files.append(output_path)

    return output_files


def split_cue(
    cue_sheet: CueSheet,
    cue_path: Path,
    source_path: Path,
    output_dir: Path,
    force: bool = False,
) -> SplitResult:
    """Split a source audio file according to a cue sheet.

    This is the main entry point for splitting. It:
    1. Checks if already split (skip unless force)
    2. Splits with shntool (or ffmpeg fallback for APE/WV)
    3. Tags each output track
    4. Adds ReplayGain
    5. Embeds cover art

    Args:
        cue_sheet: Parsed CueSheet.
        cue_path: Path to the .cue file.
        source_path: Path to the source audio file.
        output_dir: Directory for output files (usually same as source).
        force: If True, re-split even if output exists.

    Returns:
        SplitResult with status and details.
    """
    result = SplitResult(
        source_path=source_path,
        cue_path=cue_path,
        track_count=len(cue_sheet.tracks),
    )

    # Check if already split
    if not force and check_already_split(cue_sheet, output_dir):
        result.status = "skipped"
        return result

    # If force, remove existing output files first
    if force:
        for track in cue_sheet.tracks:
            existing = output_dir / track_output_filename(track)
            if existing.exists():
                existing.unlink()

    # Split
    ext = source_path.suffix.lower()
    try:
        if ext in SHNTOOL_EXTENSIONS:
            output_files = split_with_shntool(cue_path, source_path, output_dir)
        elif ext in SUPPORTED_EXTENSIONS:
            # APE/WV: try shntool first, fall back to ffmpeg
            try:
                output_files = split_with_shntool(cue_path, source_path, output_dir)
            except subprocess.CalledProcessError:
                logger.info("shntool failed for %s, falling back to ffmpeg", source_path.name)
                output_files = split_with_ffmpeg(cue_sheet, source_path, output_dir)
        else:
            result.status = "error"
            result.error = f"Unsupported format: {ext}"
            return result
    except subprocess.CalledProcessError as e:
        result.status = "error"
        result.error = f"Split failed: {e.stderr or str(e)}"
        return result

    result.output_files = output_files

    # Tag each output track
    try:
        for track in cue_sheet.tracks:
            expected_path = output_dir / track_output_filename(track)
            if expected_path.exists():
                tag_track(track, expected_path)
    except subprocess.CalledProcessError as e:
        result.status = "error"
        result.error = f"Tagging failed: {e.stderr or str(e)}"
        return result

    # Add ReplayGain (needs all tracks at once for album gain)
    existing_outputs = [
        output_dir / track_output_filename(t)
        for t in cue_sheet.tracks
        if (output_dir / track_output_filename(t)).exists()
    ]
    try:
        add_replay_gain(existing_outputs)
    except subprocess.CalledProcessError as e:
        # ReplayGain failure is non-fatal
        logger.warning("ReplayGain failed: %s", e.stderr or str(e))

    # Embed cover art
    covers = find_cover_art(output_dir)
    if covers:
        try:
            for track_file in existing_outputs:
                embed_cover_art(track_file, covers)
        except subprocess.CalledProcessError as e:
            # Cover art failure is non-fatal
            logger.warning("Cover art embedding failed: %s", e.stderr or str(e))

    result.status = "ok"
    return result
