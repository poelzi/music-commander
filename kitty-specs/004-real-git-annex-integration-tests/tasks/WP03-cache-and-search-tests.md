---
work_package_id: WP03
title: Cache Build & Search Integration Tests
lane: "done"
dependencies: [WP02]
base_branch: 004-real-git-annex-integration-tests-WP02
base_commit: c0006eedf11bf52dd2c7a2b3865976012f3b4db1
created_at: '2026-01-29T18:46:04.524590+00:00'
subtasks:
- T012
- T013
- T014
- T015
- T016
- T017
- T018
- T019
- T020
- T021
- T022
phase: Phase 1 - Core Tests
assignee: ''
agent: "claude-opus"
shell_pid: "323169"
review_status: "approved"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-01-29T17:54:16Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP03 - Cache Build & Search Integration Tests

## Objectives & Success Criteria

- Verify cache build produces correct `file` and `present` fields for all tracks
- Verify metadata is correctly parsed from real git-annex data
- Verify search returns both present and non-present tracks
- All tests pass against real git-annex fixtures

**Done when**: All 11 tests in `test_cache_build.py` and `test_search.py` pass.

## Context & Constraints

- **Plan**: `kitty-specs/004-real-git-annex-integration-tests/plan.md` (test plan section)
- **Source code**: `music_commander/cache/builder.py`, `music_commander/search/query.py`
- Uses fixtures from WP02: `clone_cache_session`, `origin_cache_session`, `partial_clone`
- Import `parse_query` from `music_commander.search.parser` and `execute_search` from `music_commander.search.query`

**Implementation command**: `spec-kitty implement WP03 --base WP02`

## Subtasks & Detailed Guidance

### Subtask T012 - `test_all_tracks_have_file_path`

- **Purpose**: Verify the core bug — all tracks must have `file IS NOT NULL` after cache build, even non-present ones.
- **Steps**:
  1. Query `session.query(CacheTrack).all()`
  2. Assert `len(tracks) == 6`
  3. Assert `all(t.file is not None for t in tracks)`
- **Files**: `tests/integration/test_cache_build.py`

### Subtask T013 - `test_present_field_accuracy`

- **Purpose**: Verify `present` field matches actual local file availability.
- **Steps**:
  1. Query all CacheTrack objects from `clone_cache_session`
  2. Build expected map: tracks 1-3 present=True, tracks 4-6 present=False
  3. Assert each track's `present` matches expected value
- **Files**: `tests/integration/test_cache_build.py`
- **Notes**: Match by filename or artist to identify which track is which

### Subtask T014 - `test_metadata_correctness`

- **Purpose**: Verify metadata parsed from real git-annex matches what was set.
- **Steps**:
  1. For each of the 6 tracks, query by a unique field (e.g., artist)
  2. Assert artist, title, genre, bpm, rating match the plan's track table values
- **Files**: `tests/integration/test_cache_build.py`

### Subtask T015 - `test_crate_data`

- **Purpose**: Verify TrackCrate join table populated correctly.
- **Steps**:
  1. Query `session.query(TrackCrate).all()`
  2. Assert 6 crate entries (one per track)
  3. Verify correct crate names per track
- **Files**: `tests/integration/test_cache_build.py`

### Subtask T016 - `test_incremental_refresh_no_change`

- **Purpose**: Verify refresh returns None when no changes occurred.
- **Steps**:
  1. After initial `build_cache`, call `refresh_cache(repo_path, session)`
  2. Assert result is `None`
- **Files**: `tests/integration/test_cache_build.py`
- **Notes**: Need a fresh session for this test (not the shared session-scoped one) or use `partial_clone` path directly

### Subtask T017 - `test_fts5_search`

- **Purpose**: Verify FTS5 virtual table works with real data.
- **Steps**:
  1. Execute raw SQL: `SELECT key FROM tracks_fts WHERE tracks_fts MATCH 'AlphaArtist'`
  2. Assert 1 result returned
- **Files**: `tests/integration/test_cache_build.py`

### Subtask T018 - `test_search_returns_all_tracks`

- **Purpose**: Verify search doesn't filter by presence.
- **Steps**:
  1. `query = parse_query("")` (empty = match all)
  2. `results = execute_search(session, query)`
  3. Assert `len(results) == 6`
- **Files**: `tests/integration/test_search.py`

### Subtask T019 - `test_field_filter_includes_non_present` [P]

- **Purpose**: Verify field filters include non-present tracks.
- **Steps**:
  1. `query = parse_query("rating:>=4")`
  2. `results = execute_search(session, query)`
  3. Assert `len(results) == 4` (tracks 1,2,3,5 — track 5 is non-present)
  4. Assert at least one result has `present == False`
- **Files**: `tests/integration/test_search.py`

### Subtask T020 - `test_text_search` [P]

- **Purpose**: Verify free-text search via FTS5.
- **Steps**:
  1. `query = parse_query("DarkPulse")`
  2. Assert 1 result with title "DarkPulse"
- **Files**: `tests/integration/test_search.py`

### Subtask T021 - `test_genre_filter` [P]

- **Purpose**: Verify genre filter returns non-present tracks.
- **Steps**:
  1. `query = parse_query("genre:Ambient")`
  2. Assert 2 results (tracks 4, 6 — both non-present)
- **Files**: `tests/integration/test_search.py`

### Subtask T022 - `test_crate_search` [P]

- **Purpose**: Verify crate search works with real data.
- **Steps**:
  1. `query = parse_query("crate:Festival")`
  2. Assert 2 results (tracks 1, 3)
- **Files**: `tests/integration/test_search.py`

## Risks & Mitigations

- **FTS5 availability**: SQLite must be compiled with FTS5 support — nix-provided SQLite includes it
- **Metadata field name mismatches**: git-annex metadata field names must exactly match what `parse_metadata_log()` expects

## Review Guidance

- Key assertion: T012 proves the bug fix — if `file` is NULL for non-present tracks, this test fails
- T013 proves the `present` field is set correctly
- T019 proves search doesn't filter by presence

## Activity Log

- 2026-01-29T17:54:16Z - system - lane=planned - Prompt created.
- 2026-01-29T18:45:59Z – unknown – lane=doing – Moved to doing
- 2026-01-29T18:47:32Z – unknown – lane=for_review – Moved to for_review
- 2026-01-29T20:31:19Z – claude-opus – shell_pid=323169 – lane=doing – Started review via workflow command
- 2026-01-29T20:31:41Z – claude-opus – shell_pid=323169 – lane=done – Review passed: 11/11 tests pass, core bug regression test_all_tracks_have_file_path verified
