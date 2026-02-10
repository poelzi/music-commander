"""HTML content parser for Dark Psy Portal WordPress posts.

Extracts structured release data (artist, album, download URLs, tracklist,
credits, cover art) from WordPress REST API post objects.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from bs4 import BeautifulSoup


@dataclass
class TrackInfo:
    """Parsed track from a release tracklist."""

    number: int | None
    title: str
    artist: str | None = None
    bpm: str | None = None


@dataclass
class ParsedRelease:
    """Structured data extracted from a portal post."""

    artist: str
    album: str
    download_urls: dict[str, str] = field(default_factory=dict)
    tracklist: list[TrackInfo] = field(default_factory=list)
    credits: str | None = None
    cover_art_url: str | None = None
    release_date: str | None = None
    label: str | None = None


# ---------------------------------------------------------------------------
# Title parsing
# ---------------------------------------------------------------------------

# V/A prefix patterns
_VA_PATTERN = re.compile(
    r"^(?:V/A|VA)\s*[-–—:]\s*(.+)$",
    re.IGNORECASE,
)
_VA_SPACE_PATTERN = re.compile(
    r"^(?:V/A|VA)\s+(.+)$",
    re.IGNORECASE,
)

# Label suffix in parentheses: "Title (Label Name)"
_LABEL_SUFFIX = re.compile(r"\s*\([^)]*(?:records?|label|audio)\s*[^)]*\)\s*$", re.IGNORECASE)


def parse_title(title: str) -> tuple[str, str]:
    """Split a WordPress post title into (artist, album).

    Handles HTML entities, V/A prefixes, and em-dash/en-dash separators.

    Args:
        title: The ``title.rendered`` field from the WordPress API.

    Returns:
        Tuple of (artist, album).
    """
    # 1. HTML-decode
    t = html.unescape(title).strip()

    # 2. Strip label suffix in parentheses
    t = _LABEL_SUFFIX.sub("", t).strip()

    # 3. Check V/A prefix
    m = _VA_PATTERN.match(t)
    if m:
        return "Various Artists", m.group(1).strip()
    m = _VA_SPACE_PATTERN.match(t)
    if m:
        return "Various Artists", m.group(1).strip()

    # 4. Split on first em-dash, en-dash, or ' - '
    for sep in ("\u2013", "\u2014", " - "):
        idx = t.find(sep)
        if idx > 0:
            left = t[:idx].strip()
            right = t[idx + len(sep) :].strip()
            if left and right:
                return left, right

    # 5. No delimiter found
    return "Various Artists", t


# ---------------------------------------------------------------------------
# Download URL extraction
# ---------------------------------------------------------------------------

_ARCHIVE_EXTENSIONS = (".zip", ".rar")


def extract_download_urls(html_content: str) -> dict[str, str]:
    """Extract archive download URLs from HTML content.

    Looks for ``<a>`` tags with hrefs pointing to anomalisticrecords.com
    that end in archive file extensions.

    Args:
        html_content: The ``content.rendered`` field from the WordPress API.

    Returns:
        Dict mapping format key to URL. Keys: ``"wav"``, ``"mp3"``,
        or ``"download"`` for unclassified archives.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    urls: dict[str, str] = {}

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if "anomalisticrecords.com" not in href:
            continue

        # Check the decoded URL for format classification
        href_decoded = unquote(href).lower()

        if not any(href_decoded.endswith(ext) for ext in _ARCHIVE_EXTENSIONS):
            continue

        if "wav" in href_decoded:
            urls["wav"] = href
        elif "mp3" in href_decoded:
            urls["mp3"] = href
        else:
            urls.setdefault("download", href)

    return urls


# ---------------------------------------------------------------------------
# Cover art extraction
# ---------------------------------------------------------------------------


def extract_cover_art(html_content: str, post: dict[str, Any] | None = None) -> str | None:
    """Extract cover art URL from HTML content.

    Looks for the first ``<img>`` tag in the content. Prefers the largest
    available size from srcset. Falls back to ``_embedded.wp:featuredmedia``
    if available in the post dict.

    Args:
        html_content: The ``content.rendered`` field.
        post: Optional full post dict (for featured media fallback).

    Returns:
        Cover art URL string, or None if not found.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Find first img tag (cover art is always the first image)
    img = soup.find("img")
    if img:
        # Prefer srcset for the largest image
        srcset = img.get("srcset", "")
        if srcset:
            best_url = _best_srcset_url(srcset)
            if best_url:
                return best_url
        # Fall back to src attribute
        src = img.get("src")
        if src:
            return src

    # Fallback: check featured media in post _embedded
    if post:
        embedded = post.get("_embedded", {})
        featured = embedded.get("wp:featuredmedia", [])
        if featured and isinstance(featured, list):
            media = featured[0]
            source_url = media.get("source_url")
            if source_url:
                return source_url

    return None


def _best_srcset_url(srcset: str) -> str | None:
    """Pick the largest image URL from an HTML srcset attribute.

    Args:
        srcset: The srcset attribute value (e.g., "url1 300w, url2 1024w").

    Returns:
        URL of the largest image, or None if srcset is empty.
    """
    best_width = 0
    best_url: str | None = None

    for entry in srcset.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.rsplit(None, 1)
        if len(parts) == 2:
            url, descriptor = parts
            # Parse width descriptor (e.g., "1024w")
            if descriptor.endswith("w"):
                try:
                    width = int(descriptor[:-1])
                    if width > best_width:
                        best_width = width
                        best_url = url.strip()
                except ValueError:
                    pass
        elif len(parts) == 1:
            # No descriptor — use as fallback
            if best_url is None:
                best_url = parts[0].strip()

    return best_url


# ---------------------------------------------------------------------------
# Tracklist extraction
# ---------------------------------------------------------------------------

# Pattern: "1. Title" or "01 - Title" or "1- Title" or "1.- Title"
_TRACK_LINE = re.compile(r"^\s*(\d{1,2})\s*[.\-–—)]+\s*(.+)$")

# BPM pattern: "[174 bpms]" or "[225 bpm]" or "(180 bpm)" or "[200bpms]"
_BPM_PATTERN = re.compile(
    r"[\[\(]\s*(\d{2,3}(?:\s*[-–]\s*\d{2,3})*)\s*bpms?\s*[\]\)]",
    re.IGNORECASE,
)

# Track artist pattern: "Title – Artist" (common in V/A compilations)
_TRACK_ARTIST_PATTERN = re.compile(r"^(.+?)\s*[-–—]\s+(.+)$")


def extract_tracklist(html_content: str) -> list[TrackInfo]:
    """Extract a tracklist from HTML content.

    Parses numbered lines from the content, extracting track number, title,
    artist (for compilations), and BPM where available.

    Args:
        html_content: The ``content.rendered`` field.

    Returns:
        List of TrackInfo objects. Empty list if no tracklist found.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text("\n", strip=True)

    tracks: list[TrackInfo] = []

    for line in text.split("\n"):
        line = line.strip()
        m = _TRACK_LINE.match(line)
        if not m:
            continue

        track_num = int(m.group(1))
        remainder = m.group(2).strip()

        # Extract BPM if present
        bpm: str | None = None
        bpm_match = _BPM_PATTERN.search(remainder)
        if bpm_match:
            bpm = bpm_match.group(1).strip()
            remainder = remainder[: bpm_match.start()].strip()

        # Try to split "Title – Artist" (V/A format)
        artist: str | None = None
        artist_match = _TRACK_ARTIST_PATTERN.match(remainder)
        if artist_match:
            title = artist_match.group(1).strip()
            artist = artist_match.group(2).strip()
        else:
            title = remainder

        # Clean up trailing punctuation
        title = title.rstrip(" -–—.,;:")

        if title:
            tracks.append(
                TrackInfo(
                    number=track_num,
                    title=title,
                    artist=artist,
                    bpm=bpm,
                )
            )

    return tracks


# ---------------------------------------------------------------------------
# Credits extraction
# ---------------------------------------------------------------------------

_CREDIT_PATTERNS = [
    re.compile(r"(?:written\s+(?:and\s+)?produced\s+by|produced\s+by)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:master(?:ed|ing)?\s+(?:by|at))[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:artwork|art|cover\s+art)\s+(?:by|–)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:released\s+by)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:compiled\s+by)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:mix(?:ed)?\s+by)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:design\s+by)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:letters?\s+by)[:\s]+(.+)", re.IGNORECASE),
    re.compile(r"(?:logo\s+by)[:\s]+(.+)", re.IGNORECASE),
]


def extract_credits(html_content: str) -> str | None:
    """Extract production credits from HTML content.

    Looks for lines matching common credit patterns like
    "Mastered by", "Artwork by", "Written and Produced by", etc.

    Args:
        html_content: The ``content.rendered`` field.

    Returns:
        Semicolon-separated credit string, or None if none found.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text("\n", strip=True)

    credits: list[str] = []

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for pattern in _CREDIT_PATTERNS:
            m = pattern.search(line)
            if m:
                # Use the full matched line (not just the capture group)
                # to preserve the credit type label
                credits.append(line.strip())
                break

    if not credits:
        return None

    return "; ".join(credits)


# ---------------------------------------------------------------------------
# Label extraction
# ---------------------------------------------------------------------------

_RELEASED_BY_PATTERN = re.compile(
    r"released\s+(?:by|on)[:\s]+(.+)",
    re.IGNORECASE,
)

_LABEL_STRIP = re.compile(r"\s*(?:records?|recordings?|music|audio|label)\s*$", re.IGNORECASE)


def extract_label(html_content: str) -> str | None:
    """Extract the record label name from HTML content.

    Looks for "Released by" or "Released on" patterns in the post text.
    Strips common suffixes like "Records" for a cleaner label name.

    Args:
        html_content: The ``content.rendered`` field.

    Returns:
        Label name string, or None if not found.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text("\n", strip=True)

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        m = _RELEASED_BY_PATTERN.search(line)
        if m:
            label = m.group(1).strip().rstrip(".,;:")
            # Take only the first label if multiple are joined with &/and
            for sep in (" & ", " and ", ", "):
                if sep in label.lower():
                    label = label[: label.lower().index(sep)]
                    break
            return label if label else None

    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def parse_release_content(post: dict[str, Any]) -> ParsedRelease:
    """Parse a WordPress post into structured release data.

    Args:
        post: A post dict from the WordPress REST API, with at least
            ``title.rendered``, ``content.rendered``, and ``date`` fields.

    Returns:
        ParsedRelease with extracted metadata.
    """
    title_rendered = post.get("title", {}).get("rendered", "")
    content_rendered = post.get("content", {}).get("rendered", "")
    date = post.get("date")

    artist, album = parse_title(title_rendered)

    release = ParsedRelease(
        artist=artist,
        album=album,
        download_urls=extract_download_urls(content_rendered),
        tracklist=extract_tracklist(content_rendered),
        credits=extract_credits(content_rendered),
        cover_art_url=extract_cover_art(content_rendered, post),
        release_date=date,
        label=extract_label(content_rendered),
    )

    return release
