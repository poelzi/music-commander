# Feature Specification: Real Git-Annex Integration Test Suite

**Feature Branch**: `004-real-git-annex-integration-tests`
**Created**: 2026-01-29
**Status**: Draft
**Input**: User description: "Build a real test suite replacing mock-based git-annex tests with real git-annex operations, synthetic audio files, and verification of --include-missing behavior."

## User Scenarios & Testing

### User Story 1 - Test Fixture: Real Git-Annex Repository with Synthetic Audio (Priority: P1)

A developer runs the integration test suite. The test infrastructure creates a fresh git-annex repository in a temporary directory, generates synthetic audio files in three formats (mp3, flac, aiff) with real audio content (sine waves), proper metadata tags (artist, title, genre, bpm, rating, year, crate), and embedded cover artwork. The files are added and annexed, and metadata is set via `git annex metadata`.

**Why this priority**: Without a working test fixture, no other tests can run. This is the foundation.

**Independent Test**: Can be verified by running the fixture setup and confirming the git-annex repo contains the expected files with correct metadata readable via `git annex metadata`.

**Acceptance Scenarios**:

1. **Given** a clean temporary directory, **When** the test fixture initializes, **Then** a valid git-annex repository is created containing at least 6 synthetic audio files (2 mp3, 2 flac, 2 aiff) with distinct metadata per file.
2. **Given** the initialized repo, **When** querying `git annex metadata` on any file, **Then** the expected fields (artist, title, genre, bpm, rating, crate) are present and correctly set.
3. **Given** the initialized repo, **When** inspecting the audio files, **Then** each file contains valid audio data and embedded tags readable by standard audio tools.

---

### User Story 2 - Partial Clone Fixture (Priority: P1)

The test infrastructure clones the origin repository and runs `git annex get` on only half of the files, creating a realistic scenario where some file content is locally present and some is not.

**Why this priority**: The partial clone is essential for testing `present` vs non-present file behavior, which is the core of the `--include-missing` bug.

**Independent Test**: Can be verified by confirming the clone has all git-annex metadata but only half the file content locally available.

**Acceptance Scenarios**:

1. **Given** the origin repo with N annexed files, **When** cloning and running `git annex get` on half the files, **Then** the clone has N/2 files with content present and N/2 files with content not present.
2. **Given** the partial clone, **When** running `git annex find`, **Then** only the fetched files are listed.
3. **Given** the partial clone, **When** running `git annex find --include='*'`, **Then** all N files are listed regardless of presence.

---

### User Story 3 - Cache Build Correctness (Priority: P1)

A developer runs cache build tests against the partial clone. The cache builder correctly maps all files (present and non-present) to their file paths, and the `present` field accurately reflects local availability.

**Why this priority**: The cache is the data layer everything depends on. If `present` or `file` fields are wrong, downstream features like `--include-missing` cannot work.

**Independent Test**: Build the cache against the partial clone and query the SQLite database to verify field correctness.

**Acceptance Scenarios**:

1. **Given** the partial clone, **When** building the cache, **Then** all tracks have a non-null `file` path (both present and non-present files are mapped).
2. **Given** the partial clone, **When** building the cache, **Then** tracks whose content is locally present have `present=True`, and tracks whose content is not present have `present=False`.
3. **Given** the partial clone, **When** building the cache, **Then** metadata fields (artist, title, genre, bpm, rating) match the values set via `git annex metadata`.
4. **Given** the partial clone after a cache build, **When** running incremental refresh with no changes, **Then** no updates are reported.

---

### User Story 4 - Search Includes Non-Present Tracks (Priority: P2)

Search results include tracks regardless of their `present` status, so that downstream commands can decide whether to include or exclude non-present files.

**Why this priority**: Search correctness is a prerequisite for view correctness, but is lower priority than cache correctness since search operates on cached data.

**Independent Test**: Run a search query that matches both present and non-present tracks and verify all are returned.

**Acceptance Scenarios**:

1. **Given** a cache built from the partial clone, **When** searching with a query that matches all tracks, **Then** the result count equals the total number of tracks (present + non-present).
2. **Given** a cache built from the partial clone, **When** searching with a field filter (e.g., `rating:>=4`), **Then** both present and non-present tracks matching the filter are returned.

---

### User Story 5 - View with --include-missing (Priority: P1)

A developer runs the view command against the partial clone. Without `--include-missing`, only present files get symlinks. With `--include-missing`, all matching files get symlinks (including those whose content is not locally available).

**Why this priority**: This is the primary bug being tested. The `--include-missing` flag must have a measurable effect.

**Independent Test**: Run the view command twice (with and without the flag) and compare symlink counts.

**Acceptance Scenarios**:

1. **Given** a cache built from the partial clone with N total tracks and N/2 present, **When** running the view command without `--include-missing`, **Then** approximately N/2 symlinks are created (only present files).
2. **Given** the same cache, **When** running the view command with `--include-missing`, **Then** approximately N symlinks are created (all files).
3. **Given** the view output with `--include-missing`, **When** inspecting symlinks for non-present files, **Then** the symlinks exist and point to the correct (albeit absent) file paths in the repo.
4. **Given** the view command is run with `--include-missing`, **Then** the number of created symlinks is strictly greater than without the flag.

---

### User Story 6 - View Against Full Repository (Priority: P2)

The view command against the origin repo (all files present) produces symlinks for all matched files, and `--include-missing` has no additional effect since nothing is missing.

**Why this priority**: Validates baseline behavior. Lower priority since the partial clone tests are more revealing.

**Independent Test**: Run view against origin repo with and without the flag, confirm identical output.

**Acceptance Scenarios**:

1. **Given** the origin repo with all files present, **When** running view with and without `--include-missing`, **Then** both runs produce the same number of symlinks.

---

### Edge Cases

- What happens when the template references a metadata field that is not set on some tracks? (Should render as "Unknown")
- What happens when multiple tracks render to the same path? (Numeric suffix deduplication)
- What happens when the cache is built against a repo with zero annexed files? (Empty cache, no errors)

## Requirements

### Functional Requirements

- **FR-001**: Test suite MUST create a real git-annex repository with synthetic audio files in mp3, flac, and aiff formats containing valid audio data.
- **FR-002**: Synthetic audio files MUST have embedded metadata tags (artist, title, album, genre, bpm, year, tracknumber) and cover artwork set via standard audio tagging.
- **FR-003**: Git-annex metadata MUST be set on all files using `git annex metadata` to match the embedded tags, plus additional fields (rating, crate) not stored in audio tags.
- **FR-004**: Test suite MUST create a clone of the origin repo and `git annex get` only a defined subset of files, producing a repo with mixed present/non-present content.
- **FR-005**: Cache build tests MUST verify that all tracks (present and non-present) have non-null `file` paths after cache building.
- **FR-006**: Cache build tests MUST verify that the `present` field accurately reflects local file availability.
- **FR-007**: Search tests MUST verify that results include both present and non-present tracks.
- **FR-008**: View tests MUST verify that `--include-missing` produces strictly more symlinks than the default when non-present files exist.
- **FR-009**: View tests MUST verify symlink targets point to correct file paths.
- **FR-010**: Audio generation dependencies (mutagen, pydub or equivalent) MUST be added to the nix flake dev shell.
- **FR-011**: Existing mock-based tests MUST be replaced where the new integration tests cover equivalent functionality.

### Key Entities

- **Test Fixture Repository**: A temporary git-annex repo with synthetic audio, metadata, and known file structure.
- **Partial Clone**: A clone of the fixture repo with only a subset of file content fetched via `git annex get`.
- **Synthetic Audio File**: A generated audio file with valid audio content, embedded tags, and cover art in one of three formats (mp3, flac, aiff).

## Success Criteria

### Measurable Outcomes

- **SC-001**: All integration tests pass when run via `pytest` in the nix dev shell.
- **SC-002**: The view test with `--include-missing` produces a measurably higher symlink count than without the flag when non-present files exist in the repo.
- **SC-003**: Cache build test confirms 100% of tracks have non-null file paths, and `present` field matches actual local availability for every track.
- **SC-004**: Mock-based tests that are superseded by integration tests are removed, reducing test maintenance burden without losing coverage.

## Assumptions

- `git` and `git-annex` are available in the nix dev shell (already present in `flake.nix`).
- `mutagen` is used for writing audio tags and embedding artwork (standard Python audio tagging library).
- Audio generation uses Python standard library or lightweight dependencies (e.g., `struct` module for WAV-based generation, then convert or write raw PCM).
- The test suite uses `pytest` fixtures with `tmp_path` for temporary directories.
- Tests are placed in `tests/integration/` to distinguish from existing unit tests.
