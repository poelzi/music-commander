---
work_package_id: "WP06"
subtasks:
  - "T041"
  - "T042"
  - "T043"
  - "T044"
  - "T045"
title: "Polish & Integration"
phase: "Phase 2 - Polish"
lane: "planned"
dependencies: ["WP04", "WP05"]
assignee: ""
agent: ""
shell_pid: ""
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-29T02:41:50Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP06 -- Polish & Integration

## Implementation Command

```bash
spec-kitty implement WP06 --base WP05
```

## Objectives & Success Criteria

- End-to-end workflow validated on real 100k+ track repository
- Edge cases handled: empty repo, no metadata, corrupt cache
- Cache management flags (`--rebuild-cache`)
- `.gitignore` updated for cache DB
- Integration test covering full pipeline: sync → cache → search → view

## Context & Constraints

- Constitution: performance must handle 100k+ tracks
- All previous WPs must be complete

## Subtasks & Detailed Guidance

### Subtask T041 -- Gitignore for cache DB
- **Purpose**: Prevent cache DB from being committed.
- **Files**: `music_commander/commands/init_config.py`, root `.gitignore`
- **Steps**:
  1. Add `.music-commander-cache.db` to generated `.gitignore` in init-config
  2. Add to project root `.gitignore` if present

### Subtask T042 -- --rebuild-cache flag
- **Purpose**: Allow users to force a full cache rebuild.
- **Files**: `music_commander/commands/search.py`, `music_commander/commands/view.py`
- **Steps**:
  1. Add `--rebuild-cache` flag to both search and view commands
  2. When set, delete existing cache and trigger full build
- **Parallel?**: Yes, independent flag addition.

### Subtask T043 -- Edge case handling
- **Purpose**: Graceful handling of error conditions.
- **Files**: Various
- **Steps**:
  1. Empty repo (no annexed files) → "No tracks found" message
  2. No metadata synced → "No metadata in git-annex. Run sync-metadata first."
  3. Corrupt cache file → delete and rebuild
  4. Search with no results → "No tracks match the query"

### Subtask T044 -- Performance validation
- **Purpose**: Verify acceptable performance on real repo.
- **Steps**:
  1. Run cache build on 100k+ track repo — target < 30 seconds
  2. Run various search queries — target < 1 second per query
  3. Run view export with 10k results — target < 10 seconds
  4. Document results

### Subtask T045 -- End-to-end integration test
- **Files**: `tests/test_e2e_search_view.py`
- **Steps**:
  1. Create test fixture with small git-annex repo (mock or temp)
  2. Sync metadata → build cache → search → verify results → create view → verify symlinks
  3. Test incremental: modify metadata → refresh cache → re-search → verify updated results

## Test Strategy

- E2E test with temporary git-annex repo (if feasible)
- Otherwise, mock git commands for deterministic testing
- Performance testing is manual (not in CI)

## Risks & Mitigations

- E2E test setup complexity — keep test repo small (10-20 files)
- Performance regression — document baseline benchmarks

## Review Guidance

- Verify edge cases produce user-friendly messages
- Verify cache rebuild works cleanly
- Check performance numbers are documented

## Activity Log

- 2026-01-29T02:41:50Z -- system -- lane=planned -- Prompt created.
