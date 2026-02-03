# Implementation Plan: CUE Sheet Splitter

**Branch**: `008-cue-sheet-splitter` | **Date**: 2026-02-03 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/008-cue-sheet-splitter/spec.md`

## Summary

Add a new `cue` CLI command group with an initial `split` subcommand that splits single-file CD rips into individual FLAC tracks using cue sheet metadata. The cue parser is ported from the existing `/space/Music/bin/split-albums` script with bug fixes. shntool is the primary splitting backend for formats it supports (FLAC, WAV), with ffmpeg as fallback for APE and WavPack. Split tracks are tagged with metaflac and optionally have cover art embedded.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: Click (CLI), shntool (splitting), metaflac (tagging/cover art), ffmpeg (fallback splitting for APE/WV)
**Storage**: N/A (file operations only, no database)
**Testing**: pytest
**Target Platform**: Linux (primary)
**Project Type**: Single project — extends existing CLI
**Performance Goals**: Handle directories with 100+ cue/file pairs without issue
**Constraints**: Must work within nix develop shell; shntool added as new nix dependency

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Python 3.13+**: PASS — using Python 3.13+
- **Click CLI framework**: PASS — new `cue` group follows existing command group pattern
- **Rich for output**: PASS — using existing `verbose()`, `info()`, `error()` utilities
- **Nix flake packaging**: PASS — shntool added to flake dependencies
- **Testing**: PASS — unit tests for cue parser and split logic
- **100k+ track scale**: PASS — operates on individual directories, no dataset-wide operations
- **No external services**: PASS — purely local file operations
- **Works without Mixxx**: PASS — no Mixxx dependency

No constitution violations.

## Project Structure

### Documentation (this feature)

```
kitty-specs/008-cue-sheet-splitter/
├── spec.md
├── plan.md              # This file
├── meta.json
├── research.md
├── data-model.md
├── checklists/
│   └── requirements.md
└── tasks/
```

### Source Code (repository root)

```
music_commander/
├── cue/                       # New package: cue sheet processing
│   ├── __init__.py
│   ├── parser.py              # CueParser — ported and fixed from split-albums
│   └── splitter.py            # Split logic: shntool + ffmpeg fallback, tagging, cover art
├── commands/
│   └── cue/                   # New command group
│       ├── __init__.py        # Click group "cue" with cli attribute
│       └── split.py           # "cue split" subcommand

tests/
└── unit/
    ├── test_cue_parser.py     # CueParser unit tests
    └── test_cue_splitter.py   # Splitter logic unit tests

flake.nix                      # Add shntool to dependencies
```

**Structure Decision**: Follows the established pattern — `music_commander/cue/` for domain logic (like `music_commander/bandcamp/`), `music_commander/commands/cue/` for CLI commands (like `music_commander/commands/bandcamp/`). The parser is a standalone module in `cue/` so future cue-related commands can reuse it.

## Research

### Decision 1: Splitting backend strategy

**Decision**: shntool as primary, ffmpeg as fallback
**Rationale**: shntool handles cue-based splitting natively with frame-level CD precision (75 fps at 44100Hz). It supports FLAC and WAV directly. For APE and WavPack, ffmpeg handles the decoding/splitting since shntool may not have those decoders available.
**Alternatives considered**:
- shntool only: Would miss APE/WV support without additional decoder plugins
- ffmpeg only: Less native cue split support, would need manual timestamp calculation from cue parser output

### Decision 2: CUE parser approach

**Decision**: Port the existing CueParser class from `/space/Music/bin/split-albums` with bug fixes
**Rationale**: The existing parser handles the core cue sheet commands (PERFORMER, TITLE, FILE, TRACK, INDEX, REM, FLAGS) and calculates sample-accurate positions. It needs these fixes:
- `TRACK_NUM` → `TRACKNUMBER` tag mapping (was `TRACKNU02MBER`, a typo)
- Proper encoding fallback (UTF-8 → Latin-1 → user-specified)
- Better error handling (no bare `pass` on errors)
- Filesystem-safe filename generation
**Alternatives considered**:
- Third-party cue parser library: No well-maintained Python library exists for this specific use case
- Writing from scratch: Unnecessary when the existing code is functional and just needs cleanup

### Decision 3: Tagging approach

**Decision**: Use metaflac for FLAC tagging and cover art embedding
**Rationale**: metaflac is already a dependency, handles all required operations (tag setting, ReplayGain, picture embedding), and is the standard tool for FLAC metadata. The existing script already uses this approach.
**Alternatives considered**:
- mutagen (Python library): Would add a dependency; metaflac is simpler for this use case
- ffmpeg metadata: Less precise control over FLAC-specific tags

### Decision 4: Output filename sanitization

**Decision**: Replace filesystem-unsafe characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`) with `_` in track titles used for filenames
**Rationale**: Simple, predictable, and consistent with common practice. No existing utility in the codebase for this — add a small helper in `cue/splitter.py`.

## Data Model

### CueSheet

Represents a parsed `.cue` file.

- `performer`: str — Global performer/artist (default: "Unknown")
- `album`: str — Album title (default: "Unknown")
- `genre`: str | None — Genre from REM GENRE
- `date`: str | None — Date/year from REM DATE
- `songwriter`: str | None — Songwriter from REM SONGWRITER
- `disc_id`: str | None — Disc ID from REM DISCID
- `comment`: str | None — Comment from REM COMMENT
- `file`: str | None — Source audio filename from FILE command
- `tracks`: list[CueTrack] — Ordered list of tracks

### CueTrack

Represents a single track within a cue sheet.

- `track_num`: int — Track number
- `title`: str — Track title
- `performer`: str — Track performer (inherited from global if not overridden)
- `songwriter`: str | None — Track songwriter
- `isrc`: str | None — ISRC code from REM ISRC
- `index`: str — Index timestring (mm:ss:ff)
- `start_samples`: int — Start position in samples (44100Hz)
- `end_samples`: int | None — End position in samples (None for last track)
- All other global fields inherited (genre, date, album, disc_id)

### SplitResult

Represents the outcome of processing one cue/file pair.

- `source_path`: Path — Path to the source audio file
- `cue_path`: Path — Path to the cue file
- `track_count`: int — Number of tracks in cue sheet
- `output_files`: list[Path] — Paths to created track files
- `status`: str — One of: "ok", "skipped", "error"
- `error`: str | None — Error message if status is "error"

## Quickstart

After implementation, the feature is used as follows:

```bash
# Split a single directory
music-cmd cue split /path/to/album/

# Split recursively through a collection
music-cmd cue split /path/to/collection/ --recursive

# Preview what would be split
music-cmd cue split /path/to/collection/ --recursive --dry-run

# Split and remove originals
music-cmd cue split /path/to/album/ --remove-originals

# Force re-split even if output exists
music-cmd cue split /path/to/album/ --force

# Specify cue file encoding
music-cmd cue split /path/to/album/ --encoding cp1252

# Verbose output
music-cmd cue split /path/to/album/ -v
```
