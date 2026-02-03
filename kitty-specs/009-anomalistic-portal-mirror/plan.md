# Implementation Plan: Anomalistic Portal Mirror

**Branch**: `009-anomalistic-portal-mirror` | **Date**: 2026-02-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/009-anomalistic-portal-mirror/spec.md`

## Summary

Build a new top-level `mirror` CLI command group with an `anomalistic` subcommand that scrapes the Dark Psy Portal WordPress REST API, downloads WAV/MP3 ZIP/RAR archives, converts tracks to a configurable format (FLAC by default), organizes output via Jinja2 folder patterns, embeds source URLs as comment tags, and deduplicates against the existing collection using extracted shared fuzzy matching logic.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: Click (CLI), requests (HTTP), beautifulsoup4 (HTML parsing), SQLAlchemy (cache DB), Rich (progress), Jinja2 (folder patterns), rapidfuzz (matching), ffmpeg (conversion)
**Storage**: SQLite cache DB at `<music_repo>/.music-commander-cache.db` — new `anomalistic_releases` and `anomalistic_tracks` tables
**Testing**: pytest — unit tests for client, parser, matcher integration, title parsing, folder pattern rendering
**Target Platform**: Linux (primary)
**Project Type**: Single Python CLI project (existing)
**Performance Goals**: Handle full catalog (~278 releases) in single invocation; incremental runs skip already-downloaded releases in seconds
**Constraints**: Sequential downloads (one at a time), no authentication required, `unrar` must be available as system dependency
**Scale/Scope**: ~278 releases, ~80 WordPress categories, static catalog (grows slowly)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Python 3.13+**: Pass — using Python 3.13+
- **Click CLI**: Pass — new `mirror` group follows existing Click pattern
- **SQLAlchemy**: Pass — new cache models follow existing `CacheBase` pattern
- **Rich output**: Pass — reuse existing `info()`, `error()`, `success()`, progress display
- **Jinja2 templates**: Pass — used for folder pattern rendering
- **Nix flake**: Pass — `unrar` added to `buildInputs`
- **Testing**: Pass — unit tests required for client, parser, matcher, CLI command
- **100k+ track handling**: Pass — cache queries are indexed; portal catalog is small (~278)
- **No external services required**: Note — this feature inherently requires network access to the Dark Psy Portal. This is analogous to the existing Bandcamp integration which also requires network. Acceptable exception.
- **Batch processing**: Pass — catalog fetch uses paginated API (100 items/page); downloads sequential but batch-driven

No violations requiring justification.

## Project Structure

### Documentation (this feature)

```
kitty-specs/009-anomalistic-portal-mirror/
├── plan.md              # This file
├── spec.md              # Feature specification
├── meta.json            # Feature metadata
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks/               # Phase 2 output (created by /spec-kitty.tasks)
```

### Source Code (repository root)

```
music_commander/
├── commands/
│   └── mirror/
│       ├── __init__.py          # mirror group + exit codes
│       └── anomalistic.py       # anomalistic subcommand
├── anomalistic/
│   ├── __init__.py
│   ├── client.py                # WordPress REST API client
│   ├── parser.py                # HTML content parser (download URLs, metadata)
│   └── category.py              # Genre/label category classification
├── cache/
│   └── models.py                # + AnomaListicRelease, AnomaListicTrack models
│   └── session.py               # + register new models in _ALL_MODELS
├── utils/
│   ├── matching.py              # NEW: extracted shared matching functions
│   └── encoder.py               # Existing (reused, add comment metadata support)
├── bandcamp/
│   └── matcher.py               # Refactored to import from utils/matching.py
└── config.py                    # + [anomalistic] config section

tests/
└── unit/
    ├── test_anomalistic_client.py
    ├── test_anomalistic_parser.py
    ├── test_anomalistic_category.py
    ├── test_matching.py           # Tests for extracted shared matching
    └── test_anomalistic_command.py

flake.nix                          # + pkgs.unrar-free in buildInputs
```

**Structure Decision**: Follows the existing pattern established by `music_commander/bandcamp/` — a dedicated package (`music_commander/anomalistic/`) for the domain logic, with the CLI command in `music_commander/commands/mirror/`. Shared matching logic extracted to `music_commander/utils/matching.py` for DRY reuse.

## Key Design Decisions

### 1. Shared Matching Module Extraction

Extract `normalize_for_matching()`, `match_release()`, and `match_track()` from `music_commander/bandcamp/matcher.py` into `music_commander/utils/matching.py`. Both the bandcamp matcher and the anomalistic dedup logic import from the shared module. The bandcamp matcher retains its multi-phase orchestration logic; only the scoring primitives move.

### 2. WordPress REST API as Data Source

Use `wp-json/wp/v2/posts` (paginated, `per_page=100`) and `wp-json/wp/v2/categories` to fetch the full catalog. No individual page scraping needed. Download URLs extracted from the rendered HTML `content` field using BeautifulSoup4.

### 3. Title Parsing Strategy

Post titles follow `"Artist – Album"` pattern. Split on em-dash (`—` U+2014), en-dash (`–` U+2013), or hyphen (`-`). Left side = artist, right side = album. Recognize `V/A` and `VA` prefixes as "Various Artists". No delimiter = artist defaults to "Various Artists", full title = album.

### 4. Category Classification

WordPress categories are classified into three types:
- **Genres**: Known set of music style categories (DarkPsy=9, Psycore=7, Hi-Tech=12, Experimental=8, Forest=33, ForestCore=15, Psytrance=10, DownTempo=11, Squirrel=16, Swamp=69, Full-On=28, Morning=29, Ambient=44, Dark Techno=48, IDM=47, Horrordelic=14, Independent=30)
- **Ignored**: All Releases=3, Uncategorized=1, P=42, Nerdy Psouth=6
- **Labels**: Everything else (record label names)

Hardcoded genre ID set. Primary genre = first genre category in the API response's `categories` array.

### 5. Folder Pattern Rendering

Standard Jinja2 template rendering. Variables: `{{genre}}`, `{{label}}`, `{{artist}}`, `{{album}}`, `{{year}}`. Optional segments use `{% if label %}[{{label}}]{% endif %}` syntax. Filesystem-unsafe characters sanitized from rendered paths.

### 6. Archive Extraction

- ZIP: Python `zipfile` stdlib module
- RAR: Subprocess call to `unrar` (free implementation), added as Nix dependency

### 7. Conversion Pipeline

Reuse existing `encoder.py` — `FormatPreset` selection based on config `format` value, `build_ffmpeg_command()` for encoding, add `-metadata comment=<release_url>` to ffmpeg args for URL tagging. Handle edge case: if download format matches target format, still process to add comment tag.

### 8. Download Flow

Sequential (one at a time), no rate limiting. Temp file pattern (`.filename.tmp` → atomic rename). Progress display via Rich. Resume on re-run via cache check (skip already-downloaded releases).

## Complexity Tracking

No constitution violations. No complexity justifications needed.
