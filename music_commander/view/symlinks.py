"""Symlink tree creation from search results and templates."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from music_commander.view.template import get_template_variables, render_path

if TYPE_CHECKING:
    from music_commander.cache.models import CacheTrack

# Characters unsafe for most filesystems
_UNSAFE_CHARS = re.compile(r'[<>:"|?*\x00]')

# Multi-value fields (stored in separate tables)
_MULTI_VALUE_FIELDS: frozenset[str] = frozenset({"crate"})


def sanitize_path_segment(segment: str) -> str:
    """Sanitize a single path segment for filesystem safety.

    - Replaces unsafe characters with ``-``
    - Strips leading/trailing whitespace and dots
    - Truncates to 255 bytes (filesystem max)
    """
    segment = _UNSAFE_CHARS.sub("-", segment)
    segment = segment.strip().strip(".")
    # Truncate to 255 bytes
    encoded = segment.encode("utf-8")
    if len(encoded) > 255:
        segment = encoded[:255].decode("utf-8", errors="ignore")
    return segment or "Unknown"


def sanitize_rendered_path(rendered: str) -> str:
    """Sanitize a full rendered path (preserving ``/`` separators).

    Each segment between ``/`` is sanitized individually.
    """
    segments = rendered.split("/")
    sanitized = [sanitize_path_segment(s) for s in segments if s]
    return "/".join(sanitized)


def _build_metadata_dict(
    track: CacheTrack,
    crate_values: list[str] | None = None,
) -> dict[str, str | None]:
    """Build a metadata dict from a CacheTrack for template rendering."""
    d: dict[str, str | None] = {
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "genre": track.genre,
        "bpm": str(track.bpm) if track.bpm is not None else None,
        "rating": str(track.rating) if track.rating is not None else None,
        "key": track.key_musical,
        "year": track.year,
        "tracknumber": track.tracknumber,
        "comment": track.comment,
        "color": track.color,
        "file": track.file,
    }
    if crate_values is not None:
        # For multi-value expansion, set crate to the specific value
        d["crate"] = crate_values[0] if crate_values else None
    return d


def _expand_multi_value(
    track: CacheTrack,
    template_vars: set[str],
    crates: list[str],
) -> list[dict[str, str | None]]:
    """Expand multi-value fields into multiple metadata dicts.

    If the template uses ``crate`` and the track has multiple crate values,
    yields one dict per crate value.
    """
    if "crate" in template_vars and crates:
        return [_build_metadata_dict(track, [c]) for c in crates]
    return [_build_metadata_dict(track)]


def _make_unique_path(path: str, used_paths: set[str]) -> str:
    """Ensure a path is unique by appending a numeric suffix if needed."""
    if path not in used_paths:
        used_paths.add(path)
        return path

    base, ext = os.path.splitext(path)
    counter = 1
    while True:
        candidate = f"{base}_{counter}{ext}"
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
        counter += 1


def cleanup_output_dir(output_dir: Path) -> int:
    """Remove old symlinks and empty directories from the output directory.

    Only removes symlinks — regular files are left untouched.

    Returns:
        Number of symlinks removed.
    """
    if not output_dir.exists():
        return 0

    removed = 0
    # First pass: remove symlinks
    for root, _dirs, files in os.walk(output_dir):
        root_path = Path(root)
        for f in files:
            fpath = root_path / f
            if fpath.is_symlink():
                fpath.unlink()
                removed += 1

    # Second pass: remove empty directories (bottom-up)
    for root, dirs, files in os.walk(output_dir, topdown=False):
        root_path = Path(root)
        if root_path == output_dir:
            continue
        try:
            if not any(root_path.iterdir()):
                root_path.rmdir()
        except OSError:
            pass

    return removed


def create_symlink_tree(
    tracks: list[CacheTrack],
    crates_by_key: dict[str, list[str]],
    template_str: str,
    output_dir: Path,
    repo_path: Path,
    *,
    absolute: bool = False,
) -> tuple[int, int]:
    """Create a symlink directory tree from search results.

    Args:
        tracks: List of CacheTrack objects from search.
        crates_by_key: Dict mapping track key to list of crate names.
        template_str: Jinja2 path template string.
        output_dir: Directory to create symlinks in.
        repo_path: Path to the music repository root.
        absolute: If True, create absolute symlinks instead of relative.

    Returns:
        Tuple of (symlinks_created, duplicates_found).
    """
    template_vars = get_template_variables(template_str)
    used_paths: set[str] = set()
    created = 0
    duplicates = 0

    output_dir.mkdir(parents=True, exist_ok=True)

    for track in tracks:
        crates = crates_by_key.get(track.key, [])
        metadata_dicts = _expand_multi_value(track, template_vars, crates)

        for metadata in metadata_dicts:
            rendered = render_path(template_str, metadata)
            sanitized = sanitize_rendered_path(rendered)

            # Append original file extension
            if track.file:
                _, ext = os.path.splitext(track.file)
                if ext and not sanitized.endswith(ext):
                    sanitized += ext

            # Handle duplicates
            original_path = sanitized
            sanitized = _make_unique_path(sanitized, used_paths)
            if sanitized != original_path:
                duplicates += 1

            # Create symlink
            symlink_path = output_dir / sanitized
            symlink_path.parent.mkdir(parents=True, exist_ok=True)

            # Compute target
            target_file = repo_path / track.file
            if absolute:
                target = target_file.resolve()
            else:
                target = Path(os.path.relpath(target_file, symlink_path.parent))

            # Remove existing symlink if present
            if symlink_path.is_symlink():
                symlink_path.unlink()

            symlink_path.symlink_to(target)
            created += 1

    return created, duplicates
