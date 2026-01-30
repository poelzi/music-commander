"""Get annexed files from git commits."""

from __future__ import annotations

from pathlib import Path

import click

from music_commander.cli import Context, pass_context
from music_commander.exceptions import (
    InvalidRevisionError,
    NotGitAnnexRepoError,
    NotGitRepoError,
)
from music_commander.utils.git import (
    FetchResult,
    annex_drop_files,
    annex_get_files_with_progress,
    check_git_annex_repo,
    filter_annexed_files,
    get_files_from_revision,
)
from music_commander.utils.output import (
    console,
    create_table,
    error,
    info,
    success,
    warning,
)
from music_commander.utils.search_ops import (
    FileOperationResult,
    execute_search_files,
    show_operation_summary,
)

# Exit codes per CLI contract
EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_INVALID_REVISION = 2
EXIT_NOT_ANNEX_REPO = 3
EXIT_NO_RESULTS = 0
EXIT_PARSE_ERROR = 1
EXIT_CACHE_ERROR = 2
EXIT_NO_REPO = 3


@click.group("files")
def cli() -> None:
    """File management commands.

    Commands for fetching and managing files from git-annex.
    """
    pass


@cli.command("get-commit")
@click.argument("revision")
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Show files without fetching",
)
@click.option(
    "--remote",
    "-r",
    type=str,
    default=None,
    help="Preferred git-annex remote",
)
@click.option(
    "--jobs",
    "-J",
    type=int,
    default=1,
    help="Number of parallel fetch jobs",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show git annex commands and per-file status",
)
@pass_context
def get_commit(
    ctx: Context,
    revision: str,
    dry_run: bool,
    remote: str | None,
    jobs: int,
    verbose: bool,
) -> None:
    """Fetch git-annexed files from commits, ranges, branches, or tags.

    REVISION can be:

    \b
      - A commit hash: abc123
      - A relative commit: HEAD~1
      - A range: HEAD~5..HEAD
      - A branch name: feature/new-tracks
      - A tag: v2025-summer-set

    Examples:

    \b
      # Fetch files from last commit
      music-commander files get-commit HEAD~1

    \b
      # Fetch files from last 5 commits
      music-commander files get-commit HEAD~5..HEAD

    \b
      # Preview without fetching
      music-commander files get-commit --dry-run HEAD~3..HEAD

    \b
      # Fetch from specific remote
      music-commander files get-commit --remote nas HEAD~1
    """
    # Get config
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)

    # Use configured remote if not specified
    if remote is None:
        remote = config.default_remote

    # Get repository path
    repo_path = config.music_repo

    # Validate repository
    try:
        check_git_annex_repo(repo_path)
    except NotGitRepoError:
        error(
            f"Not a git repository: {repo_path}",
            hint="Specify a git repository with --config or music_repo in config",
        )
        raise SystemExit(EXIT_NOT_ANNEX_REPO)
    except NotGitAnnexRepoError:
        error(
            f"Not a git-annex repository: {repo_path}",
            hint="Run 'git annex init' to initialize git-annex",
        )
        raise SystemExit(EXIT_NOT_ANNEX_REPO)

    # Get files from revision
    try:
        all_files = get_files_from_revision(repo_path, revision)
    except InvalidRevisionError:
        error(
            f"Invalid revision: {revision}",
            hint="Check revision with 'git rev-parse' or use a valid commit/branch/tag",
        )
        raise SystemExit(EXIT_INVALID_REVISION)

    if not all_files:
        info(f"No files changed in {revision}")
        raise SystemExit(EXIT_SUCCESS)

    # Filter to annexed files only
    annexed_files = filter_annexed_files(all_files)

    if not annexed_files:
        info(f"No annexed files in {revision} ({len(all_files)} regular files found)")
        raise SystemExit(EXIT_SUCCESS)

    # Dry run: just show files
    if dry_run:
        _show_dry_run(repo_path, annexed_files)
        raise SystemExit(EXIT_SUCCESS)

    # Fetch files
    if not ctx.quiet:
        info(f"Fetching {len(annexed_files)} annexed files from {revision}...")

    result = annex_get_files_with_progress(
        repo_path,
        annexed_files,
        remote=remote,
        jobs=jobs,
        verbose=verbose,
    )

    # Show summary
    _show_summary(repo_path, result)

    # Exit with appropriate code
    if result.failed:
        raise SystemExit(EXIT_PARTIAL_FAILURE)
    raise SystemExit(EXIT_SUCCESS)


def _show_dry_run(repo_path: Path, files: list[Path]) -> None:
    """Show files that would be fetched."""
    console.print(f"\n[bold]Would fetch {len(files)} annexed files:[/bold]\n")

    for file_path in files:
        rel_path = file_path.relative_to(repo_path)
        console.print(f"  [path]{rel_path}[/path]")

    console.print()


def _show_summary(repo_path: Path, result: FetchResult) -> None:
    """Show fetch results summary."""
    console.print()

    # Create summary table
    table = create_table(title="Fetch Summary")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Details")

    if result.fetched:
        table.add_row(
            "[success]Fetched[/success]",
            str(len(result.fetched)),
            "Successfully retrieved",
        )

    if result.already_present:
        table.add_row(
            "[info]Present[/info]",
            str(len(result.already_present)),
            "Already available locally",
        )

    if result.failed:
        table.add_row(
            "[error]Failed[/error]",
            str(len(result.failed)),
            "Could not retrieve",
        )

    console.print(table)

    # Show failed files with reasons
    if result.failed:
        console.print("\n[error]Failed files:[/error]")
        for file_path, reason in result.failed:
            rel_path = file_path.relative_to(repo_path)
            console.print(f"  [path]{rel_path}[/path]")
            console.print(f"    [dim]{reason}[/dim]")

    # Final status message
    console.print()
    if result.success:
        success(f"All {result.total_requested} files processed successfully")
    else:
        warning(f"{len(result.failed)} of {result.total_requested} files failed to fetch")


# Shared options for search-based file operations
_SEARCH_QUERY_ARGUMENT = click.argument("query", nargs=-1, required=True)
_DRY_RUN_OPTION = click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Show files without performing the operation",
)
_JOBS_OPTION = click.option(
    "--jobs",
    "-J",
    type=int,
    default=1,
    help="Number of parallel jobs",
)
_VERBOSE_OPTION = click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show per-file status",
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
@_VERBOSE_OPTION
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
    file_paths = execute_search_files(ctx, query, config, "Fetch", verbose=verbose, dry_run=dry_run, require_present=False)
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


@cli.command("drop")
@_SEARCH_QUERY_ARGUMENT
@_DRY_RUN_OPTION
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Drop files even if insufficient copies exist",
)
@_VERBOSE_OPTION
@pass_context
def drop(
    ctx: Context,
    query: tuple[str, ...],
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> None:
    """Drop files matching a search query to free up disk space.

    Uses the same search syntax as the 'search' command to find files,
    then removes their content from the local repository (keeping the
    symlink placeholders). The files can be fetched again later if needed.

    WARNING: Only drops files if git-annex knows of other copies, unless
    --force is used.

    Examples:

    \b
      # Drop all files by an artist
      music-commander files drop artist:Basinski

    \b
      # Drop low-rated files (with force to override safety check)
      music-commander files drop "rating:<2" --force

    \b
      # Preview files that would be dropped
      music-commander files drop --dry-run "genre:ambient"
    """
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    # Validate repository
    try:
        check_git_annex_repo(config.music_repo)
    except NotGitRepoError:
        error(f"Not a git repository: {config.music_repo}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)
    except NotGitAnnexRepoError:
        error(f"Not a git-annex repository: {config.music_repo}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)

    # Execute search to get files (only include files that are present locally)
    file_paths = execute_search_files(ctx, query, config, "Drop", verbose=verbose, dry_run=dry_run, require_present=True)
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
            console.print(f"\n[bold]Would drop {len(annexed_files)} annexed files:[/bold]\n")
            for file_path in annexed_files:
                rel_path = file_path.relative_to(config.music_repo)
                console.print(f"  [path]{rel_path}[/path]")
            console.print()
        raise SystemExit(EXIT_SUCCESS)

    # Drop files
    if not ctx.quiet:
        info(f"Dropping {len(annexed_files)} annexed files...")
        if force:
            warning("Using --force: may drop files without sufficient copies!")

    drop_result = annex_drop_files(
        config.music_repo,
        annexed_files,
        force=force,
        verbose=verbose,
    )

    # Convert FetchResult to FileOperationResult for summary display
    op_result = FileOperationResult(
        processed=drop_result.fetched,
        skipped=drop_result.already_present,
        failed=drop_result.failed,
    )

    show_operation_summary(config.music_repo, op_result, "Drop")

    # Exit with appropriate code
    if drop_result.failed:
        raise SystemExit(EXIT_PARTIAL_FAILURE)
    raise SystemExit(EXIT_SUCCESS)
