"""Audio file encoding and format conversion utilities.

This module provides format preset definitions, source file probing, and
encoding decision logic for the files export command.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
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
