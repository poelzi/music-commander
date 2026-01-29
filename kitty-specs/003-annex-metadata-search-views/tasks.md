# Work Packages: Annex Metadata Search & Symlink Views

**Inputs**: Design documents from `kitty-specs/003-annex-metadata-search-views/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: Required per constitution — every command and utility must have unit tests.

---

## Work Package WP01: Dependencies & Cache Infrastructure (Priority: P0)

**Goal**: Add lark + jinja2 dependencies, create SQLite cache schema and session management.
**Independent Test**: Cache DB can be created, opened, and queried with test data.
**Prompt**: `tasks/WP01-deps-and-cache-infra.md`

### Included Subtasks
- [ ] T001 Add `lark` and `jinja2` to `flake.nix` pythonDeps and `pyproject.toml`
- [ ] T002 Create `music_commander/cache/__init__.py`
- [ ] T003 Create `music_commander/cache/models.py` — SQLAlchemy models for tracks, track_crates, cache_state tables
- [ ] T004 Create `music_commander/cache/session.py` — Cache DB session management (`.music-commander-cache.db` in repo root)
- [ ] T005 Create `tests/test_cache_models.py` — Unit tests for cache models and session

### Implementation Notes
- Follow existing patterns from `music_commander/db/` for SQLAlchemy models and session
- Cache DB is separate from Mixxx DB — different engine/session
- Add `.music-commander-cache.db` to `.gitignore`

### Dependencies
- None (starting package).

### Risks & Mitigations
- Nix flake rebuild needed after dep changes — test with `nix develop`

---

## Work Package WP02: Cache Builder (Priority: P0)

**Goal**: Build and incrementally refresh the local SQLite cache from the git-annex branch.
**Independent Test**: Run cache build against the real repo, verify tracks are populated with metadata.
**Prompt**: `tasks/WP02-cache-builder.md`

### Included Subtasks
- [x] T006 Create `music_commander/cache/builder.py` — Full cache build from git-annex branch
- [x] T007 Implement raw git-annex branch reader (`git ls-tree` + `git cat-file --batch` for `.log.met` files)
- [x] T008 Implement metadata log parser (parse `key=value` format from `.log.met` content)
- [x] T009 Implement key-to-file mapper (`git annex find --format='${key}\t${file}\n'`)
- [x] T010 Implement incremental refresh via `git diff-tree` on git-annex branch
- [x] T011 Create FTS5 virtual table for full-text search on artist, title, album, genre, file
- [x] T012 Create `tests/test_cache_builder.py` — Unit tests for builder, parser, incremental refresh

### Implementation Notes
- Full build pipeline: ls-tree → cat-file --batch → parse → key-to-file → INSERT
- Store last-seen git-annex branch commit in cache_state for incremental refresh
- FTS5 table should be populated during build, updated during refresh

### Parallel Opportunities
- T007 and T009 read different git data, can be developed in parallel

### Dependencies
- Depends on WP01 (cache models and session).

### Risks & Mitigations
- Metadata log format may have edge cases (spaces in values, multi-line) — test with real data

---

## Work Package WP03: Search Parser (Priority: P1)

**Goal**: Parse Mixxx-compatible search syntax into a structured AST using lark.
**Independent Test**: Parse complex queries and verify AST structure.
**Prompt**: `tasks/WP03-search-parser.md`

### Included Subtasks
- [x] T013 Create `music_commander/search/__init__.py`
- [x] T014 Create `music_commander/search/grammar.lark` — Lark grammar for Mixxx search syntax
- [x] T015 Create `music_commander/search/parser.py` — Parser producing SearchQuery AST
- [x] T016 Implement AST data classes: SearchQuery, OrGroup, AndClause, TextTerm, FieldFilter
- [x] T017 Handle: bare words, field:value, field:>N, field:N-M, -negation, | OR, field:="exact", field:"", quoted strings
- [x] T018 Create `tests/test_search_parser.py` — Unit tests for all query syntax variants

### Implementation Notes
- Grammar must handle: `dark psy bpm:>140 rating:>=4 -genre:ambient genre:house | genre:techno artist:="DJ Name" year:2020-2025`
- OR has lower precedence than AND (implicit)
- Negation with `-` prefix on any term or field filter

### Dependencies
- None (can run parallel to WP01/WP02).

### Risks & Mitigations
- Lark grammar edge cases with special chars — extensive test suite

---

## Work Package WP04: Search Query Execution & CLI (Priority: P1) MVP

**Goal**: Execute parsed search queries against the SQLite cache and expose via CLI.
**Independent Test**: `music-cmd search "bpm:>140 genre:psytrance"` returns matching tracks.
**Prompt**: `tasks/WP04-search-query-and-cli.md`

### Included Subtasks
- [x] T019 Create `music_commander/search/query.py` — Convert AST to SQL WHERE clauses
- [x] T020 Implement TextTerm → FTS5 MATCH query
- [x] T021 Implement FieldFilter → column comparisons (=, >, <, >=, <=, range, glob)
- [x] T022 Implement OR groups → SQL OR, negation → NOT
- [x] T023 Implement empty field search (field:"") → column IS NULL
- [x] T024 Create `music_commander/commands/search.py` — CLI search command with Rich table output
- [x] T025 Add `--format` flag (table/paths/json) for output formats
- [x] T026 Auto-build/refresh cache on first search (with progress bar)
- [x] T027 Create `tests/test_search_query.py` — Unit tests for query execution
- [x] T028 Create `tests/test_cmd_search.py` — CLI integration tests

### Implementation Notes
- Cache auto-refresh: check cache_state.annex_branch_commit vs current git-annex HEAD
- Rich table: show file, artist, title, album, genre, bpm, rating, key columns
- `--format paths`: one file path per line for piping
- `--format json`: JSON array of track objects

### Dependencies
- Depends on WP02 (cache builder) and WP03 (search parser).

### Risks & Mitigations
- FTS5 query syntax differs from Mixxx partial match — may need LIKE fallback for some queries

---

## Work Package WP05: View Template & Symlink Export (Priority: P1) MVP

**Goal**: Create symlink directory trees from search results using Jinja2 path templates.
**Independent Test**: `music-cmd view "rating:>=4" --pattern "{{ genre }}/{{ artist }} - {{ title }}" --output ./test-view` creates correct symlink tree.
**Prompt**: `tasks/WP05-view-template-and-symlinks.md`

### Included Subtasks
- [ ] T029 Create `music_commander/view/__init__.py`
- [ ] T030 Create `music_commander/view/template.py` — Jinja2 environment with custom filters (`round_to`)
- [ ] T031 Create `music_commander/view/symlinks.py` — Symlink tree creation logic
- [ ] T032 Implement multi-value field expansion (crate → one symlink per value)
- [ ] T033 Implement path sanitization (filesystem-safe characters)
- [ ] T034 Implement duplicate path handling (numeric suffix)
- [ ] T035 Implement output directory cleanup (remove old symlinks and empty dirs)
- [ ] T036 Implement relative symlink creation (default) and `--absolute` flag
- [ ] T037 Create `music_commander/commands/view.py` — CLI view command
- [ ] T038 Create `tests/test_view_template.py` — Unit tests for template rendering
- [ ] T039 Create `tests/test_view_symlinks.py` — Unit tests for symlink creation
- [ ] T040 Create `tests/test_cmd_view.py` — CLI integration tests

### Implementation Notes
- Jinja2 sandbox environment for safety
- Custom `round_to(n)` filter: `round(value / n) * n`
- Missing metadata → "Unknown" via Jinja2 `default` filter
- File extension always preserved from original file
- Warn if output dir is inside git-annex repo

### Dependencies
- Depends on WP04 (search query execution provides results to render).

### Risks & Mitigations
- Symlink creation on large result sets — batch with progress bar
- Path collisions from template rendering — numeric suffix handles this

---

## Work Package WP06: Polish & Integration (Priority: P2)

**Goal**: End-to-end validation, documentation, edge case hardening.
**Independent Test**: Full workflow works: cache build → search → view export with 100k tracks.
**Prompt**: `tasks/WP06-polish-and-integration.md`

### Included Subtasks
- [ ] T041 Add `.music-commander-cache.db` to default `.gitignore` generation in init-config
- [ ] T042 Add `--rebuild-cache` flag to search and view commands for forcing full rebuild
- [ ] T043 Handle edge cases: empty repo, no metadata, corrupt cache file
- [ ] T044 Performance validation on 100k+ track repo
- [ ] T045 End-to-end integration test: sync → cache → search → view

### Dependencies
- Depends on WP04 and WP05.

### Risks & Mitigations
- Performance regression — benchmark during validation

---

## Dependency & Execution Summary

- **Sequence**: WP01 → WP02 → WP04 (with WP03 parallel) → WP05 → WP06
- **Parallelization**: WP03 (parser) can run in parallel with WP01+WP02 (cache infrastructure)
- **MVP Scope**: WP01 + WP02 + WP03 + WP04 + WP05 = working search + view export

```
WP01 (deps+cache) ──→ WP02 (builder) ──→ WP04 (search CLI) ──→ WP05 (view) ──→ WP06 (polish)
                                              ↑
WP03 (parser) ────────────────────────────────┘
```

---

## Subtask Index (Reference)

| Subtask | Summary | WP | Priority | Parallel? |
|---------|---------|-----|----------|-----------|
| T001 | Add lark+jinja2 deps | WP01 | P0 | No |
| T002 | Create cache __init__ | WP01 | P0 | No |
| T003 | Cache SQLAlchemy models | WP01 | P0 | No |
| T004 | Cache session management | WP01 | P0 | No |
| T005 | Cache model tests | WP01 | P0 | No |
| T006 | Cache builder module | WP02 | P0 | No |
| T007 | Raw git-annex branch reader | WP02 | P0 | Yes |
| T008 | Metadata log parser | WP02 | P0 | No |
| T009 | Key-to-file mapper | WP02 | P0 | Yes |
| T010 | Incremental refresh | WP02 | P0 | No |
| T011 | FTS5 virtual table | WP02 | P0 | No |
| T012 | Cache builder tests | WP02 | P0 | No |
| T013 | Search __init__ | WP03 | P1 | No |
| T014 | Lark grammar file | WP03 | P1 | No |
| T015 | Search parser module | WP03 | P1 | No |
| T016 | AST data classes | WP03 | P1 | Yes |
| T017 | All syntax handling | WP03 | P1 | No |
| T018 | Parser tests | WP03 | P1 | No |
| T019 | Query → SQL converter | WP04 | P1 | No |
| T020 | FTS5 MATCH for text terms | WP04 | P1 | No |
| T021 | Field comparison operators | WP04 | P1 | No |
| T022 | OR groups + negation | WP04 | P1 | No |
| T023 | Empty field search | WP04 | P1 | No |
| T024 | CLI search command | WP04 | P1 | No |
| T025 | Output format flag | WP04 | P1 | Yes |
| T026 | Auto cache refresh | WP04 | P1 | No |
| T027 | Query execution tests | WP04 | P1 | No |
| T028 | CLI search tests | WP04 | P1 | No |
| T029 | View __init__ | WP05 | P1 | No |
| T030 | Jinja2 env + filters | WP05 | P1 | No |
| T031 | Symlink tree creation | WP05 | P1 | No |
| T032 | Multi-value expansion | WP05 | P1 | No |
| T033 | Path sanitization | WP05 | P1 | No |
| T034 | Duplicate path handling | WP05 | P1 | No |
| T035 | Output dir cleanup | WP05 | P1 | No |
| T036 | Relative/absolute symlinks | WP05 | P1 | No |
| T037 | CLI view command | WP05 | P1 | No |
| T038 | Template render tests | WP05 | P1 | No |
| T039 | Symlink creation tests | WP05 | P1 | No |
| T040 | CLI view tests | WP05 | P1 | No |
| T041 | Gitignore for cache DB | WP06 | P2 | Yes |
| T042 | --rebuild-cache flag | WP06 | P2 | Yes |
| T043 | Edge case handling | WP06 | P2 | No |
| T044 | Performance validation | WP06 | P2 | No |
| T045 | E2E integration test | WP06 | P2 | No |
