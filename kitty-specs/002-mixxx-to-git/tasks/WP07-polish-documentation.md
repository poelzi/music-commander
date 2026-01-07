---
work_package_id: "WP07"
subtasks:
  - "T035"
  - "T036"
  - "T037"
  - "T038"
  - "T039"
  - "T040"
title: "Polish & Documentation"
phase: "Phase 2 - Enhancement"
lane: "planned"
assignee: ""
agent: ""
shell_pid: ""
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-07T14:30:00Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP07 – Polish & Documentation

## Objectives & Success Criteria

- Handle all edge cases gracefully with clear warnings
- Validate quickstart.md scenarios work end-to-end
- Update documentation with sync-metadata command
- Add helpful examples to CLI help text

**Success**: All edge cases handled gracefully; quickstart.md scenarios work; documentation is complete and accurate.

## Context & Constraints

- **Spec**: Edge Cases section, FR-012, FR-014
- **Dependencies**: WP05 (CLI complete)
- **Quickstart**: See `kitty-specs/002-mixxx-to-git/quickstart.md`

## Subtasks & Detailed Guidance

### Subtask T035 – Edge Case: File Not in Repo

**Purpose**: Handle tracks in Mixxx that don't exist in git-annex repo.

**Steps**:
1. Check if file exists at `repo_path / relative_path`
2. If not, add to `skipped` with reason "file not in repository"
3. Log warning with file path
4. Continue processing other tracks

**Files**: `music_commander/commands/sync_metadata.py`

**Parallel?**: Yes - edge case handling is independent

**Implementation**:
```python
def sync_track(track: TrackMetadata, ...) -> tuple[str, str | None]:
    """Returns (status, reason) tuple."""
    full_path = repo_path / track.relative_path
    
    if not full_path.exists():
        return ("skipped", f"file not in repository: {track.relative_path}")
    
    # ... continue with sync
```

### Subtask T036 – Edge Case: Special Characters

**Purpose**: Handle special characters in metadata values.

**Steps**:
1. Identify problematic characters: newlines, tabs, control chars
2. Sanitize values before sending to git-annex
3. Log warning if sanitization changes value significantly
4. Test with real-world metadata (unicode, emojis, etc.)

**Files**: `music_commander/utils/annex_metadata.py`

**Parallel?**: Yes - edge case handling is independent

**Implementation**:
```python
def sanitize_metadata_value(value: str) -> str:
    """Sanitize metadata value for git-annex compatibility."""
    # Replace problematic whitespace
    sanitized = value.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    # Remove control characters
    sanitized = ''.join(c for c in sanitized if ord(c) >= 32 or c in '\t')
    return sanitized.strip()
```

### Subtask T037 – Edge Case: Long Metadata Values

**Purpose**: Handle very long metadata values (e.g., lengthy comments).

**Steps**:
1. Define max length (e.g., 1000 characters)
2. Truncate with "..." suffix if exceeded
3. Log warning with original length
4. Consider: git-annex has no hard limit but large values impact performance

**Files**: `music_commander/utils/annex_metadata.py`

**Parallel?**: Yes - edge case handling is independent

**Implementation**:
```python
MAX_METADATA_LENGTH = 1000

def truncate_if_needed(value: str, field_name: str) -> str:
    """Truncate value if too long, with warning."""
    if len(value) <= MAX_METADATA_LENGTH:
        return value
    
    warning(f"Truncating {field_name}: {len(value)} chars → {MAX_METADATA_LENGTH}")
    return value[:MAX_METADATA_LENGTH - 3] + "..."
```

### Subtask T038 – Validate Quickstart Scenarios

**Purpose**: Ensure documented usage examples work correctly.

**Steps**:
1. Review `kitty-specs/002-mixxx-to-git/quickstart.md`
2. Test each command example:
   - `music-commander sync-metadata`
   - `music-commander sync-metadata --all`
   - `music-commander sync-metadata --dry-run`
   - `music-commander sync-metadata path/to/dir/`
3. Fix any issues found
4. Update quickstart.md if behavior differs

**Files**: `kitty-specs/002-mixxx-to-git/quickstart.md`

**Parallel?**: Yes - can proceed alongside other polish tasks

### Subtask T039 – Update README

**Purpose**: Document sync-metadata command in project README.

**Steps**:
1. Add sync-metadata to command list in README.md
2. Include brief description and common use cases
3. Reference quickstart.md for detailed examples
4. Keep consistent with existing README style

**Files**: `README.md`

**Parallel?**: Yes - documentation is independent

**Section to add**:
```markdown
### Sync Metadata

Sync track metadata from your Mixxx library to git-annex:

```bash
# Sync changed tracks
music-commander sync-metadata

# Force sync all tracks
music-commander sync-metadata --all

# Preview changes
music-commander sync-metadata --dry-run
```

See [quickstart.md](kitty-specs/002-mixxx-to-git/quickstart.md) for more examples.
```

### Subtask T040 – Example in --help Output

**Purpose**: Add useful examples to CLI help text.

**Steps**:
1. Enhance docstring in `sync_metadata.py` command
2. Include common use cases with example commands
3. Follow Click docstring formatting conventions
4. Test with `music-commander sync-metadata --help`

**Files**: `music_commander/commands/sync_metadata.py`

**Parallel?**: Yes - help text is independent

**Enhanced docstring**:
```python
"""Sync Mixxx library metadata to git-annex.

Syncs track metadata (rating, BPM, color, key, artist, title, album,
genre, year, tracknumber, comment, crates) from your Mixxx library to
git-annex metadata on annexed music files.

By default, only tracks modified since the last sync are updated.
Use --all to force a full resync.

\b
Examples:
    # Sync tracks changed since last sync
    music-commander sync-metadata

    # Force sync all tracks (initial setup)
    music-commander sync-metadata --all

    # Preview what would be synced
    music-commander sync-metadata --dry-run

    # Sync only a specific directory
    music-commander sync-metadata ./darkpsy/

    # Sync with commits every 100 files
    music-commander sync-metadata --all --batch-size 100

After syncing, query tracks with git-annex:
    git annex find --metadata rating=5
    git annex find --metadata crate=Festival
"""
```

## Definition of Done Checklist

- [ ] T035: Files not in repo skipped with clear warning
- [ ] T036: Special characters sanitized without data loss
- [ ] T037: Long values truncated with warning
- [ ] T038: All quickstart.md scenarios verified working
- [ ] T039: README updated with sync-metadata documentation
- [ ] T040: Help text includes comprehensive examples
- [ ] All warnings are actionable and user-friendly
- [ ] Documentation is accurate and complete

## Risks & Mitigations

- **Documentation drift**: Keep docs close to implementation, update together
- **Edge case discovery**: Test with real Mixxx databases if available

## Review Guidance

- Try each quickstart.md example manually
- Verify edge case warnings are helpful, not cryptic
- Check README integrates well with existing content
- Run `--help` and verify examples are correct

## Activity Log

- 2026-01-07T14:30:00Z – system – lane=planned – Prompt created.
