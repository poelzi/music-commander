"""Secure file operations for sensitive data (credentials, config)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def secure_mkdir(path: Path) -> None:
    """Create directory with 0o700 permissions (owner-only access).

    If the directory already exists, its permissions are tightened to 0o700.
    Parent directories are created as needed.
    """
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def secure_atomic_write(path: Path, content: str) -> None:
    """Write content to *path* atomically with 0o600 permissions.

    Creates the parent directory with 0o700 if it doesn't exist.
    Uses a temporary file in the same directory and an atomic rename
    so readers never see a partially-written file.
    """
    secure_mkdir(path.parent)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise
