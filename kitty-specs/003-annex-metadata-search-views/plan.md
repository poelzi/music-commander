# Implementation Plan: Annex Metadata Search & Symlink Views

**Branch**: `003-annex-metadata-search-views` | **Date**: 2026-01-29 | **Spec**: `kitty-specs/003-annex-metadata-search-views/spec.md`

## Summary

Add two CLI commands to music-commander: `search` (query git-annex metadata using Mixxx-compatible syntax) and `view` (create symlink directory trees from search results using Jinja2 path templates). A local SQLite cache enables sub-second queries across 100k+ tracks.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: Click, SQLAlchemy, Rich, lark (search parser), Jinja2 (templates)
**Storage**: SQLite cache in-repo (`.music-commander-cache.db`), git-annex metadata as source of truth
**Testing**: pytest, unit tests for every command and utility module
**Target Platform**: Linux (Nix flake)
**Performance Goals**: 100k+ tracks, sub-second cached queries, ~16s cache rebuild
**Constraints**: Must work without Mixxx installed. Local-only, no external services.

## Constitution Check

**GATE: PASS**

- Python 3.11+: Compliant
- Click CLI: Compliant (new commands follow existing pattern)
- SQLAlchemy: Compliant (used for cache DB)
- Rich: Compliant (table output)
- Jinja2: Compliant (listed in constitution)
- Testing: Every command and utility will have unit tests
- Performance: Benchmarked — 16s full cache build, sub-second queries
- Nix flake: New deps (lark, jinja2) added to flake.nix
- No external services: Compliant

**New dependencies**: `lark` and `jinja2` added to `pythonDeps` in `flake.nix` and `pyproject.toml`.

## Project Structure

### Source Code (new files)

```
music_commander/
├── commands/
│   ├── search.py              # CLI search command
│   └── view.py                # CLI view command
├── search/
│   ├── __init__.py
│   ├── parser.py              # Lark grammar + AST for Mixxx search syntax
│   ├── query.py               # Execute search against SQLite cache
│   └── grammar.lark           # Lark grammar file
├── cache/
│   ├── __init__.py
│   ├── models.py              # SQLAlchemy models for cache DB
│   ├── builder.py             # Build/refresh cache from git-annex branch
│   └── session.py             # Cache DB session management
└── view/
    ├── __init__.py
    ├── template.py            # Jinja2 environment + custom filters
    └── symlinks.py            # Symlink tree creation logic

tests/
├── test_search_parser.py      # Parser unit tests
├── test_search_query.py       # Query execution tests
├── test_cache_builder.py      # Cache build/refresh tests
├── test_view_template.py      # Template rendering tests
├── test_view_symlinks.py      # Symlink creation tests
├── test_cmd_search.py         # CLI search integration tests
└── test_cmd_view.py           # CLI view integration tests
```

## Architecture

### Cache Build Pipeline

```
git-annex branch
    │
    ├─ git ls-tree -r git-annex | grep .log.met
    │  → list of blob hashes + key paths (~1s)
    │
    ├─ git cat-file --batch
    │  → raw metadata key=value lines (~4s)
    │
    ├─ git annex find --format='${key}\t${file}\n'
    │  → key-to-file mapping (~12s)
    │
    └─ Parse + INSERT into SQLite cache
       → tracks table + track_crates table + FTS5 index
```

**Incremental refresh**: `git diff-tree` between cached commit and current `git-annex` branch HEAD to find changed `.log.met` files. Update only changed rows.

### Search Pipeline

```
User query string
    │
    ├─ Lark parser → SearchQuery AST
    │
    ├─ AST → SQL WHERE clause (against cache)
    │  - TextTerm → FTS5 MATCH
    │  - FieldFilter → column comparison
    │  - OR groups → SQL OR
    │  - Negation → NOT
    │
    └─ Execute against SQLite → TrackResult list
```

### View Pipeline

```
Search results (TrackResult list)
    │
    ├─ For each track:
    │  ├─ Expand multi-value fields (crate) → N copies
    │  ├─ Render Jinja2 template → relative path
    │  ├─ Sanitize path segments
    │  ├─ Append file extension
    │  └─ Handle duplicates (numeric suffix)
    │
    ├─ Clean output directory (remove old symlinks)
    │
    └─ Create symlinks (relative by default)
```

## Key Design Decisions

1. **Cache location**: `.music-commander-cache.db` in repo root. Add to `.gitignore`.
2. **Raw branch read**: 14x faster than `metadata --batch --json` for full dump.
3. **FTS5**: SQLite full-text search for bare-word queries across multiple fields.
4. **Lark grammar**: Formal grammar for Mixxx search syntax, producing clean AST.
5. **Multi-value expansion**: Crate field in Jinja2 templates creates one symlink per crate value.
6. **Relative symlinks**: Default for portability, `--absolute` flag available.

## Complexity Tracking

No constitution violations. All choices align with established patterns.
