"""Duplicate detection for the Anomalistic portal mirror.

Detects previously-downloaded releases via three strategies:
1. URL-based cache lookup (exact match in anomalistic_releases table)
2. Comment-field scan (release URL in track comment tags)
3. Fuzzy artist+album matching against existing collection

Callers can bypass all checks by not calling ``check_duplicate()``
when the ``--force`` flag is active.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from music_commander.utils.matching import match_release
from sqlalchemy.orm import Session

from music_commander.cache.models import AnomaListicRelease, CacheTrack

logger = logging.getLogger(__name__)


@dataclass
class DedupResult:
    """Result of duplicate detection for a single release."""

    should_skip: bool
    reason: str | None = None
    match_details: str | None = None


def check_cache_url(session: Session, release_url: str) -> bool:
    """Check if a release URL exists in the cache with status 'downloaded'.

    Args:
        session: SQLAlchemy session.
        release_url: The portal release URL to check.

    Returns:
        True if the release was already downloaded by this tool.
    """
    result = (
        session.query(AnomaListicRelease)
        .filter(
            AnomaListicRelease.release_url == release_url,
            AnomaListicRelease.download_status == "downloaded",
        )
        .first()
    )
    return result is not None


def check_comment_url(session: Session, release_url: str) -> bool:
    """Check if any track in the collection has this URL in its comment field.

    This catches releases downloaded by this tool or manually tagged with
    the portal URL.

    Args:
        session: SQLAlchemy session.
        release_url: The portal release URL to search for.

    Returns:
        True if any track's comment contains the URL.
    """
    result = session.query(CacheTrack).filter(CacheTrack.comment.contains(release_url)).first()
    return result is not None


def check_fuzzy_match(
    session: Session,
    artist: str,
    album: str,
    threshold: int = 60,
    *,
    local_albums: list[tuple[str, str]] | None = None,
) -> tuple[bool, float, str | None]:
    """Fuzzy match a release against the existing collection.

    Uses ``match_release()`` from the shared matching module to compare
    artist+album against all distinct (artist, album) pairs in the cache.

    Args:
        session: SQLAlchemy session.
        artist: Release artist name.
        album: Release album title.
        threshold: Minimum score (0-100) to consider a match.
        local_albums: Pre-loaded list of (artist, album) pairs. If None,
            queries the database. Pass this when checking multiple releases
            to avoid repeated queries.

    Returns:
        Tuple of (is_match, best_score, matched_description).
    """
    if local_albums is None:
        local_albums = load_local_albums(session)

    best_score = 0.0
    best_match: str | None = None

    for local_artist, local_album in local_albums:
        score = match_release(local_artist, local_album, artist, album)
        if score > best_score:
            best_score = score
            best_match = f"{local_artist} - {local_album}"

    return (best_score >= threshold, best_score, best_match)


def load_local_albums(session: Session) -> list[tuple[str, str]]:
    """Load distinct (artist, album) pairs from the track cache.

    Args:
        session: SQLAlchemy session.

    Returns:
        List of (artist, album) tuples, excluding entries with None values.
    """
    rows = (
        session.query(CacheTrack.artist, CacheTrack.album)
        .filter(CacheTrack.artist.isnot(None), CacheTrack.album.isnot(None))
        .distinct()
        .all()
    )
    return [(r[0], r[1]) for r in rows]


def check_duplicate(
    session: Session,
    release_url: str,
    artist: str,
    album: str,
    threshold: int = 60,
    *,
    local_albums: list[tuple[str, str]] | None = None,
) -> DedupResult:
    """Check if a release is a duplicate using all detection strategies.

    Checks are ordered by speed and reliability:
    1. URL cache lookup (fastest, most reliable)
    2. Comment field scan (fast, catches manually tagged tracks)
    3. Fuzzy matching (slowest, catches cross-source duplicates)

    Callers should skip this function entirely when ``--force`` is active.

    Args:
        session: SQLAlchemy session.
        release_url: The portal release URL.
        artist: Release artist name.
        album: Release album title.
        threshold: Fuzzy match threshold (0-100).
        local_albums: Pre-loaded (artist, album) pairs for fuzzy matching.

    Returns:
        DedupResult indicating whether to skip and why.
    """
    # 1. URL cache check (fastest, most reliable)
    if check_cache_url(session, release_url):
        logger.debug("Duplicate (cached): %s", release_url)
        return DedupResult(should_skip=True, reason="cached")

    # 2. Comment field scan
    if check_comment_url(session, release_url):
        logger.debug("Duplicate (comment match): %s", release_url)
        return DedupResult(should_skip=True, reason="comment_match")

    # 3. Fuzzy matching (slowest)
    is_match, score, details = check_fuzzy_match(
        session, artist, album, threshold, local_albums=local_albums
    )
    if is_match:
        logger.debug(
            "Duplicate (fuzzy match, score: %.1f): %s - %s matched %s",
            score,
            artist,
            album,
            details,
        )
        return DedupResult(
            should_skip=True,
            reason=f"fuzzy_match (score: {score:.1f})",
            match_details=details,
        )

    return DedupResult(should_skip=False)
