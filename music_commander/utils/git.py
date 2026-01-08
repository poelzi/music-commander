"""Git and git-annex utilities."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from music_commander.exceptions import (
    InvalidRevisionError,
    NotGitAnnexRepoError,
    NotGitRepoError,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class FetchResult:
    """Result of fetching annexed files."""

    fetched: list[Path] = field(default_factory=list)
    already_present: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)  # (path, reason)

    @property
    def total_requested(self) -> int:
        """Total number of files requested."""
        return len(self.fetched) + len(self.already_present) + len(self.failed)

    @property
    def success(self) -> bool:
        """True if no files failed."""
        return len(self.failed) == 0


def check_git_repo(repo_path: Path) -> None:
    """Verify path is a git repository.

    Args:
        repo_path: Path to check.

    Raises:
        NotGitRepoError: If not a git repository.
    """
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        raise NotGitRepoError(repo_path)


def check_git_annex_repo(repo_path: Path) -> None:
    """Verify path is a git-annex repository.

    Args:
        repo_path: Path to check.

    Raises:
        NotGitRepoError: If not a git repository.
        NotGitAnnexRepoError: If not initialized for git-annex.
    """
    check_git_repo(repo_path)

    # Check for git-annex initialization
    result = subprocess.run(
        ["git", "config", "--get", "annex.uuid"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise NotGitAnnexRepoError(repo_path)


def is_valid_revision(repo_path: Path, revision: str) -> bool:
    """Check if a revision specification is valid.

    Args:
        repo_path: Git repository path.
        revision: Revision to validate.

    Returns:
        True if revision is valid.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", revision],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def get_files_from_revision(
    repo_path: Path,
    revision: str,
) -> list[Path]:
    """Get all files changed in a revision specification.

    Handles:
    - Single commit (HEAD~1): files changed in that commit
    - Range (A..B): files changed across all commits
    - Branch name: files from commits unique to that branch
    - Tag: files changed in that tagged commit

    Args:
        repo_path: Git repository path.
        revision: Git revision specification.

    Returns:
        List of file paths that were changed.

    Raises:
        InvalidRevisionError: If revision is invalid.
    """
    repo_path = repo_path.resolve()

    # Determine revision type and get appropriate file list
    if ".." in revision:
        # Range: A..B
        files = _get_files_from_range(repo_path, revision)
    elif _is_branch_name(repo_path, revision):
        # Branch: get unique commits compared to HEAD
        files = _get_files_from_branch(repo_path, revision)
    else:
        # Single commit or tag
        files = _get_files_from_commit(repo_path, revision)

    # Convert to absolute paths
    return [repo_path / f for f in files]


def _get_files_from_commit(repo_path: Path, revision: str) -> list[str]:
    """Get files changed in a single commit."""
    # Validate revision
    if not is_valid_revision(repo_path, revision):
        raise InvalidRevisionError(revision)

    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", revision],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise InvalidRevisionError(revision)

    return [f for f in result.stdout.strip().split("\n") if f]


def _get_files_from_range(repo_path: Path, revision: str) -> list[str]:
    """Get files changed across a commit range."""
    result = subprocess.run(
        ["git", "diff", "--name-only", revision],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise InvalidRevisionError(revision)

    return [f for f in result.stdout.strip().split("\n") if f]


def _get_files_from_branch(repo_path: Path, branch: str) -> list[str]:
    """Get files from commits unique to a branch (not on HEAD)."""
    # Get commits unique to branch
    result = subprocess.run(
        ["git", "log", "--name-only", "--pretty=format:", branch, "--not", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise InvalidRevisionError(branch)

    # Deduplicate file list
    files = set()
    for line in result.stdout.strip().split("\n"):
        if line:
            files.add(line)

    return list(files)


def _is_branch_name(repo_path: Path, name: str) -> bool:
    """Check if name is a branch (not a commit hash or tag)."""
    # Check if it's a branch
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{name}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True

    # Check remote branch
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/remotes/origin/{name}"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def is_annexed(file_path: Path) -> bool:
    """Check if a file is managed by git-annex.

    Args:
        file_path: Path to check.

    Returns:
        True if file is a git-annex symlink.
    """
    if not file_path.is_symlink():
        return False

    try:
        target = file_path.resolve()
        return ".git/annex/objects" in str(target)
    except (OSError, ValueError):
        return False


def is_annex_present(file_path: Path) -> bool:
    """Check if annexed file content is present locally.

    Args:
        file_path: Path to annexed file.

    Returns:
        True if content is available locally.
    """
    if not is_annexed(file_path):
        return True  # Regular file, always "present"

    try:
        # If we can resolve and access the target, it's present
        target = file_path.resolve()
        return target.exists()
    except (OSError, ValueError):
        return False


def filter_annexed_files(files: list[Path]) -> list[Path]:
    """Filter list to only annexed files.

    Args:
        files: List of file paths.

    Returns:
        List of paths that are git-annex managed.
    """
    return [f for f in files if f.exists() and is_annexed(f)]


def annex_get_files(
    repo_path: Path,
    files: list[Path],
    *,
    remote: str | None = None,
    progress_callback: Callable[[Path, float], None] | None = None,
) -> FetchResult:
    """Fetch annexed files using git-annex get.

    Args:
        repo_path: Git repository path.
        files: List of files to fetch.
        remote: Preferred remote (optional).
        progress_callback: Called with (path, progress_percent) updates.

    Returns:
        FetchResult with fetched, already_present, and failed lists.
    """
    result = FetchResult()

    for file_path in files:
        # Check if already present
        if is_annex_present(file_path):
            result.already_present.append(file_path)
            continue

        # Build command
        cmd = ["git", "annex", "get"]
        if remote:
            cmd.extend(["--from", remote])
        cmd.append(str(file_path.relative_to(repo_path)))

        # Execute git-annex get
        proc = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
        )

        if proc.returncode == 0:
            result.fetched.append(file_path)
            if progress_callback:
                progress_callback(file_path, 100.0)
        else:
            # Extract error reason
            reason = proc.stderr.strip() or "Unknown error"
            result.failed.append((file_path, reason))

    return result


def annex_get_files_with_progress(
    repo_path: Path,
    files: list[Path],
    *,
    remote: str | None = None,
    jobs: int = 1,
    verbose: bool = False,
) -> FetchResult:
    """Fetch annexed files with Rich progress display.

    Args:
        repo_path: Git repository path.
        files: List of files to fetch.
        remote: Preferred remote (optional).
        jobs: Number of parallel fetch jobs (default 1).
        verbose: If True, print git annex commands and per-file status.

    Returns:
        FetchResult with fetched, already_present, and failed lists.
    """
    import json

    from music_commander.utils.output import console, create_progress, info

    result = FetchResult()

    # Separate already-present files
    to_fetch = []
    for file_path in files:
        if is_annex_present(file_path):
            result.already_present.append(file_path)
        else:
            to_fetch.append(file_path)

    if not to_fetch:
        return result

    # Build command - use batch mode with all files at once for parallel support
    cmd = ["git", "annex", "get", "--json-progress", f"-J{jobs}"]
    if remote:
        cmd.extend(["--from", remote])

    # Add all files to the command
    rel_paths = [str(f.relative_to(repo_path)) for f in to_fetch]
    cmd.extend(rel_paths)

    if verbose:
        info(f"Running: {' '.join(cmd[:6])}... ({len(rel_paths)} files)")

    # Track which files we've seen results for
    file_map = {str(f.relative_to(repo_path)): f for f in to_fetch}
    seen_files: set[str] = set()

    with create_progress() as progress:
        task = progress.add_task(
            "Fetching files...",
            total=len(to_fetch),
        )

        # Run git annex get with streaming JSON output
        proc = subprocess.Popen(
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Handle progress updates
            if "action" in data:
                action = data.get("action", {})
                file_key = action.get("file", "")

                if "success" in data:
                    # Final result for a file
                    if file_key and file_key not in seen_files:
                        seen_files.add(file_key)
                        full_path = file_map.get(file_key)

                        if full_path:
                            if data.get("success"):
                                result.fetched.append(full_path)
                                if verbose:
                                    console.print(f"  [success]✓[/success] {file_key}")
                            else:
                                reason = data.get("error-messages", ["Unknown error"])
                                reason_str = reason[0] if reason else "Unknown error"
                                result.failed.append((full_path, reason_str))
                                if verbose:
                                    console.print(f"  [error]✗[/error] {file_key}: {reason_str}")

                            progress.advance(task)

                elif file_key:
                    # Progress update - show current file
                    progress.update(task, description=f"[cyan]{file_key}[/cyan]")

        proc.wait()

        # Handle any files we didn't get JSON results for
        for rel_path, full_path in file_map.items():
            if rel_path not in seen_files:
                # Check if file is now present
                if is_annex_present(full_path):
                    result.fetched.append(full_path)
                    if verbose:
                        console.print(f"  [success]✓[/success] {rel_path}")
                else:
                    result.failed.append((full_path, "No response from git-annex"))
                    if verbose:
                        console.print(f"  [error]✗[/error] {rel_path}: No response")
                progress.advance(task)

    return result
