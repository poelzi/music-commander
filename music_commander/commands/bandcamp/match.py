"""Bandcamp match subcommand — match Bandcamp releases against local library."""

from __future__ import annotations

import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn
from rich.table import Table
from sqlalchemy.orm import Session

from music_commander.bandcamp.matcher import (
    MatchReport,
    MatchTier,
    ReleaseMatch,
    match_releases,
)
from music_commander.cache.models import (
    BandcampRelease,
    BandcampSyncState,
    BandcampTrack,
    CacheTrack,
)
from music_commander.cache.session import get_cache_session
from music_commander.cli import pass_context
from music_commander.commands.bandcamp import EXIT_MATCH_ERROR, EXIT_SUCCESS, EXIT_SYNC_ERROR, cli
from music_commander.utils.output import THEME, error, info, is_debug, pager_print, success, verbose
from music_commander.utils.output import console as global_console

_TIER_STYLES = {
    MatchTier.EXACT: "green",
    MatchTier.HIGH: "yellow",
    MatchTier.LOW: "orange3",
    MatchTier.NONE: "dim",
}

_PHASE_LABELS = {
    "metadata": "tag",
    "comment": "comment",
    "folder": "folder",
    "global": "fuzzy",
}


@cli.command("match")
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write match results as JSON to this file.",
)
@click.option(
    "--threshold",
    "-t",
    type=click.IntRange(0, 100),
    default=None,
    help="Minimum match score (overrides config, default 60).",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=None,
    help="Maximum results to display per phase.",
)
@click.option(
    "--tag",
    is_flag=True,
    default=False,
    help="Write bandcamp-url metadata to matched git-annex files.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what --tag would do without writing metadata.",
)
@click.option(
    "--missing",
    "-m",
    "missing_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write unmatched releases as JSON (missing downloads report).",
)
@click.option(
    "--max-width",
    "-w",
    type=int,
    default=40,
    show_default=True,
    help="Max width for artist/album columns (0 = unlimited).",
)
@click.option(
    "--record-metrics",
    is_flag=True,
    default=False,
    help="Append match metrics to .music-commander/match-metrics.jsonl for CI analysis.",
)
@pass_context
def match(
    ctx: object,
    output_path: Path | None,
    threshold: int | None,
    limit: int | None,
    tag: bool,
    dry_run: bool,
    missing_path: Path | None,
    max_width: int,
    record_metrics: bool,
) -> None:
    """Match Bandcamp releases against your local library.

    Iterates through Bandcamp releases and tries to find matching local
    files using a multi-phase strategy:

    \b
      Phase 0: Already-tagged files (bandcamp-url metadata)
      Phase 1: Folder path matching (artist/album in file path)
      Phase 2: Global fuzzy search fallback

    Use --tag to write bandcamp-url metadata to matched files so future
    runs can use Phase 0 for instant matching.

    Use --missing to generate a JSON report of unmatched releases
    (missing downloads).

    Examples:

        bandcamp match

        bandcamp match --threshold 80

        bandcamp match --tag

        bandcamp match --tag --dry-run

        bandcamp match --missing missing.json
    """
    config = ctx.config  # type: ignore[attr-defined]
    repo_path = config.music_repo

    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_MATCH_ERROR)

    if threshold is None:
        threshold = config.bandcamp_match_threshold
        verbose(f"Using threshold from config: {threshold}")
    else:
        verbose(f"Using threshold from CLI: {threshold}")

    folder_threshold = max(threshold, 75)
    global_threshold = max(threshold, 65)
    verbose(f"Effective thresholds: folder={folder_threshold}, global={global_threshold}")

    if dry_run and not tag:
        tag = True  # dry-run implies tag mode for display purposes

    try:
        with get_cache_session(repo_path) as session:
            # Check that sync has been run
            sync_state = session.query(BandcampSyncState).filter_by(id=1).first()
            if sync_state is None:
                error("No Bandcamp collection data found. Run 'bandcamp sync' first.")
                raise SystemExit(EXIT_SYNC_ERROR)

            verbose(
                f"Last sync: {sync_state.last_synced}, total items in DB: {sync_state.total_items}"
            )

            report = _run_matching(session, threshold)

            _display_results(report, limit, max_width=max_width, session=session)

            if output_path is not None:
                _write_match_json(session, report, output_path)
                info(f"Match results written to {output_path}")

            if missing_path is not None:
                _write_missing_json(session, report, missing_path)
                info(f"Missing downloads report written to {missing_path}")

            if tag:
                _tag_matched_files(repo_path, report, dry_run=dry_run)

            if record_metrics:
                _record_match_metrics(repo_path, report, threshold)

    except SystemExit:
        raise
    except Exception as e:
        error(f"Matching failed: {e}")
        raise SystemExit(EXIT_MATCH_ERROR) from e

    raise SystemExit(EXIT_SUCCESS)


def _run_matching(session: Session, threshold: int) -> MatchReport:
    """Load data and run release-centric matching."""
    bc_releases = session.query(BandcampRelease).all()
    bc_tracks = session.query(BandcampTrack).all()
    local_tracks = session.query(CacheTrack).all()

    verbose(
        f"Loaded {len(local_tracks)} local tracks, "
        f"{len(bc_releases)} BC releases, {len(bc_tracks)} BC tracks"
    )

    total_releases = len(bc_releases)
    info(f"Matching {total_releases} Bandcamp releases against {len(local_tracks)} local tracks...")

    if is_debug():
        report = match_releases(bc_releases, bc_tracks, local_tracks, threshold=threshold)
    else:
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=global_console,
        )
        task_id = progress.add_task("Matching", total=total_releases)

        def _on_phase(phase: str, count: int) -> None:
            progress.advance(task_id, count)

        with progress:
            report = match_releases(
                bc_releases, bc_tracks, local_tracks, threshold=threshold, on_phase=_on_phase
            )

    if report.stats:
        s = report.stats
        total_matched = s.matched_metadata + s.matched_comment + s.matched_folder + s.matched_global
        info(
            f"Matched: {total_matched} releases "
            f"(metadata={s.matched_metadata}, comment={s.matched_comment}, "
            f"folder={s.matched_folder}, global={s.matched_global}), "
            f"Unmatched: {s.unmatched}"
        )

    return report


def _truncate(text: str, width: int) -> str:
    """Truncate text to width, adding ellipsis if needed."""
    if width <= 0 or len(text) <= width:
        return text
    return text[: width - 1] + "\u2026"


def _display_results(
    report: MatchReport,
    limit: int | None,
    *,
    max_width: int = 30,
    session: Session | None = None,
) -> None:
    """Display match results grouped by phase."""
    if not report.matched and not report.unmatched_ids:
        global_console.print("\n[dim]No matches found.[/dim]")
        return

    # Group by phase
    by_phase: dict[str, list[ReleaseMatch]] = {
        "metadata": [],
        "comment": [],
        "folder": [],
        "global": [],
    }
    for rm in report.matched:
        phase = rm.match_phase
        if phase in by_phase:
            by_phase[phase].append(rm)

    # Render all output to a buffer for pager support
    buf = io.StringIO()
    console = Console(
        file=buf,
        theme=THEME,
        force_terminal=not global_console.no_color,
        width=1000,
        no_color=global_console.no_color,
    )

    total = len(report.matched)
    console.print(f"\n[bold]Match Results:[/bold] {total} releases matched\n")

    for phase in ("metadata", "comment", "folder", "global"):
        phase_results = by_phase[phase]
        if not phase_results:
            continue

        label = _PHASE_LABELS.get(phase, phase)
        display_results = phase_results[:limit] if limit else phase_results

        table = Table(
            title=f"[bold dim]{label.upper()}[/bold dim] — {len(phase_results)} releases",
            show_lines=False,
        )
        table.add_column("T", style="dim", justify="center")
        table.add_column("BC Artist", style="magenta")
        table.add_column("BC Album", style="magenta")
        table.add_column("Local Path", style="cyan")
        table.add_column("Files", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("Tier")

        for rm in display_results:
            # For single-file matches show full path; otherwise show folder
            local_display = ""
            if rm.tracks and rm.tracks[0].local_file:
                import os

                if len(rm.tracks) <= 2:
                    local_display = rm.tracks[0].local_file
                else:
                    local_display = os.path.dirname(rm.tracks[0].local_file)

            # Color score based on tier
            tier_style = _TIER_STYLES.get(rm.tier, "dim")
            # Row color: green for match, yellow for low, red for none
            if rm.tier in (MatchTier.EXACT, MatchTier.HIGH):
                score_style = "green"
            elif rm.tier == MatchTier.LOW:
                score_style = "yellow"
            else:
                score_style = "red"

            type_label = {"a": "", "t": "S", "b": "B"}.get(rm.sale_item_type, "")
            album_display = rm.album_title
            if len(rm.tracks) <= 2:
                album_display = f"\\[t] {album_display}"
            table.add_row(
                type_label,
                _truncate(rm.band_name, max_width),
                _truncate(album_display, max_width),
                local_display,
                str(len(rm.tracks)),
                f"[{score_style}]{rm.score:.1f}[/{score_style}]",
                f"[{tier_style}]{rm.tier.value}[/{tier_style}]",
            )

        if limit and len(phase_results) > limit:
            table.add_row("", "", "", "", "", f"... +{len(phase_results) - limit} more", "")

        console.print(table)
        console.print()

    # Unmatched table
    if report.unmatched_ids and session is not None:
        unmatched_releases = (
            session.query(BandcampRelease)
            .filter(BandcampRelease.sale_item_id.in_(report.unmatched_ids))
            .order_by(BandcampRelease.band_name)
            .all()
        )

        display_unmatched = unmatched_releases[:limit] if limit else unmatched_releases

        table = Table(
            title=f"[bold red]UNMATCHED[/bold red] — {len(unmatched_releases)} releases",
            show_lines=False,
        )
        table.add_column("T", style="dim", justify="center")
        table.add_column("BC Artist", style="magenta")
        table.add_column("BC Album", style="magenta")
        table.add_column("URL", style="dim")

        for r in display_unmatched:
            type_label = {"a": "", "t": "S", "b": "B"}.get(r.sale_item_type, "")
            url = r.bandcamp_url or ""
            table.add_row(
                type_label,
                _truncate(r.band_name, max_width),
                _truncate(r.album_title, max_width),
                url,
            )

        if limit and len(unmatched_releases) > limit:
            table.add_row("", "", f"... +{len(unmatched_releases) - limit} more", "")

        console.print(table)
        console.print()
    elif report.unmatched_ids:
        console.print(f"[red]Unmatched Bandcamp releases: {len(report.unmatched_ids)}[/red]")

    # First table starts after: blank + "Match Results" + blank = line 4
    # Table header = title + border + columns = 3 lines
    pager_print(buf.getvalue(), header_lines=4, header_start=4)


def _tag_matched_files(repo_path: Path, report: MatchReport, dry_run: bool) -> None:
    """Write bandcamp-url git-annex metadata to matched files."""
    from music_commander.utils.annex_metadata import AnnexMetadataBatch

    to_tag: list[tuple[Path, str]] = []  # (file_path, url)
    for rm in report.matched:
        if not rm.bandcamp_url:
            continue
        # Skip already-tagged (Phase 0) — they already have the metadata
        if rm.match_phase == "metadata":
            continue
        for tm in rm.tracks:
            if tm.local_file:
                to_tag.append((Path(tm.local_file), rm.bandcamp_url))

    if not to_tag:
        info("No files to tag (all matches already have metadata).")
        return

    if dry_run:
        info(f"Dry run: would tag {len(to_tag)} files with bandcamp-url metadata:")
        for file_path, url in to_tag[:20]:
            verbose(f"  {file_path} -> {url}")
        if len(to_tag) > 20:
            info(f"  ... and {len(to_tag) - 20} more")
        return

    info(f"Tagging {len(to_tag)} files with bandcamp-url metadata...")
    tagged = 0
    with AnnexMetadataBatch(repo_path) as batch:
        for file_path, url in to_tag:
            ok = batch.set_metadata(file_path, {"bandcamp-url": [url]})
            if ok:
                tagged += 1
            else:
                verbose(f"  failed to tag: {file_path}")

    success(f"Tagged {tagged}/{len(to_tag)} files. Run 'rebuild-cache' to update the cache.")


def _write_match_json(
    session: Session,
    report: MatchReport,
    output_path: Path,
) -> None:
    """Write match results as JSON atomically."""
    bc_map = {r.sale_item_id: r for r in session.query(BandcampRelease).all()}

    matches_json: list[dict[str, Any]] = []
    for rm in report.matched:
        bc = bc_map.get(rm.bc_sale_item_id)
        files = [
            {
                "local_key": tm.local_key,
                "local_file": tm.local_file,
                "score": round(tm.score, 2),
                "phase": tm.match_phase,
            }
            for tm in rm.tracks
        ]
        entry: dict[str, Any] = {
            "bc_sale_item_id": rm.bc_sale_item_id,
            "bc_artist": bc.band_name if bc else rm.band_name,
            "bc_album": bc.album_title if bc else rm.album_title,
            "bandcamp_url": rm.bandcamp_url,
            "score": round(rm.score, 2),
            "tier": rm.tier.value,
            "phase": rm.match_phase,
            "files": files,
        }
        matches_json.append(entry)

    data = {
        "generated": datetime.now(tz=timezone.utc).isoformat(),
        "matched_count": len(report.matched),
        "unmatched_count": len(report.unmatched_ids),
        "matches": matches_json,
    }

    _atomic_write_json(data, output_path)


def _write_missing_json(
    session: Session,
    report: MatchReport,
    output_path: Path,
) -> None:
    """Write unmatched releases as JSON (missing downloads report)."""
    bc_map = {r.sale_item_id: r for r in session.query(BandcampRelease).all()}

    releases_json: list[dict[str, Any]] = []
    for sale_id in report.unmatched_ids:
        bc = bc_map.get(sale_id)
        if not bc:
            continue
        releases_json.append(
            {
                "sale_item_id": bc.sale_item_id,
                "band_name": bc.band_name,
                "album_title": bc.album_title,
                "bandcamp_url": bc.bandcamp_url,
                "redownload_url": bc.redownload_url,
                "purchase_date": bc.purchase_date,
            }
        )

    data = {
        "generated": datetime.now(tz=timezone.utc).isoformat(),
        "count": len(releases_json),
        "releases": releases_json,
    }

    _atomic_write_json(data, output_path)


def _atomic_write_json(data: dict[str, Any], output_path: Path) -> None:
    """Write JSON data to a file atomically."""
    content = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=output_path.parent, prefix=".match-", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(output_path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _record_match_metrics(repo_path: Path, report: MatchReport, threshold: int) -> None:
    """Append match run metrics as a JSONL line for CI analysis."""
    import subprocess
    from datetime import datetime, timezone

    stats = report.stats
    if not stats:
        return

    # Count tiers
    tier_counts: dict[str, int] = {"exact": 0, "high": 0, "low": 0, "none": 0}
    for rm in report.matched:
        tier_counts[rm.tier.value] = tier_counts.get(rm.tier.value, 0) + 1

    total_matched = (
        stats.matched_metadata + stats.matched_comment + stats.matched_folder + stats.matched_global
    )

    # Get git commit hash
    git_commit = "unknown"
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "total_releases": stats.total_releases,
        "matched_metadata": stats.matched_metadata,
        "matched_comment": stats.matched_comment,
        "matched_folder": stats.matched_folder,
        "matched_global": stats.matched_global,
        "unmatched": stats.unmatched,
        "total_matched": total_matched,
        "match_rate": round(total_matched / stats.total_releases, 4) if stats.total_releases else 0,
        "tier_exact": tier_counts.get("exact", 0),
        "tier_high": tier_counts.get("high", 0),
        "tier_low": tier_counts.get("low", 0),
        "threshold": threshold,
    }

    metrics_dir = repo_path / ".music-commander"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = metrics_dir / "match-metrics.jsonl"

    with open(metrics_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    info(f"Metrics recorded to {metrics_file}")
