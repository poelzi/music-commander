"""Rich console output helpers for music-commander."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.theme import Theme

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import contextmanager


# Custom theme for music-commander
THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "path": "blue underline",
        "track.artist": "bold",
        "track.title": "italic",
        "progress.description": "bold blue",
    }
)

# Global console instances
console = Console(theme=THEME, stderr=False)
error_console = Console(theme=THEME, stderr=True)


def info(message: str) -> None:
    """Print an info message."""
    console.print(f"[info]{message}[/info]")


def warning(message: str) -> None:
    """Print a warning message to stderr."""
    error_console.print(f"[warning]Warning:[/warning] {message}")


def error(message: str, hint: str | None = None) -> None:
    """Print an error message to stderr.

    Args:
        message: The error message.
        hint: Optional hint for resolution.
    """
    error_console.print(f"[error]Error:[/error] {message}")
    if hint:
        error_console.print(f"  [info]Hint:[/info] {hint}")


def success(message: str) -> None:
    """Print a success message."""
    console.print(f"[success]{message}[/success]")


def create_progress() -> Progress:
    """Create a progress bar for file operations.

    Returns:
        Rich Progress instance configured for file downloads.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def create_table(title: str | None = None, **kwargs: object) -> Table:
    """Create a styled table.

    Args:
        title: Optional table title.
        **kwargs: Additional Table arguments.

    Returns:
        Rich Table instance.
    """
    return Table(title=title, **kwargs)


def print_track(
    artist: str | None,
    title: str | None,
    *,
    prefix: str = "",
) -> None:
    """Print a formatted track line.

    Args:
        artist: Track artist.
        title: Track title.
        prefix: Optional prefix (e.g., "[1/10]").
    """
    artist_str = artist or "Unknown Artist"
    title_str = title or "Unknown Title"

    if prefix:
        console.print(
            f"{prefix} [track.artist]{artist_str}[/track.artist] - [track.title]{title_str}[/track.title]"
        )
    else:
        console.print(
            f"[track.artist]{artist_str}[/track.artist] - [track.title]{title_str}[/track.title]"
        )


def print_path(path: str, prefix: str = "") -> None:
    """Print a path with styling.

    Args:
        path: File or directory path.
        prefix: Optional prefix.
    """
    if prefix:
        console.print(f"{prefix} [path]{path}[/path]")
    else:
        console.print(f"[path]{path}[/path]")
