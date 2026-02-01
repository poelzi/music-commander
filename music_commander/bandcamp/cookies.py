"""Bandcamp session cookie extraction and validation.

Supports three authentication methods:
1. Browser cookie extraction via rookiepy (Firefox/Chrome)
2. Mini-browser login with temporary Firefox profile
3. Manual cookie from config.toml
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from music_commander.bandcamp.credentials import (
    BandcampCredentials,
    load_credentials,
    save_credentials,
)
from music_commander.config import Config
from music_commander.exceptions import BandcampAuthError, BandcampParseError

_USER_AGENT = "music-commander/0.1"
_BANDCAMP_URL = "https://bandcamp.com"
_REQUEST_TIMEOUT = 30


def extract_browser_cookie(browser: str) -> str:
    """Extract the Bandcamp identity cookie from a browser.

    Args:
        browser: Browser name ("firefox" or "chrome").

    Returns:
        The identity cookie value.

    Raises:
        BandcampAuthError: If cookie extraction fails.
    """
    try:
        import rookiepy
    except ImportError as e:
        raise BandcampAuthError(
            "rookiepy is not installed. Install it with: pip install rookiepy"
        ) from e

    try:
        if browser == "firefox":
            cookies = rookiepy.firefox(domains=["bandcamp.com"])
        elif browser == "chrome":
            cookies = rookiepy.chrome(domains=["bandcamp.com"])
        else:
            raise BandcampAuthError(f"Unsupported browser: {browser}. Use 'firefox' or 'chrome'.")
    except Exception as e:
        if isinstance(e, BandcampAuthError):
            raise
        raise BandcampAuthError(
            f"Failed to extract cookies from {browser}: {e}\n"
            f"Make sure {browser} is installed and you have an active Bandcamp session."
        ) from e

    # Find the identity cookie
    for cookie in cookies:
        if cookie.get("name") == "identity":
            value = cookie.get("value", "")
            if value:
                return value

    raise BandcampAuthError(
        f"No Bandcamp identity cookie found in {browser}. "
        f"Log in to bandcamp.com in {browser} first."
    )


def login_with_browser() -> str:
    """Launch a mini-browser for Bandcamp login and extract cookie from profile.

    Opens Firefox with a temporary profile pointing to the Bandcamp login page.
    After the user logs in and closes Firefox, extracts the identity cookie
    from the profile's cookies database.

    Returns:
        The identity cookie value.

    Raises:
        BandcampAuthError: If login fails or no cookie found.
    """
    # Check for GUI environment
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise BandcampAuthError(
            "No GUI environment detected (DISPLAY/WAYLAND_DISPLAY not set). "
            "Use 'bandcamp auth --browser firefox' to extract cookies from an "
            "existing browser session, or set bandcamp.session_cookie in config.toml."
        )

    # Check Firefox is installed
    firefox_path = shutil.which("firefox")
    if firefox_path is None:
        raise BandcampAuthError(
            "Firefox not found. Install Firefox or use "
            "'bandcamp auth --browser chrome' for Chrome cookie extraction."
        )

    profile_dir = tempfile.mkdtemp(prefix="mc-bandcamp-")
    try:
        proc = subprocess.Popen(
            [firefox_path, "--profile", profile_dir, "--no-remote", "https://bandcamp.com/login"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.wait()

        # Extract cookie from profile's cookies.sqlite
        cookies_db = Path(profile_dir) / "cookies.sqlite"
        if not cookies_db.exists():
            raise BandcampAuthError(
                "No cookies database found in Firefox profile. "
                "Did you complete the login before closing Firefox?"
            )

        try:
            conn = sqlite3.connect(str(cookies_db))
            cursor = conn.execute(
                "SELECT value FROM moz_cookies WHERE host LIKE '%bandcamp.com' AND name='identity'"
            )
            row = cursor.fetchone()
            conn.close()
        except sqlite3.Error as e:
            raise BandcampAuthError(f"Failed to read cookies from Firefox profile: {e}") from e

        if row is None or not row[0]:
            raise BandcampAuthError(
                "No Bandcamp identity cookie found in Firefox profile. "
                "Make sure you completed the login before closing Firefox."
            )

        return row[0]
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def validate_cookie(cookie: str) -> tuple[int, str | None]:
    """Validate a Bandcamp session cookie by fetching user identity.

    Args:
        cookie: The identity cookie value.

    Returns:
        Tuple of (fan_id, username). Username may be None.

    Raises:
        BandcampAuthError: If the cookie is invalid or expired.
    """
    try:
        resp = requests.get(
            _BANDCAMP_URL,
            cookies={"identity": cookie},
            headers={"User-Agent": _USER_AGENT},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise BandcampAuthError(f"Failed to connect to Bandcamp: {e}") from e

    soup = BeautifulSoup(resp.text, "html.parser")

    # Primary: #HomepageApp with pageContext.identity path per spec
    app_div = soup.find("div", {"id": "HomepageApp"})
    if app_div is None:
        # Fallback: #pagedata
        app_div = soup.find("div", {"id": "pagedata"})

    if app_div is None:
        raise BandcampAuthError(
            "Session cookie is invalid or expired. "
            "Could not find identity data on Bandcamp homepage. "
            "Re-authenticate with: bandcamp auth --browser firefox"
        )

    data_blob = app_div.get("data-blob")  # type: ignore[union-attr]
    if not data_blob:
        raise BandcampAuthError(
            "Session cookie is invalid or expired. Re-authenticate with: "
            "bandcamp auth --browser firefox"
        )

    try:
        blob = json.loads(data_blob)
    except json.JSONDecodeError:
        raise BandcampAuthError(
            "Session cookie is invalid or expired. "
            "Failed to parse Bandcamp identity data. "
            "Re-authenticate with: bandcamp auth --browser firefox"
        )

    # Navigate to identity info via pageContext.identity path (spec)
    fan_id: int | None = None
    username: str | None = None

    page_context = blob.get("pageContext", {})
    if isinstance(page_context, dict):
        identity = page_context.get("identity", {})
        if isinstance(identity, dict):
            fan_id = identity.get("fanId") or identity.get("fan_id")
            username = identity.get("username")

    # Fallback: identities.fan path
    if fan_id is None:
        identity = blob.get("identities", blob.get("identity", {}))
        if isinstance(identity, dict):
            fan = identity.get("fan", {})
            fan_id = fan.get("id") or fan.get("fan_id")
            username = username or fan.get("username") or fan.get("name")

    # Last resort: top-level fan_id
    if fan_id is None:
        fan_id = blob.get("fan_id")

    if fan_id is None:
        raise BandcampAuthError(
            "Session cookie is invalid or expired. Could not find fan identity. "
            "Re-authenticate with: bandcamp auth --browser firefox"
        )

    return int(fan_id), username


def get_session_cookie(config: Config, config_dir: Path | None = None) -> str:
    """Get a valid Bandcamp session cookie from available sources.

    Priority order:
    1. Credentials file (~/.config/music-commander/bandcamp-credentials.json)
    2. config.toml [bandcamp].session_cookie

    Args:
        config: Application configuration.
        config_dir: Override config directory for credentials file.

    Returns:
        The session cookie value.

    Raises:
        BandcampAuthError: If no cookie is available from any source.
    """
    # Try credentials file first
    creds = load_credentials(config_dir)
    if creds is not None and creds.session_cookie:
        return creds.session_cookie

    # Fall back to config.toml
    if config.bandcamp_session_cookie:
        return config.bandcamp_session_cookie

    raise BandcampAuthError(
        "No Bandcamp session cookie found. Authenticate first with:\n"
        "  bandcamp auth --browser firefox    (extract from browser)\n"
        "  bandcamp auth --login              (interactive login)\n"
        "  Or set bandcamp.session_cookie in config.toml"
    )


def authenticate_and_save(
    cookie: str, source: str, config_dir: Path | None = None
) -> BandcampCredentials:
    """Validate a cookie and save credentials.

    Args:
        cookie: The identity cookie value.
        source: How the cookie was obtained (e.g., "browser_firefox", "login", "config").
        config_dir: Override config directory.

    Returns:
        The saved credentials.

    Raises:
        BandcampAuthError: If validation fails.
    """
    fan_id, username = validate_cookie(cookie)

    creds = BandcampCredentials(
        session_cookie=cookie,
        fan_id=fan_id,
        username=username,
        extracted_at=datetime.now(tz=timezone.utc).isoformat(),
        source=source,
    )
    save_credentials(creds, config_dir)
    return creds
