"""Sync Mixxx metadata to git-annex."""

from __future__ import annotations

from pathlib import Path

import click
from rich.progress import track

from music_commander.cli import Context, pass_context
from music_commander.config import Config
from music_commander.db.models import SyncResult, SyncState, TrackMetadata
from music_commander.db.queries import (
    get_all_tracks,
    get_changed_tracks,
)
from music_commander.db.session import get_session
from music_commander.exceptions import (
    DatabaseNotFoundError,
    MixxxDatabaseError,
    NotGitAnnexRepoError,
    NotGitRepoError,
)
from music_commander.utils.annex_metadata import (
    AnnexMetadataBatch,
    build_annex_fields,
)
from music_commander.utils.output import (
    console,
    create_table,
    error,
    info,
    success,
    warning,
)
from music_commander.utils.sync_state import (
    now_utc,
    read_sync_state,
    write_sync_state,
)

# Exit codes per CLI contract
EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_DB_ERROR = 2
EXIT_NOT_ANNEX_REPO = 3


@click.command("sync-metadata")
@click.option(
    "--all",
    "-a",
    "sync_all",
    is_flag=True,
    default=False,
    help="Sync all tracks, ignoring change detection",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Show what would be synced without making changes",
)
@click.option(
    "--batch-size",
    "-b",
    type=int,
    default=None,
    help="Commit every N files (default: commit once at end)",
)
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
@pass_context
def cli(
    ctx: Context,
    sync_all: bool,
    dry_run: bool,
    batch_size: int | None,
    paths: tuple[Path, ...],
) -> None:
    """Sync Mixxx library metadata to git-annex.

    Syncs track metadata (rating, BPM, color, key, artist, title, album,
    genre, year, tracknumber, comment, crates) from your Mixxx library to
    git-annex metadata on annexed files.

    By default, only tracks changed since the last sync are updated.
    Use --all to force a complete resync.

    Examples:

    \b
      # Sync tracks changed since last sync
      music-commander sync-metadata

    \b
      # Force sync all tracks
      music-commander sync-metadata --all

    \b
      # Preview changes without syncing
      music-commander sync-metadata --dry-run

    \b
      # Sync specific directory
      music-commander sync-metadata ./darkpsy/

    \b
      # Sync with intermediate commits every 1000 files
      music-commander sync-metadata --batch-size 1000

    After syncing, query tracks with git-annex:

    \b
      git annex find --metadata rating=5
      git annex find --metadata crate=Festival
    """
    # Get config
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)

    # Validate Mixxx database exists
    if not config.mixxx_db.exists():
        error(
            f"Mixxx database not found: {config.mixxx_db}",
            hint="Check mixxx_db path in config or specify with --config",
        )
        raise SystemExit(EXIT_DB_ERROR)

    # Validate batch size
    if batch_size is not None and batch_size <= 0:
        error("--batch-size must be a positive integer")
        raise SystemExit(EXIT_PARTIAL_FAILURE)

    # Convert paths tuple to list
    paths_list = list(paths) if paths else None

    # Run sync
    try:
        result = sync_tracks(
            config,
            sync_all=sync_all,
            paths=paths_list,
            dry_run=dry_run,
            batch_size=batch_size,
        )
    except DatabaseNotFoundError as e:
        error(f"Database not found: {e.path}")
        raise SystemExit(EXIT_DB_ERROR)
    except MixxxDatabaseError as e:
        error(f"Mixxx database error: {e}")
        raise SystemExit(EXIT_DB_ERROR)
    except NotGitRepoError as e:
        error(
            f"Not a git repository: {e.path}",
            hint="Specify a git repository with music_repo in config",
        )
        raise SystemExit(EXIT_NOT_ANNEX_REPO)
    except NotGitAnnexRepoError as e:
        error(
            f"Not a git-annex repository: {e.path}",
            hint="Run 'git annex init' to initialize git-annex",
        )
        raise SystemExit(EXIT_NOT_ANNEX_REPO)
    except Exception as e:
        error(f"Unexpected error during sync: {e}")
        raise SystemExit(EXIT_PARTIAL_FAILURE)

    # Exit with appropriate code
    if result.failed:
        raise SystemExit(EXIT_PARTIAL_FAILURE)
    raise SystemExit(EXIT_SUCCESS)


def matches_paths(track: TrackMetadata, paths: list[Path] | None) -> bool:
    """Check if track matches any of the user-specified paths.

    Args:
        track: Track metadata with relative_path.
        paths: List of paths to filter by (file or directory).

    Returns:
        True if track matches any path, or if no paths specified.
    """
    if paths is None:
        return True

    if track.relative_path is None:
        return False

    for p in paths:
        # Exact match or parent directory match
        if track.relative_path == p:
            return True
        try:
            if track.relative_path.is_relative_to(p):
                return True
        except (ValueError, AttributeError):
            continue

    return False


def sync_tracks(
    config: Config,
    *,
    sync_all: bool = False,
    paths: list[Path] | None = None,
    dry_run: bool = False,
    batch_size: int | None = None,
) -> SyncResult:
    """Sync Mixxx metadata to git-annex.

    Main sync workflow:
    1. Read sync state to get last sync timestamp
    2. Query Mixxx database for tracks (all or changed since last sync)
    3. Filter tracks by path and repo membership
    4. Transform metadata to git-annex format
    5. Write metadata via batch subprocess
    6. Update sync state with new timestamp
    7. Return summary results

    Args:
        config: Application configuration with mixxx_db and music_repo paths.
        sync_all: If True, sync all tracks regardless of change status.
        paths: If provided, only sync tracks matching these relative paths.
        dry_run: If True, show what would be synced without making changes.
        batch_size: If provided, commit every N files (default: single commit at end).

    Returns:
        SyncResult with counts of synced, skipped, and failed tracks.
    """
    result = SyncResult()

    # Load sync state
    sync_state = read_sync_state(config.music_repo)

    if sync_state.is_first_sync:
        info("First sync detected - will sync all tracks")
        sync_all = True
    elif sync_all:
        info("Syncing all tracks (--all flag)")
    else:
        last_sync = sync_state.last_sync_timestamp
        info(f"Syncing tracks changed since {last_sync}")

    # Query Mixxx database
    with get_session(config.mixxx_db) as session:
        if sync_all:
            tracks_iter = get_all_tracks(session, config.music_repo, config.mixxx_music_root)
        else:
            # Get timestamp in milliseconds (Mixxx format)
            # Note: sync_all is True when is_first_sync, so last_sync_timestamp is not None here
            assert sync_state.last_sync_timestamp is not None
            since_ms = int(sync_state.last_sync_timestamp.timestamp() * 1000)
            tracks_iter = get_changed_tracks(
                session, config.music_repo, since_ms, config.mixxx_music_root
            )

        # Convert to list for progress tracking (and to close DB session before batch)
        tracks = list(tracks_iter)

    if not tracks:
        info("No tracks to sync")
        return result

    info(f"Found {len(tracks)} tracks to sync")

    # Filter tracks by path if specified
    if paths:
        tracks = [t for t in tracks if matches_paths(t, paths)]
        info(f"Filtered to {len(tracks)} tracks matching specified paths")

    if not tracks:
        info("No tracks match the specified paths")
        return result

    # Dry-run mode: show what would be synced
    if dry_run:
        info("[Dry Run] Would sync the following tracks:")
        for t in tracks[:10]:  # Show first 10
            console.print(f"  [path]{t.relative_path}[/path]")
        if len(tracks) > 10:
            console.print(f"  ... and {len(tracks) - 10} more")
        return result

    # Write metadata via batch subprocess
    with AnnexMetadataBatch(config.music_repo) as batch:
        for t in track(
            tracks,
            description="Syncing metadata...",
            console=console,
        ):
            # Skip tracks without relative path (shouldn't happen after filtering)
            if t.relative_path is None:
                result.skipped.append((t.file_path, "Not under music_repo"))
                continue

            # Check if file exists in repository
            # Use is_symlink() to also match git-annex dangling symlinks
            # (content not locally present but still tracked by git-annex)
            full_path = config.music_repo / t.relative_path
            if not full_path.exists() and not full_path.is_symlink():
                result.skipped.append((t.relative_path, "File not in repository"))
                continue

            # Transform metadata to git-annex format
            try:
                fields = build_annex_fields(t)
            except Exception as e:
                result.failed.append((t.relative_path, f"Transform error: {e}"))
                continue

            # Skip if no fields to sync (all None/empty)
            if not fields or all(not v for v in fields.values()):
                result.skipped.append((t.relative_path, "No metadata to sync"))
                continue

            # Write metadata
            try:
                success_flag = batch.set_metadata(t.relative_path, fields)

                if success_flag:
                    result.synced.append(t.relative_path)
                else:
                    result.failed.append((t.relative_path, "Git-annex error"))
            except Exception as e:
                result.failed.append((t.relative_path, f"Write error: {e}"))
                continue

        # Intermediate commit if batch_size specified
        if batch_size and len(result.synced) % batch_size == 0:
            batch.commit()

    # Update sync state with new timestamp
    new_state = SyncState(
        last_sync_timestamp=now_utc(),
        tracks_synced=sync_state.tracks_synced + len(result.synced),
    )
    write_sync_state(config.music_repo, new_state)

    # Display summary
    print_sync_summary(result)

    return result


def print_sync_summary(result: SyncResult) -> None:
    """Display sync operation summary.

    Args:
        result: SyncResult with operation outcomes.
    """
    table = create_table(title="Sync Summary", show_header=True, header_style="bold")
    table.add_column("Status", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="bold")
    table.add_column("Details", style="dim")

    table.add_row(
        "Synced",
        str(len(result.synced)),
        "Metadata updated" if result.synced else "-",
    )

    table.add_row(
        "Skipped",
        str(len(result.skipped)),
        "Not in repo" if result.skipped else "-",
    )

    table.add_row(
        "Failed",
        str(len(result.failed)),
        "Errors occurred" if result.failed else "-",
        style="error" if result.failed else None,
    )

    console.print(table)

    # Show failed files if any
    if result.failed:
        console.print("\n[error]Failed files:[/error]")
        for path, reason in result.failed[:10]:  # Show first 10
            error(f"{path}: {reason}")
        if len(result.failed) > 10:
            error(f"... and {len(result.failed) - 10} more failures")

    # Overall status
    if result.success:
        success("\nAll files processed successfully!")
    else:
        warning(f"\n{len(result.failed)} files failed to sync")
