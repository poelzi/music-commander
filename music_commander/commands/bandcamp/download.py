"""Bandcamp download subcommand."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TransferSpeedColumn,
)

from music_commander.bandcamp.client import BandcampClient
from music_commander.bandcamp.cookies import get_session_cookie, validate_cookie
from music_commander.bandcamp.downloader import (
    download_release,
    format_extension,
    resolve_format,
)
from music_commander.cache.models import BandcampRelease, BandcampSyncState
from music_commander.cache.session import get_cache_session
from music_commander.cli import pass_context
from music_commander.commands.bandcamp import (
    EXIT_AUTH_ERROR,
    EXIT_DOWNLOAD_ERROR,
    EXIT_SUCCESS,
    EXIT_SYNC_ERROR,
    cli,
)
from music_commander.exceptions import BandcampAuthError, BandcampError
from music_commander.utils.output import error, info, success, warning


@cli.command("download")
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--format",
    "-f",
    "fmt",
    default=None,
    help="Download format (flac, mp3, ogg, aac, alac, wav, aiff). Default from config.",
)
@click.option(
    "--output",
    "-o",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Output directory (default: current directory).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompt.",
)
@pass_context
def download(
    ctx: object,
    query: tuple[str, ...],
    fmt: str | None,
    output_dir: Path | None,
    yes: bool,
) -> None:
    """Download releases from your Bandcamp collection.

    Search your synced Bandcamp collection by artist or album name
    and download matching releases.

    Examples:

        bandcamp download radiohead

        bandcamp download "ok computer" --format flac

        bandcamp download radiohead --yes --output ./downloads
    """
    config = ctx.config  # type: ignore[attr-defined]
    repo_path = config.music_repo

    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_DOWNLOAD_ERROR)

    if fmt is None:
        fmt = config.bandcamp_default_format

    if output_dir is None:
        output_dir = Path.cwd()

    # Authenticate
    try:
        cookie = get_session_cookie(config)
        fan_id, _username = validate_cookie(cookie)
    except BandcampAuthError as e:
        error(str(e))
        raise SystemExit(EXIT_AUTH_ERROR)

    query_str = " ".join(query).lower()

    try:
        with get_cache_session(repo_path) as session:
            sync_state = session.query(BandcampSyncState).filter_by(id=1).first()
            if sync_state is None:
                error("No Bandcamp collection data found. Run 'bandcamp sync' first.")
                raise SystemExit(EXIT_SYNC_ERROR)

            # Search collection
            releases = _search_releases(session, query_str)

            if not releases:
                error(f"No releases matching '{query_str}' found in your collection.")
                raise SystemExit(EXIT_DOWNLOAD_ERROR)

            # Confirm selection
            console = Console()
            _display_releases(console, releases)

            if not yes:
                if len(releases) == 1:
                    prompt = "Download this release?"
                else:
                    prompt = f"Download all {len(releases)} releases?"
                if not click.confirm(prompt, default=True):
                    info("Download cancelled.")
                    raise SystemExit(EXIT_SUCCESS)

            # Download
            client = BandcampClient(cookie, fan_id)
            downloaded, failed = _download_releases(client, releases, fmt, output_dir, console)

            if downloaded:
                success(f"Downloaded {downloaded} release(s) to {output_dir}")
            if failed:
                warning(f"{failed} release(s) failed to download.")
                raise SystemExit(EXIT_DOWNLOAD_ERROR)

    except SystemExit:
        raise
    except BandcampError as e:
        error(str(e))
        raise SystemExit(EXIT_DOWNLOAD_ERROR)

    raise SystemExit(EXIT_SUCCESS)


def _search_releases(session: object, query: str) -> list[BandcampRelease]:
    """Search Bandcamp releases by query string against band_name and album_title."""
    all_releases = session.query(BandcampRelease).all()  # type: ignore[union-attr]
    matches = []
    for r in all_releases:
        if query in r.band_name.lower() or query in r.album_title.lower():
            matches.append(r)
    return matches


def _display_releases(console: Console, releases: list[BandcampRelease]) -> None:
    """Display a numbered list of releases."""
    console.print(f"\n[bold]Found {len(releases)} release(s):[/bold]")
    for i, r in enumerate(releases, 1):
        console.print(f"  {i}. [cyan]{r.band_name}[/cyan] — {r.album_title}")
    console.print()


def _download_releases(
    client: BandcampClient,
    releases: list[BandcampRelease],
    fmt: str,
    output_dir: Path,
    console: Console,
) -> tuple[int, int]:
    """Download multiple releases with progress.

    Returns:
        Tuple of (successful_count, failed_count).
    """
    downloaded = 0
    failed = 0

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        for release in releases:
            desc = f"{release.band_name} - {release.album_title}"
            task_id = progress.add_task(desc, total=None)

            try:
                # Check available formats
                if not release.redownload_url:
                    progress.update(
                        task_id,
                        description=f"[red]No download URL: {desc}[/red]",
                    )
                    failed += 1
                    continue

                available = client.get_download_formats(release.redownload_url)
                if not available:
                    progress.update(
                        task_id,
                        description=f"[red]No formats available: {desc}[/red]",
                    )
                    failed += 1
                    continue

                try:
                    encoding = resolve_format(fmt, list(available.keys()))
                except BandcampError:
                    available_list = ", ".join(sorted(available.keys()))
                    progress.update(
                        task_id,
                        description=(
                            f"[yellow]{desc}: '{fmt}' unavailable (have: {available_list})[/yellow]"
                        ),
                    )
                    failed += 1
                    continue

                path = download_release(
                    client,
                    release,
                    encoding,
                    output_dir,
                    progress=progress,
                    task_id=task_id,
                )
                progress.update(
                    task_id,
                    description=f"[green]Done: {path.name}[/green]",
                )
                downloaded += 1

            except KeyboardInterrupt:
                console.print("\n[yellow]Download interrupted.[/yellow]")
                raise SystemExit(EXIT_DOWNLOAD_ERROR)
            except BandcampError as e:
                progress.update(
                    task_id,
                    description=f"[red]Failed: {desc} — {e}[/red]",
                )
                failed += 1
            except Exception as e:
                progress.update(
                    task_id,
                    description=f"[red]Error: {desc} — {e}[/red]",
                )
                failed += 1

    return downloaded, failed
