"""Bandcamp authentication subcommand."""

from __future__ import annotations

import click

from music_commander.bandcamp.cookies import (
    authenticate_and_save,
    extract_browser_cookie,
    get_session_cookie,
    login_with_browser,
    validate_cookie,
)
from music_commander.bandcamp.credentials import load_credentials
from music_commander.cli import pass_context
from music_commander.commands.bandcamp import EXIT_AUTH_ERROR, EXIT_SUCCESS, cli
from music_commander.exceptions import BandcampAuthError, BandcampError
from music_commander.utils.output import error, info, success


@cli.command("auth")
@click.option(
    "--browser",
    "-b",
    type=click.Choice(["firefox", "chrome"], case_sensitive=False),
    help="Extract session cookie from browser",
)
@click.option(
    "--login",
    "-l",
    is_flag=True,
    default=False,
    help="Launch mini-browser for interactive login",
)
@click.option(
    "--status",
    "-s",
    is_flag=True,
    default=False,
    help="Check current authentication status",
)
@pass_context
def auth(ctx: object, browser: str | None, login: bool, status: bool) -> None:
    """Authenticate with Bandcamp.

    Extract session cookies from your browser, log in interactively,
    or check your current authentication status.

    Examples:

        bandcamp auth --browser firefox

        bandcamp auth --login

        bandcamp auth --status
    """
    config = ctx.config  # type: ignore[attr-defined]

    if status:
        _show_status(config)
        return

    if browser and login:
        error("Cannot use both --browser and --login at the same time.")
        raise SystemExit(EXIT_AUTH_ERROR)

    if not browser and not login:
        error(
            "Specify an authentication method:\n"
            "  --browser firefox  (extract from browser)\n"
            "  --login            (interactive login)"
        )
        raise SystemExit(EXIT_AUTH_ERROR)

    try:
        if browser:
            info(f"Extracting Bandcamp cookie from {browser}...")
            cookie = extract_browser_cookie(browser)
            source = f"browser_{browser}"
        else:
            info("Launching Firefox for Bandcamp login...")
            info("Log in to Bandcamp, then close the browser window.")
            cookie = login_with_browser()
            source = "login"

        info("Validating cookie...")
        creds = authenticate_and_save(cookie, source)

        success(f"Authenticated as: {creds.username or 'unknown'} (fan_id: {creds.fan_id})")
        info(f"Cookie source: {creds.source}")
        info(f"Credentials saved to ~/.config/music-commander/")

    except BandcampError as e:
        error(str(e))
        raise SystemExit(EXIT_AUTH_ERROR)

    raise SystemExit(EXIT_SUCCESS)


def _show_status(config: object) -> None:
    """Show current authentication status."""
    creds = load_credentials()
    if creds is None:
        # Try config fallback
        cookie = getattr(config, "bandcamp_session_cookie", None)
        if cookie:
            info("Cookie source: config.toml (manual)")
            try:
                fan_id, username = validate_cookie(cookie)
                success(f"Authenticated as: {username or 'unknown'} (fan_id: {fan_id})")
            except BandcampAuthError as e:
                error(f"Cookie from config.toml is invalid: {e}")
                raise SystemExit(EXIT_AUTH_ERROR)
        else:
            error(
                "Not authenticated. Run:\n"
                "  bandcamp auth --browser firefox\n"
                "  bandcamp auth --login"
            )
            raise SystemExit(EXIT_AUTH_ERROR)
        return

    info(f"Cookie source: {creds.source}")
    info(f"Extracted at: {creds.extracted_at}")

    try:
        fan_id, username = validate_cookie(creds.session_cookie)
        success(f"Authenticated as: {username or creds.username or 'unknown'} (fan_id: {fan_id})")
    except BandcampAuthError:
        error(
            "Stored cookie has expired. Re-authenticate with:\n"
            "  bandcamp auth --browser firefox\n"
            "  bandcamp auth --login"
        )
        raise SystemExit(EXIT_AUTH_ERROR)

    raise SystemExit(EXIT_SUCCESS)
