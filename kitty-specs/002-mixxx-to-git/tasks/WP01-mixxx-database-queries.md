---
work_package_id: "WP01"
subtasks:
  - "T001"
  - "T002"
  - "T003"
  - "T004"
  - "T005"
title: "Mixxx Database Queries"
phase: "Phase 0 - Foundation"
lane: "for_review"
assignee: ""
agent: "claude"
shell_pid: "1428338"
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
1. **Test fixture missing `source_synchronized_ms` column** - The `conftest.py` sample database fixture does not include the `source_synchronized_ms` column in the `library` table schema. This causes tests to fail with `sqlite3.OperationalError: no such column: library.source_synchronized_ms`.

2. **T003: NULL handling not implemented** - The `get_changed_tracks()` function filters by `source_synchronized_ms > since_timestamp_ms`, but the task specifies that tracks with NULL `source_synchronized_ms` should be treated as changed. Currently, NULL values are excluded.

**What Was Done Well**:
- All required functions (`get_all_tracks`, `get_track_crates`, `get_changed_tracks`, `to_relative_path`) are implemented correctly in `queries.py`
- `TrackMetadata` dataclass is properly defined with correct types in `models.py`
- Type hints pass mypy strict mode
- Query joins are correct per Mixxx schema
- Path matching handles edge cases correctly with `resolve()` before `relative_to()`
- Iterator pattern used for memory efficiency
- NULL handling is graceful for optional fields

**Action Items** (must complete before re-review):
- [ ] Update `tests/conftest.py` to add `source_synchronized_ms INTEGER` column to the `library` table schema in `sample_mixxx_db` fixture
- [ ] Fix `get_changed_tracks()` to include tracks where `source_synchronized_ms IS NULL` (treat as changed per T003 spec)

# Work Package Prompt: WP01 – Mixxx Database Queries

## Objectives & Success Criteria

- Create SQLAlchemy query functions to extract track metadata from Mixxx database
- Create query for crate membership (track → crates relationship)
- Implement change detection based on `source_synchronized_ms` timestamp
- Create `TrackMetadata` dataclass to hold extracted data
- Implement path matching to convert Mixxx absolute paths to repo-relative paths

**Success**: Query functions return correct metadata for all tracks in a Mixxx database, with proper handling of NULL values and path conversion.

## Context & Constraints

- **Existing code**: `music_commander/db/mixxx.py` has SQLAlchemy session setup
- **Research**: See `kitty-specs/002-mixxx-to-git/research.md` for Mixxx schema details
- **Data model**: See `kitty-specs/002-mixxx-to-git/data-model.md` for `TrackMetadata` fields

### Mixxx Schema Reference

```
library (main metadata)
├── id (PK)
├── location (FK → track_locations.id)
├── artist, title, album, genre, year, tracknumber, comment
├── rating (0-5), bpm (float), color (int RGB), key (str)
└── source_synchronized_ms (change detection timestamp)

track_locations (file paths)
├── id (PK)
└── location (VARCHAR - full absolute path)

crates / crate_tracks (M:N relationship)
├── crates.id, crates.name
└── crate_tracks.crate_id, crate_tracks.track_id
```

## Subtasks & Detailed Guidance

### Subtask T001 – Track Metadata Query Function

**Purpose**: Query all track metadata from Mixxx database with joined file path.

**Steps**:
1. Create `music_commander/db/queries.py`
2. Implement `get_all_tracks(session, music_repo: Path) -> Iterator[TrackMetadata]`
3. Join `library` with `track_locations` on `library.location = track_locations.id`
4. Select all metadata fields listed in research.md
5. Yield `TrackMetadata` instances

**Files**: `music_commander/db/queries.py` (new file)

**SQL Pattern**:
```sql
SELECT l.*, tl.location as file_path
FROM library l
JOIN track_locations tl ON l.location = tl.id
WHERE tl.location LIKE :music_repo_prefix || '%'
```

### Subtask T002 – Crate Membership Query

**Purpose**: Get all crate names for each track.

**Steps**:
1. Add `get_track_crates(session, track_id: int) -> list[str]`
2. Join `crate_tracks` with `crates` to get crate names
3. Return list of crate names for the given track ID

**Files**: `music_commander/db/queries.py`

**SQL Pattern**:
```sql
SELECT c.name
FROM crate_tracks ct
JOIN crates c ON ct.crate_id = c.id
WHERE ct.track_id = :track_id
```

**Parallel?**: Yes - can be developed alongside T001

### Subtask T003 – Change Detection Query

**Purpose**: Filter tracks that have changed since last sync.

**Steps**:
1. Add `get_changed_tracks(session, music_repo: Path, since_timestamp_ms: int) -> Iterator[TrackMetadata]`
2. Add WHERE clause: `source_synchronized_ms > :since_timestamp_ms`
3. Handle case where `source_synchronized_ms` is NULL (treat as changed)

**Files**: `music_commander/db/queries.py`

### Subtask T004 – TrackMetadata Dataclass

**Purpose**: Type-safe container for track metadata.

**Steps**:
1. Create `music_commander/db/models.py` (or add to existing)
2. Define `TrackMetadata` dataclass with all fields from data-model.md
3. Use `Path` for file paths, `int | None` for optional integers, etc.
4. Add `relative_path` computed from `file_path` and `music_repo`

**Files**: `music_commander/db/models.py`

**Definition**:
```python
@dataclass
class TrackMetadata:
    file_path: Path
    relative_path: Path
    rating: int | None
    bpm: float | None
    color: int | None
    key: str | None
    artist: str | None
    title: str | None
    album: str | None
    genre: str | None
    year: str | None
    tracknumber: str | None
    comment: str | None
    crates: list[str]
    source_synchronized_ms: int | None
```

**Parallel?**: Yes - can be developed first as other subtasks depend on it

### Subtask T005 – Path Matching Logic

**Purpose**: Convert Mixxx absolute paths to repo-relative paths.

**Steps**:
1. Add helper function `to_relative_path(absolute_path: Path, music_repo: Path) -> Path | None`
2. Use `Path.relative_to()` for conversion
3. Return `None` if path is not under `music_repo` (for filtering)
4. Handle edge cases: trailing slashes, case sensitivity

**Files**: `music_commander/db/queries.py` or `music_commander/utils/paths.py`

**Example**:
```python
def to_relative_path(absolute_path: Path, music_repo: Path) -> Path | None:
    try:
        return absolute_path.relative_to(music_repo)
    except ValueError:
        return None  # Path not under music_repo
```

## Definition of Done Checklist

- [ ] T001: `get_all_tracks()` returns iterator of TrackMetadata with all fields populated
- [ ] T002: `get_track_crates()` returns list of crate names for a track
- [ ] T003: `get_changed_tracks()` filters by timestamp correctly
- [ ] T004: `TrackMetadata` dataclass defined with proper types
- [ ] T005: Path conversion works for paths under music_repo, returns None otherwise
- [ ] All functions handle NULL database values gracefully
- [ ] Type hints pass mypy strict mode

## Review Guidance

- Verify query joins are correct per Mixxx schema
- Check NULL handling for all optional fields
- Verify path matching handles edge cases (symlinks, relative inputs)
- Confirm iterator pattern used for memory efficiency

## Activity Log

- 2026-01-07T14:30:00Z – system – lane=planned – Prompt created.
- 2026-01-07T14:36:50Z – claude – shell_pid=1380800 – lane=doing – Started implementation
- 2026-01-07T15:13:41Z – claude – shell_pid=1395416 – lane=for_review – Completed implementation - ready for review
- 2026-01-07T16:58:00Z – claude-reviewer – shell_pid=$$ – lane=planned – Code review: needs changes - test fixture missing source_synchronized_ms column, get_changed_tracks missing NULL handling
- 2026-01-07T17:12:11Z – claude – shell_pid=1428338 – lane=doing – Addressing review feedback: fixing test fixture and NULL handling
- 2026-01-07T17:14:01Z – claude – shell_pid=1428338 – lane=for_review – Addressed all feedback: added source_synchronized_ms to test fixture, fixed NULL handling in get_changed_tracks()
