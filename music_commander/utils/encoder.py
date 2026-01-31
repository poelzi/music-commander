"""Audio file encoding and format conversion utilities.

This module provides format preset definitions, source file probing, and
encoding decision logic for the files export command.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class FormatPreset:
    """Defines a target encoding format with all parameters needed for ffmpeg."""

    name: str
    codec: str  # ffmpeg -codec:a value
    container: str  # e.g., ".mp3", ".flac"
    ffmpeg_args: tuple[str, ...]  # additional ffmpeg args
    sample_rate: int | None = None  # None = preserve source
    bit_depth: int | None = None  # None = preserve source
    channels: int | None = None  # None = preserve source
    post_commands: tuple[tuple[str, ...], ...] | None = None  # post-processing
    supports_cover_art: bool = True


@dataclass
class SourceInfo:
    """Probed parameters of a source audio file."""

    codec_name: str
    sample_rate: int
    bit_depth: int
    channels: int
    has_cover_art: bool


@dataclass
class ExportResult:
    """Result of exporting a single file."""

    source: str
    output: str
    status: str  # "ok" | "copied" | "skipped" | "error" | "not_present"
    preset: str
    action: str  # "encoded" | "stream_copied" | "file_copied" | "skipped" | "error"
    duration_seconds: float
    error_message: str | None = None


@dataclass
class ExportReport:
    """Top-level report for an export run."""

    version: int  # Always 1
    timestamp: str  # ISO 8601
    duration_seconds: float
    repository: str
    output_dir: str
    preset: str
    arguments: list[str]
    summary: dict
    results: list[ExportResult] = field(default_factory=list)


# Format preset definitions
MP3_320 = FormatPreset(
    name="mp3-320",
    codec="libmp3lame",
    container=".mp3",
    ffmpeg_args=("-b:a", "320k", "-id3v2_version", "3"),
)

MP3_V0 = FormatPreset(
    name="mp3-v0",
    codec="libmp3lame",
    container=".mp3",
    ffmpeg_args=("-q:a", "0", "-id3v2_version", "3"),
)

FLAC = FormatPreset(
    name="flac",
    codec="flac",
    container=".flac",
    ffmpeg_args=("-compression_level", "8"),
)

FLAC_PIONEER = FormatPreset(
    name="flac-pioneer",
    codec="flac",
    container=".flac",
    ffmpeg_args=("-sample_fmt", "s16", "-ar", "44100", "-ac", "2", "-compression_level", "8"),
    sample_rate=44100,
    bit_depth=16,
    channels=2,
    post_commands=(("metaflac", "--remove-tag=WAVEFORMATEXTENSIBLE_CHANNEL_MASK"),),
)

AIFF = FormatPreset(
    name="aiff",
    codec="pcm_s16be",
    container=".aiff",
    ffmpeg_args=("-write_id3v2", "1"),
)

AIFF_PIONEER = FormatPreset(
    name="aiff-pioneer",
    codec="pcm_s16be",
    container=".aiff",
    ffmpeg_args=("-ar", "44100", "-ac", "2", "-write_id3v2", "1"),
    sample_rate=44100,
    bit_depth=16,
    channels=2,
)

WAV = FormatPreset(
    name="wav",
    codec="pcm_s16le",
    container=".wav",
    ffmpeg_args=("-rf64", "auto"),
    supports_cover_art=False,
)

WAV_PIONEER = FormatPreset(
    name="wav-pioneer",
    codec="pcm_s16le",
    container=".wav",
    ffmpeg_args=("-ar", "44100", "-ac", "2", "-rf64", "auto"),
    sample_rate=44100,
    bit_depth=16,
    channels=2,
    supports_cover_art=False,
)

# Preset registry
PRESETS: dict[str, FormatPreset] = {
    "mp3-320": MP3_320,
    "mp3-v0": MP3_V0,
    "flac": FLAC,
    "flac-pioneer": FLAC_PIONEER,
    "aiff": AIFF,
    "aiff-pioneer": AIFF_PIONEER,
    "wav": WAV,
    "wav-pioneer": WAV_PIONEER,
}

# Extension to preset mapping (for auto-detection)
EXTENSION_TO_PRESET: dict[str, str] = {
    ".mp3": "mp3-320",
    ".flac": "flac",
    ".aiff": "aiff",
    ".aif": "aiff",
    ".wav": "wav",
}

# Codec compatibility mapping (ffprobe codec names -> ffmpeg encoder names)
_CODEC_COMPAT: dict[str, set[str]] = {
    "libmp3lame": {"mp3"},
    "flac": {"flac"},
    "pcm_s16be": {"pcm_s16be", "pcm_s24be"},
    "pcm_s16le": {"pcm_s16le", "pcm_s24le"},
}

# Sample format to bit depth mapping
_SAMPLE_FMT_BIT_DEPTH: dict[str, int] = {
    "s16": 16,
    "s16p": 16,
    "s24": 24,
    "s32": 32,
    "s32p": 32,
    "flt": 32,
    "fltp": 32,
}


def probe_source(file_path: Path) -> SourceInfo:
    """Probe source file audio parameters using ffprobe.

    Args:
        file_path: Path to the audio file to probe.

    Returns:
        SourceInfo with codec, sample rate, bit depth, channels, and cover art status.

    Raises:
        RuntimeError: If ffprobe fails or returns invalid data.
    """
    # Probe audio stream parameters
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,bits_per_raw_sample,sample_fmt,sample_rate,channels",
            "-print_format",
            "json",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed with exit code {proc.returncode}: {proc.stderr}")

    try:
        data = json.loads(proc.stdout)
        stream = data["streams"][0]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise RuntimeError(f"Failed to parse ffprobe output: {e}") from e

    codec_name = stream.get("codec_name", "")
    sample_rate = int(stream.get("sample_rate", 0))
    channels = int(stream.get("channels", 0))

    # Determine bit depth: try bits_per_raw_sample first, then fall back to sample_fmt
    bit_depth = 16  # default
    bits_per_raw_sample = stream.get("bits_per_raw_sample")
    if bits_per_raw_sample and int(bits_per_raw_sample) > 0:
        bit_depth = int(bits_per_raw_sample)
    else:
        sample_fmt = stream.get("sample_fmt", "")
        bit_depth = _SAMPLE_FMT_BIT_DEPTH.get(sample_fmt, 16)

    # Check for embedded cover art (video stream)
    proc_art = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-select_streams",
            "v",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "csv=p=0",
            str(file_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    has_cover_art = bool(proc_art.stdout.strip())

    return SourceInfo(
        codec_name=codec_name,
        sample_rate=sample_rate,
        bit_depth=bit_depth,
        channels=channels,
        has_cover_art=has_cover_art,
    )


def find_cover_art(file_path: Path) -> Path | None:
    """Search for external cover art files in the source file's directory.

    Args:
        file_path: Path to the source audio file.

    Returns:
        Path to the first found cover art file, or None if not found.
    """
    parent_dir = file_path.parent

    # Priority-ordered list of cover art filenames (case-insensitive)
    cover_filenames = [
        "cover.jpg",
        "cover.png",
        "folder.jpg",
        "folder.png",
        "front.jpg",
        "front.png",
    ]

    # List directory once for case-insensitive matching
    try:
        dir_contents = {p.name.lower(): p for p in parent_dir.iterdir() if p.is_file()}
    except OSError:
        return None

    # Search for cover files in priority order
    for filename in cover_filenames:
        if filename in dir_contents:
            return dir_contents[filename]

    return None


def can_copy(source_info: SourceInfo, preset: FormatPreset) -> bool:
    """Determine if a source file can be copied instead of re-encoded.

    Args:
        source_info: Probed source file parameters.
        preset: Target format preset.

    Returns:
        True if source matches target in all required parameters, False otherwise.
    """
    # Check codec compatibility
    codec_matches = False
    for encoder_codec, probe_codecs in _CODEC_COMPAT.items():
        if encoder_codec == preset.codec and source_info.codec_name in probe_codecs:
            codec_matches = True
            break

    if not codec_matches:
        return False

    # Check sample rate constraint
    if preset.sample_rate is not None and source_info.sample_rate != preset.sample_rate:
        return False

    # Check bit depth constraint
    if preset.bit_depth is not None and source_info.bit_depth != preset.bit_depth:
        return False

    # Check channel count constraint
    if preset.channels is not None and source_info.channels != preset.channels:
        return False

    return True


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    preset: FormatPreset,
    source_info: SourceInfo,
    cover_path: Path | None = None,
    *,
    stream_copy: bool = False,
) -> list[str]:
    """Build complete ffmpeg command for encoding.

    Args:
        input_path: Source audio file path.
        output_path: Destination file path.
        preset: Target format preset.
        source_info: Probed source file parameters.
        cover_path: Optional external cover art path.
        stream_copy: If True, use stream copy instead of re-encoding.

    Returns:
        Complete ffmpeg command as a list of strings.
    """
    cmd = ["ffmpeg", "-y", "-i", str(input_path)]

    # Handle cover art inputs and mapping
    if cover_path and preset.supports_cover_art:
        # External cover art
        cmd.extend(["-i", str(cover_path)])
        cmd.extend(["-map", "0:a", "-map", "1:0"])
        cmd.extend(["-codec:v:0", "copy", "-disposition:v:0", "attached_pic"])
    elif source_info.has_cover_art and preset.supports_cover_art:
        # Preserve embedded cover art
        cmd.extend(["-map", "0:a", "-map", "0:v"])
        cmd.extend(["-codec:v:0", "copy"])

    # Audio codec selection
    if stream_copy:
        cmd.extend(["-codec:a", "copy"])
    else:
        # For AIFF/WAV non-pioneer presets, select bit-depth-aware codec
        codec = preset.codec
        if preset.bit_depth is None:  # Preserve source bit depth
            if preset.codec == "pcm_s16be":  # AIFF
                codec = f"pcm_s{source_info.bit_depth}be"
            elif preset.codec == "pcm_s16le":  # WAV
                codec = f"pcm_s{source_info.bit_depth}le"

        cmd.extend(["-codec:a", codec])
        cmd.extend(preset.ffmpeg_args)

    # Metadata copying
    cmd.extend(["-map_metadata", "0"])

    # Output file
    cmd.append(str(output_path))

    return cmd


def export_file(
    file_path: Path,
    output_path: Path,
    preset: FormatPreset,
    repo_path: Path,
    *,
    verbose: bool = False,
) -> ExportResult:
    """Export a single file using the specified preset.

    Args:
        file_path: Source file path (absolute).
        output_path: Destination file path (absolute).
        preset: Target format preset.
        repo_path: Repository root path.
        verbose: If True, log commands and output.

    Returns:
        ExportResult with status and timing information.
    """
    start_time = time.time()
    rel_source = str(file_path.relative_to(repo_path))
    rel_output = output_path.name  # Just filename for output field

    # Check if source file exists
    if not file_path.exists():
        duration = time.time() - start_time
        return ExportResult(
            source=rel_source,
            output=rel_output,
            status="not_present",
            preset=preset.name,
            action="error",
            duration_seconds=duration,
            error_message="Source file not present",
        )

    try:
        # Probe source file
        source_info = probe_source(file_path)

        # Determine cover art path
        cover_path = None
        if not source_info.has_cover_art and preset.supports_cover_art:
            cover_path = find_cover_art(file_path)

        # Determine action: copy vs encode
        is_copy_eligible = can_copy(source_info, preset)

        # File copy path (no re-encoding needed, no cover art needed, no post-processing)
        if is_copy_eligible and cover_path is None and preset.post_commands is None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, output_path)
            duration = time.time() - start_time
            return ExportResult(
                source=rel_source,
                output=rel_output,
                status="copied",
                preset=preset.name,
                action="file_copied",
                duration_seconds=duration,
            )

        # ffmpeg path (stream copy or full encode)
        is_stream_copy = is_copy_eligible and cover_path is not None

        # Create output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Use temporary file for atomic write
        temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

        try:
            # Build and run ffmpeg command
            cmd = build_ffmpeg_command(
                file_path,
                temp_path,
                preset,
                source_info,
                cover_path,
                stream_copy=is_stream_copy,
            )

            if verbose:
                print(f"Running: {' '.join(cmd)}")

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )

            if proc.returncode != 0:
                # Clean up temp file
                if temp_path.exists():
                    temp_path.unlink()

                duration = time.time() - start_time
                return ExportResult(
                    source=rel_source,
                    output=rel_output,
                    status="error",
                    preset=preset.name,
                    action="error",
                    duration_seconds=duration,
                    error_message=proc.stderr[:500] if proc.stderr else "ffmpeg failed",
                )

            # Run post-processing commands
            if preset.post_commands:
                for post_cmd in preset.post_commands:
                    # Append the output file path to the command
                    full_cmd = list(post_cmd) + [str(temp_path)]

                    if verbose:
                        print(f"Running: {' '.join(full_cmd)}")

                    post_proc = subprocess.run(
                        full_cmd,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                    if post_proc.returncode != 0:
                        # Clean up temp file
                        if temp_path.exists():
                            temp_path.unlink()

                        duration = time.time() - start_time
                        return ExportResult(
                            source=rel_source,
                            output=rel_output,
                            status="error",
                            preset=preset.name,
                            action="error",
                            duration_seconds=duration,
                            error_message=f"Post-processing failed: {post_proc.stderr[:500]}",
                        )

            # Atomic rename
            temp_path.rename(output_path)

            duration = time.time() - start_time
            action = "stream_copied" if is_stream_copy else "encoded"
            status = "copied" if is_stream_copy else "ok"

            return ExportResult(
                source=rel_source,
                output=rel_output,
                status=status,
                preset=preset.name,
                action=action,
                duration_seconds=duration,
            )

        except Exception as e:
            # Clean up temp file on any error
            if temp_path.exists():
                temp_path.unlink()
            raise

    except Exception as e:
        duration = time.time() - start_time
        return ExportResult(
            source=rel_source,
            output=rel_output,
            status="error",
            preset=preset.name,
            action="error",
            duration_seconds=duration,
            error_message=str(e)[:500],
        )


def write_export_report(report: ExportReport, output_path: Path) -> None:
    """Write export report to JSON file with atomic write.

    Args:
        report: Export report to serialize.
        output_path: Destination file path.
    """
    # Convert dataclasses to dicts
    from dataclasses import asdict

    report_dict = asdict(report)

    # Write to temp file, then rename (atomic)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    try:
        with temp_path.open("w") as f:
            json.dump(report_dict, f, indent=2)

        temp_path.rename(output_path)
    except Exception:
        # Clean up temp file on error
        if temp_path.exists():
            temp_path.unlink()
        raise
