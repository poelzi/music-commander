"""Bandcamp collection sync subcommand."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import click
from rich.console import Group
from rich.live import Live
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text
from sqlalchemy.orm import Session

from music_commander.bandcamp.client import BandcampClient
from music_commander.bandcamp.cookies import get_session_cookie, validate_cookie
from music_commander.bandcamp.parser import extract_download_formats
from music_commander.cache.models import (
    BandcampRelease,
    BandcampReleaseFormat,
    BandcampSyncState,
    BandcampTrack,
)
from music_commander.cache.session import get_cache_session
from music_commander.cli import pass_context
from music_commander.commands.bandcamp import EXIT_AUTH_ERROR, EXIT_SUCCESS, EXIT_SYNC_ERROR, cli
from music_commander.exceptions import BandcampAuthError, BandcampError
from music_commander.utils.output import debug as debug_msg
from music_commander.utils.output import error, info, is_verbose, success, verbose

logger = logging.getLogger(__name__)

_COMMIT_BATCH_SIZE = 100


@cli.command("sync")
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Force a full re-sync, ignoring previous sync state.",
)
@pass_context
def sync(ctx: object, full: bool) -> None:
    """Sync your Bandcamp purchase collection to the local database.

    Fetches all purchased releases, tracks, and available download formats
    from your Bandcamp account and stores them locally for matching and
    downloading.

    By default performs an incremental sync, only fetching new items.
    Use --full to re-sync everything from scratch.

    Examples:

        bandcamp sync

        bandcamp sync --full
    """
    config = ctx.config  # type: ignore[attr-defined]
    repo_path = config.music_repo

    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_SYNC_ERROR)

    # Authenticate
    try:
        cookie = get_session_cookie(config)
        fan_id, username = validate_cookie(cookie)
    except BandcampAuthError as e:
        error(str(e))
        raise SystemExit(EXIT_AUTH_ERROR)

    client = BandcampClient(cookie, fan_id)

    # Fetch username from collection summary if not available from cookie
    if not username:
        try:
            summary = client.fetch_collection_summary()
            username = summary.get("username")
        except Exception:
            pass

    info(f"Authenticated as: {username or 'unknown'} (fan_id: {fan_id})")

    try:
        with get_cache_session(repo_path) as session:
            total, new_count = sync_collection(client, session, fan_id, username, full=full)
            success(f"Synced {total} releases ({new_count} new)")
    except BandcampError as e:
        error(str(e))
        raise SystemExit(EXIT_SYNC_ERROR)

    raise SystemExit(EXIT_SUCCESS)


def sync_collection(
    client: BandcampClient,
    session: Session,
    fan_id: int,
    username: str | None,
    full: bool = False,
) -> tuple[int, int]:
    """Fetch collection items from Bandcamp and store in the database.

    Args:
        client: Authenticated Bandcamp API client.
        session: SQLAlchemy session.
        fan_id: User's Bandcamp fan ID.
        username: User's Bandcamp username.
        full: If True, re-sync everything from scratch.

    Returns:
        Tuple of (total_items_processed, new_items_added).
    """
    now = datetime.now(tz=timezone.utc).isoformat()

    # Load existing sync state
    sync_state = session.query(BandcampSyncState).filter_by(id=1).first()

    # Collect existing sale_item_ids for incremental detection
    existing_ids: set[int] = set()
    if not full and sync_state is not None:
        existing_ids = {r[0] for r in session.query(BandcampRelease.sale_item_id).all()}
        if not existing_ids:
            verbose("Previous sync has no items, performing full sync")
            full = True

    total = 0
    new_count = 0
    batch_count = 0
    page_num = 0
    last_token: str | None = None

    current_item_text = Text("")
    bar = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TextColumn("{task.completed} items"),
        TimeElapsedColumn(),
    )
    bar_task = bar.add_task("Syncing...", total=None)

    with Live(Group(current_item_text, bar), transient=True) as live:
        token: str | None = None
        stop = False

        while not stop:
            page_num += 1
            data = client.fetch_collection_page(older_than_token=token)
            items = data.get("items", [])
            if not items:
                break

            more_available = data.get("more_available", False)
            if is_verbose():
                live.console.print(
                    f"[dim]Page {page_num}: {len(items)} items "
                    f"(more_available={more_available})[/dim]"
                )

            redownload_urls = data.get("redownload_urls", {})

            for item in items:
                sale_item_id = item.get("sale_item_id")
                if sale_item_id is None:
                    continue

                # Attach redownload URL
                item_key = f"{item.get('sale_item_type', '')}{sale_item_id}"
                if item_key in redownload_urls:
                    item["redownload_url"] = redownload_urls[item_key]

                total += 1
                batch_count += 1

                # Incremental: stop if we hit a known item
                if not full and sale_item_id in existing_ids:
                    if is_verbose():
                        live.console.print(
                            f"[dim]Found existing item (sale_item_id={sale_item_id}), "
                            f"stopping incremental sync after {total} items[/dim]"
                        )
                    stop = True
                    break

                band_name = item.get("band_name", "Unknown")
                album_title = item.get("item_title", item.get("album_title", "Unknown"))
                current_item_text = Text.from_markup(f"[bold]{band_name}[/bold] - {album_title}")
                bar.update(bar_task, completed=total)
                live.update(Group(current_item_text, bar))

                is_new = _upsert_release(session, item, now)
                if is_new:
                    new_count += 1

                # Store formats and tracks from redownload page
                _store_item_details(client, session, item)

                # Handle discography bundles
                if _is_discography_item(item):
                    _expand_discography(client, session, item, now)

                # Commit in batches
                if batch_count >= _COMMIT_BATCH_SIZE:
                    session.commit()
                    batch_count = 0

            # Track pagination token
            token = data.get("last_token")
            if token is not None:
                last_token = token
            else:
                break

        # Final commit for remaining items
        session.commit()

    # Update sync state
    if sync_state is None:
        sync_state = BandcampSyncState(id=1, fan_id=fan_id, last_synced=now, total_items=0)
        session.add(sync_state)

    sync_state.fan_id = fan_id
    sync_state.username = username
    sync_state.last_synced = now
    sync_state.total_items = session.query(BandcampRelease).count()
    sync_state.last_token = last_token
    session.commit()

    return total, new_count


def _upsert_release(session: Session, item: dict[str, Any], now: str) -> bool:
    """Create or update a BandcampRelease from an API collection item.

    Returns True if this is a new release, False if updated.
    """
    sale_item_id = item["sale_item_id"]

    existing = session.query(BandcampRelease).filter_by(sale_item_id=sale_item_id).first()
    is_new = existing is None

    if is_new:
        release = BandcampRelease(
            sale_item_id=sale_item_id,
            sale_item_type=item.get("sale_item_type", "a"),
            band_name=item.get("band_name", "Unknown"),
            album_title=item.get("item_title", item.get("album_title", "Unknown")),
            band_id=item.get("band_id"),
            redownload_url=item.get("redownload_url"),
            purchase_date=item.get("purchased"),
            is_discography=_is_discography_item(item),
            artwork_url=item.get("item_art_url"),
            bandcamp_url=item.get("item_url"),
            last_synced=now,
        )
        session.add(release)
    else:
        existing.band_name = item.get("band_name", existing.band_name)
        existing.album_title = item.get("item_title", item.get("album_title", existing.album_title))
        existing.redownload_url = item.get("redownload_url") or existing.redownload_url
        existing.artwork_url = item.get("item_art_url") or existing.artwork_url
        existing.bandcamp_url = item.get("item_url") or existing.bandcamp_url
        existing.last_synced = now

    # Store tracks if available in the item data
    tralbum = item.get("tralbum_data") or {}
    tracks = tralbum.get("tracks") or item.get("tracks") or []
    if tracks:
        _store_tracks(session, sale_item_id, tracks)

    return is_new


def _store_tracks(session: Session, release_id: int, tracks: list[dict[str, Any]]) -> None:
    """Store or update tracks for a release."""
    # Clear existing tracks for this release and re-insert
    session.query(BandcampTrack).filter_by(release_id=release_id).delete()

    for t in tracks:
        title = t.get("title") or t.get("track_title", "")
        if not title:
            continue
        track = BandcampTrack(
            release_id=release_id,
            title=title,
            track_number=t.get("track_num") or t.get("track_number"),
            duration_seconds=t.get("duration"),
        )
        session.add(track)


def _store_formats(session: Session, release_id: int, formats: dict[str, str]) -> None:
    """Store available download formats for a release."""
    for encoding in formats:
        exists = (
            session.query(BandcampReleaseFormat)
            .filter_by(release_id=release_id, encoding=encoding)
            .first()
        )
        if not exists:
            fmt = BandcampReleaseFormat(release_id=release_id, encoding=encoding)
            session.add(fmt)


def _store_item_details(client: BandcampClient, session: Session, item: dict[str, Any]) -> None:
    """Store download formats and tracks for a collection item.

    Formats are fetched from the redownload page; tracks come from the
    mobile album API (the redownload page does not include track data).
    """
    sale_item_id = item.get("sale_item_id")
    if sale_item_id is None:
        return

    has_formats = (
        session.query(BandcampReleaseFormat).filter_by(release_id=sale_item_id).count() > 0
    )
    has_tracks = session.query(BandcampTrack).filter_by(release_id=sale_item_id).count() > 0

    if has_formats and has_tracks:
        return

    debug_msg(
        f"  details: fetching {sale_item_id}"
        f" (need_formats={not has_formats}, need_tracks={not has_tracks})"
    )

    # Fetch formats from redownload page
    if not has_formats:
        redownload_url = item.get("redownload_url")
        if redownload_url:
            try:
                digital_items = client.fetch_redownload_page_items(redownload_url)
                if digital_items:
                    formats = extract_download_formats(digital_items[0])
                    if formats:
                        _store_formats(session, sale_item_id, formats)
                        debug_msg(f"  details: stored {len(formats)} formats for {sale_item_id}")
            except Exception as exc:
                debug_msg(f"  details: error fetching formats for {sale_item_id}: {exc}")
                logger.debug("Could not fetch formats for sale_item_id=%s", sale_item_id)

    # Fetch tracks from tralbum API
    if not has_tracks:
        tralbum_type = item.get("tralbum_type") or item.get("url_hints", {}).get("item_type")
        tralbum_id = item.get("tralbum_id") or item.get("item_id")
        band_id = item.get("band_id")
        if tralbum_type and tralbum_id and band_id:
            try:
                tracks = client.fetch_tralbum_tracks(tralbum_type, tralbum_id, band_id)
                if tracks:
                    _store_tracks(session, sale_item_id, tracks)
                    debug_msg(f"  details: stored {len(tracks)} tracks for {sale_item_id}")
                else:
                    debug_msg(f"  details: no tracks from tralbum API for {sale_item_id}")
            except Exception as exc:
                debug_msg(f"  details: error fetching tracks for {sale_item_id}: {exc}")
                logger.debug("Could not fetch tracks for sale_item_id=%s", sale_item_id)
        else:
            debug_msg(
                f"  details: skip tracks for {sale_item_id} (missing tralbum_type/id/band_id)"
            )


def _is_discography_item(item: dict[str, Any]) -> bool:
    """Check if a collection item is a discography bundle."""
    if item.get("is_discography"):
        return True
    return False


def _expand_discography(
    client: BandcampClient,
    session: Session,
    item: dict[str, Any],
    now: str,
) -> None:
    """Expand a discography bundle into individual release records.

    Fetches the redownload page to discover individual releases
    within the bundle.
    """
    redownload_url = item.get("redownload_url")
    if not redownload_url:
        return

    try:
        digital_items = client.fetch_redownload_page_items(redownload_url)
    except BandcampError:
        logger.warning(
            "Could not expand discography bundle for %s - %s",
            item.get("band_name"),
            item.get("item_title"),
        )
        return

    parent_band_name = item.get("band_name", "Unknown")

    for di in digital_items:
        # Each digital item on the redownload page is a separate release
        di_title = di.get("title", "")
        if not di_title:
            continue

        # Use a synthetic sale_item_id for sub-releases (parent_id * 10000 + index)
        # to avoid collision with real sale_item_ids
        di_id = di.get("id") or di.get("art_id")
        if di_id is None:
            continue

        existing = session.query(BandcampRelease).filter_by(sale_item_id=di_id).first()
        if existing:
            continue

        release = BandcampRelease(
            sale_item_id=di_id,
            sale_item_type="a",
            band_name=di.get("artist", parent_band_name),
            album_title=di_title,
            band_id=item.get("band_id"),
            redownload_url=redownload_url,
            purchase_date=item.get("purchased"),
            is_discography=True,
            artwork_url=di.get("thumb_url") or item.get("item_art_url"),
            bandcamp_url=di.get("url"),
            last_synced=now,
        )
        session.add(release)

        # Store formats if available
        formats = extract_download_formats(di)
        if formats:
            _store_formats(session, di_id, formats)

        # Store tracks from digital item
        tracks = di.get("tracks") or []
        if tracks:
            _store_tracks(session, di_id, tracks)
