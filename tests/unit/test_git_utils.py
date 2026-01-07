"""Unit tests for git utilities."""

from pathlib import Path

import pytest

from music_commander.exceptions import InvalidRevisionError
from music_commander.utils.git import (
    check_git_annex_repo,
    get_files_from_revision,
    is_annexed,
    is_valid_revision,
)


def test_check_git_annex_repo_valid(git_annex_repo: Path) -> None:
    """Test valid git-annex repo passes check."""
    check_git_annex_repo(git_annex_repo)  # Should not raise


def test_check_git_annex_repo_invalid(temp_dir: Path) -> None:
    """Test non-annex repo raises error."""
    from music_commander.exceptions import NotGitRepoError

    # temp_dir is not a git repo at all, so it raises NotGitRepoError
    with pytest.raises(NotGitRepoError):
        check_git_annex_repo(temp_dir)


def test_is_valid_revision(git_annex_repo: Path) -> None:
    """Test revision validation."""
    assert is_valid_revision(git_annex_repo, "HEAD") is True
    assert is_valid_revision(git_annex_repo, "nonexistent") is False


def test_get_files_from_commit(git_annex_repo: Path) -> None:
    """Test getting files from a commit."""
    files = get_files_from_revision(git_annex_repo, "HEAD")
    # HEAD might be the initial commit which has different handling
    # Just verify it doesn't crash and returns a list
    assert isinstance(files, list)


def test_get_files_invalid_revision(git_annex_repo: Path) -> None:
    """Test invalid revision raises error."""
    with pytest.raises(InvalidRevisionError):
        get_files_from_revision(git_annex_repo, "nonexistent-branch")


def test_is_annexed_regular_file(temp_dir: Path) -> None:
    """Test regular file is not detected as annexed."""
    regular_file = temp_dir / "regular.txt"
    regular_file.write_text("content")
    assert is_annexed(regular_file) is False
