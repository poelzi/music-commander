"""Check availability of external tool dependencies."""

from __future__ import annotations

import shutil

import click
from rich.table import Table

from music_commander.cli import Context, pass_context
from music_commander.utils.output import console, error, info, success

# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

# Each entry: (name, category, required, purpose, used_by)
_TOOL_REGISTRY: list[tuple[str, str, bool, str, list[str]]] = [
    # Core
    ("git", "Core", True, "Version control", ["all"]),
    ("git-annex", "Core", True, "Content-addressed file management", ["all"]),
    # Audio Processing
    ("ffmpeg", "Audio Processing", True, "Audio conversion, checking, fallback splitting", [
        "files check", "files export", "cue split", "mirror anomalistic",
    ]),
    ("ffprobe", "Audio Processing", True, "Audio file metadata probing", ["files export"]),
    # CD Ripping / Splitting
    ("shntool", "CD Ripping", True, "CUE sheet splitting", ["cue split", "files check"]),
    ("metaflac", "CD Ripping", True, "FLAC tagging, analysis, and cover art", [
        "cue split", "files check", "files export",
    ]),
    # Integrity Checking (optional, per-format)
    ("flac", "Integrity Checking", False, "FLAC integrity testing", ["files check"]),
    ("mp3val", "Integrity Checking", False, "MP3 integrity testing", ["files check"]),
    ("ogginfo", "Integrity Checking", False, "OGG/Vorbis integrity testing", ["files check"]),
    ("sox", "Integrity Checking", False, "WAV/AIFF integrity testing", ["files check"]),
    # Archive Extraction
    ("unrar", "Archive Extraction", False, "RAR archive extraction", ["mirror anomalistic"]),
    # Browser
    ("firefox", "Browser", False, "Bandcamp browser authentication", ["bandcamp auth"]),
]


@click.command("check-deps")
@pass_context
def cli(ctx: Context) -> None:
    """Check availability of external tool dependencies.

    Prints a table of all external tools used by music-commander,
    whether they are found on PATH, and which commands need them.

    Exits with code 1 if any required tools are missing.
    """
    table = Table(title="External Dependencies", show_lines=False)
    table.add_column("Tool", style="bold")
    table.add_column("Status")
    table.add_column("Required")
    table.add_column("Path")
    table.add_column("Purpose")
    table.add_column("Used By")

    missing_required: list[str] = []
    current_category = ""

    for name, category, required, purpose, used_by in _TOOL_REGISTRY:
        # Add section header when category changes
        if category != current_category:
            if current_category:
                table.add_section()
            current_category = category

        path = shutil.which(name)
        found = path is not None

        if found:
            status = "[green]found[/green]"
        elif required:
            status = "[red]MISSING[/red]"
            missing_required.append(name)
        else:
            status = "[yellow]not found[/yellow]"

        req_str = "yes" if required else "no"
        path_str = path or ""
        used_str = ", ".join(used_by)

        table.add_row(name, status, req_str, path_str, purpose, used_str)

    console.print(table)
    console.print()

    if missing_required:
        error(
            f"Missing {len(missing_required)} required tool(s): "
            f"{', '.join(missing_required)}"
        )
        info("Install them via your package manager or use 'nix develop'.")
        raise SystemExit(1)
    else:
        success("All required tools are available.")
