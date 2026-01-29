---
work_package_id: "WP04"
subtasks:
  - "T019"
  - "T020"
  - "T021"
  - "T022"
  - "T023"
  - "T024"
  - "T025"
  - "T026"
  - "T027"
  - "T028"
title: "Search Query Execution & CLI"
phase: "Phase 1 - Core"
lane: "doing"
dependencies: ["WP02", "WP03"]
assignee: ""
agent: "claude-opus"
shell_pid: "193019"
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-29T02:41:50Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP04 -- Search Query Execution & CLI

## Implementation Command

```bash
spec-kitty implement WP04 --base WP02
```

Note: WP03 (parser) should also be merged before starting. If using worktrees, ensure both WP02 and WP03 are complete.

## Objectives & Success Criteria

- Convert parsed SearchQuery AST into SQL WHERE clauses against the SQLite cache
- Execute queries with FTS5 for text terms, column comparisons for field filters
- CLI `search` command with Rich table output
- Support `--format` flag: table (default), paths, json
- Auto-build/refresh cache on first search
- Unit and integration tests

## Context & Constraints

- Plan: `kitty-specs/003-annex-metadata-search-views/plan.md` — Search Pipeline section
- Data model: `kitty-specs/003-annex-metadata-search-views/data-model.md` — SearchQuery AST
- Follow existing CLI patterns from `music_commander/commands/sync_metadata.py`
- Use `@pass_context` decorator for config access

## Subtasks & Detailed Guidance

### Subtask T019 -- Query to SQL converter
- **Purpose**: Transform SearchQuery AST into SQLAlchemy WHERE clauses.
- **Files**: `music_commander/search/query.py`
- **Steps**:
  1. Create `execute_search(session: Session, query: SearchQuery) -> list[CacheTrack]`
  2. For each OrGroup: build AND clause, combine groups with OR
  3. Return list of CacheTrack objects with joined TrackCrate data

### Subtask T020 -- FTS5 MATCH for text terms
- **Purpose**: Bare-word search across artist/title/album/genre/filename.
- **Files**: `music_commander/search/query.py`
- **Steps**:
  1. TextTerm → `tracks_fts MATCH 'value*'` (prefix matching for partial match)
  2. Multiple TextTerms in same OrGroup → AND in FTS5 query
  3. Join FTS5 results with tracks table via rowid
- **Notes**: FTS5 MATCH syntax uses `*` for prefix, `AND`/`OR`/`NOT` keywords. Map from AST.

### Subtask T021 -- Field comparison operators
- **Purpose**: Translate field:op:value to SQL column comparisons.
- **Files**: `music_commander/search/query.py`
- **Steps**:
  1. `contains` → `column LIKE '%value%'` (case-insensitive)
  2. `=` (exact) → `column = 'value'` (case-insensitive via COLLATE NOCASE)
  3. `>`, `<`, `>=`, `<=` → numeric column comparison (cast to float for bpm)
  4. `range` → `column >= low AND column <= high`
  5. Map field names to cache model columns (e.g., `key` search field → `key_musical` column, `location` → `file` column)

### Subtask T022 -- OR groups and negation
- **Purpose**: Combine OR groups and handle negation.
- **Files**: `music_commander/search/query.py`
- **Steps**:
  1. OR groups → `sqlalchemy.or_()` across groups
  2. Negation → `~clause` (SQLAlchemy NOT)
  3. AND within groups → `sqlalchemy.and_()`

### Subtask T023 -- Empty field search
- **Purpose**: `field:""` matches tracks where the field is NULL or empty.
- **Files**: `music_commander/search/query.py`
- **Steps**: `column IS NULL OR column = ''`

### Subtask T024 -- CLI search command
- **Purpose**: `music-cmd search QUERY` command.
- **Files**: `music_commander/commands/search.py`
- **Steps**:
  1. Click command with query string argument
  2. Parse query → execute against cache → display results
  3. Default output: Rich table with columns: file, artist, title, album, genre, bpm, rating, key
  4. Show result count
  5. Follow exit code patterns from existing commands

### Subtask T025 -- Output format flag
- **Purpose**: `--format table|paths|json` for different output modes.
- **Files**: `music_commander/commands/search.py`
- **Steps**:
  1. `table` (default): Rich table via `create_table()` from output.py
  2. `paths`: Print one relative file path per line (for piping)
  3. `json`: JSON array of objects with all metadata fields
- **Parallel?**: Yes, independent UI work.

### Subtask T026 -- Auto cache refresh
- **Purpose**: Automatically build/refresh cache on search if stale.
- **Files**: `music_commander/commands/search.py`
- **Steps**:
  1. Before search, call `refresh_cache()` from builder
  2. If no cache exists, trigger full build with progress bar
  3. If cache exists but stale (git-annex branch moved), incremental refresh
  4. If cache is current, skip refresh

### Subtask T027 -- Query execution tests
- **Files**: `tests/test_search_query.py`
- **Steps**:
  1. Create in-memory cache with test data
  2. Test text term search via FTS5
  3. Test field comparisons (all operators)
  4. Test OR groups, negation, range, empty field
  5. Test combined queries

### Subtask T028 -- CLI search integration tests
- **Files**: `tests/test_cmd_search.py`
- **Steps**:
  1. Test CLI invocation with Click test runner
  2. Test output formats (table, paths, json)
  3. Test error cases (invalid query, no cache)

## Test Strategy

- In-memory SQLite with pre-populated test data for query tests
- Click CliRunner for command integration tests
- Mock cache builder for CLI tests (avoid git dependency)

## Risks & Mitigations

- FTS5 query syntax mismatch with Mixxx partial match — use LIKE fallback for exact substring matching
- Performance on large result sets — limit default output, add `--limit` flag if needed

## Review Guidance

- Verify all Mixxx search operators produce correct SQL
- Verify FTS5 text search returns relevant results
- Verify CLI output formats are well-formed

## Activity Log

- 2026-01-29T02:41:50Z -- system -- lane=planned -- Prompt created.
- 2026-01-29T12:55:43Z – claude-opus – shell_pid= – lane=doing – Starting implementation of WP04: Search Query Execution
- 2026-01-29T13:02:10Z – claude-opus – shell_pid= – lane=for_review – Ready for review: query executor, CLI with 3 output formats, 31 tests all passing
- 2026-01-29T14:21:45Z – claude-opus – shell_pid=193019 – lane=doing – Started review via workflow command
