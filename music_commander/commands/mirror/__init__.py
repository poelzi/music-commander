"""Mirror commands for syncing with external music portals."""

from __future__ import annotations

import click

# Exit codes per CLI contract
EXIT_SUCCESS = 0
EXIT_MIRROR_ERROR = 1


@click.group("mirror")
def cli() -> None:
    """Mirror releases from external music portals."""
    pass


# Import submodules to register their commands with the cli group
from music_commander.commands.mirror import anomalistic as _anomalistic  # noqa: E402, F401
