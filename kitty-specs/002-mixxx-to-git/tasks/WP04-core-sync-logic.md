---
work_package_id: "WP04"
subtasks:
  - "T017"
  - "T018"
  - "T019"
  - "T020"
  - "T021"
  - "T022"
  - "T023"
title: "Core Sync Logic"
phase: "Phase 1 - MVP"
lane: "planned"
assignee: ""
agent: "claude-reviewer"
shell_pid: "$$"
review_status: "has_feedback"
reviewed_by: "claude-reviewer"
history:
  - timestamp: "2026-01-07T14:30:00Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

## Review Feedback

**Status**: ❌ **Needs Changes**

**Key Issues**:
1. **Wrong import name** (Line 18) - `from music_commander.db.session import create_session` should be `get_session` (the function is named `get_session` in session.py)

2. **Null safety error** (Line 264) - `sync_state.last_sync_timestamp.timestamp()` is called but `last_sync_timestamp` can be `None`. While the logic flow ensures this branch only runs when `sync_all=False` and not first sync, mypy can't verify this. Add an assertion or guard.

3. **Variable shadowing** (Line 296) - `for i, track in track(tracks, ...)` uses `track` as both the loop variable and the imported `rich.progress.track` function. Rename the loop variable to `t` or `item`.

**What Was Done Well**:
- Core sync workflow is well-structured
- `matches_paths()` filter logic is correct
- `SyncResult` dataclass properly defined in models.py
- Dry-run mode implemented
- Progress tracking with Rich integrated
- Summary reporting with table output

**Action Items** (must complete before re-review):
- [ ] Fix import: change `create_session` to `get_session` on line 18
- [ ] Fix null safety: add `assert sync_state.last_sync_timestamp is not None` before line 264, or restructure logic
- [ ] Fix variable shadowing: rename loop variable `track` to avoid shadowing `rich.progress.track` import

# Work Package Prompt: WP04 – Core Sync Logic 🎯 MVP

## Objectives & Success Criteria

- Implement main sync workflow: query Mixxx → filter → transform → write to annex
- Support change detection (sync only modified tracks by default)
- Implement path matching to filter tracks within repo
- Track sync results: synced, skipped, failed
- Show progress during sync and summary at completion

**Success**: Running sync on a Mixxx DB updates git-annex metadata correctly with progress feedback.

## Context & Constraints

- **Dependencies**: WP01 (queries), WP02 (batch wrapper), WP03 (sync state)
- **Performance**: 1000 tracks in <60 seconds (SC-001)
- **Data model**: See `kitty-specs/002-mixxx-to-git/data-model.md` for entity definitions
- **Spec**: User Story 1 (P1) - Sync Changed Tracks

### Sync Flow (from data-model.md)

```
[Loading Config] → [Reading Sync State] → [Querying Mixxx DB]
     → [Matching Paths] → [Transforming Metadata] → [Writing to Git-Annex]
     → [Committing Changes] → [Updating Sync State] → [Reporting Summary]
```

## Subtasks & Detailed Guidance

### Subtask T017 – Core Sync Function

**Purpose**: Main orchestration function for the sync workflow.

**Steps**:
1. Create `music_commander/commands/sync_metadata.py`
2. Implement `sync_tracks(config, sync_all: bool = False) -> SyncResult`
3. Orchestrate: load state → query → filter → transform → write → commit → update state
4. Use generator pattern for memory efficiency

**Files**: `music_commander/commands/sync_metadata.py` (new file)

**Signature**:
```python
def sync_tracks(
    config: Config,
    sync_all: bool = False,
    paths: list[Path] | None = None,
    dry_run: bool = False,
    batch_size: int | None = None,
) -> SyncResult:
    """
    Sync Mixxx metadata to git-annex.
    
    Args:
        config: Application configuration
        sync_all: If True, sync all tracks regardless of change status
        paths: If provided, only sync tracks matching these paths
        dry_run: If True, show what would be synced without making changes
        batch_size: If provided, commit every N files
    
    Returns:
        SyncResult with synced, skipped, and failed counts
    """
```

### Subtask T018 – Track Filtering

**Purpose**: Filter tracks based on change status or --all flag.

**Steps**:
1. Read sync state to get last sync timestamp
2. If `sync_all=True` or first sync, use `get_all_tracks()`
3. Otherwise, use `get_changed_tracks(since_timestamp_ms)`
4. Convert Mixxx timestamp to milliseconds for comparison

**Files**: `music_commander/commands/sync_metadata.py`

**Logic**:
```python
sync_state = read_sync_state(config.music_repo)

if sync_all or sync_state.is_first_sync:
    tracks = get_all_tracks(session, config.music_repo)
else:
    since_ms = int(sync_state.last_sync_timestamp.timestamp() * 1000)
    tracks = get_changed_tracks(session, config.music_repo, since_ms)
```

### Subtask T019 – Path Matching Filter

**Purpose**: Filter tracks to only those within the repo and matching user paths.

**Steps**:
1. Skip tracks where `relative_path is None` (not under repo)
2. If `paths` argument provided, filter to matching paths
3. Log skipped tracks with warning
4. Support both file and directory path filters

**Files**: `music_commander/commands/sync_metadata.py`

**Logic**:
```python
def matches_paths(track: TrackMetadata, paths: list[Path] | None) -> bool:
    if paths is None:
        return True
    for p in paths:
        if track.relative_path == p or track.relative_path.is_relative_to(p):
            return True
    return False
```

### Subtask T020 – Metadata Transformation

**Purpose**: Convert Mixxx fields to git-annex format.

**Steps**:
1. Use transformation functions from WP02 (T011)
2. Build `fields` dict with only non-None values
3. Convert all values to list format for git-annex
4. Handle multi-value `crate` field

**Files**: `music_commander/commands/sync_metadata.py`

**Logic**:
```python
def build_annex_fields(track: TrackMetadata) -> dict[str, list[str]]:
    fields = {}
    
    if (v := transform_rating(track.rating)):
        fields["rating"] = [v]
    if (v := transform_bpm(track.bpm)):
        fields["bpm"] = [v]
    if (v := transform_color(track.color)):
        fields["color"] = [v]
    if track.key:
        fields["key"] = [track.key]
    # ... repeat for other fields
    if track.crates:
        fields["crate"] = track.crates  # Already a list
    
    return fields
```

### Subtask T021 – Batch Write with Progress

**Purpose**: Write metadata to git-annex with progress tracking.

**Steps**:
1. Use `AnnexMetadataBatch` context manager
2. Show Rich progress bar during batch write
3. If `batch_size` provided, commit every N files
4. Collect results for each file (success/failure)

**Files**: `music_commander/commands/sync_metadata.py`

**Logic**:
```python
from music_commander.utils.output import create_progress

with AnnexMetadataBatch(config.music_repo) as batch:
    with create_progress() as progress:
        task = progress.add_task("Syncing metadata...", total=track_count)
        
        for i, track in enumerate(tracks):
            fields = build_annex_fields(track)
            success = batch.set_metadata(track.relative_path, fields)
            
            if success:
                result.synced.append(track.relative_path)
            else:
                result.failed.append((track.relative_path, "annex error"))
            
            progress.advance(task)
            
            if batch_size and (i + 1) % batch_size == 0:
                batch.commit()
```

### Subtask T022 – SyncResult Dataclass

**Purpose**: Track sync operation results.

**Steps**:
1. Add `SyncResult` to `music_commander/db/models.py`
2. Include lists: `synced`, `skipped`, `failed`
3. Add computed properties: `success`, `total_requested`
4. Add `summary()` method for human-readable output

**Files**: `music_commander/db/models.py`

**Parallel?**: Yes - can be developed independently

**Definition**:
```python
@dataclass
class SyncResult:
    synced: list[Path] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)
    
    @property
    def total_requested(self) -> int:
        return len(self.synced) + len(self.skipped) + len(self.failed)
    
    @property
    def success(self) -> bool:
        return len(self.failed) == 0
```

### Subtask T023 – Summary Reporting

**Purpose**: Display sync results to user at completion.

**Steps**:
1. Create Rich table with sync summary
2. Show counts: synced, skipped, failed
3. If failed, list failed files with reasons
4. Use existing `music_commander/utils/output.py` utilities

**Files**: `music_commander/commands/sync_metadata.py`

**Parallel?**: Yes - can be developed alongside T022

**Output format**:
```
┌─────────────────────────────────┐
│        Sync Summary             │
├──────────┬──────┬───────────────┤
│ Status   │ Count│ Details       │
├──────────┼──────┼───────────────┤
│ Synced   │  523 │ Updated       │
│ Skipped  │   12 │ Not in repo   │
│ Failed   │    2 │ Annex errors  │
└──────────┴──────┴───────────────┘

All files processed successfully!
```

## Definition of Done Checklist

- [ ] T017: Core `sync_tracks()` function orchestrates full workflow
- [ ] T018: Change detection filters tracks correctly
- [ ] T019: Path matching filters to repo and user-specified paths
- [ ] T020: Metadata transformation handles all field types
- [ ] T021: Batch write shows progress and handles batch commits
- [ ] T022: `SyncResult` tracks all outcome categories
- [ ] T023: Summary displays clearly at completion
- [ ] Dry-run mode shows what would be synced without changes
- [ ] Memory efficient with large track counts (generator pattern)
- [ ] Type hints pass mypy strict mode

## Risks & Mitigations

- **Memory with large libraries**: Use generator pattern, don't load all tracks into memory
- **Partial failures**: Log per-file errors, continue processing, report summary
- **Interrupted sync**: State not updated until completion (safe to re-run)

## Review Guidance

- Verify change detection filters correctly
- Test with real Mixxx database if available
- Check progress bar updates smoothly
- Confirm dry-run makes no changes

## Activity Log

- 2026-01-07T14:30:00Z – system – lane=planned – Prompt created.
- 2026-01-07T15:15:34Z – claude – shell_pid=1395416 – lane=doing – Started - Core sync logic
- 2026-01-07T15:17:36Z – claude – shell_pid=1395416 – lane=for_review – Completed
- 2026-01-07T17:12:00Z – claude-reviewer – shell_pid=$$ – lane=planned – Code review: needs changes - wrong import (create_session→get_session), null safety on timestamp, variable shadowing in loop
