"""Unit tests for the CUE sheet parser."""

from __future__ import annotations

from pathlib import Path

import pytest
from music_commander.cue.parser import (
    CueParseError,
    CueSheet,
    CueTrack,
    parse_cue,
    sanitize_filename,
)


def _write_cue(tmp_path: Path, content: str, encoding: str = "utf-8") -> Path:
    """Helper to write a cue file with given content and encoding."""
    cue_file = tmp_path / "test.cue"
    cue_file.write_text(content, encoding=encoding)
    return cue_file


# --- Basic parsing ---


BASIC_CUE = """\
REM GENRE Rock
REM DATE 1995
REM DISCID AB012345
PERFORMER "The Band"
TITLE "Greatest Hits"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "First Song"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "Second Song"
    INDEX 01 03:45:00
  TRACK 03 AUDIO
    TITLE "Third Song"
    INDEX 01 07:22:50
"""


def test_basic_global_metadata(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    assert cue.performer == "The Band"
    assert cue.album == "Greatest Hits"
    assert cue.genre == "Rock"
    assert cue.date == "1995"
    assert cue.disc_id == "AB012345"
    assert cue.file == "album.flac"


def test_basic_track_count(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    assert len(cue.tracks) == 3


def test_basic_track_metadata(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    t1 = cue.tracks[0]
    assert t1.track_num == 1
    assert t1.title == "First Song"
    assert t1.performer == "The Band"  # inherited from global
    assert t1.album == "Greatest Hits"  # inherited from global
    assert t1.genre == "Rock"  # inherited from global
    assert t1.date == "1995"  # inherited from global


def test_basic_track_titles(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    titles = [t.title for t in cue.tracks]
    assert titles == ["First Song", "Second Song", "Third Song"]


# --- Sample position calculation ---


def test_sample_position_zero(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    assert cue.tracks[0].start_samples == 0


def test_sample_position_minutes_seconds(tmp_path: Path) -> None:
    """03:45:00 = 225 seconds = 225 * 44100 = 9922500 samples."""
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    assert cue.tracks[1].start_samples == 225 * 44100


def test_sample_position_with_frames(tmp_path: Path) -> None:
    """07:22:50 = 442 seconds + 50 frames.
    442 * 44100 + 50 * 588 = 19492200 + 29400 = 19521600.
    """
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    expected = 442 * 44100 + 50 * 588
    assert cue.tracks[2].start_samples == expected


def test_end_samples_calculated(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, BASIC_CUE))
    # Track 1 ends where track 2 starts
    assert cue.tracks[0].end_samples == cue.tracks[1].start_samples
    # Track 2 ends where track 3 starts
    assert cue.tracks[1].end_samples == cue.tracks[2].start_samples
    # Last track has no end
    assert cue.tracks[2].end_samples is None


# --- Track-level performer override ---


OVERRIDE_CUE = """\
PERFORMER "Global Artist"
TITLE "Compilation"
FILE "comp.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Song A"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    PERFORMER "Guest Artist"
    TITLE "Song B"
    INDEX 01 04:00:00
  TRACK 03 AUDIO
    TITLE "Song C"
    INDEX 01 08:00:00
"""


def test_track_performer_override(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, OVERRIDE_CUE))
    assert cue.tracks[0].performer == "Global Artist"
    assert cue.tracks[1].performer == "Guest Artist"
    assert cue.tracks[2].performer == "Global Artist"


# --- REM fields ---


REM_CUE = """\
REM GENRE "Electronic"
REM DATE 2020
REM DISCID CD123456
REM COMMENT "Ripped with EAC"
PERFORMER "DJ Test"
TITLE "Mix Album"
FILE "mix.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Intro"
    REM ISRC USRC17607839
    INDEX 01 00:00:00
"""


def test_rem_fields_global(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, REM_CUE))
    assert cue.genre == "Electronic"
    assert cue.date == "2020"
    assert cue.disc_id == "CD123456"
    assert cue.comment == "Ripped with EAC"


def test_rem_isrc_on_track(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, REM_CUE))
    assert cue.tracks[0].isrc == "USRC17607839"


# --- Encoding handling ---


def test_utf8_encoding(tmp_path: Path) -> None:
    content = 'PERFORMER "Ärzte"\nTITLE "Übung"\nFILE "f.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "Müll"\n    INDEX 01 00:00:00\n'
    cue = parse_cue(_write_cue(tmp_path, content, encoding="utf-8"))
    assert cue.performer == "Ärzte"
    assert cue.tracks[0].title == "Müll"


def test_latin1_fallback(tmp_path: Path) -> None:
    content = 'PERFORMER "Ärzte"\nTITLE "Übung"\nFILE "f.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "Müll"\n    INDEX 01 00:00:00\n'
    cue_file = tmp_path / "latin1.cue"
    cue_file.write_bytes(content.encode("latin-1"))
    cue = parse_cue(cue_file)
    assert cue.performer == "Ärzte"


def test_explicit_encoding(tmp_path: Path) -> None:
    content = 'PERFORMER "Ärzte"\nTITLE "Übung"\nFILE "f.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "Müll"\n    INDEX 01 00:00:00\n'
    cue_file = tmp_path / "cp1252.cue"
    cue_file.write_bytes(content.encode("cp1252"))
    cue = parse_cue(cue_file, encoding="cp1252")
    assert cue.performer == "Ärzte"


def test_invalid_encoding_raises(tmp_path: Path) -> None:
    content = 'PERFORMER "Test"\nTITLE "Test"\nFILE "f.flac" WAVE\n  TRACK 01 AUDIO\n    TITLE "T"\n    INDEX 01 00:00:00\n'
    cue_file = _write_cue(tmp_path, content)
    with pytest.raises(CueParseError, match="encoding"):
        parse_cue(cue_file, encoding="nonexistent-encoding")


# --- Multi-FILE cue sheet ---


MULTI_FILE_CUE = """\
PERFORMER "Artist"
TITLE "Double Album"
FILE "disc1.flac" WAVE
  TRACK 01 AUDIO
    TITLE "D1 Track 1"
    INDEX 01 00:00:00
  TRACK 02 AUDIO
    TITLE "D1 Track 2"
    INDEX 01 05:00:00
FILE "disc2.flac" WAVE
  TRACK 03 AUDIO
    TITLE "D2 Track 1"
    INDEX 01 00:00:00
  TRACK 04 AUDIO
    TITLE "D2 Track 2"
    INDEX 01 04:30:00
"""


def test_multi_file_track_count(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, MULTI_FILE_CUE))
    assert len(cue.tracks) == 4


def test_multi_file_track_file_associations(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, MULTI_FILE_CUE))
    assert cue.tracks[0].file == "disc1.flac"
    assert cue.tracks[1].file == "disc1.flac"
    assert cue.tracks[2].file == "disc2.flac"
    assert cue.tracks[3].file == "disc2.flac"


def test_multi_file_end_samples(tmp_path: Path) -> None:
    """Last track of each FILE block should have None end_samples.
    Tracks within a file use the next track's start."""
    cue = parse_cue(_write_cue(tmp_path, MULTI_FILE_CUE))
    # Track 1 ends at track 2's start (same file)
    assert cue.tracks[0].end_samples == cue.tracks[1].start_samples
    # Track 2 is last of disc1 → None (different file boundary)
    assert cue.tracks[1].end_samples is None
    # Track 3 ends at track 4's start (same file)
    assert cue.tracks[2].end_samples == cue.tracks[3].start_samples
    # Track 4 is last of disc2 → None
    assert cue.tracks[3].end_samples is None


# --- INDEX 00 (pregap) ---


PREGAP_CUE = """\
PERFORMER "Artist"
TITLE "Album"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Track 1"
    INDEX 00 00:00:00
    INDEX 01 00:02:00
  TRACK 02 AUDIO
    TITLE "Track 2"
    INDEX 01 04:00:00
"""


def test_pregap_index00_ignored_for_start(tmp_path: Path) -> None:
    """INDEX 00 should not be used as start position; only INDEX 01."""
    cue = parse_cue(_write_cue(tmp_path, PREGAP_CUE))
    # Track 1 starts at INDEX 01 (00:02:00 = 2 seconds * 44100 + 0 frames)
    # Actually 00:02:00 means 0 min, 2 sec, 0 frames = 2 * 44100 = 88200
    assert cue.tracks[0].start_samples == 2 * 44100


# --- Empty/missing fields ---


MINIMAL_CUE = """\
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    INDEX 01 00:00:00
"""


def test_minimal_cue_defaults(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, MINIMAL_CUE))
    assert cue.performer == "Unknown"
    assert cue.album == "Unknown"
    assert cue.genre is None
    assert cue.date is None
    assert len(cue.tracks) == 1
    t = cue.tracks[0]
    assert t.track_num == 1
    assert t.title == ""
    assert t.performer == "Unknown"


# --- Filename sanitization ---


def test_sanitize_basic_unsafe_chars() -> None:
    assert sanitize_filename('Track / With : Bad * Chars "here"') == (
        "Track _ With _ Bad _ Chars _here_"
    )


def test_sanitize_collapses_underscores() -> None:
    assert sanitize_filename("a///b") == "a_b"


def test_sanitize_strips_dots_and_spaces() -> None:
    assert sanitize_filename("  .hidden.  ") == "hidden"


def test_sanitize_preserves_normal_chars() -> None:
    assert sanitize_filename("Normal Track Title (feat. Someone)") == (
        "Normal Track Title (feat. Someone)"
    )


def test_sanitize_question_mark() -> None:
    assert sanitize_filename("Why?") == "Why_"


def test_sanitize_pipe() -> None:
    assert sanitize_filename("A|B") == "A_B"


# --- SONGWRITER field ---


SONGWRITER_CUE = """\
PERFORMER "Singer"
TITLE "Album"
SONGWRITER "Writer"
FILE "album.flac" WAVE
  TRACK 01 AUDIO
    TITLE "Song"
    SONGWRITER "Track Writer"
    INDEX 01 00:00:00
"""


def test_global_songwriter(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, SONGWRITER_CUE))
    assert cue.songwriter == "Writer"


def test_track_songwriter_override(tmp_path: Path) -> None:
    cue = parse_cue(_write_cue(tmp_path, SONGWRITER_CUE))
    assert cue.tracks[0].songwriter == "Track Writer"
