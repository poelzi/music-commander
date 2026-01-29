"""Command-line interface for music-commander."""

from __future__ import annotations

import os
from pathlib import Path

import click

from music_commander import __version__
from music_commander.config import Config, load_config
from music_commander.utils.output import (
    console,
    error,
    set_color,
    set_pager,
    set_verbosity,
    warning,
)


class Context:
    """Shared context for all commands."""

    def __init__(self) -> None:
        self.config: Config | None = None
        self.verbose: bool = False
        self.debug: bool = False
        self.quiet: bool = False
        self.pager: bool | None = None  # None = auto


pass_context = click.make_pass_decorator(Context, ensure=True)


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=False, path_type=Path),
    help="Path to config file (default: ~/.config/music-commander/config.toml)",
)
@click.option(
    "--repo",
    "-R",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    help="Path to git-annex music repository (overrides config)",
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
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug output (implies --verbose)",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    default=False,
    help="Suppress non-error output",
)
@click.option(
    "--pager/--no-pager",
    default=None,
    help="Force pager on/off (default: auto-detect)",
)
@click.version_option(version=__version__, prog_name="music-commander")
@click.pass_context
def cli(
    ctx: click.Context,
    config: Path | None,
    repo: Path | None,
    no_color: bool,
    verbose: bool,
    debug: bool,
    quiet: bool,
    pager: bool | None,
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
    app_ctx.verbose = verbose or debug
    app_ctx.debug = debug
    app_ctx.quiet = quiet
    app_ctx.pager = pager

    # Configure module-level verbosity for output helpers
    set_verbosity(verbose=verbose, debug=debug)

    # Configure pager
    set_pager(pager)

    # Configure color output: disabled by --no-color, NO_COLOR env, or config
    disable_color = no_color or os.environ.get("NO_COLOR") is not None

    if disable_color:
        set_color(False)

    # Load configuration
    try:
        loaded_config, warnings = load_config(config)
        app_ctx.config = loaded_config

        # Override music_repo if --repo is specified
        if repo is not None:
            loaded_config.music_repo = repo.expanduser().resolve()

        # Apply config settings
        if not disable_color and not loaded_config.colored_output:
            set_color(False)

        # Show warnings unless quiet
        if not quiet:
            for warn in warnings:
                warning(warn)

    except Exception as e:
        error(str(e))
        ctx.exit(1)


@cli.command("help")
@click.argument("command", required=False, nargs=-1)
@click.pass_context
def help_cmd(ctx: click.Context, command: tuple[str, ...]) -> None:
    """Show help for a command."""
    group = cli
    # Resolve subcommand chain
    for name in command:
        cmd = group.get_command(ctx, name)
        if cmd is None:
            error(f"Unknown command: {name}")
            ctx.exit(1)
            return
        if isinstance(cmd, click.Group):
            group = cmd
        else:
            click.echo(cmd.get_help(ctx))
            return
    # Print group help
    click.echo(group.get_help(ctx))


def register_commands() -> None:
    """Register all commands from the commands package."""
    from music_commander.commands import discover_commands

    for command in discover_commands():
        cli.add_command(command)


# Register commands on import
register_commands()
