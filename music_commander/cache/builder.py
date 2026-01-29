"""Build and refresh the local metadata cache from the git-annex branch."""

from __future__ import annotations

import base64
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from music_commander.cache.models import CacheBase, CacheState, CacheTrack, TrackCrate
from music_commander.utils.output import debug, verbose

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# T008: Metadata log parser
# ---------------------------------------------------------------------------

_TIMESTAMP_RE = re.compile(r"^\d+(\.\d+)?s$")


def _decode_value(raw: str) -> str:
    """Decode a git-annex metadata value.

    Values prefixed with ``!`` are base64-encoded (they contain spaces,
    special characters, or non-ASCII).  Plain values are returned as-is.
    """
    if raw.startswith("!"):
        return base64.b64decode(raw[1:]).decode("utf-8", errors="replace")
    return raw


def parse_metadata_log(content: str) -> dict[str, list[str]]:
    """Parse a ``.log.met`` blob into field → values mapping.

    Each line has the format::

        <timestamp>s <field1> +<val> [+<val2>] [-<val3>] <field2> +<val> …

    For multi-line blobs the lines are replayed chronologically: ``+``
    adds a value, ``-`` removes it.

    Returns a dict mapping field names to their *current* list of values.
    """
    # field → set of current values (replay semantics)
    state: dict[str, set[str]] = {}

    for line in content.strip().splitlines():
        tokens = line.split()
        if not tokens:
            continue

        # Skip timestamp token (e.g. "1769651283s" or "1507541153.566038914s")
        idx = 0
        if idx < len(tokens) and _TIMESTAMP_RE.match(tokens[idx]):
            idx += 1

        current_field: str | None = None
        while idx < len(tokens):
            tok = tokens[idx]
            idx += 1

            if tok.startswith("+") or tok.startswith("-"):
                # This is a value for the current field
                if current_field is None:
                    continue
                is_add = tok[0] == "+"
                raw_val = tok[1:]
                decoded = _decode_value(raw_val)

                if current_field not in state:
                    state[current_field] = set()

                if is_add:
                    state[current_field].add(decoded)
                else:
                    state[current_field].discard(decoded)
            else:
                # This is a field name
                current_field = tok
                if current_field not in state:
                    state[current_field] = set()

    return {k: sorted(v) for k, v in state.items()}


# ---------------------------------------------------------------------------
# T007: Raw git-annex branch reader
# ---------------------------------------------------------------------------


def _extract_key_from_path(path: str) -> str:
    """Extract the git-annex key from a ``.log.met`` path.

    Path format: ``xxx/yyy/KEY.log.met`` where ``xxx/yyy/`` is a hash
    directory prefix.
    """
    # Remove directory prefix and .log.met suffix
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    if filename.endswith(".log.met"):
        return filename[: -len(".log.met")]
    return filename


def read_metadata_from_branch(
    repo_path: Path,
) -> Iterator[tuple[str, dict[str, list[str]]]]:
    """Read all metadata from the git-annex branch.

    Yields ``(annex_key, parsed_metadata)`` tuples by reading ``.log.met``
    blobs directly from the ``git-annex`` branch.
    """
    # Step 1: list all .log.met files with their blob hashes
    debug("git ls-tree -r git-annex")
    ls_tree = subprocess.run(
        ["git", "ls-tree", "-r", "git-annex"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )

    entries: list[tuple[str, str]] = []  # (blob_hash, annex_key)
    for line in ls_tree.stdout.splitlines():
        # Format: <mode> <type> <hash>\t<path>
        if not line.endswith(".log.met"):
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta_parts = parts[0].split()
        if len(meta_parts) < 3:
            continue
        blob_hash = meta_parts[2]
        path = parts[1]
        annex_key = _extract_key_from_path(path)
        entries.append((blob_hash, annex_key))

    if not entries:
        return

    verbose(f"Found {len(entries)} metadata entries")

    # Step 2: batch-read all blobs via git cat-file --batch
    debug(f"git cat-file --batch ({len(entries)} blobs)")
    input_data = "\n".join(h for h, _ in entries) + "\n"
    cat_file = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo_path,
        input=input_data,
        capture_output=True,
        text=True,
        check=True,
    )

    # Parse cat-file output: each blob has a header line then content
    output = cat_file.stdout
    pos = 0
    for _, annex_key in entries:
        # Header: "<hash> blob <size>\n"
        newline = output.find("\n", pos)
        if newline == -1:
            break
        header = output[pos:newline]
        pos = newline + 1

        header_parts = header.split()
        if len(header_parts) < 3 or header_parts[1] != "blob":
            continue
        size = int(header_parts[2])

        content = output[pos : pos + size]
        pos += size
        # Skip trailing newline after blob content
        if pos < len(output) and output[pos] == "\n":
            pos += 1

        parsed = parse_metadata_log(content)
        if parsed:
            yield annex_key, parsed


# ---------------------------------------------------------------------------
# T009: Key-to-file mapper
# ---------------------------------------------------------------------------


def build_key_to_file_map(repo_path: Path) -> dict[str, str]:
    """Map git-annex keys to repository-relative file paths.

    Uses ``git annex find --include='*'`` to include all annexed files,
    even those whose content is not locally present.
    """
    verbose("Building key-to-file mapping...")
    debug("git annex find --include='*' --format=${key}\\t${file}\\n")
    result = subprocess.run(
        ["git", "annex", "find", "--include=*", "--format=${key}\t${file}\n"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )

    key_to_file: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        key, file_path = line.split("\t", 1)
        key_to_file[key] = file_path

    verbose(f"Mapped {len(key_to_file)} keys to files")
    return key_to_file


def build_present_keys(repo_path: Path) -> set[str]:
    """Return the set of annex keys whose content is locally present.

    Uses ``git annex find`` (without ``--branch``) which only lists files
    with content available in the local repository.
    """
    verbose("Checking locally present files...")
    debug("git annex find --format=${key}\\n")
    result = subprocess.run(
        ["git", "annex", "find", "--format=${key}\n"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )

    keys = {line for line in result.stdout.splitlines() if line}
    verbose(f"Found {len(keys)} locally present files")
    return keys


# ---------------------------------------------------------------------------
# T011: FTS5 virtual table
# ---------------------------------------------------------------------------


def _create_fts5_table(session: Session) -> None:
    """Create the FTS5 virtual table for full-text search if it doesn't exist."""
    session.execute(
        text("""
        CREATE VIRTUAL TABLE IF NOT EXISTS tracks_fts USING fts5(
            key, artist, title, album, genre, file
        )
    """)
    )
    session.commit()


def _rebuild_fts5(session: Session) -> None:
    """Rebuild the FTS5 index from the tracks table."""
    session.execute(text("DELETE FROM tracks_fts"))
    session.execute(
        text("""
        INSERT INTO tracks_fts(key, artist, title, album, genre, file)
        SELECT key, artist, title, album, genre, file FROM tracks
    """)
    )
    session.commit()


# ---------------------------------------------------------------------------
# T006: Cache builder orchestration
# ---------------------------------------------------------------------------


def _get_annex_branch_commit(repo_path: Path) -> str | None:
    """Get the current commit hash of the git-annex branch."""
    debug("git rev-parse git-annex")
    try:
        result = subprocess.run(
            ["git", "rev-parse", "git-annex"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def _metadata_to_track(
    annex_key: str,
    metadata: dict[str, list[str]],
    file_path: str | None,
) -> CacheTrack:
    """Convert parsed metadata + file path into a CacheTrack."""

    def first(field: str) -> str | None:
        vals = metadata.get(field)
        if vals:
            return vals[0]
        return None

    def first_float(field: str) -> float | None:
        val = first(field)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
        return None

    def first_int(field: str) -> int | None:
        val = first(field)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                return None
        return None

    return CacheTrack(
        key=annex_key,
        file=file_path,
        artist=first("artist"),
        title=first("title"),
        album=first("album"),
        genre=first("genre"),
        bpm=first_float("bpm"),
        rating=first_int("rating"),
        key_musical=first("key"),
        year=first("year"),
        tracknumber=first("tracknumber"),
        comment=first("comment"),
        color=first("color"),
    )


def _metadata_to_crates(
    annex_key: str,
    metadata: dict[str, list[str]],
) -> list[TrackCrate]:
    """Extract crate entries from metadata."""
    crates = metadata.get("crate", [])
    return [TrackCrate(key=annex_key, crate=c) for c in crates if c]


def build_cache(repo_path: Path, session: Session) -> int:
    """Build the full cache from the git-annex branch.

    Returns the number of tracks inserted.

    Raises:
        subprocess.CalledProcessError: If the repository has no git-annex
            branch (not a git-annex repository or no files annexed yet).
    """
    from datetime import datetime, timezone

    # Create FTS5 table
    _create_fts5_table(session)

    # Clear existing data
    session.query(TrackCrate).delete()
    session.query(CacheTrack).delete()
    session.commit()

    # Read metadata from git-annex branch
    verbose("Reading metadata from git-annex branch...")
    metadata_map: dict[str, dict[str, list[str]]] = {}
    for annex_key, parsed in read_metadata_from_branch(repo_path):
        metadata_map[annex_key] = parsed

    # Build key-to-file mapping (includes all annexed files, present or not)
    key_to_file = build_key_to_file_map(repo_path)

    # Determine which keys have content locally present
    present_keys = build_present_keys(repo_path)

    # Insert tracks
    verbose("Inserting tracks into cache...")
    track_count = 0
    missing_count = 0
    no_file_count = 0
    for annex_key, metadata in metadata_map.items():
        file_path = key_to_file.get(annex_key)
        is_present = file_path is not None and annex_key in present_keys

        track = _metadata_to_track(annex_key, metadata, file_path)
        track.present = is_present
        session.add(track)

        for crate in _metadata_to_crates(annex_key, metadata):
            session.add(crate)

        track_count += 1
        if file_path is None:
            no_file_count += 1
        elif not is_present:
            missing_count += 1

    if no_file_count:
        verbose(f"{no_file_count} tracks with no file path (not in current tree)")
    if missing_count:
        verbose(f"{missing_count} tracks not locally present (content on remote)")

    session.commit()

    # Rebuild FTS5 index
    verbose("Rebuilding FTS5 index...")
    _rebuild_fts5(session)

    # Update cache state
    commit = _get_annex_branch_commit(repo_path)
    now = datetime.now(timezone.utc).isoformat()

    state = session.query(CacheState).filter_by(id=1).first()
    if state is None:
        state = CacheState(id=1)
        session.add(state)
    state.annex_branch_commit = commit
    state.last_updated = now
    state.track_count = track_count
    session.commit()

    verbose(f"Cache built: {track_count} tracks")
    return track_count


# ---------------------------------------------------------------------------
# T010: Incremental refresh
# ---------------------------------------------------------------------------


def _get_changed_log_met_files(
    repo_path: Path,
    old_commit: str,
    new_commit: str,
) -> list[str]:
    """Get list of changed .log.met file paths between two git-annex commits."""
    debug(f"git diff-tree -r --name-only {old_commit[:12]} {new_commit[:12]}")
    result = subprocess.run(
        ["git", "diff-tree", "-r", "--name-only", old_commit, new_commit],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.endswith(".log.met")]


def _read_specific_blobs(
    repo_path: Path,
    paths: list[str],
) -> Iterator[tuple[str, dict[str, list[str]]]]:
    """Read specific .log.met blobs from the current git-annex branch."""
    if not paths:
        return

    # Get blob hashes for specific paths
    for path in paths:
        try:
            result = subprocess.run(
                ["git", "cat-file", "-p", f"git-annex:{path}"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            annex_key = _extract_key_from_path(path)
            parsed = parse_metadata_log(result.stdout)
            if parsed:
                yield annex_key, parsed
        except subprocess.CalledProcessError:
            # File was deleted in the new commit
            annex_key = _extract_key_from_path(path)
            yield annex_key, {}


def refresh_cache(repo_path: Path, session: Session) -> int | None:
    """Incrementally refresh the cache if the git-annex branch has changed.

    Returns the number of updated tracks, or None if no refresh was needed.
    If no cache exists, performs a full build instead.
    """
    current_commit = _get_annex_branch_commit(repo_path)
    if current_commit is None:
        return None

    state = session.query(CacheState).filter_by(id=1).first()

    # No cache exists — do a full build
    if state is None or state.annex_branch_commit is None:
        return build_cache(repo_path, session)

    # Cache is up-to-date
    if state.annex_branch_commit == current_commit:
        verbose("Cache is current, no refresh needed")
        return None

    old_commit = state.annex_branch_commit

    # Find changed .log.met files
    changed_paths = _get_changed_log_met_files(repo_path, old_commit, current_commit)
    if not changed_paths:
        # No metadata changes, just update commit
        verbose("No metadata changes detected")
        state.annex_branch_commit = current_commit
        session.commit()
        return 0

    verbose(f"{len(changed_paths)} changed metadata files detected")

    # Ensure FTS5 table exists
    _create_fts5_table(session)

    # Get key-to-file mapping (needed for new/changed entries)
    key_to_file = build_key_to_file_map(repo_path)
    present_keys = build_present_keys(repo_path)

    updated_count = 0
    for annex_key, metadata in _read_specific_blobs(repo_path, changed_paths):
        # Delete existing track and crates for this key
        session.query(TrackCrate).filter_by(key=annex_key).delete()
        session.query(CacheTrack).filter_by(key=annex_key).delete()

        # If metadata is empty, the entry was deleted
        if not metadata:
            continue

        file_path = key_to_file.get(annex_key)
        track = _metadata_to_track(annex_key, metadata, file_path)
        track.present = file_path is not None and annex_key in present_keys
        session.add(track)

        for crate in _metadata_to_crates(annex_key, metadata):
            session.add(crate)

        updated_count += 1

    session.commit()

    # Rebuild FTS5 index
    _rebuild_fts5(session)

    # Update cache state
    from datetime import datetime, timezone

    state.annex_branch_commit = current_commit
    state.last_updated = datetime.now(timezone.utc).isoformat()
    state.track_count = session.query(CacheTrack).count()
    session.commit()

    return updated_count
