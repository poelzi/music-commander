---
work_package_id: "WP01"
subtasks:
  - "T001"
  - "T002"
  - "T003"
  - "T004"
  - "T005"
title: "Dependencies & Cache Infrastructure"
phase: "Phase 0 - Setup"
lane: "for_review"
dependencies: []
assignee: ""
agent: "claude-opus"
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

# Work Package Prompt: WP01 -- Dependencies & Cache Infrastructure

## Objectives & Success Criteria

- Add `lark` and `jinja2` as runtime dependencies to the Nix flake and pyproject.toml
- Create the SQLAlchemy cache module with models for tracks, track_crates, and cache_state
- Cache DB session management targeting `.music-commander-cache.db` in the repo root
- Unit tests for all cache models and session management
- Imports succeed and cache DB can be created, populated, and queried

## Context & Constraints

- Constitution: `.kittify/memory/constitution.md` — Python 3.13+, pytest required, every module needs tests
- Plan: `kitty-specs/003-annex-metadata-search-views/plan.md`
- Data model: `kitty-specs/003-annex-metadata-search-views/data-model.md`
- Follow existing patterns from `music_commander/db/` for SQLAlchemy models and session management
- Cache DB is separate from the Mixxx DB — separate engine and session factory

## Subtasks & Detailed Guidance

### Subtask T001 -- Add lark and jinja2 dependencies
- **Purpose**: Make `lark` and `jinja2` importable in the project.
- **Files**:
  - `flake.nix`: Add `lark` and `jinja2` to `pythonDeps` list
  - `pyproject.toml`: Add `lark>=1.0` and `jinja2>=3.0` to `dependencies`
- **Steps**:
  1. Edit `flake.nix`, find `pythonDeps = ps: with ps; [...]` and add `lark` and `jinja2`
  2. Edit `pyproject.toml`, add to `[project] dependencies`
  3. Verify with `nix develop --command python -c "import lark; import jinja2; print('OK')"`

### Subtask T002 -- Create cache __init__.py
- **Purpose**: Initialize the cache package.
- **Files**: `music_commander/cache/__init__.py`
- **Steps**: Create minimal `__init__.py` exporting key classes.

### Subtask T003 -- Create cache SQLAlchemy models
- **Purpose**: Define the schema for the local metadata cache.
- **Files**: `music_commander/cache/models.py`
- **Steps**:
  1. Define `CacheTrack` model with fields from `data-model.md`: key (PK), file, artist, title, album, genre, bpm (REAL), rating (INTEGER), key_musical, year, tracknumber, comment, color
  2. Define `TrackCrate` model: key (FK), crate — composite PK (key, crate)
  3. Define `CacheState` model: id (always 1), annex_branch_commit, last_updated, track_count
  4. Use SQLAlchemy 2.0 Mapped types matching `music_commander/db/models.py` patterns
- **Notes**: The `key` field in CacheTrack is the git-annex key (e.g., `SHA256E-s6850832--...mp3`), not the musical key. Musical key is `key_musical`.

### Subtask T004 -- Create cache session management
- **Purpose**: Manage SQLite connections for the cache database.
- **Files**: `music_commander/cache/session.py`
- **Steps**:
  1. Create `get_cache_session(repo_path: Path)` context manager
  2. DB path: `repo_path / ".music-commander-cache.db"`
  3. Auto-create tables on first use (`Base.metadata.create_all`)
  4. Follow patterns from `music_commander/db/session.py`

### Subtask T005 -- Create cache model tests
- **Purpose**: Verify cache models, session, and basic CRUD.
- **Files**: `tests/test_cache_models.py`
- **Steps**:
  1. Test table creation with in-memory SQLite
  2. Test inserting CacheTrack, TrackCrate, CacheState
  3. Test querying by field (artist, bpm range, etc.)
  4. Test CacheState singleton pattern

## Test Strategy

- pytest with in-memory SQLite (`:memory:`) for fast tests
- Test all model fields and relationships
- Test session context manager lifecycle

## Risks & Mitigations

- Nix flake cache may need rebuilding after dep changes — verify with `nix develop`
- SQLAlchemy version compatibility — use same version as Mixxx DB module

## Review Guidance

- Verify models match data-model.md exactly
- Verify cache DB is completely separate from Mixxx DB
- Verify tests cover all model fields

## Activity Log

- 2026-01-29T02:41:50Z -- system -- lane=planned -- Prompt created.
- 2026-01-29T03:08:07Z – claude-opus – shell_pid= – lane=doing – Starting implementation of WP01: Dependencies & Cache Infrastructure
- 2026-01-29T03:12:17Z – claude-opus – shell_pid= – lane=for_review – Ready for review: cache models, session, 16 passing tests
