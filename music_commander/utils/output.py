"""Rich console output helpers for music-commander."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from typing import Any

# Module-level verbosity flags (set by cli.py after argument parsing)
_verbose_enabled: bool = False
_debug_enabled: bool = False

# Module-level pager setting (None = auto, True = forced, False = disabled)
_pager_mode: bool | None = None


def set_verbosity(*, verbose: bool = False, debug: bool = False) -> None:
    """Configure module-level verbosity flags.

    Called from the CLI entry point after argument parsing.
    """
    global _verbose_enabled, _debug_enabled
    _verbose_enabled = verbose or debug  # debug implies verbose
    _debug_enabled = debug


def is_verbose() -> bool:
    """Return whether verbose mode is enabled."""
    return _verbose_enabled


def set_color(enabled: bool) -> None:
    """Enable or disable color on both console instances."""
    console.no_color = not enabled
    error_console.no_color = not enabled


def set_pager(mode: bool | None) -> None:
    """Configure pager mode.

    Args:
        mode: True = always, False = never, None = auto (TTY + content > height).
    """
    global _pager_mode
    _pager_mode = mode


def _find_pager() -> list[str]:
    """Determine the pager command to use.

    Priority:
    1. $PAGER environment variable
    2. bat (with plain style)
    3. less (with ANSI color, horizontal scroll, quit-if-one-screen)
    """
    pager_env = os.environ.get("PAGER")
    if pager_env:
        return pager_env.split()

    return ["less", "-RFS"]


def pager_print(content: str, *, header_lines: int = 0) -> None:
    """Print content through a pager if appropriate.

    Uses auto-detection: pages only if stdout is a TTY and content
    exceeds the terminal height. Honors ``_pager_mode`` setting.

    Args:
        content: ANSI-formatted string to display.
        header_lines: Number of header lines to keep sticky (for less --header).
    """
    lines = content.count("\n")
    term_height = shutil.get_terminal_size().lines

    use_pager = _pager_mode
    if use_pager is None:
        # Auto: pager only when TTY and content overflows
        use_pager = sys.stdout.isatty() and lines > term_height

    if not use_pager:
        sys.stdout.write(content)
        sys.stdout.flush()
        return

    cmd = _find_pager()

    # Add sticky header support for less
    if cmd[0] == "less" and header_lines > 0:
        cmd.append(f"--header={header_lines}")

    try:
        env = os.environ.copy()
        env.setdefault("LESSCHARSET", "utf-8")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        proc.communicate(input=content)
    except (OSError, subprocess.SubprocessError):
        # Pager failed, fall back to direct output
        sys.stdout.write(content)
        sys.stdout.flush()


from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.theme import Theme

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


def verbose(message: str) -> None:
    """Print a message only when verbose mode is enabled."""
    if _verbose_enabled:
        console.print(f"[info]{message}[/info]")


def debug(message: str) -> None:
    """Print a debug message only when debug mode is enabled."""
    if _debug_enabled:
        error_console.print(f"[warning]\\[DEBUG][/warning] {message}")


def create_progress() -> Progress:
    """Create a progress bar for file operations.

    Returns:
        Rich Progress instance configured for file counts.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def create_table(title: str | None = None, **kwargs: Any) -> Table:
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
            f"{prefix} [track.artist]{artist_str}[/track.artist] - "
            f"[track.title]{title_str}[/track.title]"
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
