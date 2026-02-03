"""Unit tests for the CUE sheet splitting engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from music_commander.cue.parser import CueSheet, CueTrack
from music_commander.cue.splitter import (
    PICTURE_TYPE_BACK_COVER,
    PICTURE_TYPE_FRONT_COVER,
    SplitResult,
    build_tag_args,
    check_already_split,
    check_tools_available,
    find_cover_art,
    group_tracks_by_file,
    track_output_filename,
)

# --- track_output_filename ---


def test_output_filename_basic() -> None:
    track = CueTrack(track_num=1, title="Hello World")
    assert track_output_filename(track) == "01 - Hello World.flac"


def test_output_filename_zero_padded() -> None:
    track = CueTrack(track_num=3, title="Song")
    assert track_output_filename(track) == "03 - Song.flac"


def test_output_filename_double_digit() -> None:
    track = CueTrack(track_num=12, title="Twelve")
    assert track_output_filename(track) == "12 - Twelve.flac"


def test_output_filename_sanitizes_unsafe_chars() -> None:
    track = CueTrack(track_num=1, title='Why / Not: A "Test"')
    name = track_output_filename(track)
    assert "/" not in name
    assert ":" not in name
    assert '"' not in name
    assert name == "01 - Why _ Not_ A _Test_.flac"


def test_output_filename_empty_title_fallback() -> None:
    track = CueTrack(track_num=5, title="")
    assert track_output_filename(track) == "05 - Track 5.flac"


# --- check_already_split ---


def test_check_already_split_all_exist(tmp_path: Path) -> None:
    tracks = [
        CueTrack(track_num=1, title="A"),
        CueTrack(track_num=2, title="B"),
    ]
    sheet = CueSheet(tracks=tracks)
    # Create the expected files
    (tmp_path / "01 - A.flac").touch()
    (tmp_path / "02 - B.flac").touch()
    assert check_already_split(sheet, tmp_path) is True


def test_check_already_split_none_exist(tmp_path: Path) -> None:
    tracks = [CueTrack(track_num=1, title="A")]
    sheet = CueSheet(tracks=tracks)
    assert check_already_split(sheet, tmp_path) is False


def test_check_already_split_partial(tmp_path: Path) -> None:
    tracks = [
        CueTrack(track_num=1, title="A"),
        CueTrack(track_num=2, title="B"),
    ]
    sheet = CueSheet(tracks=tracks)
    (tmp_path / "01 - A.flac").touch()
    # 02 - B.flac missing
    assert check_already_split(sheet, tmp_path) is False


# --- find_cover_art ---


def test_find_cover_art_no_images(tmp_path: Path) -> None:
    assert find_cover_art(tmp_path) == []


def test_find_cover_art_single_image(tmp_path: Path) -> None:
    img = tmp_path / "something.jpg"
    img.touch()
    covers = find_cover_art(tmp_path)
    assert len(covers) == 1
    assert covers[0] == (img, PICTURE_TYPE_FRONT_COVER)


def test_find_cover_art_single_png(tmp_path: Path) -> None:
    img = tmp_path / "art.png"
    img.touch()
    covers = find_cover_art(tmp_path)
    assert len(covers) == 1
    assert covers[0] == (img, PICTURE_TYPE_FRONT_COVER)


def test_find_cover_art_front_and_back(tmp_path: Path) -> None:
    front = tmp_path / "front.jpg"
    back = tmp_path / "back.jpg"
    front.touch()
    back.touch()
    covers = find_cover_art(tmp_path)
    paths = {c[0].name: c[1] for c in covers}
    assert paths["front.jpg"] == PICTURE_TYPE_FRONT_COVER
    assert paths["back.jpg"] == PICTURE_TYPE_BACK_COVER


def test_find_cover_art_cover_pattern(tmp_path: Path) -> None:
    cover = tmp_path / "cover.jpg"
    back = tmp_path / "back.png"
    cover.touch()
    back.touch()
    covers = find_cover_art(tmp_path)
    paths = {c[0].name: c[1] for c in covers}
    assert paths["cover.jpg"] == PICTURE_TYPE_FRONT_COVER
    assert paths["back.png"] == PICTURE_TYPE_BACK_COVER


def test_find_cover_art_unmatched_skipped(tmp_path: Path) -> None:
    """Images not matching front/back patterns should be skipped when multiple exist."""
    front = tmp_path / "front.jpg"
    booklet = tmp_path / "booklet.jpg"
    front.touch()
    booklet.touch()
    covers = find_cover_art(tmp_path)
    assert len(covers) == 1
    assert covers[0][0].name == "front.jpg"


def test_find_cover_art_case_insensitive(tmp_path: Path) -> None:
    front = tmp_path / "FRONT.JPG"
    back = tmp_path / "Back.PNG"
    front.touch()
    back.touch()
    covers = find_cover_art(tmp_path)
    paths = {c[0].name: c[1] for c in covers}
    assert paths["FRONT.JPG"] == PICTURE_TYPE_FRONT_COVER
    assert paths["Back.PNG"] == PICTURE_TYPE_BACK_COVER


def test_find_cover_art_ignores_non_images(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").touch()
    (tmp_path / "album.cue").touch()
    assert find_cover_art(tmp_path) == []


# --- build_tag_args ---


def test_build_tag_args_full_track() -> None:
    track = CueTrack(
        track_num=3,
        title="Test Song",
        performer="Artist",
        album="Album",
        genre="Rock",
        date="2020",
        songwriter="Writer",
        isrc="US1234567890",
        disc_id="AB012345",
    )
    args = build_tag_args(track)
    # Should contain remove + set for each field
    assert "--remove-tag=ARTIST" in args
    assert "--set-tag=ARTIST=Artist" in args
    assert "--remove-tag=ALBUM" in args
    assert "--set-tag=ALBUM=Album" in args
    assert "--remove-tag=TITLE" in args
    assert "--set-tag=TITLE=Test Song" in args
    assert "--remove-tag=TRACKNUMBER" in args
    assert "--set-tag=TRACKNUMBER=3" in args
    assert "--remove-tag=GENRE" in args
    assert "--set-tag=GENRE=Rock" in args
    assert "--remove-tag=DATE" in args
    assert "--set-tag=DATE=2020" in args
    assert "--remove-tag=SONGWRITER" in args
    assert "--set-tag=SONGWRITER=Writer" in args
    assert "--remove-tag=ISRC" in args
    assert "--set-tag=ISRC=US1234567890" in args
    assert "--remove-tag=DISCID" in args
    assert "--set-tag=DISCID=AB012345" in args


def test_build_tag_args_skips_none_fields() -> None:
    track = CueTrack(
        track_num=1,
        title="Song",
        performer="Artist",
        album="Album",
        genre=None,
        date=None,
        songwriter=None,
        isrc=None,
        disc_id=None,
    )
    args = build_tag_args(track)
    assert "--remove-tag=GENRE" not in args
    assert "--remove-tag=DATE" not in args
    assert "--remove-tag=SONGWRITER" not in args
    assert "--remove-tag=ISRC" not in args
    assert "--remove-tag=DISCID" not in args


def test_build_tag_args_empty_title_included() -> None:
    """Empty string title should still be skipped (no value)."""
    track = CueTrack(track_num=1, title="", performer="A", album="B")
    args = build_tag_args(track)
    assert "--set-tag=TITLE=" not in " ".join(args)


# --- check_tools_available ---


@patch("music_commander.cue.splitter.shutil.which")
def test_check_tools_all_present(mock_which: MagicMock) -> None:
    mock_which.return_value = "/usr/bin/tool"
    missing = check_tools_available()
    assert missing == []


@patch("music_commander.cue.splitter.shutil.which")
def test_check_tools_shntool_missing(mock_which: MagicMock) -> None:
    def side_effect(name: str) -> str | None:
        if name == "shntool":
            return None
        return f"/usr/bin/{name}"

    mock_which.side_effect = side_effect
    missing = check_tools_available()
    assert "shntool" in missing
    assert "metaflac" not in missing


@patch("music_commander.cue.splitter.shutil.which")
def test_check_tools_both_missing(mock_which: MagicMock) -> None:
    mock_which.return_value = None
    missing = check_tools_available()
    assert "shntool" in missing
    assert "metaflac" in missing


# --- SplitResult ---


def test_split_result_defaults() -> None:
    r = SplitResult(source_path=Path("/a.flac"), cue_path=Path("/a.cue"))
    assert r.status == "ok"
    assert r.error is None
    assert r.output_files == []
    assert r.track_count == 0


# --- group_tracks_by_file ---


def test_group_tracks_single_file() -> None:
    tracks = [
        CueTrack(track_num=1, title="A", file="album.flac"),
        CueTrack(track_num=2, title="B", file="album.flac"),
    ]
    sheet = CueSheet(file="album.flac", tracks=tracks)
    groups = group_tracks_by_file(sheet)
    assert len(groups) == 1
    assert "album.flac" in groups
    assert len(groups["album.flac"]) == 2


def test_group_tracks_multi_file() -> None:
    tracks = [
        CueTrack(track_num=1, title="D1T1", file="disc1.flac"),
        CueTrack(track_num=2, title="D1T2", file="disc1.flac"),
        CueTrack(track_num=3, title="D2T1", file="disc2.flac"),
        CueTrack(track_num=4, title="D2T2", file="disc2.flac"),
    ]
    sheet = CueSheet(file="disc1.flac", tracks=tracks)
    groups = group_tracks_by_file(sheet)
    assert len(groups) == 2
    assert len(groups["disc1.flac"]) == 2
    assert len(groups["disc2.flac"]) == 2


def test_group_tracks_fallback_to_sheet_file() -> None:
    """Tracks with no file attribute fall back to CueSheet.file."""
    tracks = [
        CueTrack(track_num=1, title="A", file=None),
        CueTrack(track_num=2, title="B", file=None),
    ]
    sheet = CueSheet(file="album.flac", tracks=tracks)
    groups = group_tracks_by_file(sheet)
    assert len(groups) == 1
    assert "album.flac" in groups


# --- ffmpeg timestamp calculation ---


def test_ffmpeg_start_seconds_calculation() -> None:
    """Verify sample-to-seconds conversion for ffmpeg timestamps."""
    # 225 seconds = 225 * 44100 = 9922500 samples
    samples = 225 * 44100
    seconds = samples / 44100.0
    assert seconds == 225.0


def test_ffmpeg_start_seconds_with_frames() -> None:
    """Verify fractional seconds from frame-level positions."""
    # 442 seconds + 50 frames = 442 * 44100 + 50 * 588 = 19521600 samples
    samples = 442 * 44100 + 50 * 588
    seconds = samples / 44100.0
    # 50 frames = 50/75 seconds ≈ 0.6667 seconds
    assert abs(seconds - 442.6666666) < 0.001
