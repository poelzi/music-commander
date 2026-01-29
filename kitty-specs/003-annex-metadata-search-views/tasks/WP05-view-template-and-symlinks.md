---
work_package_id: "WP05"
subtasks:
  - "T029"
  - "T030"
  - "T031"
  - "T032"
  - "T033"
  - "T034"
  - "T035"
  - "T036"
  - "T037"
  - "T038"
  - "T039"
  - "T040"
title: "View Template & Symlink Export"
phase: "Phase 1 - Core"
lane: "doing"
dependencies: ["WP04"]
assignee: ""
agent: "claude-opus"
shell_pid: "194846"
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-29T02:41:50Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP05 -- View Template & Symlink Export

## Implementation Command

```bash
spec-kitty implement WP05 --base WP04
```

## Objectives & Success Criteria

- Render Jinja2 path templates with track metadata
- Create symlink directory trees from search results
- Handle multi-value fields (crate) by creating one symlink per value
- Sanitize paths for filesystem safety
- Handle duplicate paths with numeric suffixes
- Clean up old view directories before regenerating
- CLI `view` command with `--pattern`, `--output`, `--absolute` flags
- Unit and integration tests

## Context & Constraints

- Spec: FR-012 through FR-023
- Plan: `kitty-specs/003-annex-metadata-search-views/plan.md` — View Pipeline section
- Data model: `kitty-specs/003-annex-metadata-search-views/data-model.md` — View Template Context
- Jinja2 sandbox environment for safety
- Symlinks are relative by default for portability

## Subtasks & Detailed Guidance

### Subtask T029 -- Create view __init__.py
- **Files**: `music_commander/view/__init__.py`

### Subtask T030 -- Jinja2 environment with custom filters
- **Purpose**: Set up Jinja2 for rendering path templates.
- **Files**: `music_commander/view/template.py`
- **Steps**:
  1. Create sandboxed Jinja2 `Environment` (no file loading, string templates only)
  2. Register custom filter `round_to(value, n)`: `round(value / n) * n` — rounds to nearest N
  3. Set `undefined=StrictUndefined` initially, then catch and replace with "Unknown"
  4. Create `render_path(template_str: str, metadata: dict) -> str` function
  5. The template string comes from `--pattern` CLI flag
- **Notes**: All metadata fields from data-model.md must be available as template variables. Missing values → "Unknown" default.

### Subtask T031 -- Symlink tree creation
- **Purpose**: Create directory tree of symlinks from rendered paths.
- **Files**: `music_commander/view/symlinks.py`
- **Steps**:
  1. Create `create_symlink_tree(tracks: list, template_str: str, output_dir: Path, repo_path: Path, absolute: bool = False)` function
  2. For each track: render template → sanitize → create dirs → create symlink
  3. Symlink target: compute relative path from symlink location to original file (or absolute if flagged)
  4. Show progress bar with Rich

### Subtask T032 -- Multi-value field expansion
- **Purpose**: A track with crates ["Festival", "DarkPsy"] creates two symlinks when `{{ crate }}` is in the template.
- **Files**: `music_commander/view/symlinks.py`
- **Steps**:
  1. Detect which template variables are multi-value (currently only `crate`)
  2. For each track, if multi-value field is in template, yield N copies of metadata dict — one per value
  3. If multi-value field is NOT in template, yield one copy

### Subtask T033 -- Path sanitization
- **Purpose**: Replace filesystem-unsafe characters in rendered paths.
- **Files**: `music_commander/view/symlinks.py`
- **Steps**:
  1. Replace `/` in metadata values (not template path separators) with `-`
  2. Replace `\0` with empty string
  3. Replace other unsafe chars as needed (`:`, `*`, `?`, `"`, `<`, `>`, `|`)
  4. Trim leading/trailing whitespace and dots from path segments
  5. Truncate segments to filesystem max (255 bytes)

### Subtask T034 -- Duplicate path handling
- **Purpose**: Append numeric suffix when two tracks produce the same path.
- **Files**: `music_commander/view/symlinks.py`
- **Steps**:
  1. Track used paths in a set
  2. On collision: try `name_1.ext`, `name_2.ext`, etc.
  3. Warn user about duplicates (count)

### Subtask T035 -- Output directory cleanup
- **Purpose**: Remove old symlinks before regenerating.
- **Files**: `music_commander/view/symlinks.py`
- **Steps**:
  1. Walk output directory
  2. Remove all symlinks (only symlinks, not regular files)
  3. Remove empty directories bottom-up
  4. Warn if output dir is inside git-annex repo

### Subtask T036 -- Relative/absolute symlinks
- **Purpose**: Create relative symlinks by default, absolute with `--absolute` flag.
- **Files**: `music_commander/view/symlinks.py`
- **Steps**:
  1. Relative: compute `os.path.relpath(target, symlink_parent_dir)`
  2. Absolute: use `target.resolve()` or `target.absolute()`
  3. Default to relative for portability

### Subtask T037 -- CLI view command
- **Purpose**: `music-cmd view QUERY --pattern TEMPLATE --output DIR` command.
- **Files**: `music_commander/commands/view.py`
- **Steps**:
  1. Click command with query argument, `--pattern` required, `--output` required
  2. `--absolute` flag (default False)
  3. Parse query → search cache → render template → create symlinks
  4. Auto-refresh cache (same as search command)
  5. Report: N symlinks created, N duplicates, output directory
  6. Append original file extension to every symlink

### Subtask T038 -- Template render tests
- **Files**: `tests/test_view_template.py`
- **Steps**:
  1. Test basic variable substitution
  2. Test `round_to` filter
  3. Test built-in Jinja2 filters (lower, upper, default, truncate)
  4. Test missing metadata → "Unknown"
  5. Test path separator in template creates directories

### Subtask T039 -- Symlink creation tests
- **Files**: `tests/test_view_symlinks.py`
- **Steps**:
  1. Test symlink creation in temp directory
  2. Test relative vs absolute symlink targets
  3. Test multi-value expansion (crate)
  4. Test duplicate handling (numeric suffix)
  5. Test cleanup of old symlinks
  6. Test path sanitization

### Subtask T040 -- CLI view integration tests
- **Files**: `tests/test_cmd_view.py`
- **Steps**:
  1. Test CLI invocation with Click CliRunner
  2. Test with mock search results
  3. Test error cases: missing pattern, invalid template

## Test Strategy

- Use `tmp_path` pytest fixture for symlink creation tests
- Mock search results for view tests (avoid cache dependency)
- Verify symlink targets are correct (resolve and check)

## Risks & Mitigations

- Large result sets → progress bar + batch symlink creation
- Path collisions from template rendering → numeric suffix handles this
- Filesystem limits (path length, character restrictions) → sanitization

## Review Guidance

- Verify multi-value field expansion creates correct number of symlinks
- Verify relative symlinks resolve correctly from the view directory
- Verify cleanup removes only symlinks, not regular files
- Verify file extension is always preserved

## Activity Log

- 2026-01-29T02:41:50Z -- system -- lane=planned -- Prompt created.
- 2026-01-29T13:41:07Z – claude-opus – shell_pid= – lane=doing – Starting implementation of WP05: View Export
- 2026-01-29T13:46:50Z – claude-opus – shell_pid= – lane=for_review – All 40 tests pass (18 template, 18 symlinks, 4 CLI). 173 total tests green. Commit 5a4e80e.
- 2026-01-29T14:23:35Z – claude-opus – shell_pid=194846 – lane=doing – Started review via workflow command
