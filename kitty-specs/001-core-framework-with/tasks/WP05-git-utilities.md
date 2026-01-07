---
work_package_id: "WP05"
subtasks:
  - "T015"
  - "T016"
  - "T017"
title: "Git Utilities"
phase: "Phase 2 - Core Components"
lane: "done"
assignee: ""
agent: "claude-reviewer"
shell_pid: "1312373"
review_status: "approved without changes"
reviewed_by: "claude-reviewer"
history:
  - timestamp: "2026-01-06"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP05 – Git Utilities

## Objectives & Success Criteria

- Parse git revisions (commits, ranges, branches, tags)
- Detect annexed files vs regular git files
- Execute `git annex get` with Rich progress bars
- Handle errors gracefully (missing git-annex, invalid revisions)
- Support all revision types per FR-019a/b/c

## Context & Constraints

**Constitution Requirements**:
- MUST handle git-annex operations correctly (get, drop, sync)
- MUST handle large file counts efficiently (10,000+ tracks)

**Reference Documents**:
- `kitty-specs/001-core-framework-with/spec.md` - FR-018 through FR-026
- `kitty-specs/001-core-framework-with/research.md` - Git integration patterns
- `kitty-specs/001-core-framework-with/contracts/cli-interface.md` - Exit codes

**Dependencies**: WP04 must be complete (utils/output.py for progress bars)

## Subtasks & Detailed Guidance

### Subtask T015 – Create utils/git.py with revision parsing

**Purpose**: Parse git revisions and get changed files.

**File**: `music_commander/utils/git.py`

**Implementation**:
```python
"""Git and git-annex utilities."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from music_commander.exceptions import (
    AnnexGetError,
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
        return len(self.fetched) + len(self.already_present) + len(self.failed)
    
    @property
    def success(self) -> bool:
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
        else:
            # Extract error reason
            reason = proc.stderr.strip() or "Unknown error"
            result.failed.append((file_path, reason))
    
    return result
```

**Parallel**: Can proceed alongside T016, T017 (they're all in the same file).

### Subtask T016 – Implement annexed file detection

**Purpose**: Already included in T015 (`is_annexed()`, `is_annex_present()`, `filter_annexed_files()`).

**Notes**: This is implemented as part of T015. The functions `is_annexed()`, `is_annex_present()`, and `filter_annexed_files()` handle this requirement.

### Subtask T017 – Implement git-annex get with progress

**Purpose**: Enhanced version of `annex_get_files()` with Rich progress integration.

**Additional Implementation** (add to utils/git.py):
```python
def annex_get_files_with_progress(
    repo_path: Path,
    files: list[Path],
    *,
    remote: str | None = None,
) -> FetchResult:
    """Fetch annexed files with Rich progress display.
    
    Args:
        repo_path: Git repository path.
        files: List of files to fetch.
        remote: Preferred remote (optional).
        
    Returns:
        FetchResult with fetched, already_present, and failed lists.
    """
    from music_commander.utils.output import console, create_progress
    
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
    
    with create_progress() as progress:
        task = progress.add_task(
            f"Fetching {len(to_fetch)} files...",
            total=len(to_fetch),
        )
        
        for file_path in to_fetch:
            # Update description
            rel_path = file_path.relative_to(repo_path)
            progress.update(task, description=f"[cyan]{rel_path.name}[/cyan]")
            
            # Build command
            cmd = ["git", "annex", "get", "--json-progress"]
            if remote:
                cmd.extend(["--from", remote])
            cmd.append(str(rel_path))
            
            # Execute
            proc = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            
            if proc.returncode == 0:
                result.fetched.append(file_path)
            else:
                reason = proc.stderr.strip() or "Unknown error"
                result.failed.append((file_path, reason))
            
            progress.advance(task)
    
    return result
```

## Definition of Done Checklist

- [ ] T015: Revision parsing for commits, ranges, branches, tags
- [ ] T016: `is_annexed()` correctly detects annexed files
- [ ] T017: Progress bars show during fetch
- [ ] All functions have proper type hints
- [ ] InvalidRevisionError raised for bad revisions
- [ ] NotGitAnnexRepoError raised when not in git-annex repo
- [ ] FetchResult correctly categorizes files
- [ ] `mypy music_commander/utils/` passes
- [ ] `ruff check music_commander/utils/` passes

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| git-annex not installed | Check in `check_git_annex_repo()`, clear error |
| Large file lists slow | Process in batches if needed |
| Progress parsing unreliable | Use file count progress, not byte progress |

## Review Guidance

- Test with real git-annex repository
- Verify all revision types work (commit, range, branch, tag)
- Check progress display updates smoothly
- Ensure errors are clear and actionable

## Activity Log

- 2026-01-06 – system – lane=planned – Prompt created.
- 2026-01-07T11:27:25Z – claude-reviewer – shell_pid=1312373 – lane=done – Code review complete: Git utilities for revision parsing, annexed file detection, and git-annex get with progress verified. mypy/ruff pass.
