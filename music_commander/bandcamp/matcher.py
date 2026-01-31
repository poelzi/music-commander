"""Fuzzy matching engine for local library ↔ Bandcamp collection."""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from music_commander.cache.models import BandcampRelease, BandcampTrack, CacheTrack

# Pre-compiled patterns
_MULTI_SPACE = re.compile(r"\s+")
_NON_ALNUM_SPACE = re.compile(r"[^\w\s]", re.UNICODE)
_EDITION_SUFFIX = re.compile(
    r"\s*[\(\[](deluxe|remaster(?:ed)?|bonus\s+track(?:\s+version)?|expanded"
    r"|anniversary|special|limited|collector'?s?|super\s+deluxe"
    r"|(?:\d+(?:st|nd|rd|th)\s+anniversary))"
    r"(?:\s+edition)?[\)\]]",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# T016 – String normalization
# ---------------------------------------------------------------------------


def normalize(s: str) -> str:
    """Lowercase, strip edges, collapse whitespace."""
    return _MULTI_SPACE.sub(" ", s.lower().strip())


def strip_punctuation(s: str) -> str:
    """Remove non-alphanumeric characters except spaces."""
    return _NON_ALNUM_SPACE.sub("", s)


def strip_edition_suffixes(s: str) -> str:
    """Remove common parenthetical edition suffixes."""
    return _EDITION_SUFFIX.sub("", s)


def normalize_for_matching(s: str) -> str:
    """Full normalization pipeline for fuzzy comparison."""
    return strip_punctuation(normalize(strip_edition_suffixes(s)))


# ---------------------------------------------------------------------------
# T019 – Confidence tier classification
# ---------------------------------------------------------------------------


class MatchTier(enum.Enum):
    """Human-readable confidence tiers for match scores."""

    EXACT = "exact"
    HIGH = "high"
    LOW = "low"
    NONE = "none"


def classify_match(score: float) -> MatchTier:
    """Classify a 0-100 match score into a confidence tier."""
    if score >= 95:
        return MatchTier.EXACT
    if score >= 80:
        return MatchTier.HIGH
    if score >= 60:
        return MatchTier.LOW
    return MatchTier.NONE


@dataclass(frozen=True, slots=True)
class MatchResult:
    """A single match between a local track and a Bandcamp item."""

    local_key: str
    bc_sale_item_id: int
    score: float
    tier: MatchTier
    match_type: str  # "release" or "track"


# ---------------------------------------------------------------------------
# T017 – Release-level matching
# ---------------------------------------------------------------------------


def match_release(
    local_artist: str,
    local_album: str,
    bc_artist: str,
    bc_album: str,
) -> float:
    """Score a local album against a Bandcamp release (0-100).

    Weighted: artist 40%, album 60%.
    """
    la = normalize_for_matching(local_artist)
    ll = normalize_for_matching(local_album)
    ba = normalize_for_matching(bc_artist)
    bl = normalize_for_matching(bc_album)
    artist_score = fuzz.token_sort_ratio(la, ba)
    album_score = fuzz.token_sort_ratio(ll, bl)
    return artist_score * 0.4 + album_score * 0.6


# ---------------------------------------------------------------------------
# T018 – Track-level matching
# ---------------------------------------------------------------------------


def match_track(
    local_artist: str,
    local_title: str,
    bc_artist: str,
    bc_title: str,
) -> float:
    """Score a local track against a Bandcamp track (0-100).

    Weighted: artist 40%, title 60%.
    """
    la = normalize_for_matching(local_artist)
    lt = normalize_for_matching(local_title)
    ba = normalize_for_matching(bc_artist)
    bt = normalize_for_matching(bc_title)
    artist_score = fuzz.token_sort_ratio(la, ba)
    title_score = fuzz.token_sort_ratio(lt, bt)
    return artist_score * 0.4 + title_score * 0.6


# ---------------------------------------------------------------------------
# T020 – Batch matching
# ---------------------------------------------------------------------------


def batch_match(
    local_tracks: list[CacheTrack],
    bc_releases: list[BandcampRelease],
    bc_tracks: list[BandcampTrack],
    threshold: int = 60,
) -> list[MatchResult]:
    """Match all local tracks against Bandcamp releases and tracks.

    Strategy:
    1. Pre-normalize all Bandcamp strings once.
    2. For each local track with artist+album, try release-level match.
    3. If no release match >= threshold, try track-level match.
    4. Return results sorted by score descending.
    """
    # Pre-normalize Bandcamp release strings
    norm_releases: list[tuple[int, str, str]] = [
        (r.sale_item_id, normalize_for_matching(r.band_name), normalize_for_matching(r.album_title))
        for r in bc_releases
    ]

    # Pre-normalize Bandcamp track strings (need artist from parent release)
    release_artist_map: dict[int, str] = {
        r.sale_item_id: normalize_for_matching(r.band_name) for r in bc_releases
    }
    norm_tracks: list[tuple[int, int, str, str]] = []
    for t in bc_tracks:
        artist = release_artist_map.get(t.release_id, "")
        norm_tracks.append((t.release_id, t.id, artist, normalize_for_matching(t.title)))

    results: list[MatchResult] = []

    for lt in local_tracks:
        local_artist = lt.artist or ""
        local_album = lt.album or ""
        local_title = lt.title or ""

        if not local_artist:
            continue

        norm_la = normalize_for_matching(local_artist)

        # Try release-level match first
        best_release_score = 0.0
        best_release_id = 0
        if local_album:
            norm_ll = normalize_for_matching(local_album)
            for bc_id, bc_a, bc_al in norm_releases:
                artist_score = fuzz.token_sort_ratio(norm_la, bc_a)
                album_score = fuzz.token_sort_ratio(norm_ll, bc_al)
                score = artist_score * 0.4 + album_score * 0.6
                if score > best_release_score:
                    best_release_score = score
                    best_release_id = bc_id

        if best_release_score >= threshold:
            tier = classify_match(best_release_score)
            results.append(
                MatchResult(
                    local_key=lt.key,
                    bc_sale_item_id=best_release_id,
                    score=best_release_score,
                    tier=tier,
                    match_type="release",
                )
            )
            continue

        # Fall back to track-level match
        if not local_title:
            continue

        norm_lt = normalize_for_matching(local_title)
        best_track_score = 0.0
        best_track_release_id = 0
        for bc_rid, _bc_tid, bc_a, bc_t in norm_tracks:
            artist_score = fuzz.token_sort_ratio(norm_la, bc_a)
            title_score = fuzz.token_sort_ratio(norm_lt, bc_t)
            score = artist_score * 0.4 + title_score * 0.6
            if score > best_track_score:
                best_track_score = score
                best_track_release_id = bc_rid

        if best_track_score >= threshold:
            tier = classify_match(best_track_score)
            results.append(
                MatchResult(
                    local_key=lt.key,
                    bc_sale_item_id=best_track_release_id,
                    score=best_track_score,
                    tier=tier,
                    match_type="track",
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    return results
