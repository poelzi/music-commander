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

# Exit codes per CLI contract
EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_INVALID_REVISION = 2
EXIT_NOT_ANNEX_REPO = 3


@click.command("get-commit-files")
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
    "-j",
    type=int,
    default=1,
    help="Parallel fetch jobs (not yet implemented)",
)
@pass_context
def cli(
    ctx: Context,
    revision: str,
    dry_run: bool,
    remote: str | None,
    jobs: int,
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
      music-commander get-commit-files HEAD~1

    \b
      # Fetch files from last 5 commits
      music-commander get-commit-files HEAD~5..HEAD

    \b
      # Preview without fetching
      music-commander get-commit-files --dry-run HEAD~3..HEAD

    \b
      # Fetch from specific remote
      music-commander get-commit-files --remote nas HEAD~1
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
