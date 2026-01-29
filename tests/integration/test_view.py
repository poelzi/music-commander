"""Integration tests for view/symlink creation against real git-annex repos."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from music_commander.cache.models import CacheTrack, TrackCrate
from music_commander.search.parser import parse_query
from music_commander.search.query import execute_search
from music_commander.view.symlinks import create_symlink_tree

from .conftest import TRACK_METADATA

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEMPLATE = "{{ genre }}/{{ artist }} - {{ title }}"


def _get_crates_by_key(session: Session) -> dict[str, list[str]]:
    """Build crates_by_key dict from session."""
    crates: dict[str, list[str]] = {}
    for tc in session.query(TrackCrate).all():
        crates.setdefault(tc.key, []).append(tc.crate)
    return crates


# ---------------------------------------------------------------------------
# T023: view without --include-missing
# ---------------------------------------------------------------------------


def test_view_without_include_missing(
    clone_cache_session: Session,
    partial_clone: Path,
    tmp_path: Path,
) -> None:
    """Without --include-missing, only present tracks get symlinks."""
    query = parse_query("rating:>=4")
    tracks = execute_search(clone_cache_session, query)
    assert len(tracks) == 4  # tracks 1,2,3 (present) + 5 (non-present)

    crates = _get_crates_by_key(clone_cache_session)
    created, _dupes = create_symlink_tree(
        tracks,
        crates,
        TEMPLATE,
        tmp_path / "view",
        partial_clone,
        include_missing=False,
    )
    assert created == 3  # only present tracks 1, 2, 3


# ---------------------------------------------------------------------------
# T024: view WITH --include-missing (THE key regression test)
# ---------------------------------------------------------------------------


def test_view_with_include_missing(
    clone_cache_session: Session,
    partial_clone: Path,
    tmp_path: Path,
) -> None:
    """With --include-missing, non-present tracks also get symlinks."""
    query = parse_query("rating:>=4")
    tracks = execute_search(clone_cache_session, query)
    assert len(tracks) == 4

    crates = _get_crates_by_key(clone_cache_session)
    created, _dupes = create_symlink_tree(
        tracks,
        crates,
        TEMPLATE,
        tmp_path / "view",
        partial_clone,
        include_missing=True,
    )
    assert created == 4  # all 4 matching tracks including non-present track 5
    assert created > 3  # strictly more than without flag


# ---------------------------------------------------------------------------
# T025: symlink targets correct
# ---------------------------------------------------------------------------


def test_symlink_targets_correct(
    clone_cache_session: Session,
    partial_clone: Path,
    tmp_path: Path,
) -> None:
    """Symlinks must point to correct repo-relative file paths."""
    query = parse_query("")
    tracks = execute_search(clone_cache_session, query)
    crates = _get_crates_by_key(clone_cache_session)

    output_dir = tmp_path / "view"
    create_symlink_tree(
        tracks,
        crates,
        TEMPLATE,
        output_dir,
        partial_clone,
        include_missing=True,
    )

    symlinks_found = []
    for root, _dirs, files in os.walk(output_dir):
        for f in files:
            fpath = Path(root) / f
            if fpath.is_symlink():
                target = os.readlink(fpath)
                # Resolve relative to symlink's parent
                resolved = (fpath.parent / target).resolve()
                symlinks_found.append((fpath, resolved))

    assert len(symlinks_found) == 6

    # All symlink targets should reference a tracks/ path in the repo.
    # For present files, resolve() follows through .git/annex/objects;
    # for non-present files the symlink is dangling. So we check the
    # *unresolved* relative target contains "tracks/<filename>".
    expected_filenames = {t["filename"] for t in TRACK_METADATA}
    for symlink_path, _ in symlinks_found:
        raw_target = os.readlink(symlink_path)
        target_basename = Path(raw_target).name
        assert target_basename in expected_filenames, (
            f"Symlink {symlink_path} target basename {target_basename} "
            f"not in expected files {expected_filenames}"
        )


# ---------------------------------------------------------------------------
# T026: full repo — no difference with/without flag
# ---------------------------------------------------------------------------


def test_view_full_repo_no_difference(
    origin_cache_session: Session,
    origin_repo: Path,
    tmp_path: Path,
) -> None:
    """When all files are present, --include-missing has no effect."""
    query = parse_query("")
    tracks = execute_search(origin_cache_session, query)
    crates = _get_crates_by_key(origin_cache_session)

    created_without, _ = create_symlink_tree(
        tracks,
        crates,
        TEMPLATE,
        tmp_path / "view1",
        origin_repo,
        include_missing=False,
    )
    created_with, _ = create_symlink_tree(
        tracks,
        crates,
        TEMPLATE,
        tmp_path / "view2",
        origin_repo,
        include_missing=True,
    )
    assert created_without == created_with


# ---------------------------------------------------------------------------
# T027: template rendering produces expected structure
# ---------------------------------------------------------------------------


def test_template_rendering(
    origin_cache_session: Session,
    origin_repo: Path,
    tmp_path: Path,
) -> None:
    """Template must produce expected directory structure."""
    query = parse_query("")
    tracks = execute_search(origin_cache_session, query)
    crates = _get_crates_by_key(origin_cache_session)

    output_dir = tmp_path / "view"
    create_symlink_tree(
        tracks,
        crates,
        TEMPLATE,
        output_dir,
        origin_repo,
        include_missing=True,
    )

    # Check specific paths exist
    assert (output_dir / "Darkpsy" / "AlphaArtist - DarkPulse.mp3").is_symlink()
    assert (output_dir / "Techno" / "BetaArtist - NightVibe.mp3").is_symlink()
    assert (output_dir / "Ambient" / "DeltaArtist - DeepSpace.flac").is_symlink()


# ---------------------------------------------------------------------------
# T028: duplicate handling
# ---------------------------------------------------------------------------


def test_duplicate_handling(
    origin_cache_session: Session,
    origin_repo: Path,
    tmp_path: Path,
) -> None:
    """Duplicate template paths get numeric suffix."""
    query = parse_query("")
    tracks = execute_search(origin_cache_session, query)
    crates = _get_crates_by_key(origin_cache_session)

    output_dir = tmp_path / "view"
    created, duplicates = create_symlink_tree(
        tracks,
        crates,
        "all/track",
        output_dir,
        origin_repo,
        include_missing=True,
    )
    assert created == 6
    # Extensions differ (2 mp3, 2 flac, 2 aiff) so "track.mp3" != "track.flac".
    # Only the second file of each extension collides → 3 duplicates.
    assert duplicates == 3

    # Verify files exist in the all/ directory
    all_dir = output_dir / "all"
    symlinks = [f for f in all_dir.iterdir() if f.is_symlink()]
    assert len(symlinks) == 6
