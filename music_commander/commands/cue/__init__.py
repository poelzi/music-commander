"""CUE sheet processing commands."""

from __future__ import annotations

import click

# Exit codes
EXIT_SUCCESS = 0
EXIT_SPLIT_ERROR = 1
EXIT_MISSING_DEPS = 2


@click.group("cue")
def cli() -> None:
    """CUE sheet processing commands.

    Commands for splitting and managing single-file CD rips
    using CUE sheet metadata.
    """
    pass


# Import submodules to register their commands with the cli group
from music_commander.commands.cue import split as _split  # noqa: E402, F401
