"""Get annexed files from git commits."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
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
    ToolResult,
    check_file,
    check_tool_available,
    get_checkers_for_extension,
    get_checkers_for_file,
    write_report,
)
from music_commander.utils.encoder import (
    EXTENSION_TO_PRESET,
    PRESETS,
    ExportReport,
    ExportResult,
    can_copy,
    export_file,
    find_cover_art,
    probe_source,
    write_export_report,
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
from music_commander.view.symlinks import _make_unique_path, sanitize_rendered_path
from music_commander.view.template import TemplateRenderError, render_path

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
@click.option(
    "--continue",
    "-c",
    "continue_check",
    is_flag=True,
    default=False,
    help="Continue from last report, skipping already-checked files",
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
    continue_check: bool,
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

    \b
      # Continue an interrupted check run
      music-commander files check --continue
    """
    import json
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

    # Determine report path early (needed for --continue)
    report_path = Path(output) if output else repo_path / ".music-commander-check-results.json"

    # Load previous results for --continue
    prev_results: list[dict] | None = None
    previously_checked: set[str] = set()
    if continue_check:
        if report_path.exists():
            try:
                prev_data = json.loads(report_path.read_text())
                prev_results = prev_data.get("results", [])
                for r in prev_results:
                    if r.get("status") in ("ok", "warning"):
                        previously_checked.add(r["file"])
                if not ctx.quiet:
                    info(f"Continuing: {len(previously_checked)} files already checked")
            except (json.JSONDecodeError, KeyError):
                warning(f"Could not read previous report: {report_path}")
        else:
            warning(f"No previous report found at {report_path}, checking all files")

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

    # Filter out already-checked files for --continue
    if previously_checked:
        filtered = []
        carried = 0
        for fp in to_check:
            rel = str(fp.relative_to(repo_path))
            if rel in previously_checked:
                carried += 1
            else:
                filtered.append(fp)
        to_check = filtered
        if not ctx.quiet and carried:
            info(f"Skipping {carried} already-checked files")

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

    # Inject carried-forward results from previous report (--continue)
    if prev_results:
        for r in prev_results:
            if r.get("status") in ("ok", "warning"):
                warnings = [
                    ToolResult(
                        tool=w.get("tool", ""),
                        success=w.get("success", True),
                        exit_code=w.get("exit_code", 0),
                        output=w.get("output", ""),
                    )
                    for w in r.get("warnings", [])
                ]
                results.append(
                    CheckResult(
                        file=r["file"],
                        status=r["status"],
                        tools=r.get("tools", []),
                        errors=[],
                        warnings=warnings,
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

            write_report(report, report_path)

            if not ctx.quiet:
                info(f"Report written to: {report_path}")

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
            message = result.warnings[0].output[:500]
        elif not success and result.errors:
            # Show first error message (truncated)
            message = result.errors[0].output[:500]

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
                    message = result.warnings[0].output[:500]
                elif not success and result.errors:
                    # Show first error message (truncated)
                    message = result.errors[0].output[:500]

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
                    message=str(e)[:500],
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


# Export command helpers


def _resolve_preset(format_preset: str | None, pattern: str):
    """Resolve format preset from explicit flag or template extension.

    Args:
        format_preset: Explicit preset name from --format flag (or None).
        pattern: Jinja2 template pattern string.

    Returns:
        FormatPreset instance.

    Raises:
        click.ClickException: If preset is invalid or cannot be inferred.
    """
    if format_preset:
        # Explicit format specified
        if format_preset not in PRESETS:
            valid = ", ".join(sorted(PRESETS.keys()))
            raise click.ClickException(
                f"Invalid format preset '{format_preset}'. Valid presets: {valid}"
            )

        preset = PRESETS[format_preset]

        # Check for extension conflict
        template_ext = _extract_template_extension(pattern)
        if template_ext and template_ext != preset.container:
            warning(
                f"Template extension '{template_ext}' differs from preset container "
                f"'{preset.container}'. Using template as-is."
            )

        return preset

    # Auto-detect from template extension
    template_ext = _extract_template_extension(pattern)
    if not template_ext:
        raise click.ClickException(
            "Cannot infer format from template (no file extension found). "
            "Use --format to specify a preset explicitly."
        )

    if template_ext not in EXTENSION_TO_PRESET:
        valid = ", ".join(sorted(EXTENSION_TO_PRESET.keys()))
        raise click.ClickException(
            f"Unrecognized template extension '{template_ext}'. "
            f"Valid extensions: {valid}, or use --format to specify explicitly."
        )

    preset_name = EXTENSION_TO_PRESET[template_ext]
    return PRESETS[preset_name]


def _extract_template_extension(pattern: str) -> str | None:
    """Extract file extension from template pattern.

    Args:
        pattern: Jinja2 template string.

    Returns:
        Extension including dot (e.g., ".mp3") or None if no extension found.
    """
    # Find the last segment after any }} or /
    segments = pattern.replace("}}", "|").replace("/", "|").split("|")
    last_segment = segments[-1].strip()

    # Check if it has an extension
    if "." in last_segment:
        return "." + last_segment.rsplit(".", 1)[-1].lower()

    return None


def _should_skip(source_path: Path, output_path: Path, force: bool) -> bool:
    """Determine if a file should be skipped (incremental mode).

    Args:
        source_path: Source file path.
        output_path: Output file path.
        force: If True, never skip (force re-export).

    Returns:
        True if the file should be skipped, False otherwise.
    """
    if force:
        return False

    if not output_path.exists():
        return False

    # Compare modification times
    try:
        source_mtime = source_path.stat().st_mtime
        output_mtime = output_path.stat().st_mtime
        # Re-export if source is newer
        return source_mtime <= output_mtime
    except OSError:
        # If we can't stat, assume we need to export
        return False


def _export_files_sequential(
    file_pairs: list[tuple[Path, Path]],
    preset,
    repo_path: Path,
    results: list[ExportResult],
    progress: MultilineFileProgress,
    *,
    verbose: bool = False,
    force: bool = False,
) -> None:
    """Export files sequentially with progress display.

    Args:
        file_pairs: List of (source_path, output_path) tuples.
        preset: FormatPreset instance.
        repo_path: Repository root path.
        results: Mutable list to append results to.
        progress: Progress display instance.
        verbose: If True, show verbose output.
        force: If True, re-export all files (ignore incremental).
    """
    for source_path, output_path in file_pairs:
        progress.start_file(source_path)

        # Check incremental skip
        if _should_skip(source_path, output_path, force):
            rel_source = str(source_path.relative_to(repo_path))
            result = ExportResult(
                source=rel_source,
                output=output_path.name,
                status="skipped",
                preset=preset.name,
                action="skipped",
                duration_seconds=0.0,
            )
            results.append(result)
            progress.complete_file(
                source_path, success=True, message="skipped", status="skipped", target=output_path
            )
            continue

        # Export the file
        result = export_file(source_path, output_path, preset, repo_path, verbose=verbose)
        results.append(result)

        # Update progress
        is_success = result.status in ("ok", "copied", "skipped")
        message = ""
        if not is_success and result.error_message:
            message = result.error_message[:500]

        progress.complete_file(
            source_path,
            success=is_success,
            message=message,
            status=result.status,
            target=output_path,
        )


def _export_files_parallel(
    file_pairs: list[tuple[Path, Path]],
    preset,
    repo_path: Path,
    results: list[ExportResult],
    progress: MultilineFileProgress,
    jobs: int,
    *,
    verbose: bool = False,
    force: bool = False,
) -> None:
    """Export files in parallel using ThreadPoolExecutor.

    Progress updates happen from the main thread as futures complete,
    ensuring thread-safe interaction with Rich.

    On KeyboardInterrupt, cancels pending futures and shuts down the
    executor so no new ffmpeg processes are spawned.

    Args:
        file_pairs: List of (source_path, output_path) tuples.
        preset: FormatPreset instance.
        repo_path: Repository root path.
        results: Mutable list to append results to.
        progress: Progress display instance.
        jobs: Number of parallel workers.
        verbose: If True, show verbose output.
        force: If True, re-export all files (ignore incremental).
    """

    def _export_worker(source_path: Path, output_path: Path):
        """Worker function for parallel export."""
        # Check incremental skip
        if _should_skip(source_path, output_path, force):
            rel_source = str(source_path.relative_to(repo_path))
            return ExportResult(
                source=rel_source,
                output=output_path.name,
                status="skipped",
                preset=preset.name,
                action="skipped",
                duration_seconds=0.0,
            )

        # Export the file
        return export_file(source_path, output_path, preset, repo_path, verbose=verbose)

    executor = ThreadPoolExecutor(max_workers=jobs)
    try:
        # Submit all files for export
        future_to_pair = {
            executor.submit(_export_worker, source_path, output_path): (source_path, output_path)
            for source_path, output_path in file_pairs
        }

        # Process results as they complete
        for future in as_completed(future_to_pair):
            source_path, output_path = future_to_pair[future]

            try:
                result = future.result()
                results.append(result)

                if verbose:
                    rel_path = source_path.relative_to(repo_path)
                    output_verbose(f"Exported: {rel_path} -> {result.status}")

                # Update progress (called from main thread)
                is_success = result.status in ("ok", "copied", "skipped")
                message = ""
                if not is_success and result.error_message:
                    message = result.error_message[:500]

                progress.complete_file(
                    source_path,
                    success=is_success,
                    message=message,
                    status=result.status,
                    target=output_path,
                )

            except Exception as e:
                # Handle unexpected errors in worker thread
                rel_source = str(source_path.relative_to(repo_path))
                results.append(
                    ExportResult(
                        source=rel_source,
                        output=output_path.name,
                        status="error",
                        preset=preset.name,
                        action="encode",
                        duration_seconds=0.0,
                        error_message=str(e),
                    )
                )
                progress.complete_file(
                    source_path,
                    success=False,
                    message=str(e)[:500],
                    status="error",
                    target=output_path,
                )
    except KeyboardInterrupt:
        # Cancel all pending futures so no new ffmpeg processes start
        for future in future_to_pair:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        executor.shutdown(wait=True)


def _show_export_summary(summary: dict, results: list[ExportResult]) -> None:
    """Display export summary with colored counts.

    Args:
        summary: Summary dict with counts.
        results: List of ExportResult instances.
    """
    # Create summary table
    table = create_table("Export Summary")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Description")

    if summary["ok"] > 0:
        table.add_row("[green]OK (Encoded)[/green]", str(summary["ok"]), "Successfully encoded")

    if summary["copied"] > 0:
        table.add_row("[cyan]Copied[/cyan]", str(summary["copied"]), "Copied without re-encoding")

    if summary["skipped"] > 0:
        table.add_row("[dim]Skipped[/dim]", str(summary["skipped"]), "Already exported")

    if summary["error"] > 0:
        table.add_row("[red]Error[/red]", str(summary["error"]), "Export failed")

    if summary["not_present"] > 0:
        table.add_row(
            "[dim]Not Present[/dim]", str(summary["not_present"]), "Source not locally available"
        )

    console.print(table)
    console.print()

    # Show failed files
    failed_results = [r for r in results if r.status == "error"]
    if failed_results:
        console.print("[red]Failed files:[/red]")
        for result in failed_results[:10]:
            console.print(f"  [path]{result.source}[/path]")
            if result.error_message:
                console.print(f"    [dim]{result.error_message[:100]}[/dim]")
        if len(failed_results) > 10:
            console.print(f"  [dim]... and {len(failed_results) - 10} more[/dim]")
        console.print()


@cli.command("export")
@click.argument("args", nargs=-1)
@click.option(
    "--format",
    "-f",
    "format_preset",
    default=None,
    help="Format preset (mp3-320, mp3-v0, flac, flac-pioneer, aiff, aiff-pioneer, wav, wav-pioneer)",
)
@click.option(
    "--pattern", "-p", required=True, help='Jinja2 path template, e.g. "{{ artist }}/{{ title }}"'
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(path_type=Path),
    help="Base output directory",
)
@click.option("--force", is_flag=True, default=False, help="Re-export all files (ignore existing)")
@click.option(
    "--dry-run", "-n", is_flag=True, default=False, help="Preview export without encoding"
)
@click.option("--jobs", "-j", default=1, type=int, help="Number of parallel export jobs")
@click.option(
    "--verbose", "-v", is_flag=True, default=False, help="Show ffmpeg commands and output"
)
@pass_context
def export(
    ctx: Context,
    args: tuple[str, ...],
    format_preset: str | None,
    pattern: str,
    output: Path,
    force: bool,
    dry_run: bool,
    jobs: int,
    verbose: bool,
) -> None:
    """Export audio files in a specified format.

    Export files matched by search query or paths, recoding them to the
    specified format using ffmpeg. Metadata and cover art are preserved.

    Examples:

        Export FLAC collection to MP3-320:
        $ music-cmd files export "genre:ambient" -p "{{ artist }}/{{ title }}.mp3" -o /mnt/usb

        Export with explicit format:
        $ music-cmd files export -p "{{ title }}" -o /tmp -f flac-pioneer "rating:>=4"
    """
    config = ctx.config
    repo_path = config.music_repo

    # Resolve preset
    try:
        preset = _resolve_preset(format_preset, pattern)
    except click.ClickException:
        raise

    if not ctx.quiet:
        info(f"Using preset: {preset.name}")

    # Resolve files
    file_paths = resolve_args_to_files(ctx, args, config, require_present=False, verbose=verbose)

    if file_paths is None:
        raise click.ClickException("Failed to resolve files")

    if not file_paths:
        info("No files to export")
        return

    # Load track metadata for template rendering
    from music_commander.cache.models import CacheTrack
    from music_commander.cache.session import get_cache_session

    # Eagerly load all attributes into dicts while session is open
    # (CacheTrack ORM instances become detached after session closes)
    track_metadata_by_file: dict[Path, dict] = {}
    with get_cache_session(repo_path) as session:
        for t in session.query(CacheTrack).all():
            if t.file:
                track_metadata_by_file[repo_path / t.file] = {
                    "artist": t.artist,
                    "title": t.title,
                    "album": t.album,
                    "genre": t.genre,
                    "bpm": t.bpm,
                    "rating": t.rating,
                    "key": t.key_musical,
                    "year": t.year,
                    "tracknumber": t.tracknumber,
                    "comment": t.comment,
                }

    # Render output paths
    file_pairs: list[tuple[Path, Path]] = []
    used_paths: set[str] = set()

    for file_path in file_paths:
        # Get track metadata
        track_meta = track_metadata_by_file.get(file_path)
        if not track_meta:
            if verbose:
                warning(f"No metadata for {file_path}, skipping")
            continue

        # Build template context
        metadata = {
            **track_meta,
            "file": str(file_path),
            "filename": file_path.stem,
            "ext": file_path.suffix,
        }

        # Render template
        try:
            rendered = render_path(pattern, metadata)
        except TemplateRenderError as e:
            error(f"Template error: {e}")
            raise click.ClickException(f"Template error: {e}")

        # Sanitize path
        rendered = sanitize_rendered_path(rendered)

        # Append preset container if no extension
        if not _extract_template_extension(pattern):
            rendered += preset.container

        # Deduplicate paths
        rendered = _make_unique_path(rendered, used_paths)

        # Compute full output path
        output_path = output / rendered

        file_pairs.append((file_path, output_path))

    if not file_pairs:
        info("No files matched with metadata")
        return

    if not ctx.quiet:
        info(f"Matched {len(file_pairs)} files for export")

    # Dry-run mode
    if dry_run:
        if not ctx.quiet:
            info("Dry-run mode: preview only, no files will be written")

        # Build preview table
        from rich.table import Table

        table = Table(title="Export Preview", show_header=True, header_style="bold")
        table.add_column("Source", style="cyan", no_wrap=False)
        table.add_column("Output", style="green", no_wrap=False)
        table.add_column("Action", style="yellow")
        table.add_column("Cover", style="magenta")

        action_counts = {"encode": 0, "copy": 0, "skip": 0, "error": 0}

        for source_path, output_path in file_pairs:
            # Determine action
            action = "encode"
            cover_status = "-"

            # Check if would skip
            if _should_skip(source_path, output_path, force):
                action = "skip"
            else:
                # Probe source to determine copy vs encode
                try:
                    source_info = probe_source(source_path)
                    if can_copy(source_info, preset):
                        action = "copy"

                    # Find cover art
                    cover_path = find_cover_art(source_path)
                    if source_info.has_cover_art:
                        cover_status = "embedded"
                    elif cover_path:
                        cover_status = cover_path.name
                except Exception as e:
                    action = "error"
                    cover_status = str(e)[:20]

            action_counts[action] += 1

            # Truncate paths for display
            rel_source = str(source_path.relative_to(repo_path))
            if len(rel_source) > 50:
                rel_source = "..." + rel_source[-47:]

            output_name = output_path.name
            if len(output_name) > 40:
                output_name = output_name[:37] + "..."

            table.add_row(rel_source, output_name, action, cover_status)

        console.print(table)
        console.print()

        # Show summary
        summary_table = create_table("Dry-Run Summary")
        summary_table.add_column("Action", style="bold")
        summary_table.add_column("Count", justify="right")
        if action_counts["encode"] > 0:
            summary_table.add_row("Would encode", str(action_counts["encode"]))
        if action_counts["copy"] > 0:
            summary_table.add_row("Would copy", str(action_counts["copy"]))
        if action_counts["skip"] > 0:
            summary_table.add_row("Would skip", str(action_counts["skip"]))
        if action_counts["error"] > 0:
            summary_table.add_row("Errors", str(action_counts["error"]))

        console.print(summary_table)
        return

    # Export files
    results: list[ExportResult] = []
    start_time = time.time()

    try:
        with MultilineFileProgress(total=len(file_pairs), operation="Exporting") as progress:
            # Use parallel or sequential export based on jobs
            if jobs > 1:
                _export_files_parallel(
                    file_pairs,
                    preset,
                    repo_path,
                    results,
                    progress,
                    jobs,
                    verbose=verbose,
                    force=force,
                )
            else:
                _export_files_sequential(
                    file_pairs,
                    preset,
                    repo_path,
                    results,
                    progress,
                    verbose=verbose,
                    force=force,
                )

            duration = time.time() - start_time

            # Build summary
            summary = {
                "total": len(results),
                "ok": sum(1 for r in results if r.status == "ok"),
                "copied": sum(1 for r in results if r.status == "copied"),
                "skipped": sum(1 for r in results if r.status == "skipped"),
                "error": sum(1 for r in results if r.status == "error"),
                "not_present": sum(1 for r in results if r.status == "not_present"),
            }

            # Create export report
            report = ExportReport(
                version=1,
                timestamp=datetime.now(timezone.utc).isoformat(),
                duration_seconds=duration,
                repository=str(repo_path),
                output_dir=str(output),
                preset=preset.name,
                arguments=list(args) if args else [],
                summary=summary,
                results=results,
            )

    except KeyboardInterrupt:
        # Build partial report
        duration = time.time() - start_time
        summary = {
            "total": len(results),
            "ok": sum(1 for r in results if r.status == "ok"),
            "copied": sum(1 for r in results if r.status == "copied"),
            "skipped": sum(1 for r in results if r.status == "skipped"),
            "error": sum(1 for r in results if r.status == "error"),
            "not_present": sum(1 for r in results if r.status == "not_present"),
        }

        report = ExportReport(
            version=1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            duration_seconds=duration,
            repository=str(repo_path),
            output_dir=str(output),
            preset=preset.name,
            arguments=list(args) if args else [],
            summary=summary,
            results=results,
        )

        # Write partial report
        report_path = output / ".music-commander-export-report.json"
        write_export_report(report, report_path)

        if not ctx.quiet:
            info(f"Interrupted. Partial report written to: {report_path}")

        raise

    finally:
        # Always write report
        if "report" in locals():
            report_path = output / ".music-commander-export-report.json"
            write_export_report(report, report_path)

            if not ctx.quiet and "summary" in locals():
                _show_export_summary(summary, results)
                info(f"Report written to: {report_path}")

    # Exit code
    if summary["error"] > 0:
        raise SystemExit(1)
