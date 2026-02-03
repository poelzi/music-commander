"""Developer tools and diagnostics."""

from __future__ import annotations

import click


@click.group("dev")
def cli() -> None:
    """Developer tools and diagnostics.

    Commands for analyzing algorithm performance, recording metrics,
    and debugging the matching pipeline.
    """
    pass


# Import submodules to register their commands with the cli group
from music_commander.commands.dev import bandcamp_metrics as _bandcamp_metrics  # noqa: E402, F401
