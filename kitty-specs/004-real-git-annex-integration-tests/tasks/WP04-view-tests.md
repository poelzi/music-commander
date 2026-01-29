---
work_package_id: "WP04"
subtasks:
  - "T023"
  - "T024"
  - "T025"
  - "T026"
  - "T027"
  - "T028"
title: "View Integration Tests"
phase: "Phase 1 - Core Tests"
lane: "planned"
assignee: ""
agent: ""
shell_pid: ""
review_status: ""
reviewed_by: ""
dependencies: ["WP02"]
history:
  - timestamp: "2026-01-29T17:54:16Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP04 - View Integration Tests

## Objectives & Success Criteria

- Verify `--include-missing` produces strictly more symlinks than the default
- Verify symlink targets point to correct file paths
- Verify view against full repo shows no difference with/without the flag
- All 6 tests pass

**Done when**: `test_view_with_include_missing` proves the flag has measurable effect, and all view tests pass.

## Context & Constraints

- **Plan**: `kitty-specs/004-real-git-annex-integration-tests/plan.md` (view test section)
- **Source code**: `music_commander/view/symlinks.py` (`create_symlink_tree`, `cleanup_output_dir`)
- Uses fixtures from WP02: `clone_cache_session`, `origin_cache_session`, `partial_clone`, `origin_repo`
- Each test uses its own `tmp_path` for view output (not session-scoped)
- Call `create_symlink_tree()` directly — not via CLI

**Implementation command**: `spec-kitty implement WP04 --base WP02`

## Subtasks & Detailed Guidance

### Subtask T023 - `test_view_without_include_missing`

- **Purpose**: Baseline — only present files get symlinks.
- **Steps**:
  1. Use `clone_cache_session` to get session and `partial_clone` for repo path
  2. `query = parse_query("rating:>=4")`
  3. `tracks = execute_search(session, query)` — should return 4 tracks
  4. Load crate data for tracks
  5. `created, dupes = create_symlink_tree(tracks, crates_by_key, template, output_dir, repo_path, include_missing=False)`
  6. Assert `created == 3` (only present tracks 1, 2, 3)
- **Files**: `tests/integration/test_view.py`
- **Notes**: Template: `"{{ genre }}/{{ artist }} - {{ title }}"`

### Subtask T024 - `test_view_with_include_missing`

- **Purpose**: THE key regression test — flag must produce more symlinks.
- **Steps**:
  1. Same setup as T023
  2. `created_with, dupes = create_symlink_tree(..., include_missing=True)`
  3. Assert `created_with == 4` (all matching tracks including non-present track 5)
  4. Assert `created_with > 3` (strictly greater than without flag)
- **Files**: `tests/integration/test_view.py`
- **Notes**: If this test fails, the `--include-missing` bug is NOT fixed

### Subtask T025 - `test_symlink_targets_correct`

- **Purpose**: Verify symlinks point to correct repo paths.
- **Steps**:
  1. Create view with `include_missing=True`
  2. Walk the output directory, find all symlinks
  3. For each symlink, resolve its target and verify it points to a valid path relative to repo_path
  4. Verify the target filename matches expected track files
- **Files**: `tests/integration/test_view.py`

### Subtask T026 - `test_view_full_repo_no_difference` [P]

- **Purpose**: When all files present, flag has no effect.
- **Steps**:
  1. Use `origin_cache_session` and `origin_repo`
  2. Run view with `include_missing=False` — count symlinks
  3. Run view with `include_missing=True` — count symlinks
  4. Assert counts are equal
- **Files**: `tests/integration/test_view.py`

### Subtask T027 - `test_template_rendering` [P]

- **Purpose**: Verify template produces expected directory structure.
- **Steps**:
  1. Use template `"{{ genre }}/{{ artist }} - {{ title }}"`
  2. Create view with all tracks
  3. Verify directory structure: `Darkpsy/AlphaArtist - DarkPulse.mp3` exists, etc.
  4. Check at least 2-3 specific paths
- **Files**: `tests/integration/test_view.py`

### Subtask T028 - `test_duplicate_handling` [P]

- **Purpose**: Verify numeric suffix when template produces duplicate paths.
- **Steps**:
  1. Use template `"all/track"` (same path for every track)
  2. Create view with all 6 tracks (use `include_missing=True` against origin repo)
  3. Assert `created == 6`
  4. Assert `duplicates == 5`
  5. Verify files like `all/track.mp3`, `all/track_1.flac`, `all/track_2.aiff` exist
- **Files**: `tests/integration/test_view.py`
- **Notes**: Extension is auto-appended from original file

## Risks & Mitigations

- **Bug not fixed**: T023/T024 will fail if `build_key_to_file_map()` still uses `--branch HEAD` — this is the expected behavior of a regression test
- **Symlink target resolution**: Relative symlinks may need careful path comparison — use `os.readlink()` and compare against expected relative path
- **Output dir cleanup**: Each test uses fresh `tmp_path` so no cleanup needed between tests

## Review Guidance

- **Critical**: T024 is THE test. If `created_with == created_without`, the bug is present.
- Verify T025 actually reads symlink targets (not just checks existence)
- Verify T028 uses a template that genuinely produces collisions

## Activity Log

- 2026-01-29T17:54:16Z - system - lane=planned - Prompt created.
