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
