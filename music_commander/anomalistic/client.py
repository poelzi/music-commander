"""HTTP client for the Dark Psy Portal WordPress REST API."""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from typing import Any

import requests

from music_commander.exceptions import AnomaListicConnectionError, AnomaListicError

logger = logging.getLogger(__name__)

_USER_AGENT = "music-commander/0.1"
_REQUEST_TIMEOUT = 30
_MAX_RETRIES = 3
_BACKOFF_BASE = 2.0


class AnomaListicClient:
    """Client for the Dark Psy Portal WordPress REST API.

    Fetches categories and posts (releases) from
    darkpsyportal.anomalisticrecords.com using the WP REST API v2.
    No authentication required.
    """

    PORTAL_BASE = "https://darkpsyportal.anomalisticrecords.com"
    API_BASE = f"{PORTAL_BASE}/wp-json/wp/v2"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _USER_AGENT})

    def _request(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        """Make a GET request with retry and backoff logic.

        Handles HTTP 429 (rate limited) and 503 (service unavailable)
        with exponential backoff.

        Args:
            url: Request URL.
            params: Optional query parameters.

        Returns:
            The HTTP response.

        Raises:
            AnomaListicError: If max retries exceeded.
            AnomaListicConnectionError: If connection fails.
        """
        for attempt in range(_MAX_RETRIES):
            try:
                resp = self._session.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            except requests.RequestException as e:
                if attempt == _MAX_RETRIES - 1:
                    raise AnomaListicConnectionError(
                        f"Request to {url} failed after {_MAX_RETRIES} attempts: {e}"
                    ) from e
                wait = _BACKOFF_BASE * (2**attempt)
                logger.warning("Request failed, retrying in %.1fs: %s", wait, e)
                time.sleep(wait)
                continue

            if resp.status_code in (429, 503):
                if attempt == _MAX_RETRIES - 1:
                    raise AnomaListicError(
                        f"Rate limited after {_MAX_RETRIES} retries (HTTP {resp.status_code}). "
                        f"Try again later."
                    )
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(float(retry_after), _BACKOFF_BASE)
                    except ValueError:
                        wait = _BACKOFF_BASE * (2**attempt)
                else:
                    wait = _BACKOFF_BASE * (2**attempt)
                logger.warning(
                    "Rate limit detected (HTTP %d), waiting %.1fs...",
                    resp.status_code,
                    wait,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp

        # Should not reach here, but satisfy type checker
        raise AnomaListicError(f"Request to {url} failed unexpectedly")  # pragma: no cover

    def fetch_categories(self) -> list[dict[str, Any]]:
        """Fetch all categories from the portal.

        Returns:
            List of category dicts from the WordPress API.
        """
        url = f"{self.API_BASE}/categories"
        all_categories: list[dict[str, Any]] = []
        page = 1

        while True:
            resp = self._request(url, params={"per_page": 100, "page": page})
            categories = resp.json()
            if not categories:
                break
            all_categories.extend(categories)
            total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
            if page >= total_pages:
                break
            page += 1

        return all_categories

    def fetch_posts_page(self, page: int = 1) -> tuple[list[dict[str, Any]], int]:
        """Fetch a single page of posts.

        Args:
            page: Page number (1-indexed).

        Returns:
            Tuple of (posts list, total_pages).
        """
        url = f"{self.API_BASE}/posts"
        resp = self._request(url, params={"per_page": 100, "page": page})
        posts = resp.json()
        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        return posts, total_pages

    def iter_releases(self) -> Generator[dict[str, Any], None, None]:
        """Iterate through all posts (releases) with pagination.

        Yields:
            Each post dict from the WordPress API.
        """
        page = 1
        while True:
            posts, total_pages = self.fetch_posts_page(page)
            if not posts:
                break
            for post in posts:
                yield post
            if page >= total_pages:
                break
            page += 1
