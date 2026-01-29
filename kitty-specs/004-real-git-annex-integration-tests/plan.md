# Implementation Plan: Real Git-Annex Integration Test Suite

**Branch**: `004-real-git-annex-integration-tests` | **Date**: 2026-01-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/004-real-git-annex-integration-tests/spec.md`

## Summary

Replace fragile mock-based git-annex tests with a real integration test suite. The suite creates actual git-annex repositories with synthetic audio files (mp3/flac/aiff), clones with partial content, and verifies the full pipeline: cache build, search, and view with `--include-missing`. This directly tests the bug where non-present files have `file=NULL` in the cache, making `--include-missing` a no-op.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: pytest, mutagen (new), ffmpeg (new system dep), git-annex (existing)
**Storage**: SQLite via SQLAlchemy (cache DB created in test tmp dirs)
**Testing**: pytest with `tmp_path` fixtures in `tests/integration/`
**Target Platform**: Linux (nix dev shell)
**Project Type**: Single project (CLI tool)
**Performance Goals**: Tests should complete in under 30 seconds total
**Constraints**: Requires `git`, `git-annex`, `ffmpeg` in PATH
**Scale/Scope**: ~6-8 synthetic audio files per test fixture, 2 repos (origin + partial clone)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Python 3.13+**: Pass (test code is Python)
- **pytest required**: Pass (using pytest)
- **Every CLI command must have unit tests**: Pass (view command tested via integration)
- **Tests must pass before merging**: Pass (new tests will be green)
- **Nix flake for packaging**: Pass (adding deps to flake.nix)
- **No external services**: Pass (all local git-annex operations)
- **Must work without Mixxx**: Pass (tests use git-annex metadata only, no Mixxx DB)

No violations.

## Project Structure

### Documentation (this feature)

```
kitty-specs/004-real-git-annex-integration-tests/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```
tests/
├── conftest.py              # Existing shared fixtures (enhanced)
├── unit/
│   ├── test_cache_builder.py    # MODIFIED: remove TestBuildCache, TestRefreshCache, TestFTS5
│   └── test_e2e_search_view.py  # MODIFIED: remove TestE2EPipeline
└── integration/
    ├── __init__.py
    ├── conftest.py              # NEW: integration-specific fixtures
    ├── test_cache_build.py      # NEW: cache build + refresh tests
    ├── test_search.py           # NEW: search correctness tests
    └── test_view.py             # NEW: view + --include-missing tests

flake.nix                        # MODIFIED: add ffmpeg, mutagen
pyproject.toml                   # MODIFIED: add mutagen to dev deps
```

**Structure Decision**: Integration tests in `tests/integration/` with their own `conftest.py` for heavyweight fixtures (repo creation, audio generation). Shared fixtures in `tests/conftest.py` remain for unit tests.

## Design

### Audio File Generation Strategy

1. **WAV generation**: Use Python `struct` + `wave` modules to create a short sine wave (~0.5s, 44100Hz, mono)
2. **Format conversion**: Shell out to `ffmpeg` to convert WAV to mp3, flac, and aiff
3. **Tagging**: Use `mutagen` to write ID3 (mp3), VorbisComment (flac), and ID3 (aiff) tags
4. **Artwork**: Generate a small solid-color PNG (e.g., 4x4 pixels) using raw bytes, embed via mutagen

### Test Fixture Design

```python
# tests/integration/conftest.py

@pytest.fixture(scope="session")
def audio_files(tmp_path_factory) -> dict[str, Path]:
    """Generate 6 synthetic audio files with tags and artwork."""
    # Returns {"track1.mp3": Path, "track2.flac": Path, ...}

@pytest.fixture(scope="session")
def origin_repo(tmp_path_factory, audio_files) -> Path:
    """Git-annex repo with all 6 files, metadata set."""

@pytest.fixture(scope="session")
def partial_clone(tmp_path_factory, origin_repo) -> Path:
    """Clone of origin with only 3 of 6 files fetched."""
```

Session-scoped fixtures avoid re-creating repos for each test (expensive git-annex operations).

### Track Metadata Schema

6 tracks with distinct, searchable metadata:

| # | Format | Artist | Title | Genre | BPM | Rating | Crate |
|---|--------|--------|-------|-------|-----|--------|-------|
| 1 | mp3 | AlphaArtist | DarkPulse | Darkpsy | 148 | 5 | Festival |
| 2 | mp3 | BetaArtist | NightVibe | Techno | 130 | 4 | Club |
| 3 | flac | GammaArtist | ForestDawn | Psytrance | 145 | 5 | Festival |
| 4 | flac | DeltaArtist | DeepSpace | Ambient | 80 | 3 | Chill |
| 5 | aiff | EpsilonArtist | RhythmStorm | DnB | 174 | 4 | Club |
| 6 | aiff | ZetaArtist | SilentWave | Ambient | 70 | 2 | Chill |

**Partial clone selection**: First 3 tracks fetched (tracks 1-3), last 3 not fetched (tracks 4-6). Deterministic by filename sort order.

This gives:
- Present: tracks 1,2,3 (mp3, mp3, flac) — ratings 5, 4, 5
- Not present: tracks 4,5,6 (flac, aiff, aiff) — ratings 3, 4, 2

Useful query splits:
- `rating:>=4` matches tracks 1,2,3,5 — 3 present, 1 not present
- `genre:Ambient` matches tracks 4,6 — both not present
- Free text "dark" matches track 1 — present

### Git-Annex Metadata Setup

For each track, after `git annex add` and commit:
```bash
git annex metadata <file> -s artist=<val> -s title=<val> -s genre=<val> \
    -s bpm=<val> -s rating=<val> -s crate=<val>
```

### Test Plan

#### `tests/integration/test_cache_build.py`

1. **test_all_tracks_have_file_path**: Build cache against partial clone. Assert every CacheTrack has `file IS NOT NULL`.
2. **test_present_field_accuracy**: Build cache against partial clone. Assert tracks 1-3 have `present=True`, tracks 4-6 have `present=False`.
3. **test_metadata_correctness**: Build cache. Assert artist, title, genre, bpm, rating match expected values for all 6 tracks.
4. **test_crate_data**: Build cache. Assert TrackCrate entries exist for all tracks with correct crate values.
5. **test_incremental_refresh_no_change**: Build cache, then refresh. Assert refresh returns `None` (no changes).
6. **test_fts5_search**: Build cache. Query FTS5 table for known artist name, verify result.

#### `tests/integration/test_search.py`

1. **test_search_returns_all_tracks**: Search with empty/match-all query. Assert count equals 6 (present + non-present).
2. **test_field_filter_includes_non_present**: Search `rating:>=4`. Assert 4 results (tracks 1,2,3,5), including non-present track 5.
3. **test_text_search**: Search for "DarkPulse". Assert 1 result (track 1).
4. **test_genre_filter**: Search `genre:Ambient`. Assert 2 results (tracks 4,6), both non-present.
5. **test_crate_search**: Search `crate:Festival`. Assert 2 results (tracks 1,3).

#### `tests/integration/test_view.py`

1. **test_view_without_include_missing**: Build cache on partial clone, create view with `rating:>=4` query. Assert symlink count equals 3 (only present tracks 1,2,3).
2. **test_view_with_include_missing**: Same query with `--include-missing`. Assert symlink count equals 4 (tracks 1,2,3,5). Assert strictly greater than without flag.
3. **test_symlink_targets_correct**: With `--include-missing`, verify each symlink target points to the correct repo-relative file path.
4. **test_view_full_repo_no_difference**: Build cache on origin repo (all present). Run view with and without `--include-missing`. Assert identical symlink counts.
5. **test_template_rendering**: Verify template `{{ genre }}/{{ artist }} - {{ title }}` produces expected directory structure.
6. **test_duplicate_handling**: Use a template that would produce duplicate paths, verify numeric suffix resolution.

### Mock Test Removal

Remove from `tests/unit/test_cache_builder.py`:
- Class `TestBuildCache` (3 methods)
- Class `TestRefreshCache` (4 methods)
- Class `TestFTS5` (1 method)

Keep in `tests/unit/test_cache_builder.py`:
- Class `TestParseMetadataLog` (14 methods)
- Class `TestDecodeValue` (3 methods)
- Class `TestExtractKeyFromPath` (3 methods)
- Class `TestMetadataToTrack` (4 methods)
- Class `TestMetadataToCrates` (2 methods)

Remove from `tests/unit/test_e2e_search_view.py`:
- Class `TestE2EPipeline` (8 methods)
- Module-level mock constants (`_LOG_TRACK1`, `_LOG_TRACK2`, `_LS_TREE`, `_CAT_FILE`, `_ANNEX_FIND_ALL`, `_ANNEX_FIND_PRESENT`, `_mock_subprocess_run`)
- Standalone test methods that use the mock infrastructure (`test_render_path_integration`, `test_delete_cache`)

Keep `test_render_path_integration` and `test_delete_cache` only if they don't depend on the removed mock infrastructure (they don't — they're standalone methods on `TestE2EPipeline` but can be moved to unit tests or integration tests).

### Nix Flake Changes

```nix
# flake.nix changes:

# Add mutagen to Python dev deps
devDeps = ps: with ps; [
  pytest
  pytest-cov
  mypy
  ruff
  mutagen    # NEW: audio file tagging for integration tests
];

# Add ffmpeg to system buildInputs
devShells.default = pkgs.mkShell {
  buildInputs = [
    pythonEnv
    python-music-cmd
    pkgs.git-annex
    pkgs.ffmpeg        # NEW: audio format conversion for integration tests
    spec-kitty.packages.${system}.default
  ];
  # ...
};
```

### pyproject.toml Changes

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "mypy>=1.0",
    "ruff>=0.1",
    "mutagen>=1.45",    # NEW
]
```

## Complexity Tracking

No constitution violations. No complexity justifications needed.
