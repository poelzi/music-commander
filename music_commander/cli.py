"""CLI stub - replaced in WP04."""

import click


@click.group()
@click.version_option()
def cli() -> None:
    """music-commander: Manage git-annex music collections."""
    pass
