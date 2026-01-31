"""Bandcamp collection management commands."""

from __future__ import annotations

import click

# Exit codes per CLI contract
EXIT_SUCCESS = 0
EXIT_AUTH_ERROR = 1
EXIT_SYNC_ERROR = 2
EXIT_MATCH_ERROR = 3
EXIT_DOWNLOAD_ERROR = 4
EXIT_PARSE_ERROR = 5


@click.group("bandcamp")
def cli() -> None:
    """Bandcamp collection management.

    Commands for syncing, matching, downloading, and repairing
    files from your Bandcamp purchase collection.
    """
    pass


# Import submodules to register their commands with the cli group
from music_commander.commands.bandcamp import auth as _auth  # noqa: E402, F401
from music_commander.commands.bandcamp import download as _download  # noqa: E402, F401
from music_commander.commands.bandcamp import repair as _repair  # noqa: E402, F401
from music_commander.commands.bandcamp import sync as _sync  # noqa: E402, F401
