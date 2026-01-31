"""Fetch files matching a search query from git-annex remotes."""

from __future__ import annotations

import click

from music_commander.cli import Context, pass_context
from music_commander.commands.files import (
    _JOBS_OPTION,
    _SEARCH_QUERY_ARGUMENT,
    _VERBOSE_OPTION,
    EXIT_CACHE_ERROR,
    EXIT_NO_REPO,
    EXIT_NO_RESULTS,
    EXIT_NOT_ANNEX_REPO,
    EXIT_PARTIAL_FAILURE,
    EXIT_SUCCESS,
    cli,
)
from music_commander.exceptions import (
    NotGitAnnexRepoError,
    NotGitRepoError,
)
from music_commander.utils.git import (
    annex_get_files_with_progress,
    check_git_annex_repo,
    filter_annexed_files,
)
from music_commander.utils.output import (
    console,
    error,
    info,
)
from music_commander.utils.search_ops import (
    FileOperationResult,
    execute_search_files,
    show_operation_summary,
)

_DRY_RUN_OPTION = click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Show files without performing the operation",
)


@cli.command("get")
@_SEARCH_QUERY_ARGUMENT
@_DRY_RUN_OPTION
@click.option(
    "--remote",
    "-r",
    type=str,
    default=None,
    help="Preferred git-annex remote",
)
@_JOBS_OPTION
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show per-file status",
)
@pass_context
def get(
    ctx: Context,
    query: tuple[str, ...],
    dry_run: bool,
    remote: str | None,
    jobs: int,
    verbose: bool,
) -> None:
    """Fetch files matching a search query from git-annex remotes.

    Uses the same search syntax as the 'search' command to find files,
    then fetches them from git-annex remotes.

    Examples:

    \b
      # Fetch all files by an artist
      music-commander files get artist:Basinski

    \b
      # Fetch high-rated techno files
      music-commander files get "rating:>=4 genre:techno"

    \b
      # Preview files that would be fetched
      music-commander files get --dry-run "bpm:>140"
    """
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    # Use configured remote if not specified
    if remote is None:
        remote = config.default_remote

    # Validate repository
    try:
        check_git_annex_repo(config.music_repo)
    except NotGitRepoError:
        error(f"Not a git repository: {config.music_repo}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)
    except NotGitAnnexRepoError:
        error(f"Not a git-annex repository: {config.music_repo}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)

    # Execute search to get files (include all files, not just present ones)
    file_paths = execute_search_files(
        ctx, query, config, "Fetch", verbose=verbose, dry_run=dry_run, require_present=False
    )
    if file_paths is None:
        raise SystemExit(EXIT_CACHE_ERROR)

    if not file_paths:
        raise SystemExit(EXIT_NO_RESULTS)

    # Filter to annexed files only
    annexed_files = filter_annexed_files(file_paths)

    if not annexed_files:
        info("No annexed files found matching the search query")
        raise SystemExit(EXIT_SUCCESS)

    # Dry run: just show files
    if dry_run:
        if verbose or not ctx.quiet:
            console.print(f"\n[bold]Would fetch {len(annexed_files)} annexed files:[/bold]\n")
            for file_path in annexed_files:
                rel_path = file_path.relative_to(config.music_repo)
                console.print(f"  [path]{rel_path}[/path]")
            console.print()
        raise SystemExit(EXIT_SUCCESS)

    # Fetch files
    if not ctx.quiet:
        info(f"Fetching {len(annexed_files)} annexed files...")

    fetch_result = annex_get_files_with_progress(
        config.music_repo,
        annexed_files,
        remote=remote,
        jobs=jobs,
        verbose=verbose,
    )

    # Convert FetchResult to FileOperationResult for summary display
    op_result = FileOperationResult(
        processed=fetch_result.fetched,
        skipped=fetch_result.already_present,
        failed=fetch_result.failed,
    )

    show_operation_summary(config.music_repo, op_result, "Fetch")

    # Exit with appropriate code
    if fetch_result.failed:
        raise SystemExit(EXIT_PARTIAL_FAILURE)
    raise SystemExit(EXIT_SUCCESS)
