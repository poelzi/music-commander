"""End-to-end integration test for cache → search → view pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.builder import build_cache, refresh_cache
from music_commander.cache.models import CacheBase, CacheState, CacheTrack, TrackCrate
from music_commander.cache.session import CACHE_DB_NAME, delete_cache
from music_commander.search.parser import parse_query
from music_commander.search.query import execute_search
from music_commander.view.symlinks import cleanup_output_dir, create_symlink_tree
from music_commander.view.template import render_path

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Simulated git-annex metadata log contents for two tracks
_LOG_TRACK1 = (
    "1700000000s artist +TestArtist title +TestTitle genre +Darkpsy "
    "bpm +148 rating +5 key +Am crate +Festival crate +Live\n"
)
_LOG_TRACK2 = (
    "1700000001s artist +AmbientArtist title +CalmSong genre +Ambient bpm +80 rating +3 key +C\n"
)

# Simulated ls-tree output
_LS_TREE = (
    "100644 blob aaa111\tabc/def/KEY1--file1.mp3.log.met\n"
    "100644 blob bbb222\tabc/def/KEY2--file2.mp3.log.met\n"
)

# Simulated cat-file --batch output
_CAT_FILE = (
    f"aaa111 blob {len(_LOG_TRACK1)}\n{_LOG_TRACK1}bbb222 blob {len(_LOG_TRACK2)}\n{_LOG_TRACK2}"
)

# Simulated annex find output (all files — for build_key_to_file_map with --include=*)
_ANNEX_FIND_ALL = "KEY1--file1.mp3\tdarkpsy/Track.mp3\nKEY2--file2.mp3\tambient/Calm.mp3\n"

# Simulated annex find output (present files only — for build_present_keys)
_ANNEX_FIND_PRESENT = "KEY1--file1.mp3\nKEY2--file2.mp3\n"


def _mock_subprocess_run(args, **kwargs):
    """Mock subprocess.run for git commands."""
    cmd = args[0] if args else ""
    if args[:3] == ["git", "ls-tree", "-r"]:
        result = MagicMock()
        result.stdout = _LS_TREE
        return result
    elif args[:2] == ["git", "cat-file"]:
        result = MagicMock()
        result.stdout = _CAT_FILE
        return result
    elif args[:3] == ["git", "annex", "find"]:
        result = MagicMock()
        # --include=* returns all files with key\tfile format
        if "--include=*" in args:
            result.stdout = _ANNEX_FIND_ALL
        else:
            # Plain git annex find returns only present keys
            result.stdout = _ANNEX_FIND_PRESENT
        return result
    elif args[:2] == ["git", "rev-parse"]:
        result = MagicMock()
        result.stdout = "abc123commit\n"
        return result
    elif args[:2] == ["git", "diff-tree"]:
        result = MagicMock()
        result.stdout = ""
        return result
    raise ValueError(f"Unmocked git command: {args}")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a fake repo directory with source files."""
    (tmp_path / "darkpsy").mkdir()
    (tmp_path / "darkpsy" / "Track.mp3").write_text("audio1")
    (tmp_path / "ambient").mkdir()
    (tmp_path / "ambient" / "Calm.mp3").write_text("audio2")
    return tmp_path


@pytest.fixture
def session() -> Session:
    """Create an in-memory SQLAlchemy session."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()
    return sess


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestE2EPipeline:
    """Full pipeline: build cache → search → view → incremental refresh."""

    @patch("music_commander.cache.builder.subprocess.run", side_effect=_mock_subprocess_run)
    def test_build_cache(self, mock_run, repo: Path, session: Session) -> None:
        """T045-1: Build cache from mocked git-annex data."""
        count = build_cache(repo, session)

        assert count == 2
        tracks = session.query(CacheTrack).all()
        assert len(tracks) == 2

        # Verify track data
        t1 = session.query(CacheTrack).filter_by(key="KEY1--file1.mp3").first()
        assert t1 is not None
        assert t1.artist == "TestArtist"
        assert t1.genre == "Darkpsy"
        assert t1.bpm == 148.0
        assert t1.file == "darkpsy/Track.mp3"

        # Verify crates
        crates = session.query(TrackCrate).filter_by(key="KEY1--file1.mp3").all()
        crate_names = sorted(c.crate for c in crates)
        assert crate_names == ["Festival", "Live"]

        # Verify FTS5
        fts_rows = session.execute(
            text("SELECT key FROM tracks_fts WHERE tracks_fts MATCH 'TestArtist'")
        ).fetchall()
        assert len(fts_rows) == 1

        # Verify cache state
        state = session.query(CacheState).first()
        assert state is not None
        assert state.track_count == 2
        assert state.annex_branch_commit == "abc123commit"

    @patch("music_commander.cache.builder.subprocess.run", side_effect=_mock_subprocess_run)
    def test_search_after_build(self, mock_run, repo: Path, session: Session) -> None:
        """T045-2: Search the cache after building it."""
        build_cache(repo, session)

        # Text search
        query = parse_query("TestArtist")
        results = execute_search(session, query)
        assert len(results) == 1
        assert results[0].artist == "TestArtist"

        # Field filter
        query = parse_query("genre:Darkpsy")
        results = execute_search(session, query)
        assert len(results) == 1
        assert results[0].genre == "Darkpsy"

        # BPM range
        query = parse_query("bpm:>100")
        results = execute_search(session, query)
        assert len(results) == 1
        assert results[0].bpm == 148.0

        # Negation
        query = parse_query("-genre:Ambient")
        results = execute_search(session, query)
        assert len(results) == 1
        assert results[0].genre == "Darkpsy"

        # OR query
        query = parse_query("genre:Darkpsy OR genre:Ambient")
        results = execute_search(session, query)
        assert len(results) == 2

    @patch("music_commander.cache.builder.subprocess.run", side_effect=_mock_subprocess_run)
    def test_view_after_search(self, mock_run, repo: Path, session: Session) -> None:
        """T045-3: Create a symlink view from search results."""
        build_cache(repo, session)

        # Search for Darkpsy tracks
        query = parse_query("genre:Darkpsy")
        tracks = execute_search(session, query)
        assert len(tracks) == 1

        # Load crates
        track_keys = [t.key for t in tracks]
        crate_rows = session.query(TrackCrate).filter(TrackCrate.key.in_(track_keys)).all()
        crates_by_key: dict[str, list[str]] = {}
        for row in crate_rows:
            crates_by_key.setdefault(row.key, []).append(row.crate)

        # Create view with genre/artist - title template
        output_dir = repo / "views"
        created, duplicates = create_symlink_tree(
            tracks=tracks,
            crates_by_key=crates_by_key,
            template_str="{{ genre }}/{{ artist }} - {{ title }}",
            output_dir=output_dir,
            repo_path=repo,
            absolute=False,
            include_missing=True,
        )

        assert created == 1
        assert duplicates == 0
        link = output_dir / "Darkpsy" / "TestArtist - TestTitle.mp3"
        assert link.is_symlink()
        assert link.resolve() == (repo / "darkpsy" / "Track.mp3").resolve()

    @patch("music_commander.cache.builder.subprocess.run", side_effect=_mock_subprocess_run)
    def test_view_with_crate_expansion(self, mock_run, repo: Path, session: Session) -> None:
        """T045-3b: Crate expansion creates multiple symlinks per track."""
        build_cache(repo, session)

        query = parse_query("genre:Darkpsy")
        tracks = execute_search(session, query)

        track_keys = [t.key for t in tracks]
        crate_rows = session.query(TrackCrate).filter(TrackCrate.key.in_(track_keys)).all()
        crates_by_key: dict[str, list[str]] = {}
        for row in crate_rows:
            crates_by_key.setdefault(row.key, []).append(row.crate)

        output_dir = repo / "views_crate"
        created, duplicates = create_symlink_tree(
            tracks=tracks,
            crates_by_key=crates_by_key,
            template_str="{{ crate }}/{{ artist }} - {{ title }}",
            output_dir=output_dir,
            repo_path=repo,
            absolute=False,
            include_missing=True,
        )

        # Track1 has 2 crates → 2 symlinks
        assert created == 2
        assert (output_dir / "Festival" / "TestArtist - TestTitle.mp3").is_symlink()
        assert (output_dir / "Live" / "TestArtist - TestTitle.mp3").is_symlink()

    @patch("music_commander.cache.builder.subprocess.run", side_effect=_mock_subprocess_run)
    def test_cleanup_and_rebuild_view(self, mock_run, repo: Path, session: Session) -> None:
        """T045-4: Cleanup old symlinks and rebuild view."""
        build_cache(repo, session)

        query = parse_query("genre:Darkpsy OR genre:Ambient")
        tracks = execute_search(session, query)

        output_dir = repo / "views"
        created, _ = create_symlink_tree(
            tracks=tracks,
            crates_by_key={},
            template_str="{{ genre }}/{{ artist }} - {{ title }}",
            output_dir=output_dir,
            repo_path=repo,
            absolute=False,
            include_missing=True,
        )
        assert created == 2

        # Now cleanup
        removed = cleanup_output_dir(output_dir)
        assert removed == 2

        # Directories should be cleaned up too
        assert not (output_dir / "Darkpsy").exists()
        assert not (output_dir / "Ambient").exists()

    @patch("music_commander.cache.builder.subprocess.run", side_effect=_mock_subprocess_run)
    def test_incremental_refresh_no_change(self, mock_run, repo: Path, session: Session) -> None:
        """T045-5: Incremental refresh returns None when no changes."""
        build_cache(repo, session)

        # Same commit → no refresh needed
        result = refresh_cache(repo, session)
        assert result is None

    @patch("music_commander.cache.builder.subprocess.run")
    def test_incremental_refresh_with_change(self, mock_run, repo: Path, session: Session) -> None:
        """T045-6: Incremental refresh updates changed tracks."""
        # First build
        mock_run.side_effect = _mock_subprocess_run
        build_cache(repo, session)

        # Simulate a new commit with a changed log.met
        updated_log = (
            "1700000000s artist +TestArtist title +UpdatedTitle genre +Darkpsy "
            "bpm +150 rating +5 key +Am\n"
        )

        def _mock_refresh_run(args, **kwargs):
            if args[:2] == ["git", "rev-parse"]:
                result = MagicMock()
                result.stdout = "newcommit456\n"
                return result
            elif args[:2] == ["git", "diff-tree"]:
                result = MagicMock()
                result.stdout = "abc/def/KEY1--file1.mp3.log.met\n"
                return result
            elif args[:2] == ["git", "cat-file"]:
                result = MagicMock()
                result.stdout = updated_log
                return result
            elif args[:3] == ["git", "annex", "find"]:
                result = MagicMock()
                if "--include=*" in args:
                    result.stdout = _ANNEX_FIND_ALL
                else:
                    result.stdout = _ANNEX_FIND_PRESENT
                return result
            raise ValueError(f"Unmocked: {args}")

        mock_run.side_effect = _mock_refresh_run
        updated = refresh_cache(repo, session)

        assert updated == 1
        t1 = session.query(CacheTrack).filter_by(key="KEY1--file1.mp3").first()
        assert t1 is not None
        assert t1.title == "UpdatedTitle"
        assert t1.bpm == 150.0

        # Search for updated title
        query = parse_query("UpdatedTitle")
        results = execute_search(session, query)
        assert len(results) == 1
        assert results[0].title == "UpdatedTitle"

    def test_render_path_integration(self) -> None:
        """T045-7: Template rendering with round_to filter in path context."""
        result = render_path(
            "{{ genre }}/{{ bpm | round_to(5) }}/{{ artist }} - {{ title }}",
            {"genre": "Techno", "bpm": "143", "artist": "DJ Test", "title": "Track"},
        )
        assert result == "Techno/145/DJ Test - Track"

    def test_delete_cache(self, repo: Path) -> None:
        """T045-8: Delete cache file."""
        cache_path = repo / CACHE_DB_NAME
        cache_path.write_text("fake db")
        assert cache_path.exists()

        deleted = delete_cache(repo)
        assert deleted is True
        assert not cache_path.exists()

        # Deleting again returns False
        deleted = delete_cache(repo)
        assert deleted is False
