"""Rebuild the local metadata cache from the git-annex branch."""

from __future__ import annotations

import subprocess

import click

from music_commander.cache.builder import build_cache
from music_commander.cache.models import CacheTrack
from music_commander.cache.session import clear_cache_tables, get_cache_session
from music_commander.cli import Context, pass_context
from music_commander.utils.output import create_progress, error, info, success, verbose

EXIT_SUCCESS = 0
EXIT_CACHE_ERROR = 2
EXIT_NO_REPO = 3


@click.command("rebuild-cache")
@pass_context
def cli(ctx: Context) -> None:
    """Rebuild the local metadata cache from scratch.

    Clears track cache data and rebuilds by reading all metadata from
    the git-annex branch. Bandcamp sync data is preserved.

    \b
    Examples:
      music-commander rebuild-cache
      music-commander -v rebuild-cache
      music-commander --debug rebuild-cache
    """
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    repo_path = config.music_repo
    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        raise SystemExit(EXIT_NO_REPO)

    try:
        with get_cache_session(repo_path) as session:
            verbose("Clearing cache tables (preserving Bandcamp data)...")
            clear_cache_tables(session)
            if not ctx.quiet:
                info("Rebuilding cache...")
            with create_progress() as progress:
                task = progress.add_task("Building cache...", total=None)
                count = build_cache(repo_path, session)
                progress.update(task, completed=count, total=count)
            if not ctx.quiet:
                present = session.query(CacheTrack).filter_by(present=True).count()
                missing = count - present
                msg = f"Cache rebuilt with {count} tracks"
                if missing:
                    msg += f" ({present} present, {missing} missing)"
                success(msg)
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
