# Implementation Plan: Core Framework with Mixxx DB and git-annex

**Branch**: `001-core-framework-with` | **Date**: 2026-01-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/kitty-specs/001-core-framework-with/spec.md`

## Summary

Build the foundational musicCommander framework: a Python CLI tool for managing git-annex based music collections with Mixxx DJ software integration. Core deliverables include SQLAlchemy ORM models for the Mixxx database, TOML configuration system, Click-based CLI with auto-discovered subcommands, and the `get-commit-files` command for fetching annexed files from git history.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Click (CLI), Rich (terminal output), SQLAlchemy 2.0 (ORM), tomli-w (config writing)
**Storage**: SQLite (Mixxx's mixxxdb.sqlite, read/write with WAL mode awareness)
**Testing**: pytest via `nix flake check`
**Target Platform**: Linux (primary), macOS (compatible)
**Project Type**: Single CLI application
**Performance Goals**: 10,000+ track queries < 2 seconds, revision parsing < 5 seconds
**Constraints**: Must work with Mixxx running (concurrent DB access)
**Scale/Scope**: Large music collections (10,000+ tracks), multiple git-annex remotes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Nix-First Packaging | PASS | flake.nix with devShell, build, check |
| II. Python Implementation | PASS | Python 3.11+, type hints, ruff, mypy |
| III. CLI Usability | PASS | Click subcommands, Rich colors, --help |
| IV. git-annex Integration | PASS | get-commit-files command, proper annexed file detection |
| V. Test Coverage | PASS | pytest with fixtures, 80% target |
| VI. Simplicity | PASS | Minimal dependencies, straightforward architecture |

**No violations.** Proceeding without Complexity Tracking entries.

## Project Structure

### Documentation (this feature)

```
kitty-specs/001-core-framework-with/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Technology decisions
├── data-model.md        # Entity definitions
├── quickstart.md        # User guide
├── contracts/           # API contracts
│   ├── cli-interface.md
│   └── database-api.md
└── tasks.md             # Work packages (created by /spec-kitty.tasks)
```

### Source Code (repository root)

```
music_commander/
├── __init__.py          # Package version, exports
├── __main__.py          # Entry point: python -m music_commander
├── cli.py               # Click group, global options
├── config.py            # Configuration loading/saving
├── exceptions.py        # Exception hierarchy
├── commands/            # Auto-discovered subcommands
│   ├── __init__.py      # Command discovery
│   └── get_commit_files.py
├── db/                  # Database layer
│   ├── __init__.py
│   ├── models.py        # SQLAlchemy ORM models
│   ├── session.py       # Session management
│   └── queries.py       # Query functions
└── utils/               # Shared utilities
    ├── __init__.py
    ├── git.py           # Git/git-annex operations
    └── output.py        # Rich console helpers

tests/
├── conftest.py          # Fixtures (mock DB, git repo)
├── unit/
│   ├── test_config.py
│   ├── test_models.py
│   └── test_git_utils.py
├── integration/
│   ├── test_get_commit_files.py
│   └── test_db_queries.py
└── fixtures/
    └── mixxxdb_sample.sqlite

flake.nix                # Nix flake for build/dev/check
pyproject.toml           # Python project metadata
```

**Structure Decision**: Single package at root (`music_commander/`). Tests in separate `tests/` directory. Nix flake manages all dependencies and provides reproducible builds.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                        CLI Layer                         │
│  ┌─────────┐ ┌─────────────────┐ ┌──────────────────┐   │
│  │  cli.py │ │ commands/*.py   │ │  utils/output.py │   │
│  └────┬────┘ └────────┬────────┘ └────────┬─────────┘   │
│       │               │                    │             │
│       └───────────────┼────────────────────┘             │
│                       ▼                                  │
├─────────────────────────────────────────────────────────┤
│                    Core Services                         │
│  ┌────────────┐ ┌──────────────┐ ┌─────────────────┐    │
│  │ config.py  │ │ db/session   │ │ utils/git.py    │    │
│  └────────────┘ └──────┬───────┘ └─────────────────┘    │
│                        │                                 │
│                        ▼                                 │
│  ┌─────────────────────────────────────────────────┐    │
│  │              db/models.py (ORM)                  │    │
│  └─────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│                    External Systems                      │
│  ┌────────────────┐  ┌────────────┐  ┌──────────────┐   │
│  │ mixxxdb.sqlite │  │ git-annex  │  │ config.toml  │   │
│  └────────────────┘  └────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: Foundation (Sequential)

Must complete before parallel work:

1. **Nix Flake Setup** - flake.nix with Python, dependencies, devShell
2. **Package Structure** - music_commander/ with __init__.py, __main__.py
3. **Exception Hierarchy** - Base exceptions in exceptions.py
4. **Configuration System** - config.py with TOML loading/defaults

### Phase 2: Core Components (Parallel Streams)

After foundation, these can proceed independently:

**Stream A: Database Layer**
- ORM models (db/models.py)
- Session management (db/session.py)
- Query functions (db/queries.py)
- Unit tests for models

**Stream B: CLI Framework**
- Click group setup (cli.py)
- Global options (--config, --no-color, --verbose)
- Command auto-discovery (commands/__init__.py)
- Rich console helpers (utils/output.py)

**Stream C: Git Utilities**
- Git revision parsing (utils/git.py)
- Annexed file detection
- git-annex get wrapper with progress

### Phase 3: Integration (Sequential)

Combine components:

1. **get-commit-files Command** - Wire up git utils + Rich output
2. **Integration Tests** - End-to-end tests with fixtures
3. **Documentation** - README, help text refinement

## Dependency Graph

```
Phase 1 (Foundation)
    │
    ├── flake.nix ──────────────┐
    ├── package structure ──────┤
    ├── exceptions.py ──────────┤
    └── config.py ──────────────┤
                                │
                                ▼
Phase 2 (Parallel) ─────────────┬─────────────────┬──────────────────┐
                                │                 │                  │
                         Stream A          Stream B           Stream C
                         db/models.py      cli.py             utils/git.py
                         db/session.py     commands/__init__  
                         db/queries.py     utils/output.py    
                                │                 │                  │
                                └─────────────────┴──────────────────┘
                                                  │
                                                  ▼
Phase 3 (Integration)
    │
    ├── get_commit_files.py (uses all streams)
    ├── integration tests
    └── documentation
```

## Testing Strategy

| Layer | Approach | Coverage Target |
|-------|----------|-----------------|
| Unit | pytest with mocks | 80%+ |
| Integration | Fixture DB + temp git repo | Key workflows |
| CLI | Click's CliRunner | All commands |

**Fixtures Required**:
- `mixxxdb_sample.sqlite` - Minimal Mixxx DB with known tracks
- Temp git-annex repo with annexed files
- Mock git-annex remote for failure scenarios

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Mixxx DB schema changes | Schema version check on connect |
| Concurrent DB access corruption | WAL mode, short transactions, IMMEDIATE locks |
| git-annex not installed | Clear error message with install instructions |
| Large file counts slow queries | Lazy loading, pagination, efficient indexes |

## Deferred to Future Scope

The following SHOULD requirements from the constitution are explicitly deferred from this initial implementation:

| Requirement | Status | Notes |
|-------------|--------|-------|
| `--json` output flag | Deferred | Constitution SHOULD (line 50). API contract designed in [contracts/cli-interface.md](contracts/cli-interface.md#json-output-mode-future). Will be implemented in a future work package after core functionality is validated. |

These items have contracts/designs prepared but implementation is not included in the current work packages.

## Generated Artifacts

- [research.md](research.md) - Technology decisions
- [data-model.md](data-model.md) - Entity definitions
- [quickstart.md](quickstart.md) - User guide
- [contracts/cli-interface.md](contracts/cli-interface.md) - CLI contract
- [contracts/database-api.md](contracts/database-api.md) - Database API contract
