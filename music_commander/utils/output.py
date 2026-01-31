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


from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.progress import (
    Task as ProgressTask,
)
from rich.table import Table
from rich.text import Text
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


class SmoothTimeRemainingColumn(ProgressColumn):
    """Time remaining estimate using exponential moving average for stability.

    Rich's built-in TimeRemainingColumn uses a simple sliding window which
    produces jumpy estimates when file processing times vary. This uses EMA
    smoothing for a more stable display.
    """

    max_refresh = 0.5  # Limit refresh to 2x/sec like Rich's built-in

    def __init__(self, alpha: float = 0.3, **kwargs):
        super().__init__(**kwargs)
        self._ema_speed: float | None = None
        self._alpha = alpha  # Lower = smoother, higher = more responsive
        self._last_completed: float = 0
        self._last_elapsed: float | None = None

    def render(self, task: ProgressTask) -> Text:
        remaining = task.remaining
        if remaining is None:
            return Text("-:--:--", style="progress.remaining")
        if task.finished:
            return Text("0:00:00", style="progress.remaining")

        elapsed = task.elapsed
        if elapsed is None:
            return Text("-:--:--", style="progress.remaining")

        completed = task.completed

        # Update EMA speed estimate
        if self._last_elapsed is not None:
            dt = elapsed - self._last_elapsed
            dc = completed - self._last_completed
            if dt > 0.1 and dc > 0:
                instant_speed = dc / dt
                if self._ema_speed is None:
                    self._ema_speed = instant_speed
                else:
                    self._ema_speed = (
                        self._alpha * instant_speed + (1 - self._alpha) * self._ema_speed
                    )

        self._last_completed = completed
        self._last_elapsed = elapsed

        # Fall back to overall average if EMA not yet available
        speed = self._ema_speed
        if speed is None and elapsed > 0 and completed > 0:
            speed = completed / elapsed

        if speed and speed > 0:
            eta_seconds = int(remaining / speed)
            hours, remainder = divmod(eta_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                formatted = f"{minutes}:{seconds:02d}"
            return Text(formatted, style="progress.remaining")

        return Text("-:--:--", style="progress.remaining")


class MultilineFileProgress:
    """Multiline progress display for file operations.

    Shows permanently-printed completed/failed lines above a live region
    that contains in-flight file names and a progress bar:

        Fetched: file1
        Fetched: file2
        Fetching: currentfile      <- live (cleared on next update)
        Fetching: currentfile2     <- live
        [bar] 2/100 2% 0:00:05 4:57:16  <- live

    Usage:
        with MultilineFileProgress(total=100, operation="Fetching") as progress:
            for file_path in files:
                progress.start_file(file_path)
                # ... do work ...
                progress.complete_file(file_path, success=True)
    """

    def __init__(self, total: int, operation: str = "Processing"):
        """Initialize multiline progress display.

        Args:
            total: Total number of files to process.
            operation: Operation name (e.g., "Fetching", "Dropping").
        """
        self.total = total
        self.operation = operation
        # Derive past-tense label: "Fetching" -> "Fetched", "Dropping" -> "Dropped"
        self._completed_label = (
            operation[:-3] + "ed" if operation.endswith("ing") else operation + "ed"
        )
        self.current = 0
        self.current_file: Path | None = None
        self._progress: Progress | None = None
        self._task_id: int | None = None
        self._live: Live | None = None
        self._in_flight: list[Path] = []
        # Status counters for the progress bar
        self._ok_count = 0
        self._warning_count = 0
        self._error_count = 0
        self._skipped_count = 0

    def _build_status_line(self) -> str:
        """Build a colored status counter string for the progress display."""
        parts: list[str] = []
        if self._ok_count > 0:
            parts.append(f"[success]OK:{self._ok_count}[/success]")
        if self._warning_count > 0:
            parts.append(f"[yellow]Warn:{self._warning_count}[/yellow]")
        if self._error_count > 0:
            parts.append(f"[error]Err:{self._error_count}[/error]")
        if self._skipped_count > 0:
            parts.append(f"[dim]Skip:{self._skipped_count}[/dim]")
        return " ".join(parts)

    def _build_renderable(self) -> Group:
        """Build the live-region renderable: in-flight lines + progress bar."""
        parts: list = []
        for fp in self._in_flight:
            parts.append(console.render_str(f"  {self.operation}: [path]{fp}[/path]"))
        if self._progress:
            parts.append(self._progress)
        status_line = self._build_status_line()
        if status_line:
            parts.append(console.render_str(f"  {status_line}"))
        return Group(*parts)

    def __enter__(self):
        """Enter context - start Live display with progress bar."""
        self._progress = Progress(
            SpinnerColumn(),
            BarColumn(bar_width=40, complete_style="green", finished_style="bold green"),
            MofNCompleteColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            SmoothTimeRemainingColumn(),
        )
        self._task_id = self._progress.add_task(self.operation, total=self.total)
        self._live = Live(
            self._build_renderable(),
            console=console,
            refresh_per_second=10,
        )
        self._live.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - stop Live display."""
        if self._live:
            self._live.__exit__(exc_type, exc_val, exc_tb)
            self._live = None
        self._progress = None
        return False

    def _refresh(self) -> None:
        """Update the live display with current in-flight files and progress."""
        if self._live:
            self._live.update(self._build_renderable())

    def start_file(self, file_path: Path) -> None:
        """Mark a file as in-flight (shown in the live region).

        Args:
            file_path: Path to the file being processed.
        """
        self.current_file = file_path
        if file_path not in self._in_flight:
            self._in_flight.append(file_path)
        self._refresh()

    def complete_file(
        self,
        file_path: Path,
        success: bool = True,
        message: str = "",
        status: str = "",
        target: Path | str | None = None,
    ) -> None:
        """Mark a file as completed.

        Removes it from the live in-flight list and prints a permanent
        line above the live region.

        Args:
            file_path: Path to the completed file.
            success: Whether the operation succeeded.
            message: Optional status message (e.g., "already present").
            status: Result status for counter tracking ("ok", "warning", "error").
                If empty, inferred from *success*.
            target: Optional target/output path to show on a second line.
        """
        # Update status counters
        effective_status = status or ("ok" if success else "error")
        if effective_status in ("ok", "copied"):
            self._ok_count += 1
        elif effective_status == "warning":
            self._warning_count += 1
        elif effective_status == "error":
            self._error_count += 1
        elif effective_status == "skipped":
            self._skipped_count += 1
        self.current += 1

        # Remove from in-flight
        if file_path in self._in_flight:
            self._in_flight.remove(file_path)

        # Print permanent line above the live region
        if self._live:
            if effective_status == "skipped" and message:
                self._live.console.print(
                    f"  [dim]Skipped({message}): [path]{file_path}[/path][/dim]"
                )
            elif success:
                self._live.console.print(f"  {self._completed_label}: [path]{file_path}[/path]")
            else:
                self._live.console.print(f"  Failed: [path]{file_path}[/path]")
                if message:
                    # Show error as indented block, up to 4 lines
                    lines = message.strip().splitlines()[:4]
                    for line in lines:
                        self._live.console.print(f"    [dim]{line.rstrip()[:120]}[/dim]")
            if target is not None:
                self._live.console.print(f"   -> [path]{target}[/path]")

        # Update progress bar
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, advance=1)

        self.current_file = None
        self._refresh()

    def skip_file(self, file_path: Path, reason: str = "") -> None:
        """Mark a file as skipped.

        Args:
            file_path: Path to the skipped file.
            reason: Reason for skipping.
        """
        self.current += 1

        # Remove from in-flight
        if file_path in self._in_flight:
            self._in_flight.remove(file_path)

        # Print permanent line above the live region
        if self._live:
            msg = f"  Skipped: [path]{file_path}[/path]"
            if reason:
                msg += f" [dim]({reason})[/dim]"
            self._live.console.print(msg)

        # Update progress bar
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, advance=1)

        self._refresh()
