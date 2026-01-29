"""Search git-annex metadata via the local cache."""

from __future__ import annotations

import json

import click

from music_commander.cache.builder import build_cache, refresh_cache
from music_commander.cache.session import get_cache_session
from music_commander.cli import Context, pass_context
from music_commander.search.parser import SearchParseError, parse_query
from music_commander.search.query import execute_search
from music_commander.utils.output import (
    console,
    create_progress,
    create_table,
    error,
    info,
    success,
)

EXIT_SUCCESS = 0
EXIT_NO_RESULTS = 0
EXIT_PARSE_ERROR = 1
EXIT_CACHE_ERROR = 2
EXIT_NO_REPO = 3


@click.command("search")
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "paths", "json"]),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--rebuild-cache",
    is_flag=True,
    default=False,
    help="Force a full cache rebuild before searching",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=None,
    help="Limit number of results",
)
@pass_context
def cli(
    ctx: Context,
    query: tuple[str, ...],
    output_format: str,
    rebuild_cache: bool,
    limit: int | None,
) -> None:
    """Search tracks by metadata using Mixxx-compatible syntax.

    QUERY is a Mixxx-compatible search string. Multiple arguments are
    joined with spaces.

    \b
    Syntax examples:
      music-commander search "dark psy"
      music-commander search artist:Basinski
      music-commander search "bpm:>140 genre:techno"
      music-commander search "genre:house | genre:techno"
      music-commander search "-genre:ambient rating:>=4"
      music-commander search 'artist:="Com Truise"'

    \b
    Output formats:
      --format table   Rich table (default)
      --format paths   One file path per line (for piping)
      --format json    JSON array of track objects
    """
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    repo_path = config.music_repo
    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_NO_REPO)

    # Join query arguments into single string
    query_string = " ".join(query)

    # Parse the query
    try:
        parsed = parse_query(query_string)
    except SearchParseError as e:
        error(f"Invalid search query: {e}")
        raise SystemExit(EXIT_PARSE_ERROR)

    # Auto-refresh cache
    try:
        with get_cache_session(repo_path) as session:
            if rebuild_cache:
                info("Rebuilding cache...")
                with create_progress() as progress:
                    task = progress.add_task("Building cache...", total=None)
                    count = build_cache(repo_path, session)
                    progress.update(task, completed=count, total=count)
                info(f"Cache built with {count} tracks")
            else:
                # Incremental refresh
                result = refresh_cache(repo_path, session)
                if result is not None and result > 0:
                    info(f"Cache refreshed: {result} tracks updated")
                elif result is not None and result == 0:
                    pass  # No changes, silent
                # result is None when cache is already current

            # Execute search
            tracks = execute_search(session, parsed)

            if limit is not None:
                tracks = tracks[:limit]

    except Exception as e:
        error(f"Cache error: {e}")
        raise SystemExit(EXIT_CACHE_ERROR)

    # Output results
    if not tracks:
        info(f"No results for: {query_string}")
        raise SystemExit(EXIT_NO_RESULTS)

    if output_format == "table":
        _print_table(tracks, query_string)
    elif output_format == "paths":
        _print_paths(tracks)
    elif output_format == "json":
        _print_json(tracks)

    raise SystemExit(EXIT_SUCCESS)


def _print_table(tracks: list, query_string: str) -> None:
    """Print results as a Rich table."""
    table = create_table(
        title=f"Search: {query_string} ({len(tracks)} results)",
        show_header=True,
        header_style="bold",
    )
    table.add_column("File", style="path", no_wrap=True, max_width=50)
    table.add_column("Artist", style="track.artist")
    table.add_column("Title", style="track.title")
    table.add_column("Album")
    table.add_column("Genre")
    table.add_column("BPM", justify="right")
    table.add_column("Rating", justify="right")
    table.add_column("Key")

    for t in tracks:
        table.add_row(
            t.file or "",
            t.artist or "",
            t.title or "",
            t.album or "",
            t.genre or "",
            f"{t.bpm:.1f}" if t.bpm else "",
            str(t.rating) if t.rating else "",
            t.key_musical or "",
        )

    console.print(table)


def _print_paths(tracks: list) -> None:
    """Print one file path per line."""
    for t in tracks:
        click.echo(t.file)


def _print_json(tracks: list) -> None:
    """Print results as JSON array."""
    results = []
    for t in tracks:
        results.append(
            {
                "key": t.key,
                "file": t.file,
                "artist": t.artist,
                "title": t.title,
                "album": t.album,
                "genre": t.genre,
                "bpm": t.bpm,
                "rating": t.rating,
                "key_musical": t.key_musical,
                "year": t.year,
                "tracknumber": t.tracknumber,
                "comment": t.comment,
                "color": t.color,
            }
        )
    click.echo(json.dumps(results, indent=2))
