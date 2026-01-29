"""Search git-annex metadata via the local cache."""

from __future__ import annotations

import json
import os
import subprocess

import click

from music_commander.cache.builder import build_cache, refresh_cache
from music_commander.cache.models import TrackCrate
from music_commander.cache.session import delete_cache, get_cache_session
from music_commander.cli import Context, pass_context
from music_commander.search.parser import SearchParseError, parse_query
from music_commander.search.query import execute_search
from music_commander.utils.output import (
    THEME,
    console,
    create_progress,
    create_table,
    error,
    info,
    pager_print,
    success,
)

EXIT_SUCCESS = 0
EXIT_NO_RESULTS = 0
EXIT_PARSE_ERROR = 1
EXIT_CACHE_ERROR = 2
EXIT_NO_REPO = 3

# Default columns for table output
DEFAULT_COLUMNS = "artist,title,album,genre,bpm,rating,key,crates,file"

# All available columns and their table configuration
# "clip": True means the column is subject to --clip truncation
# "attr": the CacheTrack attribute name (for sorting)
COLUMN_DEFS: dict[str, dict] = {
    "artist": {
        "header": "Artist",
        "style": "track.artist",
        "justify": "left",
        "clip": True,
        "attr": "artist",
    },
    "title": {
        "header": "Title",
        "style": "track.title",
        "justify": "left",
        "clip": True,
        "attr": "title",
    },
    "album": {"header": "Album", "style": None, "justify": "left", "clip": True, "attr": "album"},
    "genre": {"header": "Genre", "style": None, "justify": "left", "attr": "genre"},
    "bpm": {"header": "BPM", "style": None, "justify": "right", "attr": "bpm"},
    "rating": {"header": "\u2605", "style": None, "justify": "right", "attr": "rating"},
    "key": {"header": "Key", "style": None, "justify": "left", "attr": "key_musical"},
    "year": {"header": "Year", "style": None, "justify": "right", "attr": "year"},
    "tracknumber": {"header": "#", "style": None, "justify": "right", "attr": "tracknumber"},
    "comment": {"header": "Comment", "style": None, "justify": "left", "attr": "comment"},
    "color": {"header": "Color", "style": None, "justify": "left", "attr": "color"},
    "crates": {"header": "Crates", "style": None, "justify": "left"},
    "file": {"header": "File", "style": "path", "justify": "left", "attr": "file"},
}


def _format_rating(rating: int | None) -> str:
    """Format a numeric rating."""
    if rating is None:
        return ""
    return str(rating)


def _format_openkey(key_musical: str | None) -> str:
    """Extract just the openkey notation (e.g. '5m' from '5m (D#m)')."""
    if not key_musical:
        return ""
    return key_musical.split(" ")[0]


def _format_bpm(bpm: float | None) -> str:
    """Format BPM as an integer."""
    if bpm is None:
        return ""
    return str(round(bpm))


def _strip_common_prefix(paths: list[str]) -> list[str]:
    """Strip the longest common directory prefix from a list of paths."""
    non_empty = [p for p in paths if p]
    if not non_empty:
        return paths
    prefix = os.path.commonpath(non_empty) if len(non_empty) > 1 else ""
    if prefix and not prefix.endswith("/"):
        prefix = os.path.dirname(prefix)
    if not prefix:
        return paths
    prefix_len = len(prefix) + 1  # +1 for trailing slash
    return [p[prefix_len:] if p else "" for p in paths]


def _clip_text(value: str, max_width: int | None) -> str:
    """Truncate text to max_width, appending ellipsis if clipped."""
    if max_width is None or len(value) <= max_width:
        return value
    if max_width <= 1:
        return value[:max_width]
    return value[: max_width - 1] + "\u2026"


def _get_cell_value(
    track,
    col: str,
    crates_by_key: dict[str, list[str]],
    file_display: str,
    clip_width: int | None = None,
) -> str:
    """Get the formatted cell value for a column."""
    cdef = COLUMN_DEFS[col]
    clip = clip_width if cdef.get("clip") else None

    if col == "artist":
        return _clip_text(track.artist or "", clip)
    elif col == "title":
        return _clip_text(track.title or "", clip)
    elif col == "album":
        return _clip_text(track.album or "", clip)
    elif col == "genre":
        return track.genre or ""
    elif col == "bpm":
        return _format_bpm(track.bpm)
    elif col == "rating":
        return _format_rating(track.rating)
    elif col == "key":
        return _format_openkey(track.key_musical)
    elif col == "year":
        return track.year or ""
    elif col == "tracknumber":
        return track.tracknumber or ""
    elif col == "comment":
        return track.comment or ""
    elif col == "color":
        return track.color or ""
    elif col == "crates":
        crates = crates_by_key.get(track.key, [])
        return ", ".join(sorted(crates)) if crates else ""
    elif col == "file":
        return file_display
    return ""


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
@click.option(
    "--columns",
    "-C",
    default=None,
    help=f"Comma-separated list of columns to display (default: {DEFAULT_COLUMNS}). "
    f"Available: {', '.join(COLUMN_DEFS.keys())}",
)
@click.option(
    "--clip",
    "-W",
    type=int,
    default=25,
    show_default=True,
    help="Max width for artist/title/album columns (0 = no clip)",
)
@click.option(
    "--sort",
    "-s",
    "sort_col",
    default=None,
    help="Sort by column name. Prefix with - for descending (e.g. -bpm)",
)
@pass_context
def cli(
    ctx: Context,
    query: tuple[str, ...],
    output_format: str,
    rebuild_cache: bool,
    limit: int | None,
    columns: str | None,
    clip: int,
    sort_col: str | None,
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

    \b
    Column selection:
      --columns artist,title,bpm,key
      Available: artist, title, album, genre, bpm, rating, key,
                 year, tracknumber, comment, color, crates, file
    """
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    repo_path = config.music_repo
    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_NO_REPO)

    # Parse column list
    col_list = [c.strip() for c in (columns or DEFAULT_COLUMNS).split(",")]
    for c in col_list:
        if c not in COLUMN_DEFS:
            error(f"Unknown column: {c}", hint=f"Available: {', '.join(COLUMN_DEFS.keys())}")
            raise SystemExit(EXIT_PARSE_ERROR)

    # Validate sort column
    sort_descending = False
    sort_attr: str | None = None
    if sort_col is not None:
        sc = sort_col
        if sc.startswith("-"):
            sort_descending = True
            sc = sc[1:]
        if sc not in COLUMN_DEFS:
            error(f"Unknown sort column: {sc}", hint=f"Available: {', '.join(COLUMN_DEFS.keys())}")
            raise SystemExit(EXIT_PARSE_ERROR)
        sort_attr = COLUMN_DEFS[sc].get("attr")
        if sort_attr is None:
            error(f"Column '{sc}' is not sortable")
            raise SystemExit(EXIT_PARSE_ERROR)

    # Clip width (0 means no clip)
    clip_width: int | None = clip if clip > 0 else None

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
        if rebuild_cache:
            delete_cache(repo_path)

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

            # Sort if requested
            if sort_attr is not None:

                def _sort_key(t):
                    v = getattr(t, sort_attr)
                    # Put None values last regardless of direction
                    if v is None:
                        return (1, "")
                    if isinstance(v, str):
                        return (0, v.lower())
                    return (0, v)

                tracks = sorted(tracks, key=_sort_key, reverse=sort_descending)

            if limit is not None:
                tracks = tracks[:limit]

            # Output results (must be inside session context)
            if not tracks:
                info(f"No results for: {query_string}")
                raise SystemExit(EXIT_NO_RESULTS)

            # Load crate data if needed for table or json output
            crates_by_key: dict[str, list[str]] = {}
            if "crates" in col_list or output_format == "json":
                track_keys = [t.key for t in tracks]
                crate_rows = session.query(TrackCrate).filter(TrackCrate.key.in_(track_keys)).all()
                for row in crate_rows:
                    crates_by_key.setdefault(row.key, []).append(row.crate)

            if output_format == "table":
                _print_table(tracks, query_string, col_list, crates_by_key, clip_width)
            elif output_format == "paths":
                _print_paths(tracks)
            elif output_format == "json":
                _print_json(tracks, crates_by_key)

    except subprocess.CalledProcessError as e:
        if "git-annex" in (e.stderr or ""):
            error("No git-annex branch found. Is this a git-annex repository?")
        else:
            error(f"Git command failed: {e}")
        raise SystemExit(EXIT_CACHE_ERROR)
    except Exception as e:
        error(f"Cache error: {e}")
        raise SystemExit(EXIT_CACHE_ERROR)

    raise SystemExit(EXIT_SUCCESS)


def _print_table(
    tracks: list,
    query_string: str,
    col_list: list[str],
    crates_by_key: dict[str, list[str]],
    clip_width: int | None = None,
) -> None:
    """Print results as a Rich table, using pager when appropriate."""
    import io

    from rich.console import Console

    # Print title separately so it doesn't interfere with pager header
    info(f"Search: {query_string} ({len(tracks)} results)")

    table = create_table(
        show_header=True,
        header_style="bold",
    )

    # Pre-compute file display values (strip common prefix)
    file_paths = [t.file or "" for t in tracks]
    file_display = _strip_common_prefix(file_paths) if "file" in col_list else file_paths

    # Add columns
    for col in col_list:
        cdef = COLUMN_DEFS[col]
        kwargs: dict = {"justify": cdef["justify"]}
        if cdef["style"]:
            kwargs["style"] = cdef["style"]
        table.add_column(cdef["header"], no_wrap=True, **kwargs)

    # Add rows
    for i, t in enumerate(tracks):
        row = []
        for col in col_list:
            row.append(_get_cell_value(t, col, crates_by_key, file_display[i], clip_width))
        table.add_row(*row)

    # Render to buffer so we can route through pager
    # Use very wide width so columns auto-size to content; pager handles scrolling
    render_width = 1000

    buf = io.StringIO()
    render_console = Console(
        file=buf,
        theme=THEME,
        force_terminal=not console.no_color,
        width=render_width,
        no_color=console.no_color,
    )
    render_console.print(table)
    content = buf.getvalue()

    # Table header = title line + top border + header + header border = 4 lines
    pager_print(content, header_lines=3)


def _print_paths(tracks: list) -> None:
    """Print one file path per line."""
    for t in tracks:
        click.echo(t.file or "")


def _print_json(tracks: list, crates_by_key: dict[str, list[str]]) -> None:
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
                "crates": sorted(crates_by_key.get(t.key, [])),
                "present": t.present,
            }
        )
    click.echo(json.dumps(results, indent=2))
