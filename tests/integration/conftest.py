"""Integration test fixtures for real git-annex operations."""

from __future__ import annotations

import math
import shutil
import struct
import subprocess
import wave
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Track metadata definitions
# ---------------------------------------------------------------------------

TRACK_METADATA = [
    {
        "filename": "track01.mp3",
        "format": "mp3",
        "artist": "AlphaArtist",
        "title": "DarkPulse",
        "album": "TestAlbum1",
        "genre": "Darkpsy",
        "bpm": "148",
        "rating": "5",
        "year": "2024",
        "tracknumber": "1",
        "crate": "Festival",
    },
    {
        "filename": "track02.mp3",
        "format": "mp3",
        "artist": "BetaArtist",
        "title": "NightVibe",
        "album": "TestAlbum2",
        "genre": "Techno",
        "bpm": "130",
        "rating": "4",
        "year": "2023",
        "tracknumber": "2",
        "crate": "Club",
    },
    {
        "filename": "track03.flac",
        "format": "flac",
        "artist": "GammaArtist",
        "title": "ForestDawn",
        "album": "TestAlbum3",
        "genre": "Psytrance",
        "bpm": "145",
        "rating": "5",
        "year": "2024",
        "tracknumber": "3",
        "crate": "Festival",
    },
    {
        "filename": "track04.flac",
        "format": "flac",
        "artist": "DeltaArtist",
        "title": "DeepSpace",
        "album": "TestAlbum4",
        "genre": "Ambient",
        "bpm": "80",
        "rating": "3",
        "year": "2022",
        "tracknumber": "4",
        "crate": "Chill",
    },
    {
        "filename": "track05.aiff",
        "format": "aiff",
        "artist": "EpsilonArtist",
        "title": "RhythmStorm",
        "album": "TestAlbum5",
        "genre": "DnB",
        "bpm": "174",
        "rating": "4",
        "year": "2025",
        "tracknumber": "5",
        "crate": "Club",
    },
    {
        "filename": "track06.aiff",
        "format": "aiff",
        "artist": "ZetaArtist",
        "title": "SilentWave",
        "album": "TestAlbum6",
        "genre": "Ambient",
        "bpm": "70",
        "rating": "2",
        "year": "2021",
        "tracknumber": "6",
        "crate": "Chill",
    },
]

# First 3 tracks are fetched in the partial clone
PRESENT_TRACKS = TRACK_METADATA[:3]
MISSING_TRACKS = TRACK_METADATA[3:]


# ---------------------------------------------------------------------------
# T006: Minimal PNG artwork generator
# ---------------------------------------------------------------------------


def generate_png(width: int = 8, height: int = 8, r: int = 255, g: int = 0, b: int = 0) -> bytes:
    """Generate a minimal valid PNG image without any image library.

    Returns raw PNG bytes for an 8x8 solid-color RGB image.
    """

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        length = struct.pack(">I", len(data))
        crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        return length + chunk_type + data + crc

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR: width, height, bit_depth=8, color_type=2(RGB), compression=0, filter=0, interlace=0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT: raw RGB scanlines with filter byte 0 per row
    raw_data = b""
    for _ in range(height):
        raw_data += b"\x00"  # filter byte (none)
        for _ in range(width):
            raw_data += bytes([r, g, b])
    idat_data = zlib.compress(raw_data)
    idat = _chunk(b"IDAT", idat_data)

    # IEND
    iend = _chunk(b"IEND", b"")

    return signature + ihdr + idat + iend


# ---------------------------------------------------------------------------
# T004: WAV generation + ffmpeg conversion
# ---------------------------------------------------------------------------


def generate_wav(path: Path, duration_s: float = 0.5, freq_hz: int = 440) -> None:
    """Generate a WAV file with a sine wave using stdlib only."""
    sample_rate = 44100
    n_samples = int(sample_rate * duration_s)
    amplitude = 16000  # 16-bit range

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)

        frames = b""
        for i in range(n_samples):
            sample = int(amplitude * math.sin(2 * math.pi * freq_hz * i / sample_rate))
            frames += struct.pack("<h", sample)
        wf.writeframes(frames)


def convert_audio(wav_path: Path, output_path: Path) -> None:
    """Convert a WAV file to another format using ffmpeg."""
    ext = output_path.suffix.lower()
    cmd = ["ffmpeg", "-y", "-i", str(wav_path)]

    if ext == ".mp3":
        cmd.extend(["-q:a", "2"])
    # flac and aiff need no extra flags

    cmd.append(str(output_path))

    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# T005: Mutagen tagging helper
# ---------------------------------------------------------------------------


def tag_audio_file(
    path: Path,
    metadata: dict[str, str],
    artwork_png: bytes,
) -> None:
    """Write metadata tags and artwork to an audio file using mutagen."""
    ext = path.suffix.lower()

    if ext == ".mp3":
        _tag_mp3(path, metadata, artwork_png)
    elif ext == ".flac":
        _tag_flac(path, metadata, artwork_png)
    elif ext in (".aiff", ".aif"):
        _tag_aiff(path, metadata, artwork_png)


def _tag_mp3(path: Path, metadata: dict[str, str], artwork_png: bytes) -> None:
    from mutagen.id3 import APIC, ID3, TALB, TBPM, TCON, TDRC, TIT2, TPE1, TRCK

    tags = ID3()
    tags.add(TPE1(encoding=3, text=[metadata.get("artist", "")]))
    tags.add(TIT2(encoding=3, text=[metadata.get("title", "")]))
    tags.add(TALB(encoding=3, text=[metadata.get("album", "")]))
    tags.add(TCON(encoding=3, text=[metadata.get("genre", "")]))
    tags.add(TBPM(encoding=3, text=[metadata.get("bpm", "")]))
    tags.add(TDRC(encoding=3, text=[metadata.get("year", "")]))
    tags.add(TRCK(encoding=3, text=[metadata.get("tracknumber", "")]))
    tags.add(
        APIC(
            encoding=3,
            mime="image/png",
            type=3,
            desc="Cover",
            data=artwork_png,
        )
    )
    tags.save(path)


def _tag_flac(path: Path, metadata: dict[str, str], artwork_png: bytes) -> None:
    from mutagen.flac import FLAC, Picture

    audio = FLAC(str(path))
    audio["artist"] = metadata.get("artist", "")
    audio["title"] = metadata.get("title", "")
    audio["album"] = metadata.get("album", "")
    audio["genre"] = metadata.get("genre", "")
    audio["bpm"] = metadata.get("bpm", "")
    audio["date"] = metadata.get("year", "")
    audio["tracknumber"] = metadata.get("tracknumber", "")

    pic = Picture()
    pic.type = 3  # Cover (front)
    pic.mime = "image/png"
    pic.desc = "Cover"
    pic.data = artwork_png
    pic.width = 8
    pic.height = 8
    pic.depth = 24
    audio.add_picture(pic)
    audio.save()


def _tag_aiff(path: Path, metadata: dict[str, str], artwork_png: bytes) -> None:
    from mutagen.aiff import AIFF
    from mutagen.id3 import APIC, TALB, TBPM, TCON, TDRC, TIT2, TPE1, TRCK

    audio = AIFF(str(path))
    audio.add_tags()
    audio.tags.add(TPE1(encoding=3, text=[metadata.get("artist", "")]))
    audio.tags.add(TIT2(encoding=3, text=[metadata.get("title", "")]))
    audio.tags.add(TALB(encoding=3, text=[metadata.get("album", "")]))
    audio.tags.add(TCON(encoding=3, text=[metadata.get("genre", "")]))
    audio.tags.add(TBPM(encoding=3, text=[metadata.get("bpm", "")]))
    audio.tags.add(TDRC(encoding=3, text=[metadata.get("year", "")]))
    audio.tags.add(TRCK(encoding=3, text=[metadata.get("tracknumber", "")]))
    audio.tags.add(
        APIC(
            encoding=3,
            mime="image/png",
            type=3,
            desc="Cover",
            data=artwork_png,
        )
    )
    audio.save()


# ---------------------------------------------------------------------------
# T007: audio_files session fixture (defined here, used by WP02+)
# ---------------------------------------------------------------------------


def generate_all_audio_files(output_dir: Path) -> dict[str, Path]:
    """Generate all 6 synthetic audio files with tags and artwork.

    Returns a dict mapping filename to Path.
    """
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not found in PATH")

    artwork = generate_png()
    result: dict[str, Path] = {}

    # Generate a single WAV source
    wav_path = output_dir / "source.wav"
    generate_wav(wav_path)

    for track in TRACK_METADATA:
        filename = track["filename"]
        target = output_dir / filename
        convert_audio(wav_path, target)
        tag_audio_file(target, track, artwork)
        result[filename] = target

    # Clean up WAV source
    wav_path.unlink()

    return result


@pytest.fixture(scope="session")
def audio_files(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Generate 6 synthetic audio files with tags and artwork."""
    output_dir = tmp_path_factory.mktemp("audio")
    return generate_all_audio_files(output_dir)
