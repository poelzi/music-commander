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
                            console.print(
                                f"  [dim]{track.file} (outside repository, skipping)[/dim]"
                            )
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


def _list_all_annexed_files(
    config: Config,
    verbose: bool = False,
) -> list[Path] | None:
    """List all annexed files in the repository.

    Uses git-annex find to list all files managed by git-annex,
    regardless of whether they are present locally.

    Args:
        config: Application configuration.
        verbose: If True, show progress output.

    Returns:
        List of all annexed file paths, or None on error.
    """
    repo_path = config.music_repo

    if verbose:
        info("Listing all annexed files...")

    try:
        proc = subprocess.run(
            ["git", "annex", "find", "--include", "*"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        # Parse output: one file path per line
        file_paths = []
        for line in proc.stdout.strip().split("\n"):
            if line:
                file_path = repo_path / line
                # Validate path is under repo
                try:
                    file_path.relative_to(repo_path)
                    file_paths.append(file_path)
                except ValueError:
                    if verbose:
                        warning(f"Skipping file outside repository: {line}")
                    continue

        if verbose:
            info(f"Found {len(file_paths)} annexed files")

        return file_paths

    except subprocess.CalledProcessError as e:
        error(f"Failed to list annexed files: {e.stderr if e.stderr else str(e)}")
        return None
    except Exception as e:
        error(f"Error listing annexed files: {e}")
        return None


def _scan_directory_files(
    dir_path: Path,
    repo_path: Path,
    verbose: bool = False,
) -> list[Path]:
    """Recursively find all files in a directory.

    Args:
        dir_path: Directory to scan.
        repo_path: Repository root path (for validation).
        verbose: If True, show progress output.

    Returns:
        List of file paths found in directory.
    """
    file_paths = []

    try:
        # Use rglob to recursively find all files
        for item in dir_path.rglob("*"):
            # Only include regular files
            if item.is_file():
                # Validate path is under repo
                try:
                    item.relative_to(repo_path)
                    file_paths.append(item)
                except ValueError:
                    if verbose:
                        warning(f"Skipping file outside repository: {item}")
                    continue

        if verbose:
            info(f"Found {len(file_paths)} files in directory: {dir_path}")

    except (OSError, PermissionError) as e:
        if verbose:
            warning(f"Error scanning directory {dir_path}: {e}")

    return file_paths


def resolve_args_to_files(
    ctx: "Context",
    args: tuple[str, ...],
    config: Config,
    *,
    require_present: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
) -> list[Path] | None:
    """Resolve CLI arguments to file paths.

    Auto-detects whether arguments are file/directory paths or search terms.
    Paths take precedence over search terms when ambiguous.

    Args:
        ctx: CLI context with configuration.
        args: Positional arguments from command line.
        config: Application configuration.
        require_present: If True, only return files that exist locally.
        verbose: If True, show detailed progress output.
        dry_run: If True, this is a dry run (affects output messages).

    Returns:
        List of resolved file paths, or None if an error occurred.
    """
    repo_path = config.music_repo

    # Handle empty args: list all annexed files
    if not args:
        if verbose or not ctx.quiet:
            info("No arguments provided, checking all annexed files...")
        return _list_all_annexed_files(config, verbose=verbose)

    # Classify arguments as paths or query terms
    path_args: list[Path] = []
    query_args: list[str] = []

    for arg in args:
        # Try to resolve as path (check CWD first, then repo root)
        resolved_path: Path | None = None

        # Check relative to CWD
        cwd_path = Path.cwd() / arg
        if cwd_path.exists():
            resolved_path = cwd_path.resolve()

        # Check relative to repo root
        if not resolved_path:
            repo_rel_path = repo_path / arg
            if repo_rel_path.exists():
                resolved_path = repo_rel_path.resolve()

        # Check if arg itself is an absolute path
        if not resolved_path:
            abs_path = Path(arg)
            if abs_path.is_absolute() and abs_path.exists():
                resolved_path = abs_path

        if resolved_path:
            # Validate path is under repo
            try:
                resolved_path.relative_to(repo_path)
                path_args.append(resolved_path)
                if verbose:
                    info(f"Resolved path: {arg} -> {resolved_path}")
            except ValueError:
                # Path exists but is outside repo - treat as query term
                query_args.append(arg)
                if verbose:
                    info(f"Path outside repository, treating as query: {arg}")
        else:
            # Not a valid path, treat as query term
            query_args.append(arg)
            if verbose:
                info(f"Treating as query term: {arg}")

    # Collect files from paths
    all_files: list[Path] = []
    seen_paths: set[Path] = set()

    for path in path_args:
        if path.is_file():
            # Single file
            if path not in seen_paths:
                all_files.append(path)
                seen_paths.add(path)
        elif path.is_dir():
            # Directory - scan recursively
            dir_files = _scan_directory_files(path, repo_path, verbose=verbose)
            for f in dir_files:
                if f not in seen_paths:
                    all_files.append(f)
                    seen_paths.add(f)

    # Execute search for query terms
    if query_args:
        query_tuple = tuple(query_args)
        search_files = execute_search_files(
            ctx=ctx,
            query=query_tuple,
            config=config,
            operation="check",
            verbose=verbose,
            dry_run=dry_run,
            require_present=require_present,
        )

        if search_files is None:
            return None  # Error occurred in search

        # Merge search results
        for f in search_files:
            if f not in seen_paths:
                all_files.append(f)
                seen_paths.add(f)

    # Filter by presence if required
    if require_present:
        filtered_files = []
        for f in all_files:
            # Check if file is present (exists or is a valid symlink)
            is_present = f.exists() or f.is_symlink()
            if is_present:
                filtered_files.append(f)
            elif verbose:
                rel_path = f.relative_to(repo_path)
                console.print(f"  [dim]{rel_path} (not present, skipping)[/dim]")

        all_files = filtered_files

    if verbose or not ctx.quiet:
        info(f"Resolved {len(all_files)} files from arguments")

    return all_files


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
