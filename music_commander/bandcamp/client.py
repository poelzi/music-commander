"""Bandcamp HTTP client for collection and download APIs.

Handles authenticated requests to Bandcamp's undocumented API endpoints
for fetching purchase collections and resolving download URLs.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from typing import Any

import requests

from music_commander.bandcamp.parser import (
    extract_download_formats,
    parse_digital_items,
    parse_pagedata,
)
from music_commander.exceptions import (
    BandcampAuthError,
    BandcampError,
    BandcampParseError,
)

logger = logging.getLogger(__name__)

_USER_AGENT = "music-commander/0.1"
_REQUEST_TIMEOUT = 30
_COLLECTION_PAGE_SIZE = 100
_MAX_RETRIES = 5
_BACKOFF_BASE = 2.0  # seconds

_COLLECTION_API_URL = "https://bandcamp.com/api/fancollection/1/collection_items"


class _AdaptiveRateLimiter:
    """AIMD (Additive Increase / Multiplicative Decrease) rate limiter.

    Discovers the optimal request rate by:
    - Linearly decreasing the inter-request interval on each success
    - Multiplicatively increasing it on 429/503 responses

    Converges to the server's actual rate limit and stays near it.
    """

    def __init__(
        self,
        min_interval: float = 0.05,
        max_interval: float = 30.0,
        initial_interval: float = 0.1,
        increase_delta: float = 0.1,
        decrease_factor: float = 1.2,
    ) -> None:
        self._interval = initial_interval
        self._min = min_interval
        self._max = max_interval
        self._delta = increase_delta
        self._factor = decrease_factor
        self._last_request = 0.0

    def wait(self) -> None:
        """Sleep if needed to respect the current rate limit interval."""
        now = time.monotonic()
        elapsed = now - self._last_request
        if self._last_request > 0 and elapsed < self._interval:
            time.sleep(self._interval - elapsed)
        self._last_request = time.monotonic()

    def on_success(self) -> None:
        """Additive increase: slowly ramp up request rate."""
        self._interval = max(self._min, self._interval - self._delta)

    def on_rate_limited(self) -> None:
        """Multiplicative decrease: back off on 429/503."""
        self._interval = min(self._max, self._interval * self._factor)
        logger.info(
            "Rate limiter: slowing to %.2fs between requests (%.1f req/s)",
            self._interval,
            1.0 / self._interval if self._interval > 0 else 0,
        )

    @property
    def interval(self) -> float:
        return self._interval


class BandcampClient:
    """HTTP client for Bandcamp API interactions.

    Args:
        session_cookie: The identity cookie value for authentication.
        fan_id: The authenticated user's fan ID.
    """

    def __init__(self, session_cookie: str, fan_id: int) -> None:
        self.session_cookie = session_cookie
        self.fan_id = fan_id
        self._session = requests.Session()
        self._session.cookies.set("identity", session_cookie, domain=".bandcamp.com")
        self._session.headers.update({"User-Agent": _USER_AGENT})
        self._limiter = _AdaptiveRateLimiter()

    def _request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        """Make an HTTP request with retry and backoff logic.

        Handles HTTP 429 (rate limited) and 503 (service unavailable)
        with exponential backoff.

        Args:
            method: HTTP method ("GET" or "POST").
            url: Request URL.
            **kwargs: Additional arguments passed to requests.

        Returns:
            The HTTP response.

        Raises:
            BandcampError: If max retries exceeded.
            BandcampAuthError: If authentication fails (401/403).
        """
        kwargs.setdefault("timeout", _REQUEST_TIMEOUT)

        for attempt in range(_MAX_RETRIES):
            self._limiter.wait()

            try:
                resp = self._session.request(method, url, **kwargs)
            except requests.RequestException as e:
                if attempt == _MAX_RETRIES - 1:
                    raise BandcampError(
                        f"Request to {url} failed after {_MAX_RETRIES} attempts: {e}"
                    ) from e
                wait = _BACKOFF_BASE * (2**attempt)
                logger.warning("Request failed, retrying in %.1fs: %s", wait, e)
                time.sleep(wait)
                continue

            if resp.status_code in (401, 403):
                raise BandcampAuthError(
                    "Bandcamp authentication failed. Your session cookie may have expired. "
                    "Re-authenticate with: bandcamp auth --browser firefox"
                )

            if resp.status_code in (429, 503):
                self._limiter.on_rate_limited()
                if attempt == _MAX_RETRIES - 1:
                    raise BandcampError(
                        f"Rate limited by Bandcamp after {_MAX_RETRIES} retries. Try again later."
                    )
                # Respect Retry-After header if present
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(float(retry_after), _BACKOFF_BASE)
                    except ValueError:
                        wait = _BACKOFF_BASE * (2**attempt)
                else:
                    wait = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Bandcamp rate limit detected (HTTP %d), waiting %.1fs...",
                    resp.status_code,
                    wait,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            self._limiter.on_success()
            return resp

        # Should not reach here, but satisfy type checker
        raise BandcampError(f"Request to {url} failed after {_MAX_RETRIES} attempts")

    def stream_get(self, url: str, **kwargs: Any) -> requests.Response:
        """Make a streaming GET request through the authenticated session.

        Uses the shared session (with auth cookies) and rate limiter,
        providing retry and backoff logic consistent with all other
        Bandcamp API calls. Suitable for large file downloads where the
        response body should be consumed incrementally.

        Args:
            url: Request URL.
            **kwargs: Additional arguments passed to requests (e.g. timeout).

        Returns:
            The HTTP response with streaming enabled.
        """
        kwargs["stream"] = True
        return self._request("GET", url, **kwargs)

    def fetch_collection_summary(self) -> dict[str, Any]:
        """Fetch collection summary including username and item count.

        Uses the fan/2/collection_summary API endpoint.

        Returns:
            Dict with 'username', 'url', and 'tralbum_lookup' (dict of all items).
        """
        resp = self._request(
            "POST",
            "https://bandcamp.com/api/fan/2/collection_summary",
            json={"fan_id": self.fan_id},
        )
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data.get("collection_summary", {})

    def fetch_collection_count(self) -> int | None:
        """Fetch the total number of items in the user's collection.

        Returns:
            Total item count, or None if it cannot be determined.
        """
        try:
            summary = self.fetch_collection_summary()
            lookup = summary.get("tralbum_lookup")
            if lookup is not None:
                return len(lookup)
            return None
        except Exception:
            logger.debug("Could not fetch collection count")
            return None

    def fetch_collection_page(self, older_than_token: str | None = None) -> dict[str, Any]:
        """Fetch a single page of the user's purchase collection.

        Args:
            older_than_token: Pagination token for fetching older items.
                None fetches the first (newest) page.

        Returns:
            API response dict containing 'items' and 'redownload_urls'.
        """
        payload: dict[str, Any] = {
            "fan_id": self.fan_id,
            "count": _COLLECTION_PAGE_SIZE,
            "older_than_token": older_than_token or "9999999999::a::",
        }

        resp = self._request("POST", _COLLECTION_API_URL, json=payload)

        try:
            data = resp.json()
        except ValueError as e:
            raise BandcampParseError(
                _COLLECTION_API_URL,
                f"Invalid JSON in collection response: {e}",
                resp.text[:500],
            ) from e

        return data

    def iter_collection(self) -> Generator[dict[str, Any], None, None]:
        """Iterate over all items in the user's purchase collection.

        Handles pagination automatically, yielding individual items.
        Each item contains purchase metadata including band_name,
        album_title, sale_item_type, sale_item_id, etc.

        Yields:
            Individual collection item dicts.
        """
        token: str | None = None

        while True:
            data = self.fetch_collection_page(older_than_token=token)

            items = data.get("items", [])
            if not items:
                break

            redownload_urls = data.get("redownload_urls", {})

            for item in items:
                # Attach redownload URL to item if available
                item_key = f"{item.get('sale_item_type', '')}{item.get('sale_item_id', '')}"
                if item_key in redownload_urls:
                    item["redownload_url"] = redownload_urls[item_key]
                yield item

            # Get next page token
            token = data.get("last_token")
            if token is None:
                break

    def resolve_download_url(
        self,
        redownload_url: str,
        encoding: str,
        sale_item_id: int | None = None,
    ) -> str:
        """Resolve a format-specific download URL for a purchased release.

        Fetches the redownload page, extracts digital items, and finds
        the download URL for the requested encoding format.

        Args:
            redownload_url: URL to the redownload page for this purchase.
            encoding: Bandcamp encoding key (e.g., "flac", "mp3-320").
            sale_item_id: Optional sale item ID to match the correct digital
                item on pages with multiple items (e.g., discography bundles).

        Returns:
            The direct download URL for the requested format.

        Raises:
            BandcampError: If format is not available or URL cannot be resolved.
            BandcampParseError: If page structure is unexpected.
        """
        resp = self._request("GET", redownload_url)
        digital_items = parse_digital_items(resp.text, redownload_url)

        if not digital_items:
            raise BandcampError(f"No downloadable items found at {redownload_url}")

        # Match by sale_item_id if provided
        item = None
        if sale_item_id is not None:
            for di in digital_items:
                di_id = di.get("id") or di.get("art_id") or di.get("sale_item_id")
                if di_id is not None and int(di_id) == sale_item_id:
                    item = di
                    break

        # Fall back to first item if no match or no sale_item_id
        if item is None:
            item = digital_items[0]

        formats = extract_download_formats(item)

        if not formats:
            raise BandcampError(
                f"No download formats available for this release at {redownload_url}"
            )

        if encoding not in formats:
            available = ", ".join(sorted(formats.keys()))
            raise BandcampError(
                f"Format '{encoding}' is not available. Available formats: {available}"
            )

        return formats[encoding]

    def get_download_formats(self, redownload_url: str) -> dict[str, str]:
        """Get all available download formats for a release.

        Args:
            redownload_url: URL to the redownload page.

        Returns:
            Dict mapping encoding name to download URL.
        """
        resp = self._request("GET", redownload_url)
        digital_items = parse_digital_items(resp.text, redownload_url)

        if not digital_items:
            return {}

        return extract_download_formats(digital_items[0])

    def fetch_tralbum_tracks(
        self, tralbum_type: str, tralbum_id: int, band_id: int
    ) -> list[dict[str, Any]]:
        """Fetch track listing for a release via the mobile API.

        Args:
            tralbum_type: "a" for album, "t" for track.
            tralbum_id: The tralbum ID.
            band_id: The band/artist ID.

        Returns:
            List of track dicts with 'title', 'track_num', 'duration' keys.
        """
        resp = self._request(
            "GET",
            "https://bandcamp.com/api/mobile/25/tralbum_details",
            params={
                "tralbum_type": tralbum_type,
                "tralbum_id": tralbum_id,
                "band_id": band_id,
            },
        )
        try:
            data = resp.json()
        except ValueError:
            return []
        return data.get("tracks") or []

    def fetch_redownload_page_items(self, redownload_url: str) -> list[dict[str, Any]]:
        """Fetch all digital items from a redownload page.

        Used for discography bundles where multiple items exist
        on a single redownload page.

        Args:
            redownload_url: URL to the redownload page.

        Returns:
            List of digital item dicts.
        """
        resp = self._request("GET", redownload_url)
        return parse_digital_items(resp.text, redownload_url)
