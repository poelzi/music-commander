---
work_package_id: "WP06"
subtasks:
  - "T031"
  - "T032"
  - "T033"
  - "T034"
title: "Crate Sync & Multi-Value Fields"
phase: "Phase 2 - Enhancement"
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

# Work Package Prompt: WP06 – Crate Sync & Multi-Value Fields

## Objectives & Success Criteria

- Extend Mixxx query to include crate membership per track
- Implement crate name sanitization for git-annex compatibility
- Handle multi-value `crate` field in git-annex metadata
- Support crate removal (track removed from crate in Mixxx)

**Success**: Track in multiple crates shows all crate names in git-annex metadata; removing track from crate in Mixxx removes that crate from annex metadata.

## Context & Constraints

- **Spec**: User Story 6 (P3) - Crate Sync as Tags
- **Research**: Crate tables documented in `research.md`
- **Dependencies**: WP01 (queries), WP02 (batch wrapper)

### Crate Schema Reference

```
crates
├── id (PK)
└── name (VARCHAR 48, UNIQUE)

crate_tracks (junction table)
├── crate_id (FK → crates.id)
└── track_id (FK → library.id)
```

## Subtasks & Detailed Guidance

### Subtask T031 – Extend Query for Crates

**Purpose**: Include crate membership in track metadata query.

**Steps**:
1. Modify `get_all_tracks()` to include crate names
2. Add subquery or separate query for crate membership
3. Group crate names by track ID
4. Return as `crates: list[str]` in `TrackMetadata`

**Files**: `music_commander/db/queries.py`

**Query pattern**:
```python
def get_track_crates(session: Session, track_id: int) -> list[str]:
    """Get all crate names for a track."""
    result = session.execute(
        text("""
            SELECT c.name
            FROM crate_tracks ct
            JOIN crates c ON ct.crate_id = c.id
            WHERE ct.track_id = :track_id
            ORDER BY c.name
        """),
        {"track_id": track_id}
    )
    return [row[0] for row in result]
```

### Subtask T032 – Crate Name Sanitization

**Purpose**: Ensure crate names are safe for git-annex metadata.

**Steps**:
1. Create `sanitize_crate_name(name: str) -> str`
2. Replace/remove characters that may cause issues:
   - Newlines, tabs → space
   - Control characters → remove
   - Leading/trailing whitespace → trim
3. Log warning if sanitization changes the name

**Files**: `music_commander/utils/annex_metadata.py`

**Parallel?**: Yes - can be developed independently

**Implementation**:
```python
import re

def sanitize_crate_name(name: str) -> str:
    """Sanitize crate name for git-annex metadata compatibility."""
    # Replace whitespace with single space
    sanitized = re.sub(r'\s+', ' ', name)
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
    # Trim
    sanitized = sanitized.strip()
    return sanitized
```

### Subtask T033 – Multi-Value Field Handling

**Purpose**: Properly handle crate as multi-value git-annex field.

**Steps**:
1. Ensure `set_metadata()` accepts list of strings for `crate` field
2. Verify git-annex stores all values: `{"crate": ["Crate1", "Crate2"]}`
3. Test querying: `git annex find --metadata crate=Crate1`

**Files**: `music_commander/utils/annex_metadata.py`

**Verification**:
```bash
# After sync, verify multi-value:
git annex metadata --json track.flac | jq '.fields.crate'
# Should output: ["Crate1", "Crate2"]

# Query works for any value:
git annex find --metadata crate=Crate1
git annex find --metadata crate=Crate2
```

### Subtask T034 – Crate Removal Handling

**Purpose**: Remove crate tags when track is removed from crate in Mixxx.

**Steps**:
1. When syncing, set `crate` field to current list (replaces all previous)
2. Empty list `[]` removes all crate tags
3. Git-annex batch mode handles this: `{"crate": []}` removes field

**Files**: `music_commander/commands/sync_metadata.py`

**Logic**:
```python
def build_annex_fields(track: TrackMetadata) -> dict[str, list[str]]:
    fields = {}
    # ... other fields ...
    
    # Crates: set to current list (replaces previous)
    # Empty list removes all crate metadata
    if track.crates:
        fields["crate"] = [sanitize_crate_name(c) for c in track.crates]
    else:
        fields["crate"] = []  # Explicitly remove if no crates
    
    return fields
```

## Definition of Done Checklist

- [ ] T031: Crate membership included in track metadata
- [ ] T032: Crate names sanitized for git-annex compatibility
- [ ] T033: Multi-value crate field works correctly
- [ ] T034: Removing track from crate removes crate tag
- [ ] Can query tracks by crate: `git annex find --metadata crate=X`
- [ ] Type hints pass mypy strict mode

## Risks & Mitigations

- **Very long crate lists**: No practical limit, but warn if >50 crates per track
- **Special characters in crate names**: Sanitization handles safely
- **Empty crate names**: Skip empty/whitespace-only crate names

## Review Guidance

- Test with track in multiple crates
- Test removing track from one crate (should keep others)
- Test removing track from all crates (should remove field)
- Verify `git annex find --metadata crate=X` works

## Activity Log

- 2026-01-07T14:30:00Z – system – lane=planned – Prompt created.
- 2026-01-07T15:17:36Z – claude – shell_pid=1395416 – lane=for_review – Completed
- 2026-01-07T16:36:13Z – claude-reviewer – shell_pid=1395416 – lane=done – Approved - crate query, sanitization, and multi-value handling all implemented correctly. Depends on WP02 fixes for full functionality.
