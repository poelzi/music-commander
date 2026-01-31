"""Export audio files in a specified format."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click

from music_commander.cli import Context, pass_context
from music_commander.commands.files import (
    EXIT_PARTIAL_FAILURE,
    cli,
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
    probe_tags,
    write_export_report,
)
from music_commander.utils.git import is_annex_present
from music_commander.utils.output import (
    MultilineFileProgress,
    console,
    create_table,
    error,
    info,
    warning,
)
from music_commander.utils.output import (
    verbose as output_verbose,
)
from music_commander.utils.search_ops import resolve_args_to_files
from music_commander.view.symlinks import _make_unique_path, sanitize_rendered_path
from music_commander.view.template import TemplateRenderError, render_path


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

    # Separate present vs not-present files
    present_files: list[Path] = []
    not_present_files: list[Path] = []
    for file_path in file_paths:
        if is_annex_present(file_path):
            present_files.append(file_path)
        else:
            not_present_files.append(file_path)

    # Render output paths using tags from source files
    file_pairs: list[tuple[Path, Path]] = []
    used_paths: set[str] = set()

    for file_path in present_files:
        # Read tags directly from the source file
        tags = probe_tags(file_path)
        if not tags:
            if verbose:
                warning(f"No tags for {file_path}, skipping")
            continue

        # Map ffprobe tag names to template variables
        metadata = {
            "artist": tags.get("artist"),
            "title": tags.get("title"),
            "album": tags.get("album"),
            "genre": tags.get("genre"),
            "bpm": tags.get("bpm") or tags.get("tbpm"),
            "rating": tags.get("rating"),
            "key": tags.get("key") or tags.get("initialkey") or tags.get("initial_key"),
            "year": tags.get("date") or tags.get("year"),
            "tracknumber": tags.get("track") or tags.get("tracknumber"),
            "comment": tags.get("comment"),
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

    if not file_pairs and not not_present_files:
        info("No files matched with metadata")
        return

    if not ctx.quiet:
        msg = f"Matched {len(file_pairs)} files for export"
        if not_present_files:
            msg += f" ({len(not_present_files)} not present)"
        info(msg)

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

    # Add not-present results upfront
    for file_path in not_present_files:
        rel_source = str(file_path.relative_to(repo_path))
        results.append(
            ExportResult(
                source=rel_source,
                output="",
                status="not_present",
                preset=preset.name,
                action="skipped",
                duration_seconds=0.0,
            )
        )

    start_time = time.time()
    total = len(file_pairs) + len(not_present_files)

    try:
        with MultilineFileProgress(total=total, operation="Exporting") as progress:
            # Show not-present files as skipped
            for file_path in not_present_files:
                progress.start_file(file_path)
                progress.complete_file(file_path, success=True, message="missing", status="skipped")
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
