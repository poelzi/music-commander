"""Open a tag editor for audio files managed by git-annex."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import click

from music_commander.cli import Context, pass_context
from music_commander.commands.files import (
    _VERBOSE_OPTION,
    EXIT_CACHE_ERROR,
    EXIT_NO_REPO,
    EXIT_NO_RESULTS,
    EXIT_NOT_ANNEX_REPO,
    EXIT_PARTIAL_FAILURE,
    EXIT_SUCCESS,
    cli,
)
from music_commander.exceptions import (
    NotGitAnnexRepoError,
    NotGitRepoError,
)
from music_commander.utils.git import (
    annex_add_files,
    annex_get_files_with_progress,
    annex_unlock_files,
    check_git_annex_repo,
)
from music_commander.utils.output import (
    console,
    error,
    info,
    success,
    warning,
)
from music_commander.utils.search_ops import resolve_args_to_files

_DRY_RUN_OPTION = click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Show files without performing the operation",
)


@cli.command("edit-meta")
@click.argument("args", nargs=-1)
@_DRY_RUN_OPTION
@_VERBOSE_OPTION
@click.option(
    "--editor",
    "-e",
    type=str,
    default=None,
    help="Tag editor command (overrides config)",
)
@pass_context
def edit_meta(
    ctx: Context,
    args: tuple[str, ...],
    dry_run: bool,
    verbose: bool,
    editor: str | None,
) -> None:
    """Open a tag editor for audio files.

    Unlocks the selected git-annex files, launches the configured
    metadata tag editor (e.g. puddletag), and re-adds the files to
    git-annex when the editor exits.

    The editor can be set in the config file under [editors].meta_editor
    or overridden with --editor.

    Examples:

    \b
      # Edit tags for specific files
      music-commander files edit-meta tracks/artist/song.flac

    \b
      # Edit tags for files matching a search query
      music-commander files edit-meta "artist:Basinski"

    \b
      # Edit all files in a directory
      music-commander files edit-meta tracks/artist/

    \b
      # Use a specific editor
      music-commander files edit-meta -e kid3-cli tracks/artist/

    \b
      # Preview which files would be edited
      music-commander files edit-meta --dry-run "genre:ambient"
    """
    config = ctx.config
    if config is None:
        error("Configuration not loaded")
        raise SystemExit(EXIT_NO_REPO)

    repo_path = config.music_repo

    # Determine editor
    editor_cmd = editor or config.meta_editor
    if not editor_cmd and not dry_run:
        error(
            "No tag editor configured",
            hint=(
                "Set editors.meta_editor in config.toml or use --editor. "
                "Example: music-commander files edit-meta -e puddletag"
            ),
        )
        raise SystemExit(EXIT_NO_REPO)

    # Check editor is available (unless dry-run)
    if editor_cmd and not dry_run and not shutil.which(editor_cmd):
        error(f"Editor not found: {editor_cmd}")
        raise SystemExit(EXIT_NO_REPO)

    # Validate repository
    try:
        check_git_annex_repo(repo_path)
    except NotGitRepoError:
        error(f"Not a git repository: {repo_path}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)
    except NotGitAnnexRepoError:
        error(f"Not a git-annex repository: {repo_path}")
        raise SystemExit(EXIT_NOT_ANNEX_REPO)

    # Resolve arguments to files (include not-present so we can fetch them)
    file_paths = resolve_args_to_files(
        ctx, args, config, require_present=False, verbose=verbose, dry_run=dry_run
    )

    if file_paths is None:
        raise SystemExit(EXIT_CACHE_ERROR)

    if not file_paths:
        info("No files to edit")
        raise SystemExit(EXIT_NO_RESULTS)

    # Separate files that exist on disk vs those that need fetching
    # (works for both symlink-based and unlocked annex modes)
    present_files = []
    not_present_files = []
    for f in file_paths:
        if f.exists() and not (f.is_symlink() and not f.resolve().exists()):
            present_files.append(f)
        else:
            not_present_files.append(f)

    # Fetch not-present files
    if not_present_files and not dry_run:
        if not ctx.quiet:
            info(f"Fetching {len(not_present_files)} not-present files...")

        fetch_result = annex_get_files_with_progress(
            repo_path,
            not_present_files,
            remote=config.default_remote,
            verbose=verbose,
        )

        present_files.extend(fetch_result.fetched)

        if fetch_result.failed:
            warning(f"Failed to fetch {len(fetch_result.failed)} files")
            if verbose:
                for f, reason in fetch_result.failed:
                    rel = f.relative_to(repo_path)
                    console.print(f"  [dim]fetch failed: {rel} ({reason})[/dim]")

    if not present_files:
        error("No files available for editing")
        raise SystemExit(EXIT_NO_RESULTS)

    # Dry run
    if dry_run:
        total = len(present_files) + len(not_present_files)
        console.print(f"\n[bold]Would edit tags for {total} files:[/bold]\n")
        for file_path in present_files:
            rel_path = file_path.relative_to(repo_path)
            console.print(f"  [path]{rel_path}[/path]")
        if not_present_files:
            console.print(f"\n  [dim]Would fetch {len(not_present_files)} not-present files:[/dim]")
            for file_path in not_present_files:
                rel_path = file_path.relative_to(repo_path)
                console.print(f"    [dim]{rel_path}[/dim]")
        console.print()
        if editor_cmd:
            console.print(f"  Editor: {editor_cmd}")
        console.print()
        raise SystemExit(EXIT_SUCCESS)

    # Unlock files
    if not ctx.quiet:
        info(f"Unlocking {len(present_files)} files...")

    unlocked, unlock_failed = annex_unlock_files(repo_path, present_files)

    if unlock_failed:
        warning(f"Failed to unlock {len(unlock_failed)} files")
        if verbose:
            for f in unlock_failed:
                rel = f.relative_to(repo_path)
                console.print(f"  [dim]unlock failed: {rel}[/dim]")

    if not unlocked:
        error("No files could be unlocked")
        raise SystemExit(EXIT_PARTIAL_FAILURE)

    # Launch editor
    if not ctx.quiet:
        info(f"Opening {editor_cmd} with {len(unlocked)} files...")

    try:
        proc = subprocess.run(
            [editor_cmd] + [str(f) for f in unlocked],
            cwd=repo_path,
        )
    except (OSError, FileNotFoundError) as e:
        error(f"Failed to launch editor: {e}")
        # Still try to re-add the unlocked files
        warning("Re-adding unlocked files despite editor failure...")
        annex_add_files(repo_path, unlocked)
        raise SystemExit(EXIT_PARTIAL_FAILURE)

    if proc.returncode != 0:
        warning(f"Editor exited with code {proc.returncode}")

    # Re-add files to annex
    if not ctx.quiet:
        info(f"Re-adding {len(unlocked)} files to git-annex...")

    added, add_failed = annex_add_files(repo_path, unlocked)

    if add_failed:
        warning(f"Failed to re-add {len(add_failed)} files")
        if verbose:
            for f in add_failed:
                rel = f.relative_to(repo_path)
                console.print(f"  [dim]add failed: {rel}[/dim]")

    # Summary
    if not ctx.quiet:
        console.print()
        if added:
            success(f"Edited and re-added {len(added)} files")
        if unlock_failed or add_failed:
            total_failed = len(unlock_failed) + len(add_failed)
            warning(f"{total_failed} files had errors")

    if unlock_failed or add_failed:
        raise SystemExit(EXIT_PARTIAL_FAILURE)
    raise SystemExit(EXIT_SUCCESS)
