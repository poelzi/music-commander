"""Command-line interface for music-commander."""

from __future__ import annotations

from pathlib import Path

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
    "--config",
    "-c",
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
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Enable verbose output",
)
@click.option(
    "--quiet",
    "-q",
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
