"""Bandcamp repair subcommand — re-download broken files from Bandcamp collection."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from music_commander.bandcamp.client import BandcampClient
from music_commander.bandcamp.cookies import get_session_cookie, validate_cookie
from music_commander.bandcamp.downloader import download_release, resolve_format
from music_commander.cache.models import (
    BandcampRelease,
    BandcampReleaseFormat,
    BandcampSyncState,
    BandcampTrack,
    CacheTrack,
)
from music_commander.cache.session import get_cache_session
from music_commander.cli import pass_context
from music_commander.commands.bandcamp import (
    EXIT_AUTH_ERROR,
    EXIT_DOWNLOAD_ERROR,
    EXIT_MATCH_ERROR,
    EXIT_SUCCESS,
    EXIT_SYNC_ERROR,
    cli,
)
from music_commander.exceptions import BandcampAuthError, BandcampError
from music_commander.utils.matching import (
    MatchTier,
    classify_match,
    match_release,
    match_track,
)
from music_commander.utils.output import error, info, success, warning

logger = logging.getLogger(__name__)

# T047 – Extension to Bandcamp encoding mapping
_EXT_TO_ENCODING: dict[str, str] = {
    ".flac": "flac",
    ".mp3": "mp3-320",
    ".ogg": "vorbis",
    ".oga": "vorbis",
    ".m4a": "aac-hi",
    ".aac": "aac-hi",
    ".wav": "wav",
    ".aiff": "aiff-lossless",
    ".aif": "aiff-lossless",
}

_TIER_STYLES = {
    MatchTier.EXACT: "green",
    MatchTier.HIGH: "yellow",
    MatchTier.LOW: "bright_red",
    MatchTier.NONE: "dim",
}


@dataclass
class RepairCandidate:
    """A broken file matched to a Bandcamp replacement."""

    file_path: str
    error_detail: str
    local_artist: str
    local_album: str
    local_title: str
    bc_release: BandcampRelease | None
    score: float
    tier: MatchTier
    match_type: str  # "release" or "track"
    encoding: str
    format_warning: str = ""
    selected: bool = True


# ---------------------------------------------------------------------------
# T041 – Repair CLI subcommand
# ---------------------------------------------------------------------------


@cli.command("repair")
@click.option(
    "--report",
    "-r",
    "report_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to a 'files check' JSON report.",
)
@click.option(
    "--format",
    "-f",
    "fmt",
    default=None,
    help="Override download format (default: match original file format).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show proposed repairs without downloading.",
)
@click.option(
    "--threshold",
    "-t",
    type=click.IntRange(0, 100),
    default=None,
    help="Minimum match score (overrides config, default 60).",
)
@pass_context
def repair(
    ctx: object,
    report_path: Path,
    fmt: str | None,
    dry_run: bool,
    threshold: int | None,
) -> None:
    """Repair broken files using Bandcamp collection downloads.

    Reads a 'files check' JSON report, matches broken files against
    your Bandcamp purchases, and lets you select which to re-download.

    Examples:

        bandcamp repair --report check-report.json

        bandcamp repair --report check-report.json --dry-run

        bandcamp repair --report check-report.json --format flac
    """
    config = ctx.config  # type: ignore[attr-defined]
    repo_path = config.music_repo

    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_MATCH_ERROR)

    if threshold is None:
        threshold = config.bandcamp_match_threshold

    # Authenticate
    try:
        cookie = get_session_cookie(config)
        fan_id, _username = validate_cookie(cookie)
    except BandcampAuthError as e:
        error(str(e))
        raise SystemExit(EXIT_AUTH_ERROR)

    console = Console()

    try:
        # T042 – Parse check report
        broken_files = _parse_check_report(report_path)
        if not broken_files:
            info("No broken files found in report.")
            raise SystemExit(EXIT_SUCCESS)

        info(f"Found {len(broken_files)} broken file(s) in report.")

        with get_cache_session(repo_path) as session:
            sync_state = session.query(BandcampSyncState).filter_by(id=1).first()
            if sync_state is None:
                error("No Bandcamp collection data found. Run 'bandcamp sync' first.")
                raise SystemExit(EXIT_SYNC_ERROR)

            # T043 – Match broken files to BC collection
            candidates = _match_broken_files(session, broken_files, threshold, fmt)

            if not candidates:
                info("No Bandcamp matches found for broken files.")
                raise SystemExit(EXIT_SUCCESS)

            matched = [c for c in candidates if c.bc_release is not None]
            unmatched = [c for c in candidates if c.bc_release is None]
            info(f"Matched {len(matched)} of {len(candidates)} broken files.")

            if unmatched:
                warning(f"{len(unmatched)} broken file(s) have no Bandcamp match.")

            if not matched:
                raise SystemExit(EXIT_SUCCESS)

            # T045 – Dry-run mode
            if dry_run:
                _display_dry_run(console, matched)
                raise SystemExit(EXIT_SUCCESS)

            # T044 – Rich TUI selection
            confirmed = _interactive_select(console, matched)
            if not confirmed:
                info("No items selected. Nothing to do.")
                raise SystemExit(EXIT_SUCCESS)

            # T046 – Download confirmed replacements
            client = BandcampClient(cookie, fan_id)
            downloaded, failed = _download_replacements(client, confirmed, repo_path, console)

            if downloaded:
                success(f"Downloaded {downloaded} replacement(s).")
                info(
                    "Files saved with .bandcamp-replacement suffix. "
                    "Review and integrate with git-annex manually."
                )
            if failed:
                warning(f"{failed} replacement(s) failed to download.")
                raise SystemExit(EXIT_DOWNLOAD_ERROR)

    except SystemExit:
        raise
    except BandcampError as e:
        error(str(e))
        raise SystemExit(EXIT_MATCH_ERROR)

    raise SystemExit(EXIT_SUCCESS)


# ---------------------------------------------------------------------------
# T042 – Parse CheckReport JSON
# ---------------------------------------------------------------------------


def _parse_check_report(report_path: Path) -> list[tuple[str, str]]:
    """Parse a 'files check' JSON report and extract broken files.

    Returns:
        List of (file_path, error_summary) tuples.
    """
    data = json.loads(report_path.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        raise BandcampError(f"Invalid check report format in {report_path}")

    results = data.get("results", [])
    broken: list[tuple[str, str]] = []

    for r in results:
        if r.get("status") != "error":
            continue
        file_path = r.get("file", "")
        if not file_path:
            continue

        # Build error summary from tool results
        errors = r.get("errors", [])
        if errors:
            summary = "; ".join(
                f"{e.get('tool', '?')}: {e.get('output', 'unknown error')[:100]}" for e in errors
            )
        else:
            summary = "integrity check failed"

        broken.append((file_path, summary))

    return broken


# ---------------------------------------------------------------------------
# T043 – Match broken files to BC collection
# ---------------------------------------------------------------------------


def _match_broken_files(
    session: Any,
    broken_files: list[tuple[str, str]],
    threshold: int,
    fmt_override: str | None,
) -> list[RepairCandidate]:
    """Match broken files against Bandcamp collection."""
    bc_releases = session.query(BandcampRelease).all()
    bc_tracks = session.query(BandcampTrack).all()

    # Build lookup: release_id -> artist
    release_artist: dict[int, str] = {r.sale_item_id: r.band_name for r in bc_releases}

    candidates: list[RepairCandidate] = []

    for file_path, error_detail in broken_files:
        # Look up local track metadata
        track = session.query(CacheTrack).filter_by(file=file_path).first()
        if track is None:
            candidates.append(
                RepairCandidate(
                    file_path=file_path,
                    error_detail=error_detail,
                    local_artist="",
                    local_album="",
                    local_title="",
                    bc_release=None,
                    score=0,
                    tier=MatchTier.NONE,
                    match_type="none",
                    encoding="",
                )
            )
            continue

        artist = track.artist or ""
        album = track.album or ""
        title = track.title or ""

        # T047 – Determine encoding
        if fmt_override:
            encoding = fmt_override
        else:
            ext = Path(file_path).suffix.lower()
            encoding = _EXT_TO_ENCODING.get(ext, "flac")

        # Try release-level match
        best_score = 0.0
        best_release: BandcampRelease | None = None
        best_type = "release"

        if artist and album:
            for r in bc_releases:
                score = match_release(artist, album, r.band_name, r.album_title)
                if score > best_score:
                    best_score = score
                    best_release = r

        # Fall back to track-level match
        if best_score < threshold and artist and title:
            for t in bc_tracks:
                bc_artist = release_artist.get(t.release_id, "")
                score = match_track(artist, title, bc_artist, t.title)
                if score > best_score:
                    best_score = score
                    # Find parent release
                    for r in bc_releases:
                        if r.sale_item_id == t.release_id:
                            best_release = r
                            break
                    best_type = "track"

        tier = classify_match(best_score) if best_score >= threshold else MatchTier.NONE
        if best_score < threshold:
            best_release = None

        # T047 – Validate format availability against BandcampReleaseFormat
        format_warning = ""
        if best_release is not None:
            available_fmts = (
                session.query(BandcampReleaseFormat)
                .filter_by(release_id=best_release.sale_item_id)
                .all()
            )
            if available_fmts:
                available_encodings = [f.encoding for f in available_fmts]
                if encoding not in available_encodings:
                    format_warning = (
                        f"Format '{encoding}' not available; "
                        f"have: {', '.join(sorted(available_encodings))}"
                    )
                    logger.warning("%s: %s", file_path, format_warning)

        candidates.append(
            RepairCandidate(
                file_path=file_path,
                error_detail=error_detail,
                local_artist=artist,
                local_album=album,
                local_title=title,
                bc_release=best_release,
                score=best_score,
                tier=tier,
                match_type=best_type,
                encoding=encoding,
                format_warning=format_warning,
            )
        )

    return candidates


# ---------------------------------------------------------------------------
# T044 – Rich TUI scrollable selection
# ---------------------------------------------------------------------------


def _interactive_select(
    console: Console,
    candidates: list[RepairCandidate],
) -> list[RepairCandidate]:
    """Interactive TUI for selecting which files to repair."""
    cursor = 0
    page_size = min(20, console.height - 6) if console.height else 20

    def _render() -> Table:
        table = Table(
            title=f"Select files to repair (Space=toggle, Enter=confirm, q=quit)",
            show_lines=False,
        )
        table.add_column("", width=3)
        table.add_column("File", max_width=50)
        table.add_column("BC Match", max_width=30)
        table.add_column("Score", justify="right", width=6)
        table.add_column("Tier", width=6)
        table.add_column("Fmt", width=6)

        # Determine visible window
        start = max(0, cursor - page_size // 2)
        end = min(len(candidates), start + page_size)
        if end - start < page_size:
            start = max(0, end - page_size)

        for i in range(start, end):
            c = candidates[i]
            marker = "[green]x[/green]" if c.selected else " "
            row_style = "bold" if i == cursor else ""
            pointer = ">" if i == cursor else " "
            style = _TIER_STYLES.get(c.tier, "dim")

            bc_name = ""
            if c.bc_release:
                bc_name = f"{c.bc_release.band_name} - {c.bc_release.album_title}"

            table.add_row(
                f"{pointer}[{marker}]",
                c.file_path,
                bc_name[:30],
                f"{c.score:.0f}",
                f"[{style}]{c.tier.value}[/{style}]",
                c.encoding,
                style=row_style,
            )

        selected_count = sum(1 for c in candidates if c.selected)
        table.caption = f"{selected_count} of {len(candidates)} selected"
        return table

    with Live(_render(), console=console, refresh_per_second=10) as live:
        while True:
            ch = click.getchar()

            if ch in ("q", "Q", "\x1b"):
                return []
            elif ch == "\r" or ch == "\n":
                break
            elif ch == " ":
                candidates[cursor].selected = not candidates[cursor].selected
                cursor = min(cursor + 1, len(candidates) - 1)
            elif ch in ("\x1b[A", "k"):  # Up arrow or k
                cursor = max(0, cursor - 1)
            elif ch in ("\x1b[B", "j"):  # Down arrow or j
                cursor = min(len(candidates) - 1, cursor + 1)
            elif ch == "a":  # Select all
                for c in candidates:
                    c.selected = True
            elif ch == "n":  # Deselect all
                for c in candidates:
                    c.selected = False

            live.update(_render())

    return [c for c in candidates if c.selected]


# ---------------------------------------------------------------------------
# T045 – Dry-run mode
# ---------------------------------------------------------------------------


def _display_dry_run(console: Console, candidates: list[RepairCandidate]) -> None:
    """Display proposed repair actions without downloading."""
    table = Table(title="Proposed Repairs (dry run)")
    table.add_column("File")
    table.add_column("BC Match")
    table.add_column("Score", justify="right")
    table.add_column("Tier")
    table.add_column("Format")
    table.add_column("Action")

    for c in candidates:
        if c.bc_release is None:
            continue
        style = _TIER_STYLES.get(c.tier, "dim")
        action = "download"
        if c.format_warning:
            action = f"[yellow]warn: {c.format_warning}[/yellow]"
        table.add_row(
            c.file_path,
            f"{c.bc_release.band_name} - {c.bc_release.album_title}",
            f"{c.score:.0f}",
            f"[{style}]{c.tier.value}[/{style}]",
            c.encoding,
            action,
        )

    console.print(table)
    actionable = sum(1 for c in candidates if c.bc_release is not None)
    console.print(f"\n[bold]Would download {actionable} file(s).[/bold]")


# ---------------------------------------------------------------------------
# T046 – Download confirmed replacements
# ---------------------------------------------------------------------------


def _download_replacements(
    client: BandcampClient,
    candidates: list[RepairCandidate],
    repo_path: Path,
    console: Console,
) -> tuple[int, int]:
    """Download replacement files for confirmed repair candidates."""
    downloaded = 0
    failed = 0

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        for c in candidates:
            if c.bc_release is None:
                continue

            desc = f"{c.bc_release.band_name} - {c.bc_release.album_title}"
            task_id = progress.add_task(desc, total=None)

            try:
                # Download to same directory as broken file, with replacement suffix
                original = repo_path / c.file_path
                output_dir = original.parent
                output_dir.mkdir(parents=True, exist_ok=True)

                path = download_release(
                    client,
                    c.bc_release,
                    c.encoding,
                    output_dir,
                    progress=progress,
                    task_id=task_id,
                )

                # Rename to .bandcamp-replacement suffix
                replacement_name = f"{original.stem}.bandcamp-replacement{path.suffix}"
                replacement_path = output_dir / replacement_name
                if path != replacement_path:
                    path.rename(replacement_path)

                progress.update(
                    task_id,
                    description=f"[green]Done: {replacement_path.name}[/green]",
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
