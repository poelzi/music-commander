# Research: Real Git-Annex Integration Test Suite

## Decision: Audio Generation Approach

**Chosen**: Python `wave` + `struct` modules for WAV generation, `ffmpeg` for format conversion, `mutagen` for tagging.

**Rationale**: Zero extra Python dependencies for audio generation (stdlib only). FFmpeg handles all format conversions reliably. Mutagen is the standard Python audio tagging library and handles all three target formats (ID3 for mp3/aiff, VorbisComment for flac).

**Alternatives considered**:
- `pydub`: Adds a dependency that wraps ffmpeg anyway
- `numpy`/`scipy`: Heavy dependencies for a simple sine wave
- Pre-built fixture files: Not reproducible, hard to maintain

## Decision: Partial Clone File Selection

**Chosen**: Reproducible by filename sort order (first half fetched).

**Rationale**: Simple, deterministic, no dependency on metadata values. Files are named with predictable prefixes (track01, track02, etc.) so sort order is obvious.

**Alternatives considered**:
- Random selection with seed: Unnecessary complexity
- Metadata-based selection: Would couple fixture setup to test assertions

## Decision: Mock Test Replacement Scope

**Chosen**: Remove mock-heavy classes (`TestBuildCache`, `TestRefreshCache`, `TestFTS5`, `TestE2EPipeline`). Keep pure-logic classes (`TestParseMetadataLog`, `TestDecodeValue`, `TestExtractKeyFromPath`, `TestMetadataToTrack`, `TestMetadataToCrates`).

**Rationale**: Mock-heavy classes test subprocess integration with faked data — exactly what integration tests replace. Pure-logic classes test deterministic transformations that don't touch subprocess and run instantly.

**Alternatives considered**:
- Remove all mock tests: Would lose fast feedback on parser/decoder changes
- Keep all mocks alongside integration tests: Maintenance burden with no coverage gain

## Decision: Fixture Scope

**Chosen**: `session`-scoped pytest fixtures for repo creation (shared across all tests in a run).

**Rationale**: Git-annex init + audio generation + metadata setup is expensive (~5-10s). Running once per session avoids repeating this for every test function. Tests that need isolated state (e.g., view output) use separate `tmp_path` directories for output.

**Alternatives considered**:
- Function-scoped fixtures: Too slow — would multiply test time by test count
- Module-scoped: Adequate but session-scoped is simpler since all integration tests share the same fixtures

## Decision: Artwork Generation

**Chosen**: Generate a minimal valid PNG in memory (8x8 solid color, ~70 bytes) and embed via mutagen.

**Rationale**: PNG format has a simple binary structure. A minimal valid PNG can be constructed from raw bytes without any image library. Mutagen supports embedding APIC frames (mp3/aiff) and METADATA_BLOCK_PICTURE (flac).

**Alternatives considered**:
- Use Pillow: Extra dependency for a trivial image
- Skip artwork: Spec requires it for realistic test data

## Existing Infrastructure Findings

### conftest.py already has `git_annex_repo` fixture
Located at `tests/conftest.py:128`. Creates a basic git-annex repo with a single fake `.flac` file. The integration conftest.py will create its own more elaborate fixtures rather than extending this one, to avoid coupling.

### Cache functions need only `repo_path` and `session`
`build_cache(repo_path, session)` and `refresh_cache(repo_path, session)` take minimal arguments. No Config object required. Integration tests can call these directly.

### FTS5 table created inside `build_cache()`
The `_create_fts5_table()` call is internal to `build_cache()`. Tests don't need to create it manually.

### `git annex find --include='*'` confirmed to list all files
Verified on the real repo: returns 86,406 files vs 12,845 for plain `git annex find`. This is the core of the bug fix being tested.
