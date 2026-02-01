"""File management commands for git-annex repositories."""

from __future__ import annotations

import click

# Exit codes per CLI contract
EXIT_SUCCESS = 0
EXIT_PARTIAL_FAILURE = 1
EXIT_INVALID_REVISION = 2
EXIT_NOT_ANNEX_REPO = 3
EXIT_NO_RESULTS = 0
EXIT_PARSE_ERROR = 1
EXIT_CACHE_ERROR = 2
EXIT_NO_REPO = 3

# Shared options for search-based file operations
_SEARCH_QUERY_ARGUMENT = click.argument("query", nargs=-1, required=True)
_DRY_RUN_OPTION = click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Show files without performing the operation",
)
_JOBS_OPTION = click.option(
    "--jobs",
    "-J",
    type=int,
    default=1,
    help="Number of parallel jobs",
)
_VERBOSE_OPTION = click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show per-file status",
)


@click.group("files")
def cli() -> None:
    """File management commands.

    Commands for fetching and managing files from git-annex.
    """
    pass


# Import submodules to register their commands with the cli group
from music_commander.commands.files import check as _check  # noqa: E402, F401
from music_commander.commands.files import drop as _drop  # noqa: E402, F401
from music_commander.commands.files import edit_meta as _edit_meta  # noqa: E402, F401
from music_commander.commands.files import export as _export  # noqa: E402, F401
from music_commander.commands.files import get as _get  # noqa: E402, F401
from music_commander.commands.files import get_commit as _get_commit  # noqa: E402, F401
