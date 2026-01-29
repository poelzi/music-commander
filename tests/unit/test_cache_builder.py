"""Unit tests for cache builder module."""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.builder import (
    _decode_value,
    _extract_key_from_path,
    _metadata_to_crates,
    _metadata_to_track,
    build_cache,
    parse_metadata_log,
    refresh_cache,
)
from music_commander.cache.models import CacheBase, CacheState, CacheTrack, TrackCrate


def _in_memory_session() -> Session:
    """Create an in-memory SQLite session with cache tables."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# parse_metadata_log tests
# ---------------------------------------------------------------------------


class TestParseMetadataLog:
    def test_single_field_single_value(self) -> None:
        content = "1769651283s artist +AphexTwin\n"
        result = parse_metadata_log(content)
        assert result == {"artist": ["AphexTwin"]}

    def test_multiple_fields(self) -> None:
        content = "1769651283s artist +Boards of Canada genre +IDM\n"
        # Note: "of" and "Canada" look like values but they lack +/- prefix,
        # so "of" and "Canada" become field names. This matches the real format
        # where multi-word values are base64-encoded.
        # The real format for multi-word artist would be:
        content = "1769651283s artist +!Qm9hcmRzIG9mIENhbmFkYQ== genre +IDM\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["Boards of Canada"]
        assert result["genre"] == ["IDM"]

    def test_multi_value_field(self) -> None:
        content = "1769651283s genre +Ambient +IDM +Downtempo\n"
        result = parse_metadata_log(content)
        assert result["genre"] == ["Ambient", "Downtempo", "IDM"]

    def test_unset_value(self) -> None:
        content = "1769651283s genre +Ambient +IDM\n1769651284s genre -IDM\n"
        result = parse_metadata_log(content)
        assert result["genre"] == ["Ambient"]

    def test_multiline_replay(self) -> None:
        content = "1769651283s artist +OldArtist\n1769651290s artist -OldArtist +NewArtist\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["NewArtist"]

    def test_base64_value(self) -> None:
        # "Hello World" base64-encoded
        encoded = base64.b64encode(b"Hello World").decode()
        content = f"1769651283s title +!{encoded}\n"
        result = parse_metadata_log(content)
        assert result["title"] == ["Hello World"]

    def test_base64_with_special_chars(self) -> None:
        # Value with spaces and special characters
        raw = "Aphex Twin - Selected Ambient Works (Vol. 2)"
        encoded = base64.b64encode(raw.encode()).decode()
        content = f"1769651283s album +!{encoded}\n"
        result = parse_metadata_log(content)
        assert result["album"] == [raw]

    def test_empty_content(self) -> None:
        result = parse_metadata_log("")
        assert result == {}

    def test_whitespace_only(self) -> None:
        result = parse_metadata_log("   \n  \n")
        assert result == {}

    def test_timestamp_with_decimal(self) -> None:
        content = "1507541153.566038914s artist +Test\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["Test"]

    def test_multiple_fields_single_line(self) -> None:
        content = "1769651283s artist +TestArtist title +TestTitle bpm +128\n"
        result = parse_metadata_log(content)
        assert result["artist"] == ["TestArtist"]
        assert result["title"] == ["TestTitle"]
        assert result["bpm"] == ["128"]

    def test_crate_values(self) -> None:
        content = "1769651283s crate +Festival +DarkPsy +Chillout\n"
        result = parse_metadata_log(content)
        assert result["crate"] == ["Chillout", "DarkPsy", "Festival"]

    def test_unset_nonexistent_value(self) -> None:
        """Unsetting a value that was never set should not error."""
        content = "1769651283s genre -NonExistent\n"
        result = parse_metadata_log(content)
        assert result["genre"] == []

    def test_field_with_no_values(self) -> None:
        """A field name followed by another field name (no values)."""
        content = "1769651283s artist genre +IDM\n"
        result = parse_metadata_log(content)
        assert result["artist"] == []
        assert result["genre"] == ["IDM"]


# ---------------------------------------------------------------------------
# _decode_value tests
# ---------------------------------------------------------------------------


class TestDecodeValue:
    def test_plain_value(self) -> None:
        assert _decode_value("hello") == "hello"

    def test_base64_value(self) -> None:
        encoded = base64.b64encode(b"test value").decode()
        assert _decode_value(f"!{encoded}") == "test value"

    def test_base64_unicode(self) -> None:
        encoded = base64.b64encode("über cool".encode()).decode()
        assert _decode_value(f"!{encoded}") == "über cool"


# ---------------------------------------------------------------------------
# _extract_key_from_path tests
# ---------------------------------------------------------------------------


class TestExtractKeyFromPath:
    def test_standard_path(self) -> None:
        path = "abc/def/SHA256E-s6850832--abc123.mp3.log.met"
        assert _extract_key_from_path(path) == "SHA256E-s6850832--abc123.mp3"

    def test_deep_path(self) -> None:
        path = "a0/b1/SHA256E-s100--xyz.flac.log.met"
        assert _extract_key_from_path(path) == "SHA256E-s100--xyz.flac"

    def test_no_directory(self) -> None:
        path = "KEY-s100--test.mp3.log.met"
        assert _extract_key_from_path(path) == "KEY-s100--test.mp3"


# ---------------------------------------------------------------------------
# _metadata_to_track / _metadata_to_crates tests
# ---------------------------------------------------------------------------


class TestMetadataToTrack:
    def test_full_metadata(self) -> None:
        metadata = {
            "artist": ["Test Artist"],
            "title": ["Test Title"],
            "album": ["Test Album"],
            "genre": ["Ambient"],
            "bpm": ["128.5"],
            "rating": ["4"],
            "key": ["Am"],
            "year": ["2024"],
            "tracknumber": ["03"],
            "comment": ["Nice track"],
            "color": ["#FF0000"],
        }
        track = _metadata_to_track("key1", metadata, "test.mp3")
        assert track.key == "key1"
        assert track.file == "test.mp3"
        assert track.artist == "Test Artist"
        assert track.title == "Test Title"
        assert track.bpm == 128.5
        assert track.rating == 4
        assert track.key_musical == "Am"

    def test_minimal_metadata(self) -> None:
        track = _metadata_to_track("key1", {}, "test.mp3")
        assert track.key == "key1"
        assert track.file == "test.mp3"
        assert track.artist is None
        assert track.bpm is None

    def test_invalid_bpm(self) -> None:
        metadata = {"bpm": ["notanumber"]}
        track = _metadata_to_track("key1", metadata, "test.mp3")
        assert track.bpm is None

    def test_invalid_rating(self) -> None:
        metadata = {"rating": ["notanint"]}
        track = _metadata_to_track("key1", metadata, "test.mp3")
        assert track.rating is None


class TestMetadataToCrates:
    def test_multiple_crates(self) -> None:
        metadata = {"crate": ["Festival", "DarkPsy"]}
        crates = _metadata_to_crates("key1", metadata)
        assert len(crates) == 2
        assert {c.crate for c in crates} == {"Festival", "DarkPsy"}

    def test_no_crates(self) -> None:
        crates = _metadata_to_crates("key1", {})
        assert crates == []


# ---------------------------------------------------------------------------
# build_cache tests (mocked git)
# ---------------------------------------------------------------------------


def _make_completed_process(stdout: str = "", stderr: str = "") -> MagicMock:
    cp = MagicMock()
    cp.stdout = stdout
    cp.stderr = stderr
    cp.returncode = 0
    return cp


class TestBuildCache:
    def _setup_session(self) -> Session:
        engine = create_engine("sqlite:///:memory:")
        CacheBase.metadata.create_all(engine)
        return sessionmaker(bind=engine)()

    @patch("music_commander.cache.builder.subprocess.run")
    def test_full_build(self, mock_run: MagicMock) -> None:
        session = self._setup_session()
        repo = Path("/fake/repo")

        # Mock responses for each subprocess call:
        # 1. ls-tree (read_metadata_from_branch)
        ls_tree_out = (
            "100644 blob aaa111\tab/cd/SHA256E-s100--track1.mp3.log.met\n"
            "100644 blob bbb222\tef/gh/SHA256E-s200--track2.flac.log.met\n"
        )
        # 2. cat-file --batch
        blob1 = "1769651283s artist +ArtistOne title +TitleOne"
        blob2 = "1769651283s artist +ArtistTwo genre +IDM"
        cat_file_out = f"aaa111 blob {len(blob1)}\n{blob1}\nbbb222 blob {len(blob2)}\n{blob2}\n"
        # 3. git annex find (build_key_to_file_map)
        annex_find_out = (
            "SHA256E-s100--track1.mp3\tmusic/track1.mp3\n"
            "SHA256E-s200--track2.flac\tmusic/track2.flac\n"
        )
        # 4. rev-parse git-annex
        rev_parse_out = "abc123def456"

        def side_effect(cmd, **kwargs):
            if "ls-tree" in cmd:
                return _make_completed_process(ls_tree_out)
            if "cat-file" in cmd:
                return _make_completed_process(cat_file_out)
            if "annex" in cmd:
                return _make_completed_process(annex_find_out)
            if "rev-parse" in cmd:
                return _make_completed_process(rev_parse_out)
            return _make_completed_process()

        mock_run.side_effect = side_effect

        count = build_cache(repo, session)
        assert count == 2

        tracks = session.query(CacheTrack).all()
        assert len(tracks) == 2
        artists = {t.artist for t in tracks}
        assert artists == {"ArtistOne", "ArtistTwo"}

        state = session.query(CacheState).one()
        assert state.annex_branch_commit == "abc123def456"
        assert state.track_count == 2

    @patch("music_commander.cache.builder.subprocess.run")
    def test_build_with_crates(self, mock_run: MagicMock) -> None:
        session = self._setup_session()
        repo = Path("/fake/repo")

        blob = "1769651283s artist +Test crate +Festival +DarkPsy"
        ls_tree_out = "100644 blob aaa111\tab/cd/KEY1.log.met\n"
        cat_file_out = f"aaa111 blob {len(blob)}\n{blob}\n"
        annex_find_out = "KEY1\tmusic/track.mp3\n"

        def side_effect(cmd, **kwargs):
            if "ls-tree" in cmd:
                return _make_completed_process(ls_tree_out)
            if "cat-file" in cmd:
                return _make_completed_process(cat_file_out)
            if "annex" in cmd:
                return _make_completed_process(annex_find_out)
            if "rev-parse" in cmd:
                return _make_completed_process("commit1")
            return _make_completed_process()

        mock_run.side_effect = side_effect

        build_cache(repo, session)

        crates = session.query(TrackCrate).all()
        assert len(crates) == 2
        assert {c.crate for c in crates} == {"Festival", "DarkPsy"}

    @patch("music_commander.cache.builder.subprocess.run")
    def test_build_skips_unmapped_keys(self, mock_run: MagicMock) -> None:
        """Tracks with no file mapping should be skipped."""
        session = self._setup_session()
        repo = Path("/fake/repo")

        blob = "1769651283s artist +Test"
        ls_tree_out = "100644 blob aaa111\tab/cd/ORPHAN-KEY.log.met\n"
        cat_file_out = f"aaa111 blob {len(blob)}\n{blob}\n"
        # annex find returns nothing for this key
        annex_find_out = ""

        def side_effect(cmd, **kwargs):
            if "ls-tree" in cmd:
                return _make_completed_process(ls_tree_out)
            if "cat-file" in cmd:
                return _make_completed_process(cat_file_out)
            if "annex" in cmd:
                return _make_completed_process(annex_find_out)
            if "rev-parse" in cmd:
                return _make_completed_process("commit1")
            return _make_completed_process()

        mock_run.side_effect = side_effect

        count = build_cache(repo, session)
        assert count == 0
        assert session.query(CacheTrack).count() == 0


# ---------------------------------------------------------------------------
# FTS5 tests
# ---------------------------------------------------------------------------


class TestFTS5:
    @patch("music_commander.cache.builder.subprocess.run")
    def test_fts5_populated_after_build(self, mock_run: MagicMock) -> None:
        session = self._setup_session()
        repo = Path("/fake/repo")

        blob = "1769651283s artist +TestArtist title +TestTitle"
        ls_tree_out = "100644 blob aaa111\tab/cd/KEY1.log.met\n"
        cat_file_out = f"aaa111 blob {len(blob)}\n{blob}\n"
        annex_find_out = "KEY1\tmusic/track.mp3\n"

        def side_effect(cmd, **kwargs):
            if "ls-tree" in cmd:
                return _make_completed_process(ls_tree_out)
            if "cat-file" in cmd:
                return _make_completed_process(cat_file_out)
            if "annex" in cmd:
                return _make_completed_process(annex_find_out)
            if "rev-parse" in cmd:
                return _make_completed_process("commit1")
            return _make_completed_process()

        mock_run.side_effect = side_effect

        build_cache(repo, session)

        # Query FTS5
        result = session.execute(
            text("SELECT key, artist, title FROM tracks_fts WHERE tracks_fts MATCH 'TestArtist'")
        ).fetchall()
        assert len(result) == 1
        assert result[0][1] == "TestArtist"

    def _setup_session(self) -> Session:
        engine = create_engine("sqlite:///:memory:")
        CacheBase.metadata.create_all(engine)
        return sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# refresh_cache tests (mocked git)
# ---------------------------------------------------------------------------


class TestRefreshCache:
    def _setup_session_with_state(
        self, commit: str = "old_commit", track_count: int = 1
    ) -> Session:
        engine = create_engine("sqlite:///:memory:")
        CacheBase.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        # Seed with existing state and track
        session.add(CacheState(id=1, annex_branch_commit=commit, track_count=track_count))
        session.add(CacheTrack(key="existing-key", file="existing.mp3", artist="Old"))
        session.commit()
        return session

    @patch("music_commander.cache.builder.subprocess.run")
    def test_no_change_returns_none(self, mock_run: MagicMock) -> None:
        session = self._setup_session_with_state("current_commit")

        def side_effect(cmd, **kwargs):
            if "rev-parse" in cmd:
                return _make_completed_process("current_commit")
            return _make_completed_process()

        mock_run.side_effect = side_effect

        result = refresh_cache(Path("/fake"), session)
        assert result is None

    @patch("music_commander.cache.builder.subprocess.run")
    def test_incremental_update(self, mock_run: MagicMock) -> None:
        session = self._setup_session_with_state("old_commit")

        changed_blob = "1769651290s artist +UpdatedArtist"

        def side_effect(cmd, **kwargs):
            if "rev-parse" in cmd:
                return _make_completed_process("new_commit")
            if "diff-tree" in cmd:
                return _make_completed_process("ab/cd/existing-key.log.met\n")
            if "cat-file" in cmd and "-p" in cmd:
                return _make_completed_process(changed_blob)
            if "annex" in cmd:
                return _make_completed_process("existing-key\texisting.mp3\n")
            return _make_completed_process()

        mock_run.side_effect = side_effect

        result = refresh_cache(Path("/fake"), session)
        assert result == 1

        track = session.query(CacheTrack).filter_by(key="existing-key").one()
        assert track.artist == "UpdatedArtist"

        state = session.query(CacheState).one()
        assert state.annex_branch_commit == "new_commit"

    @patch("music_commander.cache.builder.subprocess.run")
    def test_no_metadata_changes(self, mock_run: MagicMock) -> None:
        """If diff-tree returns no .log.met changes, just update commit."""
        session = self._setup_session_with_state("old_commit")

        def side_effect(cmd, **kwargs):
            if "rev-parse" in cmd:
                return _make_completed_process("new_commit")
            if "diff-tree" in cmd:
                return _make_completed_process("")
            return _make_completed_process()

        mock_run.side_effect = side_effect

        result = refresh_cache(Path("/fake"), session)
        assert result == 0

        state = session.query(CacheState).one()
        assert state.annex_branch_commit == "new_commit"

    @patch("music_commander.cache.builder.subprocess.run")
    def test_no_state_triggers_full_build(self, mock_run: MagicMock) -> None:
        """When no CacheState exists, refresh_cache does a full build."""
        engine = create_engine("sqlite:///:memory:")
        CacheBase.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()

        ls_tree_out = "100644 blob aaa111\tab/cd/KEY1.log.met\n"
        blob = "1769651283s artist +FullBuild"
        cat_file_out = f"aaa111 blob {len(blob)}\n{blob}\n"
        annex_find_out = "KEY1\tmusic/track.mp3\n"

        def side_effect(cmd, **kwargs):
            if "rev-parse" in cmd:
                return _make_completed_process("commit1")
            if "ls-tree" in cmd:
                return _make_completed_process(ls_tree_out)
            if "cat-file" in cmd:
                return _make_completed_process(cat_file_out)
            if "annex" in cmd:
                return _make_completed_process(annex_find_out)
            return _make_completed_process()

        mock_run.side_effect = side_effect

        result = refresh_cache(Path("/fake"), session)
        assert result == 1
        assert session.query(CacheTrack).count() == 1
