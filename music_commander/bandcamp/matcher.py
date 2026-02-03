"""Fuzzy matching engine for local library <-> Bandcamp collection.

Iterates through Bandcamp releases and tries to find matching local files
using a 4-phase strategy:
  Phase 0: Already-tagged files (bandcamp-url git-annex metadata)
  Phase 1: Folder path matching (artist/album in file path)
  Phase 2: Global fuzzy search fallback
  Phase 3: Unmatched -> missing downloads
"""

from __future__ import annotations

import enum
import os
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from music_commander.cache.models import BandcampRelease, BandcampTrack, CacheTrack
from music_commander.utils.output import debug, is_debug, is_verbose, verbose

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
_ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_GUILLEMETS = re.compile(r"[«»„" "\u201c\u201d\u201e]")
_CATALOG_BRACKET = re.compile(r"\[[\w\d]+\]")
_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2015\-_]")
_NOISE_PHRASES = re.compile(
    r"\b(free\s+download|single|original\s+mix)\b",
    re.IGNORECASE,
)
_BC_DOMAIN = re.compile(r"https?://([\w-]+)\.bandcamp\.com")

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


def extract_embedded_artist(album_title: str) -> tuple[str | None, str]:
    """Extract embedded artist from album titles like 'Artist - Album'.

    Many Bandcamp releases store the label as band_name and embed the
    real artist in album_title as 'Artist - Album Title'.

    Returns (embedded_artist, remaining_album). If no embedded artist
    found, returns (None, album_title).
    """
    parts = [p.strip() for p in re.split(r"\s+[-\u2013\u2014]\s+", album_title) if p.strip()]
    if len(parts) >= 2:
        return parts[0], " - ".join(parts[1:])
    return None, album_title


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
# Band name splitting (label/genre prefix removal)
# ---------------------------------------------------------------------------

# Pattern to detect genre-tag prefixes: comma-separated words before " - "
_GENRE_PREFIX = re.compile(
    r"^(?:[\w.]+(?:\s*,\s*[\w.]+)*)\s*-\s+",
    re.UNICODE,
)


def split_band_name(band_name: str) -> list[str]:
    """Extract candidate artist names from a band_name that may contain prefixes.

    Bandcamp band_name often contains patterns like:
    - "Label - Artist" (label prefix)
    - "Genre, Genre - Artist - Album" (genre tags)
    - "Artist" (clean, no splitting needed)

    Returns a list of candidate artist strings to try (best first).
    The original band_name is always included as the last fallback.
    """
    candidates: list[str] = []

    # Split on the " - " separator (standard in Bandcamp metadata)
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


def _safe_partial_ratio(query: str, target: str, min_len: int = 4) -> float:
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
# Standalone scoring functions (used by repair.py and others)
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
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TrackMatch:
    """A single matched local file for a Bandcamp release."""

    local_key: str
    local_file: str | None
    bc_track_id: int | None  # None for release-level match (no track detail)
    score: float
    match_phase: str  # "metadata", "folder", "global"


@dataclass(slots=True)
class ReleaseMatch:
    """A matched Bandcamp release with its local file matches."""

    bc_sale_item_id: int
    bandcamp_url: str | None
    band_name: str
    album_title: str
    sale_item_type: str = "a"  # "a"=album, "t"=track/single, "b"=bundle
    tracks: list[TrackMatch] = field(default_factory=list)
    score: float = 0.0
    tier: MatchTier = MatchTier.NONE
    match_phase: str = ""


@dataclass(frozen=True, slots=True)
class MatchStats:
    """Statistics from the matching run."""

    total_releases: int
    matched_metadata: int
    matched_comment: int
    matched_folder: int
    matched_global: int
    unmatched: int


@dataclass(slots=True)
class MatchReport:
    """Complete results of a matching run."""

    matched: list[ReleaseMatch] = field(default_factory=list)
    unmatched_ids: list[int] = field(default_factory=list)
    stats: MatchStats | None = None


# Keep old MatchResult for backward compat with report.py during transition
@dataclass(frozen=True, slots=True)
class MatchResult:
    """Legacy: A single match between a local track and a Bandcamp item."""

    local_key: str
    bc_sale_item_id: int
    score: float
    tier: MatchTier
    match_type: str  # "release" or "track"


# ---------------------------------------------------------------------------
# Helper: extract folder from file path
# ---------------------------------------------------------------------------


def extract_folder(file_path: str) -> str:
    """Extract the directory portion of a repo-relative file path.

    Example: "Artist/Album/01-track.flac" -> "Artist/Album"
    """
    return os.path.dirname(file_path)


# ---------------------------------------------------------------------------
# Phase 0: Metadata matching (already tagged)
# ---------------------------------------------------------------------------


def _phase_metadata(
    bc_releases: list[BandcampRelease],
    url_to_tracks: dict[str, list[CacheTrack]],
) -> tuple[list[ReleaseMatch], set[int]]:
    """Match releases that already have bandcamp-url metadata on local files.

    Returns matched ReleaseMatch list and set of matched sale_item_ids.
    """
    matched: list[ReleaseMatch] = []
    matched_ids: set[int] = set()

    for release in bc_releases:
        if not release.bandcamp_url:
            continue
        tracks = url_to_tracks.get(release.bandcamp_url)
        if not tracks:
            continue

        track_matches = [
            TrackMatch(
                local_key=t.key,
                local_file=t.file,
                bc_track_id=None,
                score=100.0,
                match_phase="metadata",
            )
            for t in tracks
        ]
        rm = ReleaseMatch(
            bc_sale_item_id=release.sale_item_id,
            bandcamp_url=release.bandcamp_url,
            band_name=release.band_name,
            album_title=release.album_title,
            sale_item_type=release.sale_item_type,
            tracks=track_matches,
            score=100.0,
            tier=MatchTier.EXACT,
            match_phase="metadata",
        )
        matched.append(rm)
        matched_ids.add(release.sale_item_id)

    return matched, matched_ids


# ---------------------------------------------------------------------------
# Phase 0.5: Comment-based matching (bandcamp URL in comment tag)
# ---------------------------------------------------------------------------


def _phase_comment(
    remaining_releases: list[BandcampRelease],
    bc_tracks_by_release: dict[int, list[BandcampTrack]],
    comment_index: dict[str, list[CacheTrack]],
    folder_to_tracks: dict[str, list[CacheTrack]],
    all_tracks_by_key: dict[str, CacheTrack],
    threshold: int,
    claimed_folders: set[str] | None = None,
    on_release: Callable[[], None] | None = None,
) -> tuple[list[ReleaseMatch], set[int], set[str]]:
    """Match releases by checking if local files have the bandcamp URL in their comment tag.

    Bandcamp files embed the artist/label URL (e.g. https://artist.bandcamp.com)
    in the comment metadata. We extract the subdomain from the BC release URL and
    look for local tracks whose comments contain that subdomain.

    Returns matched ReleaseMatch list, set of matched sale_item_ids, and claimed folders.
    """
    matched: list[ReleaseMatch] = []
    matched_ids: set[int] = set()
    if claimed_folders is None:
        claimed_folders = set()
    _v = is_verbose()
    _d = is_debug()
    comment_threshold = max(threshold, 65)

    for release in remaining_releases:
        if on_release is not None:
            on_release()
        if not release.bandcamp_url:
            continue
        # Skip singles — they don't have their own folder
        if release.sale_item_type == "t":
            continue

        m = _BC_DOMAIN.search(release.bandcamp_url)
        if not m:
            continue
        subdomain = m.group(1).lower()

        candidate_tracks = comment_index.get(subdomain)
        if not candidate_tracks:
            continue

        # Group candidate tracks by folder
        folder_groups: dict[str, list[CacheTrack]] = defaultdict(list)
        for t in candidate_tracks:
            if t.file:
                folder = extract_folder(t.file)
                if folder and folder not in claimed_folders:
                    folder_groups[folder].append(t)

        if not folder_groups:
            continue

        # Find the best folder by fuzzy-matching album title
        norm_album = normalize_for_matching(release.album_title)
        best_score = 0.0
        best_folder = ""

        for folder, tracks in folder_groups.items():
            norm_folder_name = normalize_for_matching(folder.rsplit("/", 1)[-1])
            album_score = fuzz.partial_ratio(norm_album, norm_folder_name)
            if album_score > best_score:
                best_score = album_score
                best_folder = folder

        if best_score < comment_threshold:
            if _v and best_score >= comment_threshold * 0.8:
                verbose(
                    f"  [yellow]comment near-miss:[/yellow] {release.band_name} - {release.album_title} "
                    f"[bold][magenta]->[/magenta][/bold] {best_folder} (score={best_score:.1f}, subdomain={subdomain})"
                )
            continue

        # Claim this folder so duplicate releases don't grab it
        claimed_folders.add(best_folder)

        folder_tracks = folder_groups.get(best_folder, [])
        bc_tracks = bc_tracks_by_release.get(release.sale_item_id, [])
        track_matches = _match_tracks_in_folder(
            bc_tracks,
            folder_tracks,
            release.band_name,
            all_tracks_by_key,
            50,
        )

        if not track_matches:
            track_matches = [
                TrackMatch(
                    local_key=t.key,
                    local_file=t.file,
                    bc_track_id=None,
                    score=best_score,
                    match_phase="comment",
                )
                for t in folder_tracks
            ]

        rm = ReleaseMatch(
            bc_sale_item_id=release.sale_item_id,
            bandcamp_url=release.bandcamp_url,
            band_name=release.band_name,
            album_title=release.album_title,
            sale_item_type=release.sale_item_type,
            tracks=track_matches,
            score=best_score,
            tier=classify_match(best_score),
            match_phase="comment",
        )
        matched.append(rm)
        matched_ids.add(release.sale_item_id)

        if _v:
            verbose(
                f"  [green]comment match:[/green] {release.band_name} - {release.album_title} "
                f"[bold][magenta]->[/magenta][/bold] {best_folder} ({len(track_matches)} files, score={best_score:.1f})"
            )

    return matched, matched_ids, claimed_folders


# ---------------------------------------------------------------------------
# Phase 1: Folder path matching
# ---------------------------------------------------------------------------


def _score_artist_against_components(
    artist_candidates: list[str],
    components: list[str],
) -> float:
    """Score artist candidates against path components using safe partial ratio.

    Tries each artist candidate against each component and returns the best score.
    Uses _safe_partial_ratio to prevent short-string false matches.
    """
    best = 0.0
    for artist in artist_candidates:
        norm_a = normalize_for_matching(artist)
        for component in components:
            score = _safe_partial_ratio(norm_a, component)
            best = max(best, score)
    return best


def _phase_folder(
    remaining_releases: list[BandcampRelease],
    bc_tracks_by_release: dict[int, list[BandcampTrack]],
    folder_to_tracks: dict[str, list[CacheTrack]],
    norm_folder_keys: list[tuple[str, str]],  # (original_folder, normalized_folder)
    all_tracks_by_key: dict[str, CacheTrack],
    threshold: int,
    claimed_folders: set[str] | None = None,
    on_release: Callable[[], None] | None = None,
) -> tuple[list[ReleaseMatch], set[int], set[str]]:
    """Match releases by fuzzy-matching artist/album against folder paths.

    Uses a two-pass approach:
    1. Find best folder candidate for each release (no claiming).
    2. Greedily assign folders by score (highest first), preventing duplicates.

    Returns matched ReleaseMatch list, set of matched sale_item_ids, and claimed folders.
    """
    _v = is_verbose()
    _d = is_debug()
    if claimed_folders is None:
        claimed_folders = set()
    else:
        claimed_folders = set(claimed_folders)  # Copy to avoid mutating caller's set

    # --- Pass 1: Find best folder candidate for each release ---
    # Each entry: (release, best_folder, best_score, best_artist_score, best_album_score)
    candidates: list[tuple[BandcampRelease, str, float, float, float]] = []

    for release in remaining_releases:
        if on_release is not None:
            on_release()
        # Skip single-track purchases — they don't have their own folder
        if release.sale_item_type == "t":
            continue

        # Get artist candidates from split_band_name
        artist_candidates = split_band_name(release.band_name)
        norm_album = normalize_for_matching(release.album_title)

        # Extract embedded artist from album_title (e.g. "Artist - Album")
        emb_artist, emb_album = extract_embedded_artist(release.album_title)
        norm_emb_album: str | None = None
        if emb_artist:
            norm_emb_a = normalize_for_matching(emb_artist)
            if norm_emb_a not in {normalize_for_matching(c) for c in artist_candidates}:
                artist_candidates.append(emb_artist)
            norm_emb_album = normalize_for_matching(emb_album)

        best_score = 0.0
        best_folder = ""
        best_a_score = 0.0
        best_b_score = 0.0

        for orig_folder, norm_folder in norm_folder_keys:
            if orig_folder in claimed_folders:
                continue

            components = norm_folder.split("/")
            # Score artist: try all candidates, use safe_partial_ratio with length guard
            folder_artist_score = _score_artist_against_components(artist_candidates, components)

            # Score album: use _safe_partial_ratio with length guard
            # to prevent short path components like "na" from matching everything
            folder_album_score = 0.0
            for component in components:
                b_score = _safe_partial_ratio(norm_album, component)
                folder_album_score = max(folder_album_score, b_score)
                # Also try the extracted album part (without embedded artist prefix)
                if norm_emb_album:
                    b_score = _safe_partial_ratio(norm_emb_album, component)
                    folder_album_score = max(folder_album_score, b_score)

            # Both artist and album must be found somewhere in the path
            if folder_artist_score >= threshold and folder_album_score >= threshold:
                score = folder_artist_score * 0.4 + folder_album_score * 0.6
            else:
                score = 0.0

            # Volume mismatch guard: reject if both have volumes and they differ
            if score > 0:
                bc_vol = extract_volume(release.album_title)
                local_vol = extract_volume(orig_folder)
                if bc_vol is not None and local_vol is not None and bc_vol != local_vol:
                    if _d:
                        debug(
                            f"phase1: volume mismatch {release.album_title} (vol={bc_vol}) "
                            f"vs {orig_folder} (vol={local_vol}) -> rejected"
                        )
                    score = 0.0

            # Bonus for matching file count vs BC track count
            if score > 0:
                bc_track_count = len(bc_tracks_by_release.get(release.sale_item_id, []))
                folder_file_count = len(folder_to_tracks.get(orig_folder, []))
                if bc_track_count > 0 and folder_file_count > 0:
                    count_ratio = min(bc_track_count, folder_file_count) / max(
                        bc_track_count, folder_file_count
                    )
                    score += count_ratio * 5.0

            if _d and score > 50:
                debug(
                    f"phase1: {release.band_name} - {release.album_title} vs {orig_folder} | "
                    f"artist={folder_artist_score:.1f} album={folder_album_score:.1f} "
                    f"weighted={score:.1f}"
                )

            if score > best_score:
                best_score = score
                best_folder = orig_folder
                best_a_score = folder_artist_score
                best_b_score = folder_album_score

        if best_score >= threshold:
            candidates.append((release, best_folder, best_score, best_a_score, best_b_score))
        elif _v:
            if best_score >= threshold * 0.8:
                verbose(
                    f"  [yellow]folder near-miss:[/yellow] {release.band_name} - {release.album_title} "
                    f"[bold][magenta]->[/magenta][/bold] {best_folder} (score={best_score:.1f})"
                )
            elif best_score == 0:
                verbose(
                    f"  [red]folder miss:[/red] {release.band_name} - {release.album_title} "
                    f"(no folder candidate found)"
                )

    # --- Pass 2: Greedily assign folders by score (highest first) ---
    candidates.sort(key=lambda x: x[2], reverse=True)

    matched: list[ReleaseMatch] = []
    matched_ids: set[int] = set()

    for release, best_folder, best_score, best_a_score, best_b_score in candidates:
        if best_folder in claimed_folders:
            if _v:
                verbose(
                    f"  [yellow]folder claimed:[/yellow] {release.band_name} - {release.album_title} "
                    f"[bold][magenta]->[/magenta][/bold] {best_folder} (score={best_score:.1f}, already claimed)"
                )
            continue

        # Claim this folder
        claimed_folders.add(best_folder)

        # Found a matching folder - collect tracks from it
        folder_tracks = folder_to_tracks.get(best_folder, [])
        if not folder_tracks:
            continue

        bc_tracks = bc_tracks_by_release.get(release.sale_item_id, [])
        track_matches = _match_tracks_in_folder(
            bc_tracks,
            folder_tracks,
            release.band_name,
            all_tracks_by_key,
            threshold,
        )

        # If no BC tracks to match against, just assign all folder files
        if not track_matches:
            track_matches = [
                TrackMatch(
                    local_key=t.key,
                    local_file=t.file,
                    bc_track_id=None,
                    score=best_score,
                    match_phase="folder",
                )
                for t in folder_tracks
            ]

        rm = ReleaseMatch(
            bc_sale_item_id=release.sale_item_id,
            bandcamp_url=release.bandcamp_url,
            band_name=release.band_name,
            album_title=release.album_title,
            sale_item_type=release.sale_item_type,
            tracks=track_matches,
            score=best_score,
            tier=classify_match(best_score),
            match_phase="folder",
        )
        matched.append(rm)
        matched_ids.add(release.sale_item_id)

        if _v:
            verbose(
                f"  [green]folder match:[/green] {release.band_name} - {release.album_title} "
                f"[bold][magenta]->[/magenta][/bold] {best_folder} ({len(track_matches)} files, score={best_score:.1f})"
            )

    return matched, matched_ids, claimed_folders


def _match_tracks_in_folder(
    bc_tracks: list[BandcampTrack],
    folder_tracks: list[CacheTrack],
    band_name: str,
    all_tracks_by_key: dict[str, CacheTrack],
    threshold: int,
) -> list[TrackMatch]:
    """Match individual BC tracks against local files in a folder.

    If a BC track can't be matched in the folder, searches globally.
    """
    if not bc_tracks:
        return []

    results: list[TrackMatch] = []
    used_keys: set[str] = set()

    # Pre-normalize folder track titles
    norm_folder: list[tuple[CacheTrack, str]] = [
        (t, normalize_for_matching(t.title or "")) for t in folder_tracks if t.title
    ]

    for bc_track in bc_tracks:
        norm_bc_title = normalize_for_matching(bc_track.title)
        best_score = 0.0
        best_local: CacheTrack | None = None

        for local_track, norm_local_title in norm_folder:
            if local_track.key in used_keys:
                continue
            score = fuzz.token_sort_ratio(norm_bc_title, norm_local_title)
            # Bonus for matching track number
            if (
                bc_track.track_number is not None
                and local_track.tracknumber
                and str(bc_track.track_number) == local_track.tracknumber
            ):
                score = min(100.0, score + 5)
            if score > best_score:
                best_score = score
                best_local = local_track

        if best_local and best_score >= 50:
            used_keys.add(best_local.key)
            results.append(
                TrackMatch(
                    local_key=best_local.key,
                    local_file=best_local.file,
                    bc_track_id=bc_track.id,
                    score=best_score,
                    match_phase="folder",
                )
            )

    return results


# ---------------------------------------------------------------------------
# Phase 2: Global fuzzy fallback
# ---------------------------------------------------------------------------


def _phase_global(
    remaining_releases: list[BandcampRelease],
    bc_tracks_by_release: dict[int, list[BandcampTrack]],
    all_tracks: list[CacheTrack],
    threshold: int,
    claimed_folders: set[str] | None = None,
    on_release: Callable[[], None] | None = None,
) -> tuple[list[ReleaseMatch], set[int], set[str]]:
    """Global fuzzy match for releases that couldn't be folder-matched.

    Tries artist+album weighted match against all local tracks,
    grouping results by folder to find the best album match.
    Falls back to track-level matching if no album match found.

    Returns matched ReleaseMatch list, set of matched sale_item_ids, and claimed folders.
    """
    matched: list[ReleaseMatch] = []
    matched_ids: set[int] = set()
    _v = is_verbose()
    _d = is_debug()
    if claimed_folders is None:
        claimed_folders = set()
    else:
        claimed_folders = set(claimed_folders)  # Copy to avoid mutating caller's set

    # Pre-normalize local tracks
    norm_locals: list[tuple[CacheTrack, str, str, str]] = []
    for t in all_tracks:
        if not t.artist:
            continue
        norm_locals.append(
            (
                t,
                normalize_for_matching(t.artist),
                normalize_for_matching(t.album or ""),
                normalize_for_matching(t.title or ""),
            )
        )

    for release in remaining_releases:
        if on_release is not None:
            on_release()
        # Try all artist candidates from split_band_name
        artist_candidates = split_band_name(release.band_name)
        norm_bc_artists = [normalize_for_matching(a) for a in artist_candidates]
        norm_bc_album = normalize_for_matching(release.album_title)
        is_single = release.sale_item_type == "t"

        # Extract embedded artist from album_title (e.g. "Artist - Album")
        emb_artist, emb_album = extract_embedded_artist(release.album_title)
        norm_emb_album: str | None = None
        if emb_artist:
            norm_emb_a = normalize_for_matching(emb_artist)
            if norm_emb_a not in set(norm_bc_artists):
                norm_bc_artists.append(norm_emb_a)
            norm_emb_album = normalize_for_matching(emb_album)

        # Cache artist scores per unique local artist to avoid redundant computation
        _artist_score_cache: dict[str, float] = {}

        def _best_artist_score(norm_la: str) -> float:
            if norm_la in _artist_score_cache:
                return _artist_score_cache[norm_la]
            score = max(fuzz.token_sort_ratio(nba, norm_la) for nba in norm_bc_artists)
            _artist_score_cache[norm_la] = score
            return score

        # Singles skip album-level matching — go straight to track-level
        if is_single:
            bc_tracks = bc_tracks_by_release.get(release.sale_item_id, [])
            if not bc_tracks:
                # No track data — try matching album_title as track title
                bc_tracks_synthetic = [
                    type("FakeTrack", (), {"id": None, "title": release.album_title})
                ]
            else:
                bc_tracks_synthetic = bc_tracks

            track_matches = []
            for bc_track in bc_tracks_synthetic:
                norm_bc_title = normalize_for_matching(bc_track.title)
                best_score = 0.0
                best_local: CacheTrack | None = None

                for local_track, norm_la, _norm_ll, norm_lt in norm_locals:
                    if not norm_lt:
                        continue
                    artist_score = _best_artist_score(norm_la)
                    title_score = fuzz.token_sort_ratio(norm_bc_title, norm_lt)
                    score = artist_score * 0.4 + title_score * 0.6
                    if score > best_score:
                        best_score = score
                        best_local = local_track

                if best_local and best_score >= threshold:
                    track_matches.append(
                        TrackMatch(
                            local_key=best_local.key,
                            local_file=best_local.file,
                            bc_track_id=getattr(bc_track, "id", None),
                            score=best_score,
                            match_phase="global",
                        )
                    )

            if track_matches:
                avg_score = sum(tm.score for tm in track_matches) / len(track_matches)
                rm = ReleaseMatch(
                    bc_sale_item_id=release.sale_item_id,
                    bandcamp_url=release.bandcamp_url,
                    band_name=release.band_name,
                    album_title=release.album_title,
                    sale_item_type=release.sale_item_type,
                    tracks=track_matches,
                    score=avg_score,
                    tier=classify_match(avg_score),
                    match_phase="global",
                )
                matched.append(rm)
                matched_ids.add(release.sale_item_id)

                if _v:
                    local_path = track_matches[0].local_file or extract_folder(
                        track_matches[0].local_file or ""
                    )
                    verbose(
                        f"  [green]global match [t]:[/green] {release.band_name} - {release.album_title} "
                        f"[dim][white]->[/white][/dim] {local_path} (score={avg_score:.1f})"
                    )
            continue

        # Score all local tracks at release level (artist + album)
        candidates: list[tuple[CacheTrack, float]] = []
        for local_track, norm_la, norm_ll, _norm_lt in norm_locals:
            if not norm_ll:
                continue
            # Try all artist candidates, take best
            artist_score = _best_artist_score(norm_la)
            album_score = fuzz.token_sort_ratio(norm_bc_album, norm_ll)
            # Also try the extracted album part (without embedded artist prefix)
            if norm_emb_album:
                album_score = max(album_score, fuzz.token_sort_ratio(norm_emb_album, norm_ll))
            # Require BOTH artist and album to have independent relevance
            # to prevent perfect artist matches from carrying meaningless album matches
            if artist_score < 50 or album_score < 50:
                continue
            score = artist_score * 0.4 + album_score * 0.6
            if score >= threshold:
                candidates.append((local_track, score))

        if candidates:
            # Group by folder and pick the folder with the most matches
            bc_vol = extract_volume(release.album_title)
            folder_groups: dict[str, list[tuple[CacheTrack, float]]] = defaultdict(list)
            for local_track, score in candidates:
                folder = extract_folder(local_track.file or "")
                if folder in claimed_folders:
                    continue
                # Volume mismatch guard
                if bc_vol is not None:
                    local_vol = extract_volume(folder)
                    if local_vol is not None and local_vol != bc_vol:
                        continue
                folder_groups[folder].append((local_track, score))

            # Pick best folder (most tracks, then highest avg score)
            best_folder_tracks: list[tuple[CacheTrack, float]] = []
            best_folder_key = ""
            for folder, tracks in folder_groups.items():
                if len(tracks) > len(best_folder_tracks) or (
                    len(tracks) == len(best_folder_tracks)
                    and sum(s for _, s in tracks) > sum(s for _, s in best_folder_tracks)
                ):
                    best_folder_tracks = tracks
                    best_folder_key = folder

            if best_folder_tracks:
                avg_score = sum(s for _, s in best_folder_tracks) / len(best_folder_tracks)

                if _d:
                    debug(
                        f"phase2: {release.band_name} - {release.album_title} -> "
                        f"{best_folder_key} ({len(best_folder_tracks)} files, score={avg_score:.1f})"
                    )

                # Claim this folder
                claimed_folders.add(best_folder_key)

                track_matches = [
                    TrackMatch(
                        local_key=t.key,
                        local_file=t.file,
                        bc_track_id=None,
                        score=s,
                        match_phase="global",
                    )
                    for t, s in best_folder_tracks
                ]

                rm = ReleaseMatch(
                    bc_sale_item_id=release.sale_item_id,
                    bandcamp_url=release.bandcamp_url,
                    band_name=release.band_name,
                    album_title=release.album_title,
                    sale_item_type=release.sale_item_type,
                    tracks=track_matches,
                    score=avg_score,
                    tier=classify_match(avg_score),
                    match_phase="global",
                )
                matched.append(rm)
                matched_ids.add(release.sale_item_id)

                if _v:
                    verbose(
                        f"  [green]global match:[/green] {release.band_name} - {release.album_title} "
                        f"[bold][magenta]->[/magenta][/bold] {best_folder_key} ({len(track_matches)} files, score={avg_score:.1f})"
                    )
                continue

        # Track-level fallback: try matching individual BC tracks
        bc_tracks = bc_tracks_by_release.get(release.sale_item_id, [])
        if not bc_tracks:
            continue

        track_matches = []
        for bc_track in bc_tracks:
            norm_bc_title = normalize_for_matching(bc_track.title)
            best_score = 0.0
            best_local: CacheTrack | None = None

            for local_track, norm_la, _norm_ll, norm_lt in norm_locals:
                if not norm_lt:
                    continue
                # Try all artist candidates, take best
                artist_score = _best_artist_score(norm_la)
                title_score = fuzz.token_sort_ratio(norm_bc_title, norm_lt)
                score = artist_score * 0.4 + title_score * 0.6
                if score > best_score:
                    best_score = score
                    best_local = local_track

            if best_local and best_score >= threshold:
                track_matches.append(
                    TrackMatch(
                        local_key=best_local.key,
                        local_file=best_local.file,
                        bc_track_id=bc_track.id,
                        score=best_score,
                        match_phase="global",
                    )
                )

        if track_matches:
            avg_score = sum(tm.score for tm in track_matches) / len(track_matches)
            rm = ReleaseMatch(
                bc_sale_item_id=release.sale_item_id,
                bandcamp_url=release.bandcamp_url,
                band_name=release.band_name,
                album_title=release.album_title,
                sale_item_type=release.sale_item_type,
                tracks=track_matches,
                score=avg_score,
                tier=classify_match(avg_score),
                match_phase="global",
            )
            matched.append(rm)
            matched_ids.add(release.sale_item_id)

    return matched, matched_ids, claimed_folders


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def match_releases(
    bc_releases: list[BandcampRelease],
    bc_tracks: list[BandcampTrack],
    local_tracks: list[CacheTrack],
    threshold: int = 60,
    on_phase: Callable[[str, int], None] | None = None,
) -> MatchReport:
    """Match Bandcamp releases against local library using 4-phase strategy.

    Phase 0: Already-tagged files (bandcamp-url metadata)
    Phase 1: Folder path matching (artist/album in file path)
    Phase 2: Global fuzzy search fallback
    Phase 3: Remaining = unmatched (missing downloads)

    Args:
        bc_releases: All Bandcamp releases from the sync.
        bc_tracks: All Bandcamp tracks from the sync.
        local_tracks: All local tracks from the cache.
        threshold: Minimum match score (0-100).

    Returns:
        MatchReport with matched releases, unmatched IDs, and stats.
    """
    report = MatchReport()
    _v = is_verbose()

    # Build indexes
    verbose("Building match indexes...")

    # Index: bandcamp_url -> local tracks (for Phase 0)
    url_to_tracks: dict[str, list[CacheTrack]] = defaultdict(list)
    for t in local_tracks:
        if t.bandcamp_url:
            url_to_tracks[t.bandcamp_url].append(t)

    # Index: folder_path -> local tracks (for Phase 1)
    folder_to_tracks: dict[str, list[CacheTrack]] = defaultdict(list)
    for t in local_tracks:
        if t.file:
            folder = extract_folder(t.file)
            if folder:
                folder_to_tracks[folder].append(t)

    # Pre-normalize folder keys for Phase 1.
    # Normalize each path component individually and rejoin with "/"
    # so _phase_folder() can split on "/" for per-component scoring.
    norm_folder_keys: list[tuple[str, str]] = [
        (folder, "/".join(normalize_for_matching(part) for part in folder.split("/")))
        for folder in folder_to_tracks
    ]

    # Index: key -> CacheTrack
    all_tracks_by_key: dict[str, CacheTrack] = {t.key: t for t in local_tracks}

    # Index: release_id -> BC tracks
    bc_tracks_by_release: dict[int, list[BandcampTrack]] = defaultdict(list)
    for t in bc_tracks:
        bc_tracks_by_release[t.release_id].append(t)

    # Index: bandcamp subdomain -> local tracks with that URL in comment (for Phase 0.5)
    comment_index: dict[str, list[CacheTrack]] = defaultdict(list)
    for t in local_tracks:
        if t.comment:
            for m in _BC_DOMAIN.finditer(t.comment):
                comment_index[m.group(1).lower()].append(t)

    verbose(
        f"Indexes: {len(url_to_tracks)} tagged URLs, "
        f"{len(comment_index)} comment subdomains, "
        f"{len(folder_to_tracks)} folders, "
        f"{len(local_tracks)} local tracks, "
        f"{len(bc_releases)} BC releases"
    )

    matched_ids: set[int] = set()

    # --- Phase 0: Metadata ---
    verbose("Phase 0: Checking already-tagged files...")
    phase0_matches, phase0_ids = _phase_metadata(bc_releases, url_to_tracks)
    report.matched.extend(phase0_matches)
    matched_ids.update(phase0_ids)
    verbose(f"Phase 0: {len(phase0_matches)} releases matched via metadata")
    if on_phase:
        on_phase("metadata", len(phase0_matches))

    # Track claimed folders across phases to prevent duplicate assignments
    claimed_folders: set[str] = set()

    # Collect folders from Phase 0 matches
    for rm in phase0_matches:
        for tm in rm.tracks:
            if tm.local_file:
                folder = extract_folder(tm.local_file)
                if folder:
                    claimed_folders.add(folder)

    # --- Phase 0.5: Comment-based matching ---
    remaining = [r for r in bc_releases if r.sale_item_id not in matched_ids]
    verbose(f"Phase 0.5: Comment matching {len(remaining)} remaining releases...")
    phase05_matches, phase05_ids, claimed_folders = _phase_comment(
        remaining,
        bc_tracks_by_release,
        comment_index,
        folder_to_tracks,
        all_tracks_by_key,
        threshold,
        claimed_folders=claimed_folders,
    )
    report.matched.extend(phase05_matches)
    matched_ids.update(phase05_ids)
    verbose(f"Phase 0.5: {len(phase05_matches)} releases matched via comment URL")
    if on_phase:
        on_phase("comment", len(phase05_matches))

    # --- Phase 1: Folder matching ---
    folder_threshold = max(threshold, 75)
    remaining = [r for r in bc_releases if r.sale_item_id not in matched_ids]
    verbose(
        f"Phase 1: Folder matching {len(remaining)} remaining releases (threshold={folder_threshold})..."
    )
    phase1_matches, phase1_ids, claimed_folders = _phase_folder(
        remaining,
        bc_tracks_by_release,
        folder_to_tracks,
        norm_folder_keys,
        all_tracks_by_key,
        folder_threshold,
        claimed_folders=claimed_folders,
    )
    report.matched.extend(phase1_matches)
    matched_ids.update(phase1_ids)
    verbose(f"Phase 1: {len(phase1_matches)} releases matched via folder")
    if on_phase:
        on_phase("folder", len(phase1_matches))

    # --- Phase 2: Global fuzzy fallback ---
    global_threshold = max(threshold, 65)
    remaining = [r for r in bc_releases if r.sale_item_id not in matched_ids]
    verbose(
        f"Phase 2: Global matching {len(remaining)} remaining releases (threshold={global_threshold})..."
    )

    # For Phase 2 (slow), provide per-release progress callback
    phase2_on_release = (lambda: on_phase("tick", 1)) if on_phase else None
    phase2_matches, phase2_ids, claimed_folders = _phase_global(
        remaining,
        bc_tracks_by_release,
        local_tracks,
        global_threshold,
        claimed_folders=claimed_folders,
        on_release=phase2_on_release,
    )
    report.matched.extend(phase2_matches)
    matched_ids.update(phase2_ids)
    verbose(f"Phase 2: {len(phase2_matches)} releases matched via global search")

    # --- Phase 3: Unmatched ---
    report.unmatched_ids = [
        r.sale_item_id for r in bc_releases if r.sale_item_id not in matched_ids
    ]
    verbose(f"Unmatched: {len(report.unmatched_ids)} releases")

    # Build stats
    report.stats = MatchStats(
        total_releases=len(bc_releases),
        matched_metadata=len(phase0_matches),
        matched_comment=len(phase05_matches),
        matched_folder=len(phase1_matches),
        matched_global=len(phase2_matches),
        unmatched=len(report.unmatched_ids),
    )

    # Sort by score descending
    report.matched.sort(key=lambda r: r.score, reverse=True)

    return report
