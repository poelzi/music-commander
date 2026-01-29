# Implementation Plan: Mixxx to Git-Annex Metadata Sync

**Branch**: `002-mixxx-to-git` | **Date**: 2026-01-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/kitty-specs/002-mixxx-to-git/spec.md`

## Summary

Sync Mixxx DJ library metadata (rating, BPM, color, key, artist, title, album, genre, year, tracknumber, comment, crates) to git-annex metadata on annexed music files. Uses `git annex metadata --batch --json` for efficient bulk operations. Change detection via Mixxx `source_synchronized_ms` timestamp. Sync state stored in git-annex branch metadata for cross-clone sharing.

## Technical Context

**Language/Version**: Python 3.13+ (matches existing project)
**Primary Dependencies**: Click (CLI), SQLAlchemy (Mixxx DB), Rich (output) - all existing
**Storage**: Mixxx SQLite database (read), git-annex metadata (write)
**Testing**: pytest with fixtures - existing test infrastructure
**Target Platform**: Linux (primary), cross-platform compatible
**Project Type**: Single project - extend existing `music_commander/` package
**Performance Goals**: 1000 tracks in <60 seconds, minimal git commits
**Constraints**: Must use `git annex metadata --batch --json` for efficiency
**Scale/Scope**: 10,000+ track libraries, single command invocation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No constitution file present - proceeding with standard best practices:
- Follow existing code patterns in `music_commander/`
- Use type hints throughout (mypy strict)
- Maintain test coverage
- Use Rich for CLI output consistency

## Project Structure

### Documentation (this feature)

```
kitty-specs/002-mixxx-to-git/
├── plan.md              # This file
├── research.md          # Phase 0 output - Mixxx schema & git-annex batch research
├── data-model.md        # Phase 1 output - entity definitions
├── quickstart.md        # Phase 1 output - usage guide
└── tasks.md             # Phase 2 output (NOT created by /spec-kitty.plan)
```

### Source Code (repository root)

```
music_commander/
├── __init__.py
├── __main__.py
├── cli.py                      # Main CLI group (add sync-metadata command)
├── config.py                   # Configuration (music_repo already exists)
├── exceptions.py               # Add sync-specific exceptions
├── commands/
│   ├── __init__.py
│   ├── get_commit_files.py     # Existing command (reference pattern)
│   └── sync_metadata.py        # NEW: sync-metadata command
├── db/
│   ├── __init__.py
│   ├── mixxx.py                # Existing Mixxx DB models
│   └── queries.py              # NEW: Mixxx metadata queries
└── utils/
    ├── __init__.py
    ├── git.py                  # Existing git utilities
    ├── annex_metadata.py       # NEW: git-annex metadata batch operations
    └── output.py               # Existing Rich output utilities

tests/
├── conftest.py
├── unit/
│   ├── test_annex_metadata.py  # NEW: batch mode tests
│   └── test_mixxx_queries.py   # NEW: query tests
└── integration/
    └── test_sync_metadata.py   # NEW: end-to-end sync tests
```

**Structure Decision**: Extend existing single-project structure. New command in `commands/`, new utilities in `utils/`, new queries in `db/`.

## Research Findings Summary

### Mixxx Database Schema

**Key Tables**:
- `library` - Main track metadata (rating, bpm, color, key, artist, title, album, etc.)
- `track_locations` - File paths (joined via `library.location` → `track_locations.id`)
- `crates` - Crate definitions (name, id)
- `crate_tracks` - Junction table (crate_id, track_id)

**Change Detection**:
- `source_synchronized_ms` (INTEGER) - Milliseconds timestamp of last sync
- `datetime_added` (DATETIME) - When track was added (one-time)
- `last_played_at` (DATETIME) - Last playback time

**Path Storage**: `track_locations.location` contains full absolute path

### Git-Annex Batch Mode

**Usage**: `git annex metadata --batch --json`

**Input Format**:
```json
{"file":"path/to/file.mp3","fields":{"artist":["Value"],"rating":["5"]}}
```

**Output Format**:
```json
{"command":"metadata","file":"path/to/file.mp3","success":true,"fields":{...}}
```

**Key Behaviors**:
- Fields array replaces existing values (not append)
- Empty array `[]` removes field entirely
- Commits automatically to git-annex branch
- Line-buffered for streaming responses
- Use `annex.alwayscommit=false` to batch commits manually

## Design Decisions

1. **Batching Strategy**: Use single long-running `git annex metadata --batch --json` subprocess. Feed all files through stdin, read responses from stdout. Set `annex.alwayscommit=false` during sync, then manually commit once at end.

2. **Change Detection**: Compare `source_synchronized_ms` against stored last-sync timestamp. If no timestamp stored (first run), sync all. Store sync timestamp in git-annex metadata on a sentinel key.

3. **Path Matching**: Strip `config.music_repo` prefix from Mixxx paths, compare as relative paths against repo files.

4. **Crate Handling**: Query `crate_tracks` joined with `crates` to get crate names per track. Store as multi-value `crate` field.

5. **Error Handling**: Log failures per-file, continue processing, report summary at end.

## Complexity Tracking

No constitution violations identified - implementation follows existing patterns.

## Parallel Work Analysis

This feature is suitable for single-developer implementation. Work packages will be sequenced:
1. Database queries (Mixxx schema access)
2. Annex metadata batch wrapper
3. Sync logic and CLI command
4. Tests

No parallel streams required given scope.
