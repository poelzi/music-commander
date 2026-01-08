---
work_package_id: "WP03"
subtasks:
  - "T012"
  - "T013"
  - "T014"
  - "T015"
  - "T016"
title: "Sync State Management"
phase: "Phase 0 - Foundation"
lane: "done"
assignee: "claude"
agent: "claude-reviewer"
shell_pid: "1395416"
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-07T14:30:00Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP03 – Sync State Management

## Objectives & Success Criteria

- Create `SyncState` dataclass for tracking sync metadata
- Implement read/write functions for sync state in git-annex metadata
- Use sentinel file `.music-commander-sync-state` for state storage
- Support first-run detection (no prior sync)

**Success**: Sync timestamp persists across process restarts and is shared across git-annex clones.

## Context & Constraints

- **Clarification**: Sync state stored in git-annex branch metadata (shared across clones)
- **Research**: See `kitty-specs/002-mixxx-to-git/research.md` section 3
- **Dependency**: Uses `AnnexMetadataBatch` from WP02

### Storage Approach

Store sync state as git-annex metadata on a sentinel file:
- File: `.music-commander-sync-state` in repo root
- Fields: `sync-timestamp` (ISO 8601), `tracks-synced` (integer string)

## Subtasks & Detailed Guidance

### Subtask T012 – SyncState Dataclass

**Purpose**: Type-safe container for sync state data.

**Steps**:
1. Add to `music_commander/db/models.py` (or new file)
2. Define `SyncState` dataclass with fields:
   - `last_sync_timestamp: datetime | None`
   - `tracks_synced: int`
3. Add `is_first_sync` property returning `last_sync_timestamp is None`

**Files**: `music_commander/db/models.py`

**Definition**:
```python
@dataclass
class SyncState:
    last_sync_timestamp: datetime | None
    tracks_synced: int = 0
    
    @property
    def is_first_sync(self) -> bool:
        return self.last_sync_timestamp is None
```

### Subtask T013 – read_sync_state Function

**Purpose**: Read sync state from git-annex metadata on sentinel file.

**Steps**:
1. Create `music_commander/utils/sync_state.py`
2. Implement `read_sync_state(repo_path: Path) -> SyncState`
3. Use `AnnexMetadataBatch.get_metadata()` to read sentinel file
4. Parse `sync-timestamp` field as ISO 8601 datetime
5. Parse `tracks-synced` field as integer
6. Return `SyncState(None, 0)` if sentinel has no metadata (first sync)

**Files**: `music_commander/utils/sync_state.py` (new file)

**Implementation**:
```python
def read_sync_state(repo_path: Path) -> SyncState:
    sentinel = repo_path / ".music-commander-sync-state"
    if not sentinel.exists():
        return SyncState(last_sync_timestamp=None, tracks_synced=0)
    
    with AnnexMetadataBatch(repo_path) as batch:
        fields = batch.get_metadata(sentinel)
    
    if not fields:
        return SyncState(last_sync_timestamp=None, tracks_synced=0)
    
    timestamp_str = fields.get("sync-timestamp", [None])[0]
    tracks_str = fields.get("tracks-synced", ["0"])[0]
    
    timestamp = datetime.fromisoformat(timestamp_str) if timestamp_str else None
    tracks = int(tracks_str)
    
    return SyncState(last_sync_timestamp=timestamp, tracks_synced=tracks)
```

### Subtask T014 – write_sync_state Function

**Purpose**: Write sync state to git-annex metadata on sentinel file.

**Steps**:
1. Implement `write_sync_state(repo_path: Path, state: SyncState) -> None`
2. Ensure sentinel file exists (create if needed)
3. Use `AnnexMetadataBatch.set_metadata()` to write fields
4. Format timestamp as ISO 8601 UTC

**Files**: `music_commander/utils/sync_state.py`

**Implementation**:
```python
def write_sync_state(repo_path: Path, state: SyncState) -> None:
    sentinel = repo_path / ".music-commander-sync-state"
    _ensure_sentinel_exists(sentinel)
    
    fields = {
        "sync-timestamp": [state.last_sync_timestamp.isoformat()] if state.last_sync_timestamp else [],
        "tracks-synced": [str(state.tracks_synced)],
    }
    
    with AnnexMetadataBatch(repo_path) as batch:
        batch.set_metadata(sentinel, fields)
```

### Subtask T015 – Sentinel File Creation

**Purpose**: Create sentinel file if it doesn't exist.

**Steps**:
1. Implement `_ensure_sentinel_exists(path: Path) -> None`
2. Create empty file if not exists
3. Add to git-annex: `git annex add .music-commander-sync-state`
4. Handle case where file exists but is not annexed

**Files**: `music_commander/utils/sync_state.py`

**Implementation**:
```python
def _ensure_sentinel_exists(sentinel: Path) -> None:
    if sentinel.exists():
        return
    
    # Create empty sentinel file
    sentinel.write_text("# music-commander sync state - do not edit\n")
    
    # Add to git-annex
    subprocess.run(
        ["git", "annex", "add", str(sentinel)],
        cwd=sentinel.parent,
        check=True,
    )
```

### Subtask T016 – Timestamp Serialization

**Purpose**: Consistent timestamp handling for sync state.

**Steps**:
1. Always use UTC for timestamps
2. Use ISO 8601 format: `2026-01-07T14:30:00+00:00`
3. Add helper function `now_utc() -> datetime` returning timezone-aware UTC datetime
4. Handle parsing of timestamps with/without timezone info

**Files**: `music_commander/utils/sync_state.py`

**Parallel?**: Yes - can be developed independently

**Implementation**:
```python
from datetime import datetime, timezone

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_timestamp(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
```

## Definition of Done Checklist

- [ ] T012: `SyncState` dataclass with `is_first_sync` property
- [ ] T013: `read_sync_state()` returns correct state from sentinel metadata
- [ ] T014: `write_sync_state()` persists state to git-annex metadata
- [ ] T015: Sentinel file created and added to annex if not exists
- [ ] T016: Timestamps use UTC and ISO 8601 format
- [ ] First-run detection works (returns `is_first_sync=True` when no prior sync)
- [ ] State persists across process restarts
- [ ] Type hints pass mypy strict mode

## Risks & Mitigations

- **Sentinel file deleted**: Treat as first sync (sync all tracks)
- **Clock skew**: Use UTC exclusively, log warning if parsed time is in future
- **Annex batch not available**: Fall back to regular `git annex metadata` command

## Review Guidance

- Verify state persists after `git annex sync` to another clone
- Test first-run detection with fresh repo
- Check timestamp parsing handles timezone edge cases

## Activity Log

- 2026-01-07T14:30:00Z – system – lane=planned – Prompt created.
- 2026-01-07T15:15:01Z – claude – shell_pid=1395416 – lane=doing – Started implementation - Sync state management
- 2026-01-07T15:15:34Z – claude – shell_pid=1395416 – lane=for_review – Completed
- 2026-01-07T16:32:44Z – claude-reviewer – shell_pid=1395416 – lane=done – Approved - code passes mypy strict, all functions implemented. Depends on WP02 fixes.
