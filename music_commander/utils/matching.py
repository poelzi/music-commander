"""Shared fuzzy matching utilities for music metadata.

Extracted from bandcamp/matcher.py so that multiple matching engines
(Bandcamp, Anomalistic portal, etc.) can reuse the same normalization,
scoring, and classification logic.
"""

from __future__ import annotations

import enum
import re

from rapidfuzz import fuzz

# ---------------------------------------------------------------------------
# Pre-compiled patterns
# ---------------------------------------------------------------------------

_MULTI_SPACE = re.compile(r"\s+")
_NON_ALNUM_SPACE = re.compile(r"[^\w\s]", re.UNICODE)
_EDITION_SUFFIX = re.compile(
    r"\s*[\(\[](deluxe|remaster(?:ed)?|bonus\s+track(?:\s+version)?|expanded"
    r"|anniversary|special|limited|collector'?s?|super\s+deluxe"
    r"|(?:\d+(?:st|nd|rd|th)\s+anniversary))"
    r"(?:\s+edition)?[\)\]]",
    re.IGNORECASE,
)
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_GUILLEMETS = re.compile(r"[«»„" "\u201c\u201d\u201e]")
_CATALOG_BRACKET = re.compile(r"\[[\w\d]+\]")
_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\-_]")
_NOISE_PHRASES = re.compile(
    r"\b(free\s+download|single|original\s+mix)\b",
    re.IGNORECASE,
)

# Volume/part detection for series matching
_VOLUME_PATTERN = re.compile(
    r"(?:"
    r"vol(?:ume)?\.?\s*(\d+|[IVXLC]+)"  # Vol. 2, Volume II
    r"|part\.?\s*(\d+|[IVXLC]+)"  # Part 1, Pt. 2
    r"|pt\.?\s*(\d+|[IVXLC]+)"  # Pt 2, Pt. 3
    r")",
    re.IGNORECASE,
)

_ROMAN_MAP = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
}


# ---------------------------------------------------------------------------
# Roman numeral helpers
# ---------------------------------------------------------------------------


def _roman_to_int(s: str) -> int | None:
    """Convert a roman numeral string to int, or None if not recognized."""
    return _ROMAN_MAP.get(s.upper())


def extract_volume(s: str) -> int | None:
    """Extract volume/part number from a string.

    Recognizes patterns like Vol. 2, Volume II, Part 1, Pt. 3.
    Returns the volume as an integer, or None if no volume indicator found.
    """
    m = _VOLUME_PATTERN.search(s)
    if not m:
        return None
    # Check each capture group (vol, part, pt)
    for g in m.groups():
        if g is None:
            continue
        # Try arabic numeral first
        if g.isdigit():
            return int(g)
        # Try roman numeral
        val = _roman_to_int(g)
        if val is not None:
            return val
    return None


# ---------------------------------------------------------------------------
# String normalization
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
    """Full normalization pipeline for fuzzy matching.

    Handles special characters common in music metadata and filenames:
    zero-width chars, guillemets, catalog brackets, dash variants, colons.
    """
    s = _ZERO_WIDTH.sub("", s)
    s = _GUILLEMETS.sub("", s)
    s = _CATALOG_BRACKET.sub("", s)
    s = _NOISE_PHRASES.sub("", s)
    s = _DASHES.sub(" ", s)
    s = s.replace(":", " ")
    result = strip_punctuation(normalize(strip_edition_suffixes(s)))
    return _MULTI_SPACE.sub(" ", result).strip()


# ---------------------------------------------------------------------------
# Artist name extraction and splitting
# ---------------------------------------------------------------------------


def extract_embedded_artist(album_title: str) -> tuple[str | None, str]:
    """Extract embedded artist from album titles like 'Artist - Album'.

    Many releases store the label as band_name and embed the
    real artist in album_title as 'Artist - Album Title'.

    Returns (embedded_artist, remaining_album). If no embedded artist
    found, returns (None, album_title).
    """
    parts = [p.strip() for p in re.split(r"\s+[-\u2013\u2014]\s+", album_title) if p.strip()]
    if len(parts) >= 2:
        return parts[0], " - ".join(parts[1:])
    return None, album_title


# Pattern to detect genre-tag prefixes: comma-separated words before " - "
_GENRE_PREFIX = re.compile(
    r"^(?:[\w.]+(?:\s*,\s*[\w.]+)*)\s*-\s+",
    re.UNICODE,
)


def split_band_name(band_name: str) -> list[str]:
    """Extract candidate artist names from a band_name that may contain prefixes.

    band_name often contains patterns like:
    - "Label - Artist" (label prefix)
    - "Genre, Genre - Artist - Album" (genre tags)
    - "Artist" (clean, no splitting needed)

    Returns a list of candidate artist strings to try (best first).
    The original band_name is always included as the last fallback.
    """
    candidates: list[str] = []

    # Split on the " - " separator (standard in metadata)
    parts = [p.strip() for p in re.split(r"\s+[-\u2013\u2014]\s+", band_name) if p.strip()]

    if len(parts) >= 3:
        # "Label - Artist - Album" -> try middle part as artist
        candidates.append(parts[1])
        # Also try "Artist - Album" (last two joined) as artist
        candidates.append(parts[-2])
    if len(parts) >= 2:
        # "Label - Artist" -> try last part as artist
        candidates.append(parts[-1])
        # Also try first part (might actually be the artist)
        candidates.append(parts[0])

    # Always include the original as fallback
    candidates.append(band_name)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result


# ---------------------------------------------------------------------------
# Safe fuzzy matching with length guard
# ---------------------------------------------------------------------------


def safe_partial_ratio(query: str, target: str, min_len: int = 4) -> float:
    """partial_ratio with short-string and length-ratio protection.

    1. If either string is shorter than min_len characters,
       fall back to token_sort_ratio (full match, not substring).
    2. Apply a length-ratio penalty when strings differ greatly in
       length. This prevents short strings like "ra" from matching
       long strings like "ace ventura" via substring.

    Args:
        query: The search string (e.g., normalized artist name).
        target: The target string (e.g., normalized path component).
        min_len: Minimum length for either string to use partial_ratio.

    Returns:
        Fuzzy match score 0-100.
    """
    if not query or not target:
        return 0.0

    # For very short strings, use full token matching instead of substring
    if len(query) < min_len or len(target) < min_len:
        return fuzz.token_sort_ratio(query, target)

    score = fuzz.partial_ratio(query, target)

    # Apply length-ratio penalty: if strings differ greatly in length,
    # the partial match is likely a false substring match
    len_ratio = min(len(query), len(target)) / max(len(query), len(target))
    if len_ratio < 0.5:
        short, long_ = (query, target) if len(query) <= len(target) else (target, query)
        short_tokens = set(short.split())
        long_tokens = set(long_.split())
        # Relax penalty when all tokens of the shorter string appear in the
        # longer one (legitimate containment, not a false substring match).
        # Require 2+ tokens to avoid single-word coincidences like "music"
        # matching "music festival compilation".
        if len(short_tokens) >= 2 and short_tokens.issubset(long_tokens):
            score *= max(len_ratio * 2, 0.85)
        else:
            score *= len_ratio * 2

    return score


# ---------------------------------------------------------------------------
# Confidence tier classification
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


# ---------------------------------------------------------------------------
# Standalone scoring functions
# ---------------------------------------------------------------------------


def match_release(
    local_artist: str,
    local_album: str,
    bc_artist: str,
    bc_album: str,
) -> float:
    """Score a local album against a release (0-100).

    Weighted: artist 40%, album 60%.
    """
    la = normalize_for_matching(local_artist)
    ll = normalize_for_matching(local_album)
    ba = normalize_for_matching(bc_artist)
    bl = normalize_for_matching(bc_album)
    artist_score = fuzz.token_sort_ratio(la, ba)
    album_score = fuzz.token_sort_ratio(ll, bl)
    return artist_score * 0.4 + album_score * 0.6


def match_track(
    local_artist: str,
    local_title: str,
    bc_artist: str,
    bc_title: str,
) -> float:
    """Score a local track against a release track (0-100).

    Weighted: artist 40%, title 60%.
    """
    la = normalize_for_matching(local_artist)
    lt = normalize_for_matching(local_title)
    ba = normalize_for_matching(bc_artist)
    bt = normalize_for_matching(bc_title)
    artist_score = fuzz.token_sort_ratio(la, ba)
    title_score = fuzz.token_sort_ratio(lt, bt)
    return artist_score * 0.4 + title_score * 0.6
