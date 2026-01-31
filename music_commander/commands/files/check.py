"""Check integrity of audio files using format-specific tools."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click

from music_commander.cli import Context, pass_context
from music_commander.commands.files import (
    _DRY_RUN_OPTION,
    _JOBS_OPTION,
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
from music_commander.utils.git import (
    check_git_annex_repo,
    filter_annexed_files,
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
from music_commander.utils.search_ops import resolve_args_to_files


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
