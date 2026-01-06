---
work_package_id: "WP04"
subtasks:
  - "T011"
  - "T012"
  - "T013"
  - "T014"
title: "CLI Framework & Output"
phase: "Phase 2 - Core Components"
lane: "for_review"
assignee: "claude"
agent: "claude"
shell_pid: "1112538"
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-06"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
  - timestamp: "2026-01-06T20:20:00Z"
    lane: "doing"
    agent: "claude"
    shell_pid: "1112538"
    action: "Started implementation of CLI framework and output helpers"
  - timestamp: "2026-01-06T20:30:00Z"
    lane: "for_review"
    agent: "claude"
    shell_pid: "1112538"
    action: "Completed implementation. All tasks (T011-T014) done. Tests: mypy and ruff pass, CLI --help works."
---

# Work Package Prompt: WP04 – CLI Framework & Output

## Objectives & Success Criteria

- Click-based CLI with global options and subcommand structure
- Auto-discovery of commands from commands/ directory
- Rich-based output helpers for colored, styled terminal output
- `music-commander --help` shows all available commands
- `music-commander --version` shows version
- `--no-color` flag disables all ANSI styling

## Context & Constraints

**Constitution Requirements**:
- MUST use a subcommand structure
- MUST provide colored terminal output for improved readability
- MUST support `--help` at all levels with clear descriptions
- MUST output errors to stderr with actionable messages

**Reference Documents**:
- `kitty-specs/001-core-framework-with/contracts/cli-interface.md` - CLI specification
- `kitty-specs/001-core-framework-with/research.md` - Click + Rich decision

**Dependencies**: WP02 must be complete (config.py for loading settings)

## Subtasks & Detailed Guidance

### Subtask T011 – Create cli.py

**Purpose**: Main CLI entry point with Click group and global options.

**File**: `music_commander/cli.py`

**Implementation**:
```python
"""Command-line interface for music-commander."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from music_commander import __version__
from music_commander.config import Config, load_config
from music_commander.utils.output import console, error, warning


class Context:
    """Shared context for all commands."""
    
    def __init__(self) -> None:
        self.config: Config | None = None
        self.verbose: bool = False
        self.quiet: bool = False


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group()
@click.option(
    "--config", "-c",
    type=click.Path(exists=False, path_type=Path),
    help="Path to config file (default: ~/.config/music-commander/config.toml)",
)
@click.option(
    "--no-color",
    is_flag=True,
    default=False,
    help="Disable colored output",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable verbose output",
)
@click.option(
    "--quiet", "-q",
    is_flag=True,
    default=False,
    help="Suppress non-error output",
)
@click.version_option(version=__version__, prog_name="music-commander")
@click.pass_context
def cli(
    ctx: click.Context,
    config: Path | None,
    no_color: bool,
    verbose: bool,
    quiet: bool,
) -> None:
    """music-commander: Manage git-annex music collections with Mixxx integration.
    
    A command-line tool for managing large music collections stored in git-annex,
    with special integration for Mixxx DJ software.
    
    Configuration is loaded from ~/.config/music-commander/config.toml by default.
    Use --config to specify an alternative configuration file.
    
    Examples:
    
        # Fetch files from recent commits
        music-commander get-commit-files HEAD~5..HEAD
        
        # Show help for a specific command
        music-commander get-commit-files --help
    """
    # Initialize context
    ctx.ensure_object(Context)
    app_ctx = ctx.obj
    app_ctx.verbose = verbose
    app_ctx.quiet = quiet
    
    # Configure console output
    if no_color:
        console.no_color = True
        console.force_terminal = False
    
    # Load configuration
    try:
        loaded_config, warnings = load_config(config)
        app_ctx.config = loaded_config
        
        # Apply config settings
        if not no_color and not loaded_config.colored_output:
            console.no_color = True
        
        # Show warnings unless quiet
        if not quiet:
            for warn in warnings:
                warning(warn)
                
    except Exception as e:
        error(str(e))
        ctx.exit(1)


def register_commands() -> None:
    """Register all commands from the commands package."""
    from music_commander.commands import discover_commands
    
    for command in discover_commands():
        cli.add_command(command)


# Register commands on import
register_commands()
```

**Notes**: The discover_commands() function is created in T012.

### Subtask T012 – Create commands/__init__.py

**Purpose**: Command auto-discovery from the commands directory.

**File**: `music_commander/commands/__init__.py`

**Implementation**:
```python
"""Command discovery and registration."""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from collections.abc import Iterator


def discover_commands() -> Iterator[click.Command]:
    """Discover and yield all command objects from this package.
    
    Commands are discovered by scanning all modules in this package
    and looking for a 'cli' attribute that is a Click command.
    
    Yields:
        Click Command objects found in submodules.
    """
    # Import this package to get its path
    import music_commander.commands as commands_pkg
    
    # Iterate over all modules in the commands package
    for module_info in pkgutil.iter_modules(commands_pkg.__path__):
        if module_info.name.startswith("_"):
            continue  # Skip private modules
        
        # Import the module
        module = importlib.import_module(f"music_commander.commands.{module_info.name}")
        
        # Look for a 'cli' attribute that is a Click command
        if hasattr(module, "cli"):
            cmd = getattr(module, "cli")
            if isinstance(cmd, click.Command):
                yield cmd
```

**Parallel**: Can proceed alongside T011, T013, T014.

### Subtask T013 – Create utils/__init__.py

**Purpose**: Initialize utils package.

**File**: `music_commander/utils/__init__.py`

**Implementation**:
```python
"""Utility modules for music-commander."""

from music_commander.utils.output import (
    console,
    error,
    info,
    success,
    warning,
)

__all__ = [
    "console",
    "error",
    "info",
    "success",
    "warning",
]
```

**Parallel**: Can proceed alongside others.

### Subtask T014 – Create utils/output.py

**Purpose**: Rich console helpers for consistent styled output.

**File**: `music_commander/utils/output.py`

**Implementation**:
```python
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
THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "path": "blue underline",
    "track.artist": "bold",
    "track.title": "italic",
    "progress.description": "bold blue",
})

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


def create_table(title: str | None = None, **kwargs) -> Table:
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
        console.print(f"{prefix} [track.artist]{artist_str}[/track.artist] - [track.title]{title_str}[/track.title]")
    else:
        console.print(f"[track.artist]{artist_str}[/track.artist] - [track.title]{title_str}[/track.title]")


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
```

**Parallel**: Can proceed alongside others.

## Definition of Done Checklist

- [ ] T011: cli.py with Click group and global options
- [ ] T012: commands/__init__.py with auto-discovery
- [ ] T013: utils/__init__.py with exports
- [ ] T014: utils/output.py with Rich helpers
- [ ] `music-commander --help` works
- [ ] `music-commander --version` shows correct version
- [ ] `--no-color` disables ANSI codes
- [ ] Errors go to stderr with proper formatting
- [ ] `mypy music_commander/` passes
- [ ] `ruff check music_commander/` passes

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Command discovery fails silently | Log errors in verbose mode |
| Rich/Click conflict | Use Rich console directly, not click.echo |
| Terminal detection wrong | Respect --no-color explicitly |

## Review Guidance

- Test `--help` at root and subcommand level
- Verify `--no-color` produces clean output
- Check error output goes to stderr
- Ensure config warnings appear unless `--quiet`

## Activity Log

- 2026-01-06 – system – lane=planned – Prompt created.
