"""Bandcamp HTML page data extraction.

Parses Bandcamp HTML pages to extract structured JSON from
data-blob attributes on page divs.
"""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup

from music_commander.exceptions import BandcampParseError


def parse_pagedata(html: str, url: str = "") -> dict[str, Any]:
    """Extract and parse the data-blob JSON from a Bandcamp page.

    Looks for a div with id="pagedata" (or "HomepageApp" as fallback)
    and extracts its data-blob attribute as JSON.

    Args:
        html: Raw HTML content of the page.
        url: URL of the page (for error reporting).

    Returns:
        Parsed JSON dictionary from the data-blob.

    Raises:
        BandcampParseError: If the page structure is unexpected.
    """
    soup = BeautifulSoup(html, "html.parser")

    pagedata_div = soup.find("div", {"id": "pagedata"})
    if pagedata_div is None:
        pagedata_div = soup.find("div", {"id": "HomepageApp"})

    if pagedata_div is None:
        raise BandcampParseError(
            url,
            "Could not find pagedata or HomepageApp div in page",
            html[:500],
        )

    data_blob = pagedata_div.get("data-blob")  # type: ignore[union-attr]
    if not data_blob:
        raise BandcampParseError(
            url,
            "Found pagedata div but data-blob attribute is empty",
            str(pagedata_div)[:500],
        )

    try:
        return json.loads(data_blob)  # type: ignore[arg-type]
    except json.JSONDecodeError as e:
        raise BandcampParseError(
            url,
            f"Failed to parse data-blob JSON: {e}",
            str(data_blob)[:500],
        ) from e


def parse_digital_items(html: str, url: str = "") -> list[dict[str, Any]]:
    """Extract digital_items from a Bandcamp redownload page.

    The redownload page contains a pagedata div whose data-blob
    has a digital_items array with download information.

    Args:
        html: Raw HTML of the redownload page.
        url: URL of the page (for error reporting).

    Returns:
        List of digital item dictionaries.

    Raises:
        BandcampParseError: If digital_items cannot be extracted.
    """
    blob = parse_pagedata(html, url)

    digital_items = blob.get("digital_items")
    if digital_items is None:
        raise BandcampParseError(
            url,
            "No digital_items found in pagedata",
            json.dumps(list(blob.keys()))[:500],
        )

    if not isinstance(digital_items, list):
        raise BandcampParseError(
            url,
            f"digital_items is not a list: {type(digital_items).__name__}",
            str(digital_items)[:500],
        )

    return digital_items


def extract_download_formats(digital_item: dict[str, Any]) -> dict[str, str]:
    """Extract available download formats from a digital item.

    Args:
        digital_item: A single digital item from digital_items.

    Returns:
        Dict mapping encoding name to download URL.
    """
    downloads = digital_item.get("downloads", {})
    formats: dict[str, str] = {}

    if isinstance(downloads, dict):
        for encoding, info in downloads.items():
            if isinstance(info, dict) and "url" in info:
                formats[encoding] = info["url"]

    return formats
