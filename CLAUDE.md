# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

music-commander: CLI tool for managing git-annex based music collections with Mixxx DJ software integration and Bandcamp purchase management. Python 3.13+, Linux primary platform.

## Development Commands

All tools (pytest, ruff, mypy, ffmpeg, git-annex, etc.) are **only available inside `nix develop`**. Bare `pytest`, `ruff`, `python -m pytest` etc. will not work outside it.

```bash
# Enter dev shell (required — all deps including git-annex, ffmpeg, etc.)
nix develop

# Run CLI during development
nix develop --command bash -c 'cd /path/to/repo && python -m music_commander --help'
# Or from within nix develop:
music-commander --help

# Tests — must run inside nix develop
nix develop --command pytest                                # all tests
nix develop --command pytest tests/unit/ -v                 # unit only
nix develop --command pytest tests/integration/ -v          # integration only
nix develop --command pytest tests/unit/test_config.py -v   # single file
nix develop --command pytest -- -k "test_search"            # by name

# Code quality — must run inside nix develop
nix develop --command ruff check .                          # lint
nix develop --command ruff format .                         # format
nix develop --command mypy music_commander/                 # type check
nix flake check                                             # all checks (CI equivalent)
```

## Architecture

### CLI Framework
Click-based with auto-discovered commands. Each module in `music_commander/commands/` exporting a `cli` attribute (Click command or group) is auto-registered. Subgroups like `bandcamp/`, `files/`, `cue/`, `mirror/`, and `dev/` are Click groups with their own subcommands. Shared state flows through `Context` object via `@pass_context` decorator.

### Two Database Layers
- **Mixxx DB** (`music_commander/db/`): Read-only SQLAlchemy ORM against Mixxx's SQLite. WAL-mode safe for concurrent access.
- **Cache DB** (`music_commander/cache/`): Local SQLite cache (`<repo>/.music-commander-cache.db`) for fast metadata queries. Models: `CacheTrack`, `BandcampRelease`, `BandcampTrack`, `BandcampReleaseFormat`. Refreshes incrementally by checking git-annex branch HEAD.

### Bandcamp Integration (`music_commander/bandcamp/`)
- `client.py`: HTTP client with adaptive AIMD rate limiter. Collection API for purchases, mobile API (`/api/mobile/25/tralbum_details`) for track listings, redownload pages for download formats.
- `matcher.py`: 4-phase fuzzy matching (Phase 0: metadata URL, Phase 0.5: comment subdomain, Phase 1: folder path, Phase 2: global). Uses rapidfuzz for string similarity. Tracks `claimed_folders` and `claimed_files` to prevent duplicate assignments.
- `parser.py`: Extracts `digital_items` and formats from redownload page HTML (`data-blob` JSON in `#pagedata` div).
- `cookies.py`: Browser cookie extraction via rookiepy.

### Search System (`music_commander/search/`)
Mixxx-compatible query DSL parsed by Lark (Earley parser, grammar in `grammar.lark`), translated to SQLAlchemy queries against the cache. Supports field filters (`artist:X`), boolean operators, negation, range filters (`bpm:>140`).

### Git-Annex Operations (`music_commander/utils/git.py`)
All git/git-annex interaction via subprocess. Batch metadata operations via `git annex metadata --batch`. Symlink detection for annexed files.

### Output (`music_commander/utils/output.py`)
Rich-based with three verbosity levels: `verbose()` prints at `-v`, `debug()` prints at `--debug`. `is_verbose()` and `is_debug()` for conditional logic. Auto-paging for long output.

### Configuration
TOML at `~/.config/music-commander/config.toml`. Key paths: `music_repo` (git-annex repo), `mixxx_db` (Mixxx SQLite). See `config.example.toml`.

## Testing Requirements

Every code change must include tests. Write unit tests for all new functions, CLI commands, and utility modules. Tests live in `tests/unit/` and `tests/integration/`. Run `pytest` to verify before finishing any task.

## Key Conventions

- Commands export a `cli` Click command/group in their module
- `sale_item_type` values from Bandcamp API are acquisition methods (`p`=purchase, `r`=redeemed, `c`=code, `i`=bundle-item, `s`=sub-item), not content types
- Cache DB path is `<music_repo>/.music-commander-cache.db`, not the project root
- Feature development uses spec-kitty workflow (specs in `kitty-specs/`, constitution in `.kittify/memory/constitution.md`)
