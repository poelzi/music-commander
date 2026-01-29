"""Unit tests for view symlink creation."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

from music_commander.view.symlinks import (
    cleanup_output_dir,
    create_symlink_tree,
    sanitize_path_segment,
    sanitize_rendered_path,
)


def _make_track(
    key: str = "k1",
    file: str = "music/track.mp3",
    artist: str | None = "Artist",
    title: str | None = "Title",
    genre: str | None = "Genre",
    bpm: float | None = 140.0,
    rating: int | None = 4,
    **kwargs,
) -> MagicMock:
    """Create a mock CacheTrack."""
    track = MagicMock()
    track.key = key
    track.file = file
    track.artist = artist
    track.title = title
    track.album = kwargs.get("album")
    track.genre = genre
    track.bpm = bpm
    track.rating = rating
    track.key_musical = kwargs.get("key_musical")
    track.year = kwargs.get("year")
    track.tracknumber = kwargs.get("tracknumber")
    track.comment = kwargs.get("comment")
    track.color = kwargs.get("color")
    return track


# ---------------------------------------------------------------------------
# Sanitization tests
# ---------------------------------------------------------------------------


class TestSanitize:
    def test_clean_segment(self) -> None:
        assert sanitize_path_segment("Hello World") == "Hello World"

    def test_unsafe_chars(self) -> None:
        result = sanitize_path_segment('He<ll>o:W"or|ld')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "|" not in result

    def test_strip_dots(self) -> None:
        assert sanitize_path_segment("..hidden..") == "hidden"

    def test_strip_whitespace(self) -> None:
        assert sanitize_path_segment("  spaced  ") == "spaced"

    def test_empty_becomes_unknown(self) -> None:
        assert sanitize_path_segment("") == "Unknown"
        assert sanitize_path_segment("...") == "Unknown"

    def test_full_path_sanitization(self) -> None:
        result = sanitize_rendered_path("Gen:re/Art<ist/Ti>tle")
        assert ":" not in result
        assert "<" not in result
        assert ">" not in result
        # Path separators preserved
        assert result.count("/") == 2


# ---------------------------------------------------------------------------
# Symlink creation tests
# ---------------------------------------------------------------------------


class TestCreateSymlinkTree:
    def test_basic_symlink(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "music").mkdir()
        (repo / "music" / "track.mp3").touch()

        output = tmp_path / "view"
        track = _make_track(file="music/track.mp3")

        created, dupes = create_symlink_tree(
            tracks=[track],
            crates_by_key={},
            template_str="{{ artist }} - {{ title }}",
            output_dir=output,
            repo_path=repo,
        )

        assert created == 1
        assert dupes == 0
        symlink = output / "Artist - Title.mp3"
        assert symlink.is_symlink()

    def test_relative_symlink(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "music").mkdir()
        (repo / "music" / "track.mp3").touch()

        output = tmp_path / "view"
        track = _make_track(file="music/track.mp3")

        create_symlink_tree(
            tracks=[track],
            crates_by_key={},
            template_str="{{ artist }}",
            output_dir=output,
            repo_path=repo,
        )

        symlink = output / "Artist.mp3"
        target = os.readlink(symlink)
        assert not os.path.isabs(target)

    def test_absolute_symlink(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "music").mkdir()
        (repo / "music" / "track.mp3").touch()

        output = tmp_path / "view"
        track = _make_track(file="music/track.mp3")

        create_symlink_tree(
            tracks=[track],
            crates_by_key={},
            template_str="{{ artist }}",
            output_dir=output,
            repo_path=repo,
            absolute=True,
        )

        symlink = output / "Artist.mp3"
        target = os.readlink(symlink)
        assert os.path.isabs(target)

    def test_directory_creation(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "track.mp3").touch()

        output = tmp_path / "view"
        track = _make_track(file="track.mp3")

        create_symlink_tree(
            tracks=[track],
            crates_by_key={},
            template_str="{{ genre }}/{{ artist }} - {{ title }}",
            output_dir=output,
            repo_path=repo,
        )

        assert (output / "Genre").is_dir()
        assert (output / "Genre" / "Artist - Title.mp3").is_symlink()

    def test_duplicate_handling(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "a.mp3").touch()
        (repo / "b.mp3").touch()

        output = tmp_path / "view"
        t1 = _make_track(key="k1", file="a.mp3", artist="Same", title="Track")
        t2 = _make_track(key="k2", file="b.mp3", artist="Same", title="Track")

        created, dupes = create_symlink_tree(
            tracks=[t1, t2],
            crates_by_key={},
            template_str="{{ artist }} - {{ title }}",
            output_dir=output,
            repo_path=repo,
        )

        assert created == 2
        assert dupes == 1
        assert (output / "Same - Track.mp3").is_symlink()
        assert (output / "Same - Track_1.mp3").is_symlink()

    def test_multi_value_crate_expansion(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "track.mp3").touch()

        output = tmp_path / "view"
        track = _make_track(file="track.mp3")

        created, dupes = create_symlink_tree(
            tracks=[track],
            crates_by_key={"k1": ["Festival", "DarkPsy"]},
            template_str="{{ crate }}/{{ artist }}",
            output_dir=output,
            repo_path=repo,
        )

        assert created == 2
        assert (output / "Festival" / "Artist.mp3").is_symlink()
        assert (output / "DarkPsy" / "Artist.mp3").is_symlink()

    def test_no_crate_in_template_no_expansion(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "track.mp3").touch()

        output = tmp_path / "view"
        track = _make_track(file="track.mp3")

        created, _ = create_symlink_tree(
            tracks=[track],
            crates_by_key={"k1": ["Festival", "DarkPsy"]},
            template_str="{{ artist }} - {{ title }}",
            output_dir=output,
            repo_path=repo,
        )

        assert created == 1

    def test_file_extension_preserved(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "track.flac").touch()

        output = tmp_path / "view"
        track = _make_track(file="track.flac")

        create_symlink_tree(
            tracks=[track],
            crates_by_key={},
            template_str="{{ artist }}",
            output_dir=output,
            repo_path=repo,
        )

        assert (output / "Artist.flac").is_symlink()


# ---------------------------------------------------------------------------
# Cleanup tests
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_removes_symlinks(self, tmp_path: Path) -> None:
        output = tmp_path / "view"
        output.mkdir()
        symlink = output / "link.mp3"
        symlink.symlink_to("/tmp/nonexistent")

        removed = cleanup_output_dir(output)
        assert removed == 1
        assert not symlink.exists()

    def test_preserves_regular_files(self, tmp_path: Path) -> None:
        output = tmp_path / "view"
        output.mkdir()
        regular = output / "keep.txt"
        regular.write_text("keep me")
        symlink = output / "remove.mp3"
        symlink.symlink_to("/tmp/nonexistent")

        removed = cleanup_output_dir(output)
        assert removed == 1
        assert regular.exists()

    def test_removes_empty_dirs(self, tmp_path: Path) -> None:
        output = tmp_path / "view"
        subdir = output / "genre" / "artist"
        subdir.mkdir(parents=True)
        symlink = subdir / "track.mp3"
        symlink.symlink_to("/tmp/nonexistent")

        cleanup_output_dir(output)
        assert not subdir.exists()
        assert not (output / "genre").exists()

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        output = tmp_path / "nonexistent"
        removed = cleanup_output_dir(output)
        assert removed == 0
