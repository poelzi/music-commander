"""Bandcamp match subcommand — fuzzy match local library against Bandcamp collection."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table
from sqlalchemy.orm import Session

from music_commander.bandcamp.matcher import (
    MatchResult,
    MatchTier,
    batch_match,
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
from music_commander.utils.output import error, info

_TIER_STYLES = {
    MatchTier.EXACT: "green",
    MatchTier.HIGH: "yellow",
    MatchTier.LOW: "orange3",
}

_TIER_LABELS = {
    MatchTier.EXACT: "Exact (>=95)",
    MatchTier.HIGH: "High (>=80)",
    MatchTier.LOW: "Low (>=60)",
}


@cli.command("match")
@click.option(
    "--output",
    "-o",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write results as JSON to this file.",
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
    help="Maximum results to display per tier.",
)
@pass_context
def match(ctx: object, output_path: Path | None, threshold: int | None, limit: int | None) -> None:
    """Match local library tracks against your Bandcamp collection.

    Runs fuzzy matching and displays results grouped by confidence tier.

    Examples:

        bandcamp match

        bandcamp match --threshold 80

        bandcamp match --output matches.json
    """
    config = ctx.config  # type: ignore[attr-defined]
    repo_path = config.music_repo

    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_MATCH_ERROR)

    if threshold is None:
        threshold = config.bandcamp_match_threshold

    try:
        with get_cache_session(repo_path) as session:
            # Check that sync has been run
            sync_state = session.query(BandcampSyncState).filter_by(id=1).first()
            if sync_state is None:
                error("No Bandcamp collection data found. Run 'bandcamp sync' first.")
                raise SystemExit(EXIT_SYNC_ERROR)

            results, unmatched_local, unmatched_bc = _run_matching(session, threshold)

            if output_path is not None:
                _write_json(session, results, unmatched_local, unmatched_bc, output_path)
                info(f"Match results written to {output_path}")

            _display_results(session, results, unmatched_local, unmatched_bc, limit)

    except SystemExit:
        raise
    except Exception as e:
        error(f"Matching failed: {e}")
        raise SystemExit(EXIT_MATCH_ERROR) from e

    raise SystemExit(EXIT_SUCCESS)


def _run_matching(
    session: Session,
    threshold: int,
) -> tuple[list[MatchResult], list[str], list[int]]:
    """Load data and run batch matching.

    Returns:
        Tuple of (match_results, unmatched_local_keys, unmatched_bc_release_ids).
    """
    local_tracks = session.query(CacheTrack).all()
    bc_releases = session.query(BandcampRelease).all()
    bc_tracks = session.query(BandcampTrack).all()

    info(
        f"Matching {len(local_tracks)} local tracks against {len(bc_releases)} Bandcamp releases..."
    )

    results = batch_match(local_tracks, bc_releases, bc_tracks, threshold=threshold)

    # Identify unmatched items
    matched_local_keys = {r.local_key for r in results}
    unmatched_local = [t.key for t in local_tracks if t.key not in matched_local_keys and t.artist]

    matched_bc_ids = {r.bc_sale_item_id for r in results}
    unmatched_bc = [r.sale_item_id for r in bc_releases if r.sale_item_id not in matched_bc_ids]

    return results, unmatched_local, unmatched_bc


def _display_results(
    session: Session,
    results: list[MatchResult],
    unmatched_local: list[str],
    unmatched_bc: list[int],
    limit: int | None,
) -> None:
    """Display match results grouped by confidence tier."""
    console = Console()

    # Group by tier
    by_tier: dict[MatchTier, list[MatchResult]] = {
        MatchTier.EXACT: [],
        MatchTier.HIGH: [],
        MatchTier.LOW: [],
    }
    for r in results:
        if r.tier in by_tier:
            by_tier[r.tier].append(r)

    # Build lookup maps
    bc_map = {r.sale_item_id: r for r in session.query(BandcampRelease).all()}
    local_map = {t.key: t for t in session.query(CacheTrack).all()}

    total_matches = len(results)
    console.print(f"\n[bold]Match Results:[/bold] {total_matches} matches found\n")

    for tier in (MatchTier.EXACT, MatchTier.HIGH, MatchTier.LOW):
        tier_results = by_tier[tier]
        if not tier_results:
            continue

        style = _TIER_STYLES[tier]
        label = _TIER_LABELS[tier]
        display_results = tier_results[:limit] if limit else tier_results

        table = Table(
            title=f"[{style}]{label}[/{style}] — {len(tier_results)} matches",
            show_lines=False,
        )
        table.add_column("Local Artist", style="cyan")
        table.add_column("Local Album", style="cyan")
        table.add_column("BC Artist", style="magenta")
        table.add_column("BC Album", style="magenta")
        table.add_column("Score", justify="right", style=style)
        table.add_column("Type", style="dim")

        for r in display_results:
            local = local_map.get(r.local_key)
            bc = bc_map.get(r.bc_sale_item_id)

            table.add_row(
                (local.artist or "") if local else "?",
                (local.album or "") if local else "?",
                bc.band_name if bc else "?",
                bc.album_title if bc else "?",
                f"{r.score:.1f}",
                r.match_type,
            )

        if limit and len(tier_results) > limit:
            table.add_row("", "", "", "", f"... +{len(tier_results) - limit} more", "")

        console.print(table)
        console.print()

    # Unmatched summary
    if unmatched_bc:
        console.print(f"[dim]Unmatched Bandcamp releases: {len(unmatched_bc)}[/dim]")
    if unmatched_local:
        console.print(f"[dim]Unmatched local tracks: {len(unmatched_local)}[/dim]")


def _write_json(
    session: Session,
    results: list[MatchResult],
    unmatched_local: list[str],
    unmatched_bc: list[int],
    output_path: Path,
) -> None:
    """Write match results as JSON atomically."""
    bc_map = {r.sale_item_id: r for r in session.query(BandcampRelease).all()}
    local_map = {t.key: t for t in session.query(CacheTrack).all()}

    matches_json: list[dict[str, Any]] = []
    for r in results:
        local = local_map.get(r.local_key)
        bc = bc_map.get(r.bc_sale_item_id)

        entry: dict[str, Any] = {
            "local_key": r.local_key,
            "local_file": local.file if local else None,
            "local_artist": (local.artist or "") if local else "",
            "local_album": (local.album or "") if local else "",
            "local_title": (local.title or "") if local else "",
            "bc_sale_item_id": r.bc_sale_item_id,
            "bc_artist": bc.band_name if bc else "",
            "bc_album": bc.album_title if bc else "",
            "score": round(r.score, 2),
            "tier": r.tier.value,
            "type": r.match_type,
        }
        matches_json.append(entry)

    unmatched_local_json = []
    for key in unmatched_local:
        local = local_map.get(key)
        unmatched_local_json.append(
            {
                "key": key,
                "file": local.file if local else None,
                "artist": (local.artist or "") if local else "",
                "album": (local.album or "") if local else "",
            }
        )

    unmatched_bc_json = []
    for bc_id in unmatched_bc:
        bc = bc_map.get(bc_id)
        unmatched_bc_json.append(
            {
                "sale_item_id": bc_id,
                "artist": bc.band_name if bc else "",
                "album": bc.album_title if bc else "",
            }
        )

    data = {
        "matches": matches_json,
        "unmatched_local": unmatched_local_json,
        "unmatched_bc": unmatched_bc_json,
    }

    content = json.dumps(data, indent=2, ensure_ascii=True) + "\n"

    # Atomic write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=output_path.parent, prefix=".match-", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(output_path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise
