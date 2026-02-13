"""CUE split command — splits single-file CD rips into individual tracks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from music_commander.commands.cue import EXIT_MISSING_DEPS, EXIT_SPLIT_ERROR, EXIT_SUCCESS, cli
from music_commander.cue.parser import CueParseError, parse_cue
from music_commander.cue.splitter import (
    SUPPORTED_EXTENSIONS,
    SplitResult,
    check_already_split,
    check_tools_available,
    group_tracks_by_file,
    split_cue,
    track_output_filename,
)
from music_commander.utils.output import error, info, success, verbose, warning


def _find_cue_pairs(directory: Path, encoding: str | None) -> list[tuple[Path, Path, object]]:
    """Find cue + audio file pairs in a single directory.

    Returns list of (cue_path, audio_path, cue_sheet) tuples.
    For multi-FILE cue sheets, audio_path is the first referenced file;
    the splitter handles additional files via group_tracks_by_file().
    """
    pairs: list[tuple[Path, Path, object]] = []

    cue_files = sorted(f for f in directory.iterdir() if f.suffix.lower() == ".cue")
    if not cue_files:
        return pairs

    for cue_path in cue_files:
        try:
            cue_sheet = parse_cue(cue_path, encoding=encoding)
        except CueParseError as e:
            warning(f"Cannot parse {cue_path}: {e}")
            continue

        # Collect all referenced source files (multi-FILE support)
        file_groups = group_tracks_by_file(cue_sheet)
        if not file_groups:
            warning(f"No FILE reference in {cue_path}")
            continue

        # Check that at least one referenced file exists with supported format
        primary_audio = None
        missing_files = []
        for filename in file_groups:
            audio_path = directory / filename
            if not audio_path.exists():
                missing_files.append(filename)
                continue
            ext = audio_path.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                warning(f"Unsupported format {ext}: {audio_path.name}")
                continue
            if primary_audio is None:
                primary_audio = audio_path

        if missing_files:
            for mf in missing_files:
                warning(f"Source file not found: {directory / mf} (referenced by {cue_path.name})")

        if primary_audio is None:
            continue

        pairs.append((cue_path, primary_audio, cue_sheet))

    return pairs


def _scan_directories(
    directories: tuple[str, ...], recursive: bool, encoding: str | None
) -> list[tuple[Path, Path, object]]:
    """Scan directories for cue + audio pairs.

    Args:
        directories: Directory paths to scan.
        recursive: If True, walk directory trees.
        encoding: Character encoding for cue files.

    Returns:
        List of (cue_path, audio_path, cue_sheet) tuples.
    """
    all_pairs: list[tuple[Path, Path, object]] = []

    for dir_str in directories:
        dir_path = Path(dir_str)
        if not dir_path.is_dir():
            warning(f"Not a directory: {dir_path}")
            continue

        if recursive:
            for root, dirs, files in os.walk(dir_path):
                root_path = Path(root)
                pairs = _find_cue_pairs(root_path, encoding)
                all_pairs.extend(pairs)
        else:
            pairs = _find_cue_pairs(dir_path, encoding)
            all_pairs.extend(pairs)

    return all_pairs


@cli.command("split")
@click.argument(
    "directories", nargs=-1, required=True, type=click.Path(exists=True, file_okay=False)
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    default=False,
    help="Walk directory trees to find cue/audio pairs.",
)
@click.option(
    "--remove-originals",
    is_flag=True,
    default=False,
    help="Delete source audio and cue files after successful split.",
)
@click.option(
    "--force", is_flag=True, default=False, help="Re-split even if output files already exist."
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Preview what would be split without performing any operations.",
)
@click.option(
    "--encoding",
    type=str,
    default=None,
    help="Character encoding for cue files (e.g., cp1252, shift-jis).",
)
@click.option(
    "--verbose", "-v", "verbose_flag", is_flag=True, default=False, help="Show detailed output."
)
def split(
    directories: tuple[str, ...],
    recursive: bool,
    remove_originals: bool,
    force: bool,
    dry_run: bool,
    encoding: str | None,
    verbose_flag: bool,
) -> None:
    """Split single-file CD rips into individual FLAC tracks.

    Finds .cue files in the given DIRECTORIES, parses them, and splits
    the referenced audio files into individual tracks using shntool.
    Each track is tagged with metadata from the cue sheet and has
    cover art embedded if available.

    Supports FLAC, WAV, APE, and WavPack source formats.
    """
    # Check for required tools
    missing_required, missing_optional = check_tools_available()
    if missing_required:
        error(f"Missing required tools: {', '.join(missing_required)}")
        error("Install them via your package manager or nix develop shell.")
        sys.exit(EXIT_MISSING_DEPS)
    if missing_optional:
        warning(f"Optional tools not found: {', '.join(missing_optional)}")
        warning("APE/WV fallback splitting will not be available.")

    # Scan for cue/audio pairs
    pairs = _scan_directories(directories, recursive, encoding)

    if not pairs:
        info("No cue/audio pairs found.")
        sys.exit(EXIT_SUCCESS)

    info(f"Found {len(pairs)} cue/audio pair(s) to process.")

    # Dry-run mode
    if dry_run:
        for cue_path, audio_path, cue_sheet in pairs:
            already = check_already_split(cue_sheet, cue_path.parent)
            status = " (already split)" if already else ""
            info(f"\n  {cue_path.name} -> {audio_path.name}{status}")
            info(f"    Tracks: {len(cue_sheet.tracks)}")
            if verbose_flag:
                for track in cue_sheet.tracks:
                    fname = track_output_filename(track)
                    info(f"      {fname}")
        return

    # Process each pair
    results: list[SplitResult] = []
    ok_count = 0
    skip_count = 0
    error_count = 0

    for cue_path, audio_path, cue_sheet in pairs:
        output_dir = cue_path.parent
        verbose(f"Processing: {cue_path}")

        result = split_cue(
            cue_sheet=cue_sheet,
            cue_path=cue_path,
            source_path=audio_path,
            output_dir=output_dir,
            force=force,
        )
        results.append(result)

        if result.status == "ok":
            ok_count += 1
            track_count = len(cue_sheet.tracks)
            success(f"Split {audio_path.name} -> {track_count} tracks")

            # Remove originals if requested
            if remove_originals:
                try:
                    audio_path.unlink()
                    cue_path.unlink()
                    verbose(f"Removed originals: {audio_path.name}, {cue_path.name}")
                except OSError as e:
                    warning(f"Could not remove originals: {e}")

        elif result.status == "skipped":
            skip_count += 1
            info(f"Skipped (already split): {audio_path.name}")

        elif result.status == "error":
            error_count += 1
            error(f"Failed: {audio_path.name}: {result.error}")

    # Summary
    info(f"\nDone: {ok_count} split, {skip_count} skipped, {error_count} errors")

    if error_count > 0:
        sys.exit(EXIT_SPLIT_ERROR)
    sys.exit(EXIT_SUCCESS)
