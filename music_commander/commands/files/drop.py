"""Drop files matching a search query to free up disk space."""

from __future__ import annotations

import click

from music_commander.cli import Context, pass_context
from music_commander.commands.files import (
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
    annex_drop_files,
    check_git_annex_repo,
    filter_annexed_files,
)
from music_commander.utils.output import (
    console,
    error,
    info,
    warning,
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
    file_paths = execute_search_files(
        ctx, query, config, "Drop", verbose=verbose, dry_run=dry_run, require_present=True
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
