"""Tests for the Anomalistic portal duplicate detection."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from music_commander.anomalistic.dedup import (
    DedupResult,
    check_cache_url,
    check_comment_url,
    check_duplicate,
    check_fuzzy_match,
    load_local_albums,
)
from music_commander.cache.models import AnomaListicRelease, CacheBase, CacheTrack


@pytest.fixture
def session() -> Session:
    """Create an in-memory SQLite session with schema."""
    engine = create_engine("sqlite:///:memory:")
    CacheBase.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()
    yield sess
    sess.close()


# ---------------------------------------------------------------------------
# check_cache_url tests
# ---------------------------------------------------------------------------


class TestCheckCacheUrl:
    """Tests for URL-based cache lookup."""

    def test_not_in_cache(self, session):
        assert check_cache_url(session, "https://portal.example.com/release-1") is False

    def test_in_cache_downloaded(self, session):
        session.add(
            AnomaListicRelease(
                post_id=1,
                artist="Artist",
                album_title="Album",
                release_url="https://portal.example.com/release-1",
                download_status="downloaded",
                last_synced="2026-01-01T00:00:00Z",
            )
        )
        session.commit()
        assert check_cache_url(session, "https://portal.example.com/release-1") is True

    def test_in_cache_pending_not_matched(self, session):
        session.add(
            AnomaListicRelease(
                post_id=2,
                artist="Artist",
                album_title="Album",
                release_url="https://portal.example.com/release-2",
                download_status="pending",
                last_synced="2026-01-01T00:00:00Z",
            )
        )
        session.commit()
        assert check_cache_url(session, "https://portal.example.com/release-2") is False

    def test_exact_url_match_only(self, session):
        session.add(
            AnomaListicRelease(
                post_id=3,
                artist="Artist",
                album_title="Album",
                release_url="https://portal.example.com/release-3",
                download_status="downloaded",
                last_synced="2026-01-01T00:00:00Z",
            )
        )
        session.commit()
        # Partial match should not work
        assert check_cache_url(session, "https://portal.example.com/release") is False
        assert check_cache_url(session, "https://portal.example.com/release-3/extra") is False


# ---------------------------------------------------------------------------
# check_comment_url tests
# ---------------------------------------------------------------------------


class TestCheckCommentUrl:
    """Tests for comment-field URL scan."""

    def test_no_tracks(self, session):
        assert check_comment_url(session, "https://portal.example.com/release-1") is False

    def test_track_with_matching_comment(self, session):
        session.add(
            CacheTrack(
                key="track1.flac",
                artist="XianZai",
                title="Track 1",
                album="Irrational Conjunction",
                comment="https://portal.example.com/release-1",
            )
        )
        session.commit()
        assert check_comment_url(session, "https://portal.example.com/release-1") is True

    def test_track_with_non_matching_comment(self, session):
        session.add(
            CacheTrack(
                key="track2.flac",
                artist="Other",
                title="Track 2",
                album="Other Album",
                comment="https://portal.example.com/release-2",
            )
        )
        session.commit()
        assert check_comment_url(session, "https://portal.example.com/release-1") is False

    def test_url_in_longer_comment(self, session):
        """URL can be part of a longer comment string."""
        session.add(
            CacheTrack(
                key="track3.flac",
                artist="Artist",
                title="Track 3",
                album="Album",
                comment="Downloaded from https://portal.example.com/release-1 on 2026-01-01",
            )
        )
        session.commit()
        assert check_comment_url(session, "https://portal.example.com/release-1") is True

    def test_none_comment_not_matched(self, session):
        session.add(
            CacheTrack(
                key="track4.flac",
                artist="Artist",
                title="Track 4",
                album="Album",
                comment=None,
            )
        )
        session.commit()
        assert check_comment_url(session, "https://portal.example.com/release-1") is False


# ---------------------------------------------------------------------------
# check_fuzzy_match tests
# ---------------------------------------------------------------------------


class TestCheckFuzzyMatch:
    """Tests for fuzzy artist+album matching."""

    def test_no_local_albums(self, session):
        is_match, score, details = check_fuzzy_match(session, "Artist", "Album")
        assert is_match is False
        assert score == 0.0
        assert details is None

    def test_exact_match(self, session):
        session.add(
            CacheTrack(
                key="t.flac",
                artist="XianZai",
                title="T",
                album="Irrational Conjunction",
            )
        )
        session.commit()
        is_match, score, details = check_fuzzy_match(session, "XianZai", "Irrational Conjunction")
        assert is_match is True
        assert score >= 95.0
        assert "XianZai" in details
        assert "Irrational Conjunction" in details

    def test_similar_but_below_threshold(self, session):
        session.add(
            CacheTrack(
                key="t.flac",
                artist="Completely Different",
                title="T",
                album="Unrelated Album",
            )
        )
        session.commit()
        is_match, score, details = check_fuzzy_match(
            session, "XianZai", "Irrational Conjunction", threshold=80
        )
        assert is_match is False

    def test_same_artist_different_album_no_match(self, session):
        """Same artist but completely different album should NOT match."""
        local = [("Black Phillip", "Las Ruinas De Zion")]
        is_match, score, details = check_fuzzy_match(
            session, "Black Phillip", "VA Undead Xmas", local_albums=local
        )
        assert is_match is False

    def test_various_artists_different_compilations_no_match(self, session):
        """Various Artists compilations with different titles should NOT match."""
        local = [("Various Artists", "V/A SURGICAL STRIKE - compiled by Psykoze")]
        is_match, score, details = check_fuzzy_match(
            session,
            "Various Artists",
            "Kreepsy Origins (compiled by Black Phillip)",
            local_albums=local,
        )
        assert is_match is False

    def test_same_artist_similar_album_still_matches(self, session):
        """Genuine near-duplicate (same album, minor title variation) should match."""
        local = [("XianZai", "Irrational Conjunction")]
        is_match, score, details = check_fuzzy_match(
            session, "XianZai", "Irrational Conjunction (Remastered)", local_albums=local
        )
        assert is_match is True

    def test_case_insensitive_match(self, session):
        session.add(
            CacheTrack(
                key="t.flac",
                artist="xianzai",
                title="T",
                album="irrational conjunction",
            )
        )
        session.commit()
        is_match, score, details = check_fuzzy_match(session, "XianZai", "Irrational Conjunction")
        assert is_match is True
        assert score >= 90.0

    def test_custom_threshold(self, session):
        session.add(
            CacheTrack(
                key="t.flac",
                artist="XianZai",
                title="T",
                album="Similar Album Title",
            )
        )
        session.commit()
        # Very high threshold should not match partial similarity
        is_match_strict, _, _ = check_fuzzy_match(
            session, "XianZai", "Different Album", threshold=95
        )
        assert is_match_strict is False

    def test_preloaded_local_albums(self, session):
        """Passing pre-loaded albums avoids DB query."""
        local = [("XianZai", "Irrational Conjunction")]
        is_match, score, details = check_fuzzy_match(
            session, "XianZai", "Irrational Conjunction", local_albums=local
        )
        assert is_match is True
        assert score >= 95.0

    def test_multiple_local_albums_best_match(self, session):
        local = [
            ("Some Artist", "Some Album"),
            ("XianZai", "Irrational Conjunction"),
            ("Other", "Other Album"),
        ]
        is_match, score, details = check_fuzzy_match(
            session, "XianZai", "Irrational Conjunction", local_albums=local
        )
        assert is_match is True
        assert "XianZai" in details


# ---------------------------------------------------------------------------
# load_local_albums tests
# ---------------------------------------------------------------------------


class TestLoadLocalAlbums:
    """Tests for loading distinct local albums."""

    def test_empty_db(self, session):
        result = load_local_albums(session)
        assert result == []

    def test_filters_none_values(self, session):
        session.add(CacheTrack(key="a.flac", artist=None, title="T", album="Album"))
        session.add(CacheTrack(key="b.flac", artist="Artist", title="T", album=None))
        session.add(CacheTrack(key="c.flac", artist="Artist", title="T", album="Album"))
        session.commit()
        result = load_local_albums(session)
        assert len(result) == 1
        assert result[0] == ("Artist", "Album")

    def test_distinct_pairs(self, session):
        session.add(CacheTrack(key="a.flac", artist="A", title="T1", album="X"))
        session.add(CacheTrack(key="b.flac", artist="A", title="T2", album="X"))
        session.add(CacheTrack(key="c.flac", artist="B", title="T3", album="Y"))
        session.commit()
        result = load_local_albums(session)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# check_duplicate tests
# ---------------------------------------------------------------------------


class TestCheckDuplicate:
    """Tests for the combined duplicate decision logic."""

    def test_no_duplicate(self, session):
        result = check_duplicate(
            session, "https://portal.example.com/new-release", "New Artist", "New Album"
        )
        assert result.should_skip is False
        assert result.reason is None

    def test_cached_takes_priority(self, session):
        """Cache URL match should be checked first."""
        url = "https://portal.example.com/release-1"
        session.add(
            AnomaListicRelease(
                post_id=1,
                artist="XianZai",
                album_title="Irrational Conjunction",
                release_url=url,
                download_status="downloaded",
                last_synced="2026-01-01T00:00:00Z",
            )
        )
        # Also add a comment match and fuzzy match
        session.add(
            CacheTrack(
                key="t.flac",
                artist="XianZai",
                title="T",
                album="Irrational Conjunction",
                comment=url,
            )
        )
        session.commit()
        result = check_duplicate(session, url, "XianZai", "Irrational Conjunction")
        assert result.should_skip is True
        assert result.reason == "cached"

    def test_comment_match_priority_over_fuzzy(self, session):
        url = "https://portal.example.com/release-1"
        session.add(
            CacheTrack(
                key="t.flac",
                artist="XianZai",
                title="T",
                album="Irrational Conjunction",
                comment=url,
            )
        )
        session.commit()
        result = check_duplicate(session, url, "XianZai", "Irrational Conjunction")
        assert result.should_skip is True
        assert result.reason == "comment_match"

    def test_fuzzy_match_when_no_exact(self, session):
        session.add(
            CacheTrack(
                key="t.flac",
                artist="XianZai",
                title="T",
                album="Irrational Conjunction",
            )
        )
        session.commit()
        result = check_duplicate(
            session,
            "https://portal.example.com/new-url",
            "XianZai",
            "Irrational Conjunction",
        )
        assert result.should_skip is True
        assert "fuzzy_match" in result.reason
        assert result.match_details is not None

    def test_fuzzy_no_match_below_threshold(self, session):
        session.add(
            CacheTrack(
                key="t.flac",
                artist="Completely Different",
                title="T",
                album="Unrelated Album",
            )
        )
        session.commit()
        result = check_duplicate(
            session,
            "https://portal.example.com/release",
            "XianZai",
            "Irrational Conjunction",
            threshold=80,
        )
        assert result.should_skip is False

    def test_same_artist_different_album_not_duplicate(self, session):
        """Same artist with a different album should not be flagged as duplicate."""
        session.add(
            CacheTrack(
                key="t.flac",
                artist="Audiosyntax",
                title="T",
                album="Unseen Fungi",
            )
        )
        session.commit()
        result = check_duplicate(
            session,
            "https://portal.example.com/new-release",
            "Audiosyntax",
            "Noiseborn",
        )
        assert result.should_skip is False

    def test_with_preloaded_albums(self, session):
        local = [("XianZai", "Irrational Conjunction")]
        result = check_duplicate(
            session,
            "https://portal.example.com/new-url",
            "XianZai",
            "Irrational Conjunction",
            local_albums=local,
        )
        assert result.should_skip is True
        assert "fuzzy_match" in result.reason
