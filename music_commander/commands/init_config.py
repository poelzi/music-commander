"""Initialize configuration file for music-commander."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import click

from music_commander.cli import Context, pass_context
from music_commander.config import get_default_config_path
from music_commander.utils.fileops import secure_mkdir
from music_commander.utils.output import error, info, success


def _load_example_config() -> str:
    """Load the example configuration from package data."""
    return resources.files("music_commander").joinpath("config.example.toml").read_text()


@click.command("init-config")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Overwrite existing config file",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output path for config file (default: ~/.config/music-commander/config.toml)",
)
@pass_context
def cli(ctx: Context, force: bool, output: Path | None) -> None:
    """Create a new configuration file with default settings.

    Creates a configuration file at the default location
    (~/.config/music-commander/config.toml) or at a custom path
    specified with --output.

    The generated config file includes all available options with
    sensible defaults and documentation comments.

    Examples:

    \b
      # Create config at default location
      music-commander init-config

    \b
      # Create config at custom location
      music-commander init-config --output ./my-config.toml

    \b
      # Overwrite existing config
      music-commander init-config --force
    """
    # Determine output path
    config_path = output if output is not None else get_default_config_path()
    config_path = config_path.expanduser().resolve()

    # Check if file already exists
    if config_path.exists() and not force:
        error(
            f"Config file already exists: {config_path}",
            hint="Use --force to overwrite",
        )
        raise SystemExit(1)

    # Ensure parent directory exists with secure permissions
    secure_mkdir(config_path.parent)

    # Load config content from the package example (single source of truth)
    config_content = _load_example_config()

    try:
        config_path.write_text(config_content)
        config_path.chmod(0o600)
    except OSError as e:
        error(f"Failed to write config file: {e}")
        raise SystemExit(1)

    success(f"Created config file: {config_path}")
    info("Edit this file to customize your settings.")
    info(
        "Tip: Add '.music-commander-cache.db' to your music repo's "
        ".gitignore to exclude the search cache."
    )
