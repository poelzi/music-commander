---
work_package_id: "WP02"
subtasks:
  - "T006"
  - "T007"
  - "T008"
  - "T009"
  - "T010"
  - "T011"
  - "T012"
title: "Cache Builder"
phase: "Phase 0 - Setup"
lane: "done"
dependencies: ["WP01"]
assignee: ""
agent: "claude-opus"
shell_pid: "190549"
review_status: "approved"
reviewed_by: "Daniel Poelzleithner"
history:
  - timestamp: "2026-01-29T02:41:50Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP02 -- Cache Builder

## Implementation Command

```bash
spec-kitty implement WP02 --base WP01
```

## Objectives & Success Criteria

- Build a complete local SQLite cache from the git-annex branch in ~16 seconds for 100k files
- Parse `.log.met` files from the git-annex branch into structured metadata
- Map git-annex keys to file paths
- Support incremental refresh via `git diff-tree`
- Create FTS5 full-text search index for text queries
- Unit tests for all components

## Context & Constraints

- Research: `kitty-specs/003-annex-metadata-search-views/research.md` — benchmarks and raw read approach
- Data model: `kitty-specs/003-annex-metadata-search-views/data-model.md`
- The raw git-annex branch approach is 14x faster than `metadata --batch --json`
- Pipeline: `git ls-tree -r git-annex` → `grep .log.met` → `git cat-file --batch` → parse → key-to-file → INSERT

## Subtasks & Detailed Guidance

### Subtask T006 -- Create cache builder module
- **Purpose**: Orchestrate the full cache build pipeline.
- **Files**: `music_commander/cache/builder.py`
- **Steps**:
  1. Create `build_cache(repo_path: Path, session: Session)` function
  2. Pipeline: read_metadata_logs → parse_logs → map_keys_to_files → insert_all
  3. Update CacheState with current git-annex branch commit hash
  4. Show progress via Rich progress bar
  5. Create `refresh_cache(repo_path: Path, session: Session)` that checks if refresh needed

### Subtask T007 -- Raw git-annex branch reader
- **Purpose**: Read all `.log.met` blob hashes and paths from the git-annex branch.
- **Files**: `music_commander/cache/builder.py`
- **Steps**:
  1. Run `git ls-tree -r git-annex` and filter lines ending with `.log.met`
  2. Extract blob hash and path for each line
  3. Extract git-annex key from path: strip directory prefix (`xxx/yyy/`) and `.log.met` suffix
  4. Pipe blob hashes to `git cat-file --batch` to read content
  5. Return iterator of `(annex_key, raw_metadata_string)` tuples
- **Parallel?**: Yes, can be developed independently from T009.

### Subtask T008 -- Metadata log parser
- **Purpose**: Parse `.log.met` file content into structured metadata.
- **Files**: `music_commander/cache/builder.py`
- **Steps**:
  1. Parse format: `<timestamp>s <field1> +<value1> [+<value2>] [-<value3>] <field2> +<value1> ...`
  2. Skip timestamp prefix (`\d+(\.\d+)?s`)
  3. Identify field names: tokens not starting with `+` or `-`
  4. Collect subsequent `+`/`-` values until the next field name
  5. Decode `!`-prefixed values as base64 (e.g., `+!U3BhY2V5...` → `"Spacey & Sleepy Koala"`)
  6. For multi-line blobs: replay chronologically, applying set (`+`) and unset (`-`) operations
  7. Return dict of field → list[str] (multi-value fields like crate have multiple values)
- **Notes**: See `research.md` Decision 4 for full format spec with real-data examples. Multi-value fields (crate, genre) have multiple `+value` tokens on the same line. Empty field name with no `+` values means field exists but is empty.

### Subtask T009 -- Key-to-file mapper
- **Purpose**: Map git-annex keys to repository-relative file paths.
- **Files**: `music_commander/cache/builder.py`
- **Steps**:
  1. Run `git annex find --format='${key}\t${file}\n'`
  2. Parse output into dict: `{annex_key: relative_file_path}`
  3. Return the mapping
- **Parallel?**: Yes, independent from T007/T008.

### Subtask T010 -- Incremental refresh
- **Purpose**: Update only changed metadata since last cache build.
- **Files**: `music_commander/cache/builder.py`
- **Steps**:
  1. Read last-seen commit from CacheState
  2. Run `git diff-tree -r --name-only <old_commit> <new_commit>` on git-annex branch
  3. Filter changed `.log.met` files
  4. Re-read and re-parse only changed entries
  5. UPDATE/INSERT changed rows, DELETE removed rows
  6. Update CacheState with new commit hash

### Subtask T011 -- FTS5 virtual table
- **Purpose**: Enable full-text search across text metadata fields.
- **Files**: `music_commander/cache/builder.py` or `music_commander/cache/models.py`
- **Steps**:
  1. Create FTS5 virtual table: `CREATE VIRTUAL TABLE tracks_fts USING fts5(artist, title, album, genre, file, content=tracks, content_rowid=rowid)`
  2. Populate during cache build
  3. Update triggers for incremental refresh

### Subtask T012 -- Cache builder tests
- **Purpose**: Verify full build and incremental refresh pipeline.
- **Files**: `tests/test_cache_builder.py`
- **Steps**:
  1. Test metadata log parsing with various formats
  2. Test key extraction from git-annex branch paths
  3. Test full build pipeline with mock git output
  4. Test incremental refresh with mock diff-tree output
  5. Test FTS5 search queries

## Test Strategy

- Mock `subprocess.run`/`Popen` for git commands in unit tests
- Use real repo for integration testing (optional, manual)
- Test parser with edge cases: spaces in values, empty fields, multi-value crate

## Risks & Mitigations

- Metadata log format edge cases — test with real data samples from the repo
- FTS5 availability — SQLite 3.9+ ships FTS5 by default, Python 3.13 includes it
- Large dataset performance — batch INSERTs with `executemany`

## Review Guidance

- Verify pipeline produces correct metadata for known tracks
- Verify incremental refresh only touches changed entries
- Verify FTS5 index is populated and queryable

## Activity Log

- 2026-01-29T02:41:50Z -- system -- lane=planned -- Prompt created.
- 2026-01-29T03:21:09Z – claude-opus – shell_pid= – lane=doing – Starting implementation of WP02: Cache Builder
- 2026-01-29T03:27:43Z – claude-opus – shell_pid= – lane=for_review – Moved to for_review
- 2026-01-29T14:17:22Z – claude-opus – shell_pid=190549 – lane=doing – Started review via workflow command
- 2026-01-29T14:19:36Z – claude-opus – shell_pid=190549 – lane=done – Review passed: All 50 tests pass. All 7 subtasks (T006-T012) implemented correctly. Data model alignment verified. Clean code structure.
