"""Sync state management for Mixxx-to-git-annex metadata sync.

Stores sync state in git-annex metadata on a sentinel file to enable
shared state across git-annex clones.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from music_commander.db.models import SyncState
from music_commander.utils.annex_metadata import AnnexMetadataBatch

SENTINEL_FILE = ".music-commander-sync-state"


def now_utc() -> datetime:
    """Get current UTC time as timezone-aware datetime.

    Returns:
        Current UTC datetime with timezone info.
    """
    return datetime.now(timezone.utc)


def parse_timestamp(s: str) -> datetime:
    """Parse ISO 8601 timestamp string to datetime.

    Ensures returned datetime is timezone-aware (assumes UTC if none specified).

    Args:
        s: ISO 8601 timestamp string.

    Returns:
        Timezone-aware datetime.
    """
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _ensure_sentinel_exists(sentinel: Path) -> None:
    """Create and annex sentinel file if it doesn't exist.

    Args:
        sentinel: Path to sentinel file.
    """
    if sentinel.exists():
        return

    # Create empty sentinel file with header comment
    sentinel.write_text("# music-commander sync state - do not edit\n")

    # Add to git-annex
    subprocess.run(
        ["git", "annex", "add", str(sentinel.name)],
        cwd=sentinel.parent,
        check=True,
        capture_output=True,
    )


def read_sync_state(repo_path: Path) -> SyncState:
    """Read sync state from git-annex metadata on sentinel file.

    Returns default state (first sync) if sentinel doesn't exist or has no metadata.

    Args:
        repo_path: Path to git-annex repository root.

    Returns:
        SyncState with last sync timestamp and track count.
    """
    sentinel = repo_path / SENTINEL_FILE

    # If sentinel doesn't exist, this is first sync
    if not sentinel.exists():
        return SyncState(last_sync_timestamp=None, tracks_synced=0)

    # Read metadata from sentinel
    with AnnexMetadataBatch(repo_path) as batch:
        fields = batch.get_metadata(Path(SENTINEL_FILE))

    # If no metadata, this is first sync
    if not fields:
        return SyncState(last_sync_timestamp=None, tracks_synced=0)

    # Parse timestamp field
    timestamp_list = fields.get("sync-timestamp", [])
    timestamp_str = timestamp_list[0] if timestamp_list else None
    timestamp = parse_timestamp(timestamp_str) if timestamp_str else None

    # Parse tracks count field
    tracks_list = fields.get("tracks-synced", ["0"])
    tracks_str = tracks_list[0] if tracks_list else "0"

    try:
        tracks_synced = int(tracks_str)
    except ValueError:
        tracks_synced = 0

    return SyncState(
        last_sync_timestamp=timestamp,
        tracks_synced=tracks_synced,
    )


def write_sync_state(repo_path: Path, state: SyncState) -> None:
    """Write sync state to git-annex metadata on sentinel file.

    Creates sentinel file and adds to annex if it doesn't exist.

    Args:
        repo_path: Path to git-annex repository root.
        state: SyncState to persist.
    """
    sentinel = repo_path / SENTINEL_FILE

    # Ensure sentinel file exists and is annexed
    _ensure_sentinel_exists(sentinel)

    # Build metadata fields
    fields: dict[str, list[str]] = {
        "tracks-synced": [str(state.tracks_synced)],
    }

    # Add timestamp if present
    if state.last_sync_timestamp:
        fields["sync-timestamp"] = [state.last_sync_timestamp.isoformat()]

    # Write metadata
    with AnnexMetadataBatch(repo_path) as batch:
        batch.set_metadata(Path(SENTINEL_FILE), fields)


def get_last_sync_timestamp_ms(repo_path: Path) -> int | None:
    """Get last sync timestamp in milliseconds (Mixxx format).

    Convenience function to get timestamp in format used by Mixxx
    source_synchronized_ms field.

    Args:
        repo_path: Path to git-annex repository root.

    Returns:
        Timestamp in milliseconds since epoch, or None if never synced.
    """
    state = read_sync_state(repo_path)

    if state.last_sync_timestamp is None:
        return None

    return int(state.last_sync_timestamp.timestamp() * 1000)
