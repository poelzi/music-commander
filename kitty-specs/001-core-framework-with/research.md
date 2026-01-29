# Research: Core Framework with Mixxx DB and git-annex

**Date**: 2026-01-06
**Feature Branch**: `001-core-framework-with`

## Technology Decisions

### CLI Framework: Click

**Decision**: Use Click for CLI framework with subcommand auto-discovery

**Rationale**:
- Mature, well-documented library with extensive ecosystem
- Decorator-based command definition is clean and Pythonic
- Built-in support for subcommands via `@click.group()`
- Plugin/extension system via entry points for auto-discovery
- Good integration with Rich for styled output

**Alternatives Considered**:
- Typer: Built on Click but adds type hint magic that can complicate debugging
- argparse: Standard library but verbose; no built-in auto-discovery

**Implementation Pattern**:
```python
# music_commander/cli.py
@click.group()
@click.pass_context
def cli(ctx):
    ctx.ensure_object(dict)

# Auto-discovery via entry points in pyproject.toml/flake.nix
```

### Terminal Output: Rich

**Decision**: Use Rich for colored output, tables, and progress bars

**Rationale**:
- Excellent progress bar support (needed for git-annex fetch operations)
- Beautiful table rendering for track listings
- Automatic terminal detection and fallback
- Click integration via `rich-click` optional enhancement

**Alternatives Considered**:
- Click's built-in styling: Limited to basic colors, no progress bars
- Colorama: Too basic, no tables or progress

### ORM: SQLAlchemy 2.0

**Decision**: Use SQLAlchemy 2.0 with declarative models

**Rationale**:
- Mature, battle-tested ORM
- Excellent SQLite support including WAL mode
- Type hints support in 2.0 style
- Session management handles concurrent access patterns

**Alternatives Considered**:
- Peewee: Simpler but less flexible for complex queries
- Raw sqlite3: No ORM benefits, more boilerplate

### Configuration: tomllib + tomli-w

**Decision**: Use Python 3.13's built-in `tomllib` for reading, `tomli-w` for writing

**Rationale**:
- TOML is human-readable and familiar to developers
- `tomllib` is stdlib in Python 3.11+ (no extra dependency for reading; project requires 3.13+)
- `tomli-w` is small, well-maintained for write operations
- XDG Base Directory compliant (`~/.config/music-commander/`)

**Alternatives Considered**:
- YAML: More complex syntax, security concerns with unsafe loading
- JSON: Less human-friendly for manual editing
- INI: Limited type support

### Package Structure

**Decision**: Package at repository root (`music_commander/`)

**Rationale**:
- Simpler for a single-package project
- Direct mapping between package name and directory
- Works well with Nix flake packaging

**Structure**:
```
music_commander/
├── __init__.py
├── __main__.py          # Entry point: python -m music_commander
├── cli.py               # Click group and global options
├── config.py            # Configuration loading/saving
├── commands/            # Auto-discovered subcommands
│   ├── __init__.py
│   └── get_commit_files.py
├── db/                  # Database layer
│   ├── __init__.py
│   ├── models.py        # SQLAlchemy ORM models
│   └── session.py       # Session management
└── utils/               # Shared utilities
    ├── __init__.py
    ├── git.py           # Git/git-annex operations
    └── output.py        # Rich console helpers
```

## Mixxx Database Schema Analysis

Based on analysis of the actual Mixxx database at `/space/Music/Mixxx/mixxxdb.sqlite`:

### Core Tables to Model

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `library` | Track metadata | id, artist, title, album, bpm, key, duration, location (FK) |
| `track_locations` | File paths | id, location, filename, directory, filesize |
| `Playlists` | Playlist definitions | id, name, position, hidden, locked |
| `PlaylistTracks` | Playlist membership | playlist_id, track_id, position |
| `crates` | Crate definitions | id, name, count, locked |
| `crate_tracks` | Crate membership | crate_id, track_id |
| `cues` | Cue points/hot cues | id, track_id, type, position, hotcue, label, color |

### Concurrent Access Strategy

Mixxx uses SQLite in WAL (Write-Ahead Logging) mode. Our approach:

1. **Read operations**: Use short-lived sessions, no locking issues
2. **Write operations**: 
   - Use `BEGIN IMMEDIATE` transactions to detect conflicts early
   - Keep transactions short
   - Retry on `SQLITE_BUSY` with exponential backoff
3. **Connection settings**:
   - `timeout=30` seconds for busy waiting
   - `isolation_level=None` for autocommit reads
   - Explicit transactions for writes

## Git-Annex Integration Patterns

### Detecting Annexed Files

```python
# Check if file is annexed (symlink to .git/annex/objects)
def is_annexed(path: Path) -> bool:
    return path.is_symlink() and '.git/annex/objects' in str(path.resolve())
```

### Getting Files from Commits

```bash
# Files changed in a single commit
git diff-tree --no-commit-id --name-only -r <commit>

# Files changed in a range
git diff --name-only <commit1>..<commit2>

# Files unique to a branch (not on current HEAD)
git log --name-only --pretty=format: <branch> --not HEAD
```

### Executing git-annex get

```python
# Use subprocess with progress parsing
# git-annex outputs progress to stderr in format:
# get file.mp3 (from remote...) 
#   45%  10.5 MiB/s  1m30s
```

## Nix Flake Structure

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;
        
        pythonEnv = python.withPackages (ps: with ps; [
          click
          rich
          sqlalchemy
          tomli-w
          # Dev dependencies
          pytest
          pytest-cov
          mypy
          ruff
        ]);
      in {
        packages.default = python.pkgs.buildPythonApplication {
          pname = "music-commander";
          version = "0.1.0";
          src = ./.;
          propagatedBuildInputs = with python.pkgs; [
            click rich sqlalchemy tomli-w
          ];
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [ pythonEnv pkgs.git-annex ];
        };

        checks.default = /* pytest execution */;
      });
}
```

## Open Questions Resolved

All technical questions from the specification phase have been resolved through this research. No outstanding clarifications needed.
