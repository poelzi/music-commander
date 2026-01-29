---
work_package_id: WP05
title: Mock Test Cleanup
lane: planned
dependencies:
- WP03
subtasks:
- T029
- T030
- T031
- T032
- T033
- T034
phase: Phase 2 - Polish
assignee: ''
agent: ''
shell_pid: ''
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-01-29T17:54:16Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP05 - Mock Test Cleanup

## Objectives & Success Criteria

- Remove mock-heavy test classes that are now covered by integration tests
- Preserve pure-logic test classes (parser, decoder, metadata conversion)
- Relocate orphaned standalone tests to appropriate locations
- Full test suite passes after cleanup

**Done when**: `pytest tests/` passes with no failures, mock-heavy classes are removed, pure-logic classes preserved.

## Context & Constraints

- **Plan**: `kitty-specs/004-real-git-annex-integration-tests/plan.md` (mock test removal section)
- **Spec clarification**: Keep both files, remove only mock-heavy classes
- Integration tests from WP03/WP04 must exist and pass BEFORE removing mocks

**Implementation command**: `spec-kitty implement WP05 --base WP04`

## Subtasks & Detailed Guidance

### Subtask T029 - Remove `TestBuildCache` class [P]

- **Purpose**: Replaced by `tests/integration/test_cache_build.py`.
- **Steps**: Delete the `TestBuildCache` class (3 methods: `test_full_build`, `test_build_with_crates`, `test_build_indexes_unmapped_keys`)
- **Files**: `tests/unit/test_cache_builder.py`
- **Notes**: This class uses `@patch("music_commander.cache.builder.subprocess.run")` — all its scenarios are covered by real git-annex integration tests

### Subtask T030 - Remove `TestRefreshCache` class [P]

- **Purpose**: Replaced by integration test `test_incremental_refresh_no_change`.
- **Steps**: Delete the `TestRefreshCache` class (4 methods: `test_no_change_returns_none`, `test_incremental_update`, `test_no_metadata_changes`, `test_no_state_triggers_full_build`)
- **Files**: `tests/unit/test_cache_builder.py`

### Subtask T031 - Remove `TestFTS5` class [P]

- **Purpose**: Replaced by integration test `test_fts5_search`.
- **Steps**: Delete the `TestFTS5` class (1 method: `test_fts5_populated_after_build`)
- **Files**: `tests/unit/test_cache_builder.py`
- **Notes**: This class has its own `_setup_session` method that can also be removed

### Subtask T032 - Remove `TestE2EPipeline` and mock infrastructure [P]

- **Purpose**: Entire pipeline now tested via real git-annex integration tests.
- **Steps**:
  1. Delete the `TestE2EPipeline` class (8 methods)
  2. Delete module-level mock constants: `_LOG_TRACK1`, `_LOG_TRACK2`, `_LS_TREE`, `_CAT_FILE`, `_ANNEX_FIND_ALL`, `_ANNEX_FIND_PRESENT`
  3. Delete `_mock_subprocess_run` function
  4. Check if any imports are now unused and remove them
- **Files**: `tests/unit/test_e2e_search_view.py`
- **Notes**: After removal, this file may be empty. If so, delete the entire file.

### Subtask T033 - Relocate orphaned tests

- **Purpose**: `test_render_path_integration` and `test_delete_cache` are standalone methods inside `TestE2EPipeline` that don't use mocks.
- **Steps**:
  1. `test_render_path_integration`: Move to `tests/unit/test_view_template.py` as a new test method (it tests `render_path()` with `round_to` filter — pure logic)
  2. `test_delete_cache`: Move to `tests/unit/test_cache_models.py` or create in integration tests (it tests `delete_cache()` filesystem operation)
  3. Ensure both tests pass in their new locations
- **Files**: `tests/unit/test_view_template.py`, `tests/unit/test_cache_models.py` (or equivalent)

### Subtask T034 - Run full test suite verification

- **Purpose**: Ensure nothing is broken after cleanup.
- **Steps**:
  1. Run `pytest tests/unit/ -v` — all unit tests pass
  2. Run `pytest tests/integration/ -v` — all integration tests pass
  3. Run `pytest tests/ -v` — full suite passes
  4. Verify test count: unit tests should have ~26 fewer methods (removed mocks), integration tests should add ~17 new methods
- **Files**: N/A (verification only)

## Risks & Mitigations

- **Accidentally removing pure-logic tests**: Double-check class names against the keep list:
  - KEEP: `TestParseMetadataLog` (14), `TestDecodeValue` (3), `TestExtractKeyFromPath` (3), `TestMetadataToTrack` (4), `TestMetadataToCrates` (2)
  - REMOVE: `TestBuildCache` (3), `TestRefreshCache` (4), `TestFTS5` (1), `TestE2EPipeline` (8)
- **Orphaned imports**: After removing classes, check for unused imports (`MagicMock`, `patch`, `create_engine`, etc.) and clean them up
- **test_e2e_search_view.py might become empty**: If so, delete the file entirely rather than leaving an empty module

## Review Guidance

- Verify the keep/remove class list matches what was agreed
- Run `pytest tests/ -v` and compare test count before/after
- Ensure no `from unittest.mock import` remains in files where all mock users were removed

## Activity Log

- 2026-01-29T17:54:16Z - system - lane=planned - Prompt created.
