"""Git-annex metadata batch mode wrapper."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from music_commander.db.models import TrackMetadata


class AnnexMetadataBatch:
    """Context manager for git-annex metadata batch operations.

    Manages a long-running subprocess that processes metadata operations
    efficiently without creating a commit for each change.

    Usage:
        with AnnexMetadataBatch(repo_path) as batch:
            batch.set_metadata(Path("track.flac"), {"rating": ["5"]})
            metadata = batch.get_metadata(Path("track.flac"))
    """

    def __init__(self, repo_path: Path) -> None:
        """Initialize batch metadata manager.

        Args:
            repo_path: Path to git-annex repository root.
        """
        self.repo_path = repo_path
        self._proc: subprocess.Popen[str] | None = None

    def start(self) -> None:
        """Start the git-annex metadata batch subprocess."""
        cmd = [
            "git",
            "-c",
            "annex.alwayscommit=false",
            "annex",
            "metadata",
            "--batch",
            "--json",
        ]

        self._proc = subprocess.Popen(
            cmd,
            cwd=self.repo_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )

    def __enter__(self) -> AnnexMetadataBatch:
        """Enter context manager - start subprocess."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Exit context manager - cleanup subprocess and commit changes."""
        if self._proc:
            # Close stdin to signal EOF
            if self._proc.stdin:
                self._proc.stdin.close()

            # Wait for process to finish
            self._proc.wait(timeout=10)

        # Commit accumulated changes via git annex merge
        subprocess.run(
            ["git", "annex", "merge"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )

        return False  # Don't suppress exceptions

    def set_metadata(
        self,
        file_path: Path,
        fields: dict[str, list[str]],
    ) -> bool:
        """Set metadata fields for a file.

        Args:
            file_path: Repository-relative path to file.
            fields: Metadata fields (all values must be lists of strings).

        Returns:
            True if successful, False otherwise.

        Raises:
            RuntimeError: If subprocess not started or died.
        """
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise RuntimeError("Batch subprocess not running")

        # Build JSON input
        request = {
            "file": str(file_path),
            "fields": fields,
        }

        # Write request + newline
        json_line = json.dumps(request) + "\n"
        self._proc.stdin.write(json_line)
        self._proc.stdin.flush()

        # Read response
        response_line = self._proc.stdout.readline()
        if not response_line:
            return False

        try:
            response = json.loads(response_line)
            return response.get("success", False)
        except json.JSONDecodeError:
            return False

    def get_metadata(self, file_path: Path) -> dict[str, list[str]] | None:
        """Get existing metadata for a file.

        Args:
            file_path: Repository-relative path to file.

        Returns:
            Dictionary of metadata fields, or None if file not annexed.

        Raises:
            RuntimeError: If subprocess not started or died.
        """
        if not self._proc or not self._proc.stdin or not self._proc.stdout:
            raise RuntimeError("Batch subprocess not running")

        # Build JSON input (no fields = query mode)
        request = {"file": str(file_path)}

        # Write request + newline
        json_line = json.dumps(request) + "\n"
        self._proc.stdin.write(json_line)
        self._proc.stdin.flush()

        # Read response
        response_line = self._proc.stdout.readline()
        if not response_line:
            return None

        try:
            response = json.loads(response_line)
            return response.get("fields", {})
        except json.JSONDecodeError:
            return None

    def commit(self, message: str = "Sync metadata from Mixxx") -> None:
        """Force commit of accumulated metadata changes.

        Can be called mid-batch to create intermediate commits for
        very large sync operations.

        Args:
            message: Commit message (note: git-annex merge doesn't use custom messages).
        """
        subprocess.run(
            ["git", "annex", "merge"],
            cwd=self.repo_path,
            check=True,
            capture_output=True,
        )


# =============================================================================
# Field Transformations
# =============================================================================


def transform_rating(rating: int | None) -> str | None:
    """Transform Mixxx rating (0-5) to git-annex metadata format.

    Args:
        rating: Rating value from Mixxx (0-5, where 0 means unrated).

    Returns:
        String rating "1"-"5", or None if unrated.
    """
    if rating is None or rating == 0:
        return None
    return str(rating)


def transform_color(color: int | None) -> str | None:
    """Transform Mixxx color (INT) to hex color format.

    Args:
        color: Color value as integer RGB.

    Returns:
        Hex color string "#RRGGBB", or None if no color.
    """
    if color is None:
        return None
    return f"#{color:06X}"


def transform_bpm(bpm: float | None) -> str | None:
    """Transform Mixxx BPM (float) to string format.

    Args:
        bpm: BPM value from Mixxx.

    Returns:
        BPM as string with 2 decimal places, or None if invalid.
    """
    if bpm is None or bpm <= 0:
        return None
    return f"{bpm:.2f}"


def sanitize_metadata_value(value: str, max_length: int = 1000) -> str:
    """Sanitize metadata value for git-annex compatibility.

    Removes control characters, normalizes whitespace, and truncates
    if necessary to ensure values are safe for git-annex.

    Args:
        value: Raw metadata value from Mixxx.
        max_length: Maximum length before truncation (default 1000).

    Returns:
        Sanitized metadata value safe for git-annex.
    """
    # Replace problematic whitespace with single space
    sanitized = value.replace("\n", " ").replace("\r", " ").replace("\t", " ")

    # Remove control characters (ASCII 0x00-0x1f and 0x7f)
    sanitized = re.sub(r"[\x00-\x1f\x7f]", "", sanitized)

    # Collapse multiple spaces to single space
    sanitized = re.sub(r" +", " ", sanitized)

    # Trim leading/trailing whitespace
    sanitized = sanitized.strip()

    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[: max_length - 3] + "..."

    return sanitized


def sanitize_crate_name(name: str) -> str:
    """Sanitize crate name for git-annex metadata compatibility.

    Removes control characters and normalizes whitespace to ensure
    crate names are safe for use in git-annex metadata fields.

    Args:
        name: Raw crate name from Mixxx.

    Returns:
        Sanitized crate name safe for git-annex.
    """
    # Use general sanitization with shorter max length for crate names
    return sanitize_metadata_value(name, max_length=200)


def build_annex_fields(track: TrackMetadata) -> dict[str, list[str]]:
    """Build git-annex metadata fields dictionary from TrackMetadata.

    Applies all necessary transformations and filters out None values.
    All git-annex metadata values must be lists of strings.

    Args:
        track: Track metadata from Mixxx database.

    Returns:
        Dictionary ready for git-annex metadata --batch input.
    """
    fields: dict[str, list[str]] = {}

    # Transform and add rating
    rating = transform_rating(track.rating)
    if rating is not None:
        fields["rating"] = [rating]

    # Transform and add BPM
    bpm = transform_bpm(track.bpm)
    if bpm is not None:
        fields["bpm"] = [bpm]

    # Transform and add color
    color = transform_color(track.color)
    if color is not None:
        fields["color"] = [color]

    # Add string fields with sanitization (filter None)
    if track.key:
        fields["key"] = [sanitize_metadata_value(track.key, max_length=50)]

    if track.artist:
        fields["artist"] = [sanitize_metadata_value(track.artist, max_length=500)]

    if track.title:
        fields["title"] = [sanitize_metadata_value(track.title, max_length=500)]

    if track.album:
        fields["album"] = [sanitize_metadata_value(track.album, max_length=500)]

    if track.genre:
        fields["genre"] = [sanitize_metadata_value(track.genre, max_length=200)]

    if track.year:
        fields["year"] = [sanitize_metadata_value(track.year, max_length=10)]

    if track.tracknumber:
        fields["tracknumber"] = [sanitize_metadata_value(track.tracknumber, max_length=20)]

    if track.comment:
        fields["comment"] = [sanitize_metadata_value(track.comment, max_length=2000)]

    # Add crates as multi-value field (sanitized)
    if track.crates:
        # Sanitize crate names and filter out empty ones
        sanitized_crates = [sanitize_crate_name(c) for c in track.crates]
        # Filter out empty crate names after sanitization
        sanitized_crates = [c for c in sanitized_crates if c]

        if sanitized_crates:
            fields["crate"] = sanitized_crates
        else:
            # If all crates became empty after sanitization, explicitly remove field
            fields["crate"] = []
    else:
        # No crates - explicitly remove field if it exists
        fields["crate"] = []

    return fields
