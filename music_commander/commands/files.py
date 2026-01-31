"""Get annexed files from git commits."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from music_commander.cli import Context, pass_context
from music_commander.exceptions import (
    InvalidRevisionError,
    NotGitAnnexRepoError,
    NotGitRepoError,
)
from music_commander.utils.checkers import (
    CheckReport,
    CheckResult,
    check_file,
    check_tool_available,
    get_checkers_for_extension,
    get_checkers_for_file,
    write_report,
)
from music_commander.utils.git import (
    FetchResult,
    annex_drop_files,
    annex_get_files_with_progress,
    check_git_annex_repo,
    filter_annexed_files,
    get_files_from_revision,
    is_annex_present,
)
from music_commander.utils.output import (
    MultilineFileProgress,
    console,
    create_table,
    error,
    info,
    success,
    warning,
)
from music_commander.utils.output import (
    verbose as output_verbose,
)
from music_commander.utils.search_ops import (
    FileOperationResult,
    execute_search_files,
    resolve_args_to_files,
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


@cli.command("check")
@click.argument("args", nargs=-1)
@_DRY_RUN_OPTION
@_JOBS_OPTION
@_VERBOSE_OPTION
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output JSON report path",
)
@click.option(
    "--flac-multichannel-check",
    is_flag=True,
    default=False,
    help="Warn on stereo FLAC files with multichannel bit (Pioneer compatibility)",
)
@pass_context
def check(
    ctx: Context,
    args: tuple[str, ...],
    dry_run: bool,
    jobs: int,
    verbose: bool,
    output: str | None,
    flac_multichannel_check: bool,
) -> None:
    """Check integrity of audio files using format-specific tools.

    Can check files by path, directory, search query, or all annexed files.
    Writes a JSON report of all results.

    Examples:

    \b
      # Check all annexed files
      music-commander files check

    \b
      # Check specific file
      music-commander files check tracks/artist/song.flac

    \b
      # Check all files in a directory
      music-commander files check tracks/artist/

    \b
      # Check files matching search query
      music-commander files check "artist:Basinski rating:>=4"

    \b
      # Preview what would be checked
      music-commander files check --dry-run "genre:techno"

    \b
      # Custom output path
      music-commander files check --output /tmp/check-report.json
    """
    import time
    from datetime import datetime, timezone

    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    # CLI flag overrides config (CLI is True only when explicitly passed)
    flac_mc = flac_multichannel_check or config.flac_multichannel_check

    repo_path = config.music_repo

    # Validate repository
    try:
        check_git_annex_repo(repo_path)
    except NotGitRepoError:
        error(f"Not a git repository: {repo_path}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)
    except NotGitAnnexRepoError:
        error(f"Not a git-annex repository: {repo_path}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)

    # Resolve arguments to files (T014)
    file_paths = resolve_args_to_files(
        ctx,
        args,
        config,
        require_present=False,  # We want to report not-present files
        verbose=verbose,
        dry_run=dry_run,
    )

    if file_paths is None:
        raise SystemExit(EXIT_CACHE_ERROR)

    if not file_paths:
        info("No files to check")
        raise SystemExit(EXIT_NO_RESULTS)

    # Filter to annexed files only (T015)
    annexed_files = filter_annexed_files(file_paths)

    if not annexed_files:
        info("No annexed files found")
        raise SystemExit(EXIT_SUCCESS)

    # Separate present vs not-present files (T015)
    present_files = []
    not_present_files = []

    for file_path in annexed_files:
        if is_annex_present(file_path):
            present_files.append(file_path)
        else:
            not_present_files.append(file_path)

    # Separate files: checkable vs skipped (non-audio) vs missing tools
    skipped_files: list[Path] = []
    missing_tools_by_ext: dict[str, list[str]] = {}
    missing_files: list[Path] = []
    to_check: list[Path] = []

    for file_path in present_files:
        group, status_hint = get_checkers_for_file(file_path)
        if status_hint == "skipped":
            skipped_files.append(file_path)
            continue

        # Get tool names for availability check
        checkers = group.checkers if group is not None else []
        tool_names = [spec.command[0] for spec in checkers]

        # Internal validators (e.g. .cue) don't need external tools
        if group is not None and group.internal_validator:
            to_check.append(file_path)
        elif tool_names and all(not check_tool_available(t) for t in tool_names):
            ext = file_path.suffix.lower() or ".unknown"
            missing_files.append(file_path)
            missing_tools_by_ext.setdefault(ext, []).extend(tool_names)
        else:
            to_check.append(file_path)

    missing_tools = sorted(
        {tool for tool_list in missing_tools_by_ext.values() for tool in tool_list}
    )
    if missing_tools and (verbose or not ctx.quiet):
        warning("Missing checker tools detected:")
        for ext in sorted(missing_tools_by_ext.keys()):
            tools = ", ".join(sorted(set(missing_tools_by_ext[ext])))
            warning(f"  {ext}: {tools}")
        warning("Files requiring these tools will be marked as 'checker_missing'")

    # Dry-run mode (T017)
    if dry_run:
        console.print(f"\n[bold]Would check {len(to_check)} annexed files:[/bold]\n")

        # Show checkable files grouped by extension with their checkers
        by_ext: dict[str, list[Path]] = {}
        for file_path in to_check:
            ext = file_path.suffix.lower() or ".unknown"
            if ext not in by_ext:
                by_ext[ext] = []
            by_ext[ext].append(file_path)

        for ext in sorted(by_ext.keys()):
            files = by_ext[ext]
            checker_specs = get_checkers_for_extension(ext)
            tools = [spec.name for spec in checker_specs] or ["internal validator"]

            console.print(f"  [bold]{ext}[/bold] ({len(files)} files) - tools: {', '.join(tools)}")
            if verbose:
                for file_path in files[:5]:
                    rel_path = file_path.relative_to(repo_path)
                    console.print(f"    [path]{rel_path}[/path]")
                if len(files) > 5:
                    console.print(f"    ... and {len(files) - 5} more")

        if skipped_files:
            console.print(f"\n  [dim]Skipped ({len(skipped_files)} non-audio files)[/dim]")
            if verbose:
                for file_path in skipped_files[:5]:
                    rel_path = file_path.relative_to(repo_path)
                    console.print(f"    [path]{rel_path}[/path]")
                if len(skipped_files) > 5:
                    console.print(f"    ... and {len(skipped_files) - 5} more")

        if not_present_files:
            console.print(f"\n  [dim]Not present ({len(not_present_files)} files)[/dim]")
            if verbose:
                for file_path in not_present_files:
                    rel_path = file_path.relative_to(repo_path)
                    console.print(f"    [path]{rel_path}[/path]")

        console.print()
        raise SystemExit(EXIT_SUCCESS)

    # Initialize results list
    results: list[CheckResult] = []

    # Add skipped (non-audio) results upfront
    for file_path in skipped_files:
        rel_path = str(file_path.relative_to(repo_path))
        results.append(
            CheckResult(
                file=rel_path,
                status="skipped",
                tools=[],
                errors=[],
            )
        )

    # Add not-present results upfront (T015)
    for file_path in not_present_files:
        rel_path = str(file_path.relative_to(repo_path))
        results.append(
            CheckResult(
                file=rel_path,
                status="not_present",
                tools=[],
                errors=[],
            )
        )

    # Add checker-missing results upfront (T016)
    for file_path in missing_files:
        rel_path = str(file_path.relative_to(repo_path))
        ext = file_path.suffix.lower() or ".unknown"
        tools = sorted(set(missing_tools_by_ext.get(ext, [])))
        results.append(
            CheckResult(
                file=rel_path,
                status="checker_missing",
                tools=tools,
                errors=[],
            )
        )

    # Main check loop with progress (T018 + T019 with SIGINT safety)
    start_time = time.time()
    report = None

    try:
        if not ctx.quiet:
            info(f"Checking {len(to_check)} files...")

        with MultilineFileProgress(total=len(to_check), operation="Checking") as progress:
            # Choose sequential or parallel checking based on jobs parameter
            if jobs > 1:
                _check_files_parallel(
                    to_check,
                    repo_path,
                    results,
                    progress,
                    jobs,
                    verbose=verbose,
                    flac_multichannel_check=flac_mc,
                )
            else:
                _check_files_sequential(
                    to_check,
                    repo_path,
                    results,
                    progress,
                    verbose=verbose,
                    flac_multichannel_check=flac_mc,
                )

        duration = time.time() - start_time

        # Build final report (T019)
        summary = {
            "total": len(results),
            "ok": sum(1 for r in results if r.status == "ok"),
            "warning": sum(1 for r in results if r.status == "warning"),
            "error": sum(1 for r in results if r.status == "error"),
            "not_present": sum(1 for r in results if r.status == "not_present"),
            "checker_missing": sum(1 for r in results if r.status == "checker_missing"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
        }

        report = CheckReport(
            version=1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_seconds=duration,
            repository=str(repo_path),
            arguments=list(args) if args else [],
            summary=summary,
            results=results,
        )

    finally:
        # Write report even if interrupted (T019)
        if report or results:
            # Use provided output path or default
            output_path = (
                Path(output) if output else repo_path / ".music-commander-check-results.json"
            )

            # Build partial report if we don't have a complete one
            if report is None:
                duration = time.time() - start_time
                summary = {
                    "total": len(results),
                    "ok": sum(1 for r in results if r.status == "ok"),
                    "warning": sum(1 for r in results if r.status == "warning"),
                    "error": sum(1 for r in results if r.status == "error"),
                    "not_present": sum(1 for r in results if r.status == "not_present"),
                    "checker_missing": sum(1 for r in results if r.status == "checker_missing"),
                    "skipped": sum(1 for r in results if r.status == "skipped"),
                }
                report = CheckReport(
                    version=1,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    duration_seconds=duration,
                    repository=str(repo_path),
                    arguments=list(args) if args else [],
                    summary=summary,
                    results=results,
                )

            write_report(report, output_path)

            if not ctx.quiet:
                info(f"Report written to: {output_path}")

    # Show summary (T020)
    _show_check_summary(repo_path, results, report)

    # Exit with appropriate code
    has_errors = any(r.status == "error" for r in results)
    if has_errors:
        raise SystemExit(EXIT_PARTIAL_FAILURE)
    raise SystemExit(EXIT_SUCCESS)


def _check_files_sequential(
    files: list[Path],
    repo_path: Path,
    results: list[CheckResult],
    progress: MultilineFileProgress,
    *,
    verbose: bool = False,
    flac_multichannel_check: bool = False,
) -> None:
    """Check files sequentially (jobs=1).

    Raises KeyboardInterrupt cleanly so the caller can write a partial report.
    """
    for file_path in files:
        progress.start_file(file_path)

        # Check the file — KeyboardInterrupt propagates to caller
        result = check_file(
            file_path,
            repo_path,
            verbose_output=verbose,
            flac_multichannel_check=flac_multichannel_check,
        )
        results.append(result)

        if verbose:
            rel_path = file_path.relative_to(repo_path)
            output_verbose(f"Checked: {rel_path} -> {result.status}")

        # Update progress
        success = result.status in ("ok", "warning")
        message = ""
        if result.status == "warning" and result.warnings:
            message = result.warnings[0].output[:80].replace("\n", " ")
        elif not success and result.errors:
            # Show first error message (truncated)
            message = result.errors[0].output[:80].replace("\n", " ")

        progress.complete_file(file_path, success=success, message=message, status=result.status)


def _check_files_parallel(
    files: list[Path],
    repo_path: Path,
    results: list[CheckResult],
    progress: MultilineFileProgress,
    jobs: int,
    *,
    verbose: bool = False,
    flac_multichannel_check: bool = False,
) -> None:
    """Check files in parallel using ThreadPoolExecutor.

    Progress updates happen from the main thread as futures complete,
    ensuring thread-safe interaction with Rich.

    On KeyboardInterrupt, cancels pending futures and shuts down the
    executor so no new checker processes are spawned.
    """
    executor = ThreadPoolExecutor(max_workers=jobs)
    try:
        # Submit all files for checking
        future_to_file = {
            executor.submit(
                check_file,
                file_path,
                repo_path,
                flac_multichannel_check=flac_multichannel_check,
            ): file_path
            for file_path in files
        }

        # Process results as they complete
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]

            try:
                result = future.result()
                results.append(result)

                if verbose:
                    rel_path = file_path.relative_to(repo_path)
                    output_verbose(f"Checked: {rel_path} -> {result.status}")

                # Update progress (called from main thread)
                success = result.status in ("ok", "warning")
                message = ""
                if result.status == "warning" and result.warnings:
                    message = result.warnings[0].output[:80].replace("\n", " ")
                elif not success and result.errors:
                    # Show first error message (truncated)
                    message = result.errors[0].output[:80].replace("\n", " ")

                progress.complete_file(
                    file_path,
                    success=success,
                    message=message,
                    status=result.status,
                )

            except Exception as e:
                # Handle unexpected errors in worker thread
                rel_path = str(file_path.relative_to(repo_path))
                results.append(
                    CheckResult(
                        file=rel_path,
                        status="error",
                        tools=[],
                        errors=[],
                    )
                )
                progress.complete_file(
                    file_path,
                    success=False,
                    message=str(e)[:80],
                    status="error",
                )
    except KeyboardInterrupt:
        # Cancel all pending futures so no new checker processes start
        for future in future_to_file:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        executor.shutdown(wait=True)


def _show_check_summary(repo_path: Path, results: list[CheckResult], report: CheckReport) -> None:
    """Show check results summary table."""
    console.print()

    # Create summary table
    table = create_table(title="Check Summary")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Details")

    summary = report.summary

    if summary["ok"] > 0:
        table.add_row(
            "[success]OK[/success]",
            str(summary["ok"]),
            "No errors detected",
        )

    if summary.get("warning", 0) > 0:
        table.add_row(
            "[yellow]Warning[/yellow]",
            str(summary["warning"]),
            "Passed with compatibility warnings",
        )

    if summary["error"] > 0:
        table.add_row(
            "[error]Error[/error]",
            str(summary["error"]),
            "Integrity check failed",
        )

    if summary["not_present"] > 0:
        table.add_row(
            "[info]Not Present[/info]",
            str(summary["not_present"]),
            "Files not available locally",
        )

    if summary["checker_missing"] > 0:
        table.add_row(
            "[warning]Checker Missing[/warning]",
            str(summary["checker_missing"]),
            "Required checker tools not found",
        )

    if summary.get("skipped", 0) > 0:
        table.add_row(
            "[dim]Skipped[/dim]",
            str(summary["skipped"]),
            "Non-audio files",
        )

    console.print(table)

    # Show first N failed files with error details
    failed_results = [r for r in results if r.status == "error"]
    if failed_results:
        console.print("\n[error]Failed files:[/error]")
        for result in failed_results[:10]:  # Show first 10
            console.print(f"  [path]{result.file}[/path]")
            for tool_result in result.errors:
                # Show first line of error output
                first_line = tool_result.output.split("\n")[0][:100]
                console.print(f"    [{tool_result.tool}] {first_line}")

        if len(failed_results) > 10:
            console.print(f"  [dim]... and {len(failed_results) - 10} more failures[/dim]")

    # Show first N warned files with warning details
    warned_results = [r for r in results if r.status == "warning"]
    if warned_results:
        console.print("\n[yellow]Files with warnings:[/yellow]")
        for result in warned_results[:10]:
            console.print(f"  [path]{result.file}[/path]")
            for warn_result in result.warnings:
                first_line = warn_result.output.split("\n")[0][:100]
                console.print(f"    [{warn_result.tool}] {first_line}")

        if len(warned_results) > 10:
            console.print(f"  [dim]... and {len(warned_results) - 10} more warnings[/dim]")

    console.print()

    # Final status message
    if summary["error"] == 0:
        ok_count = summary["ok"] + summary.get("warning", 0)
        if summary.get("warning", 0) > 0:
            success(
                f"All {ok_count} files passed integrity checks ({summary['warning']} with warnings)"
            )
        else:
            success(f"All {ok_count} files passed integrity checks")
    else:
        warning(f"{summary['error']} of {summary['total']} files failed integrity checks")
