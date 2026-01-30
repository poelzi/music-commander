"""Search-based file operations for git-annex.

This module provides DRY (Don't Repeat Yourself) abstractions for
performing git-annex operations on files matching a search query.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from music_commander.cache.builder import refresh_cache
from music_commander.cache.session import get_cache_session
from music_commander.config import Config
from music_commander.search.parser import SearchParseError, parse_query
from music_commander.search.query import execute_search
from music_commander.utils.git import FetchResult
from music_commander.utils.output import console, error, info, success, warning

if TYPE_CHECKING:
    from music_commander.cli import Context


@dataclass
class FileOperationResult:
    """Result of a file operation on search results."""

    processed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of files requested."""
        return len(self.processed) + len(self.skipped) + len(self.failed)

    @property
    def success(self) -> bool:
        """True if no files failed."""
        return len(self.failed) == 0


def execute_search_files(
    ctx: "Context",
    query: tuple[str, ...],
    config: Config,
    operation: str,
    verbose: bool = False,
    dry_run: bool = False,
    require_present: bool = True,
) -> list[Path] | None:
    """Execute a search query and return matching file paths.

    This is a DRY helper that handles the common search logic used by
    both 'files drop' and 'files get' commands.

    Args:
        ctx: CLI context with configuration.
        query: Search query tuple (joined with spaces).
        config: Application configuration.
        operation: Name of the operation (for error messages).
        verbose: If True, show detailed progress output.
        dry_run: If True, this is a dry run (affects output messages).
        require_present: If True, only return files that exist locally.
                        If False, return all files matching the query.

    Returns:
        List of file paths to operate on, or None if an error occurred.
    """
    repo_path = config.music_repo
    if not repo_path.exists():
        error(f"Music repository not found: {repo_path}")
        return None

    # Join query arguments into single string
    query_string = " ".join(query)

    if verbose or not ctx.quiet:
        info(f"Searching: {query_string}")

    # Parse the query
    try:
        parsed = parse_query(query_string)
    except SearchParseError as e:
        error(f"Invalid search query: {e}")
        return None

    # Execute search via cache
    try:
        with get_cache_session(repo_path) as session:
            # Auto-refresh cache
            if verbose or not ctx.quiet:
                info("Checking cache...")

            result = refresh_cache(repo_path, session)
            if result is not None and result > 0:
                info(f"Cache refreshed: {result} tracks updated")
            elif verbose:
                info("Cache is up to date")

            # Execute search
            if verbose:
                info("Executing search...")

            tracks = execute_search(session, parsed)

            if not tracks:
                info(f"No results for: {query_string}")
                return []

            if verbose or not ctx.quiet:
                info(f"Found {len(tracks)} tracks matching query")

            # Convert tracks to file paths
            file_paths = []
            missing_files = 0
            path_errors = 0
            for track in tracks:
                if track.file:
                    # The cache stores relative paths - resolve against repo_path
                    file_path = repo_path / track.file

                    # Verify the resolved path is actually under repo_path
                    # (sanity check in case cache has weird absolute paths)
                    try:
                        file_path.relative_to(repo_path)
                    except ValueError:
                        # File would be outside the repository - skip it
                        path_errors += 1
                        if verbose:
                            console.print(f"  [dim]{track.file} (outside repository, skipping)[/dim]")
                        continue

                    is_present = file_path.exists() or file_path.is_symlink()

                    # For operations like 'get', include all files (even if not present)
                    # For operations like 'drop', only include present files
                    if not require_present or is_present:
                        file_paths.append(file_path)
                        if verbose:
                            rel_path = file_path.relative_to(repo_path)
                            status = " (present)" if is_present else " (not present)"
                            console.print(f"  [path]{rel_path}[/path][dim]{status}[/dim]")
                    else:
                        missing_files += 1
                        if verbose:
                            console.print(f"  [dim]{track.file} (not present, skipping)[/dim]")

            if path_errors > 0 and (verbose or not ctx.quiet):
                warning(f"Skipped {path_errors} files outside repository")

            if require_present and missing_files > 0 and (verbose or not ctx.quiet):
                info(f"Skipped {missing_files} files not present in repository")

            if verbose or not ctx.quiet:
                info(f"Found {len(file_paths)} valid files to {operation.lower()}")

            return file_paths

    except subprocess.CalledProcessError as e:
        if "git-annex" in (e.stderr or ""):
            error("No git-annex branch found. Is this a git-annex repository?")
        else:
            error(f"Git command failed: {e}")
        return None
    except Exception as e:
        error(f"Cache error: {e}")
        return None


def show_operation_summary(
    repo_path: Path,
    result: FileOperationResult,
    operation_name: str,
) -> None:
    """Show a summary table of file operation results.

    Args:
        repo_path: Git repository path.
        result: FileOperationResult with operation outcomes.
        operation_name: Name of the operation (e.g., "Drop", "Fetch").
    """
    from music_commander.utils.output import create_table

    console.print()

    # Create summary table
    table = create_table(title=f"{operation_name} Summary")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Details")

    if result.processed:
        table.add_row(
            f"[success]{operation_name}ed[/success]",
            str(len(result.processed)),
            f"Successfully {operation_name.lower()}ed",
        )

    if result.skipped:
        table.add_row(
            "[info]Skipped[/info]",
            str(len(result.skipped)),
            "Not present or already done",
        )

    if result.failed:
        table.add_row(
            "[error]Failed[/error]",
            str(len(result.failed)),
            "Could not process",
        )

    console.print(table)

    # Show failed files with reasons
    if result.failed:
        console.print(f"\n[error]Failed files:[/error]")
        for file_path, reason in result.failed[:10]:  # Show first 10
            try:
                rel_path = file_path.relative_to(repo_path)
                console.print(f"  [path]{rel_path}[/path]")
            except ValueError:
                # File is not under repo_path, show full path
                console.print(f"  [path]{file_path}[/path]")
            console.print(f"    [dim]{reason}[/dim]")
        if len(result.failed) > 10:
            warning(f"... and {len(result.failed) - 10} more failures")

    console.print()

    # Final status message
    if result.success:
        success(f"All {result.total} files processed successfully")
    else:
        warning(f"{len(result.failed)} of {result.total} files failed")
