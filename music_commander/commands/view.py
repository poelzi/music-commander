"""Create symlink views from search results and Jinja2 templates."""

from __future__ import annotations

from pathlib import Path

import click

from music_commander.cache.builder import build_cache, refresh_cache
from music_commander.cache.models import TrackCrate
from music_commander.cache.session import get_cache_session
from music_commander.cli import Context, pass_context
from music_commander.search.parser import SearchParseError, parse_query
from music_commander.search.query import execute_search
from music_commander.utils.output import (
    console,
    create_progress,
    error,
    info,
    success,
    warning,
)
from music_commander.view.symlinks import cleanup_output_dir, create_symlink_tree
from music_commander.view.template import TemplateRenderError

EXIT_SUCCESS = 0
EXIT_PARSE_ERROR = 1
EXIT_TEMPLATE_ERROR = 2
EXIT_NO_REPO = 3


@click.command("view")
@click.argument("query", nargs=-1, required=True)
@click.option(
    "--pattern",
    "-p",
    required=True,
    help='Jinja2 path template, e.g. "{{ genre }}/{{ artist }} - {{ title }}"',
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for symlink tree",
)
@click.option(
    "--absolute",
    is_flag=True,
    default=False,
    help="Create absolute symlinks instead of relative",
)
@click.option(
    "--rebuild-cache",
    is_flag=True,
    default=False,
    help="Force full cache rebuild before creating view",
)
@click.option(
    "--no-cleanup",
    is_flag=True,
    default=False,
    help="Don't remove old symlinks before creating new ones",
)
@pass_context
def cli(
    ctx: Context,
    query: tuple[str, ...],
    pattern: str,
    output: Path,
    absolute: bool,
    rebuild_cache: bool,
    no_cleanup: bool,
) -> None:
    """Create a symlink directory tree from search results.

    QUERY is a Mixxx-compatible search string. The results are rendered
    using the Jinja2 PATTERN template and symlinked into the OUTPUT directory.

    \b
    Examples:
      music-commander view "genre:Darkpsy" \\
        --pattern "{{ genre }}/{{ artist }} - {{ title }}" \\
        --output ./views/by-genre

    \b
      music-commander view "rating:>=4" \\
        --pattern "{{ rating }}/{{ bpm | round_to(5) }} - {{ artist }} - {{ title }}" \\
        --output ./views/rated

    \b
      music-commander view "crate:Festival" \\
        --pattern "{{ crate }}/{{ artist }} - {{ title }}" \\
        --output ./views/crates

    \b
    Available template variables:
      artist, title, album, genre, bpm, rating, key, year,
      tracknumber, comment, color, crate, file

    \b
    Custom filters:
      round_to(n)  - Round to nearest multiple of n: {{ bpm | round_to(5) }}
    """
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    repo_path = config.music_repo
    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_NO_REPO)

    # Validate template
    try:
        from music_commander.view.template import _env

        _env.parse(pattern)
    except Exception as e:
        error(f"Invalid template: {e}")
        raise SystemExit(EXIT_TEMPLATE_ERROR)

    query_string = " ".join(query)

    # Parse query
    try:
        parsed = parse_query(query_string)
    except SearchParseError as e:
        error(f"Invalid search query: {e}")
        raise SystemExit(EXIT_PARSE_ERROR)

    try:
        with get_cache_session(repo_path) as session:
            # Auto-refresh cache
            if rebuild_cache:
                info("Rebuilding cache...")
                count = build_cache(repo_path, session)
                info(f"Cache built with {count} tracks")
            else:
                result = refresh_cache(repo_path, session)
                if result is not None and result > 0:
                    info(f"Cache refreshed: {result} tracks updated")

            # Execute search
            tracks = execute_search(session, parsed)

            if not tracks:
                info(f"No results for: {query_string}")
                raise SystemExit(EXIT_SUCCESS)

            info(f"Found {len(tracks)} tracks matching query")

            # Load crate data for all matching tracks
            track_keys = [t.key for t in tracks]
            crate_rows = session.query(TrackCrate).filter(TrackCrate.key.in_(track_keys)).all()
            crates_by_key: dict[str, list[str]] = {}
            for row in crate_rows:
                crates_by_key.setdefault(row.key, []).append(row.crate)

    except SystemExit:
        raise
    except Exception as e:
        error(f"Cache error: {e}")
        raise SystemExit(EXIT_NO_REPO)

    # Cleanup old symlinks
    output_dir = output.resolve()
    if not no_cleanup and output_dir.exists():
        removed = cleanup_output_dir(output_dir)
        if removed > 0:
            info(f"Cleaned up {removed} old symlinks")

    # Create symlink tree
    try:
        created, duplicates = create_symlink_tree(
            tracks=tracks,
            crates_by_key=crates_by_key,
            template_str=pattern,
            output_dir=output_dir,
            repo_path=repo_path,
            absolute=absolute,
        )
    except TemplateRenderError as e:
        error(f"Template error: {e}")
        raise SystemExit(EXIT_TEMPLATE_ERROR)

    # Report
    success(f"Created {created} symlinks in {output_dir}")
    if duplicates > 0:
        warning(f"{duplicates} duplicate paths resolved with numeric suffixes")

    raise SystemExit(EXIT_SUCCESS)
