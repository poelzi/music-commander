# Feature Specification: CUE Sheet Splitter

**Feature Branch**: `008-cue-sheet-splitter`
**Created**: 2026-02-03
**Status**: Draft
**Input**: User description: "create a new cli subsystem called cue. add the first command which is split that splits a full file rip of a cd with cue file. port and integrate /space/Music/bin/split-albums"

## User Scenarios & Testing

### User Story 1 - Split a Single-File CD Rip (Priority: P1)

A user has a directory containing a full CD rip as a single FLAC file alongside a `.cue` sheet. They run `music-cmd cue split /path/to/album/` and the tool parses the cue sheet, splits the single file into individual tracks using shntool, and writes numbered track files (e.g., `01 - Track Title.flac`) into the same directory.

**Why this priority**: This is the core use case — splitting a single-file rip into individual tagged tracks. Without this, nothing else matters.

**Independent Test**: Place a single FLAC + CUE pair in a directory, run `music-cmd cue split <dir>`, and verify individual track files are created with correct boundaries.

**Acceptance Scenarios**:

1. **Given** a directory with `album.cue` and `album.flac`, **When** the user runs `music-cmd cue split /path/to/dir`, **Then** individual FLAC files are created for each track defined in the cue sheet, named `{tracknum:02d} - {title}.flac`.
2. **Given** the cue sheet references a file that does not exist in the directory, **When** the user runs the split command, **Then** an error is reported identifying the missing source file and no partial output is created.
3. **Given** split output files already exist in the directory, **When** the user runs the split command without `--force`, **Then** the split is skipped for that cue/file pair and a message is printed.

---

### User Story 2 - Tag Split Files with CUE Metadata (Priority: P1)

After splitting, each output track is tagged with metadata extracted from the cue sheet: artist/performer, album title, track title, track number, genre, date, songwriter, ISRC, and disc ID where available.

**Why this priority**: Untagged split files are nearly useless. Tagging is inseparable from the split operation.

**Independent Test**: After splitting, inspect output FLAC files with `metaflac --export-tags-to=-` and verify all cue sheet metadata fields are present.

**Acceptance Scenarios**:

1. **Given** a cue sheet with PERFORMER, TITLE, and REM DATE fields, **When** the split completes, **Then** each output track has ARTIST, ALBUM, TITLE, TRACKNUMBER, and DATE tags set correctly.
2. **Given** a cue sheet where a track overrides the global PERFORMER, **When** the split completes, **Then** that track's ARTIST tag reflects the track-level performer, not the global one.
3. **Given** a cue sheet with REM GENRE and REM ISRC fields, **When** the split completes, **Then** each track has GENRE and ISRC tags set.

---

### User Story 3 - Embed Cover Art (Priority: P2)

After splitting and tagging, the tool searches for image files in the same directory (`.jpg`, `.png`) and embeds them into each split track. A single image is embedded as front cover. If multiple images exist, files matching "front" or "cover" are embedded as front cover (type 3) and files matching "back" are embedded as back cover (type 4).

**Why this priority**: Cover art embedding completes the "ready to use" experience but the tracks are functional without it.

**Independent Test**: Place a `cover.jpg` alongside the FLAC + CUE, run split, and verify the output tracks contain embedded cover art.

**Acceptance Scenarios**:

1. **Given** a single image file (`cover.jpg`) in the directory, **When** the split completes, **Then** each output track has that image embedded as front cover art.
2. **Given** multiple image files including `front.jpg` and `back.jpg`, **When** the split completes, **Then** `front.jpg` is embedded as type 3 (front cover) and `back.jpg` is embedded as type 4 (back cover).
3. **Given** no image files in the directory, **When** the split completes, **Then** tracks are created without cover art and no error is raised.

---

### User Story 4 - Recursive Directory Walk (Priority: P2)

A user has a large collection with many albums, some of which contain unsplit CD rips. They run `music-cmd cue split /path/to/collection --recursive` and the tool walks the directory tree, finding all directories with cue + audio file pairs, and splits each one.

**Why this priority**: Batch processing is essential for large collections but the single-directory case must work first.

**Independent Test**: Create a nested directory structure with multiple cue/flac pairs at different depths, run with `--recursive`, and verify all are split.

**Acceptance Scenarios**:

1. **Given** a directory tree with cue/flac pairs at multiple depths, **When** the user runs with `--recursive`, **Then** all pairs are found and split.
2. **Given** a directory tree where some albums are already split, **When** the user runs with `--recursive`, **Then** already-split albums are skipped and only unsplit ones are processed.
3. **Given** `--recursive` is not specified, **When** the user runs on a directory, **Then** only the specified directory is processed (no subdirectory traversal).

---

### User Story 5 - Support Multiple Source Formats (Priority: P2)

A user has CD rips in formats other than FLAC (e.g., WAV, APE, WavPack). The tool detects the source format referenced in the cue sheet and splits it, always outputting FLAC tracks.

**Why this priority**: Broadens the tool's applicability but FLAC is by far the most common case.

**Independent Test**: Place a `.ape` + `.cue` pair in a directory, run split, and verify FLAC tracks are produced.

**Acceptance Scenarios**:

1. **Given** a cue sheet referencing a `.wav` file, **When** the split runs, **Then** individual FLAC tracks are created.
2. **Given** a cue sheet referencing a `.ape` file, **When** the split runs, **Then** individual FLAC tracks are created.
3. **Given** a cue sheet referencing a `.wv` (WavPack) file, **When** the split runs, **Then** individual FLAC tracks are created.
4. **Given** a cue sheet referencing an unsupported format, **When** the split runs, **Then** an error is reported identifying the unsupported format.

---

### User Story 6 - Remove Originals After Split (Priority: P3)

A user wants to clean up after splitting. They pass `--remove-originals` and after a successful split, the original single-file rip and cue file are deleted.

**Why this priority**: Convenience feature. Users can always delete manually.

**Independent Test**: Run split with `--remove-originals`, verify originals are gone and split files remain.

**Acceptance Scenarios**:

1. **Given** `--remove-originals` is specified, **When** the split completes successfully, **Then** the original source audio file and cue file are deleted.
2. **Given** `--remove-originals` is specified but the split fails, **When** the error occurs, **Then** the original files are preserved.
3. **Given** `--remove-originals` is not specified, **When** the split completes, **Then** the original files are left in place.

---

### Edge Cases

- What happens when the cue sheet has encoding issues (non-UTF-8)? The parser attempts common encodings (UTF-8, Latin-1, CP1252) and reports an error if none succeed, suggesting the user specify an encoding with `--encoding`.
- What happens when the cue sheet references multiple FILE commands (multi-file cue)? Each FILE block is processed independently, splitting the corresponding source file.
- What happens when track titles contain filesystem-unsafe characters (`/`, `\`, `:`)? Unsafe characters are replaced with safe alternatives (e.g., `_`) in output filenames.
- What happens when shntool is not installed? The command reports the missing dependency and exits before processing.
- What happens when the source audio file is shorter than the cue sheet implies? shntool reports the error; the tool relays it and skips that cue/file pair.
- What happens when a cue sheet has INDEX 00 (pregap) entries? Only INDEX 01 (track start) positions are used for split points, consistent with standard CD playback behavior.
- What happens with hidden tracks before INDEX 01 of track 1? The pregap audio before the first track's INDEX 01 is discarded (standard behavior).
- What happens when `--dry-run` is specified? The tool reports which cue/file pairs would be split and how many tracks each contains, without performing any actual splitting or tagging.

## Requirements

### Functional Requirements

- **FR-001**: The command MUST be registered as a new `cue` command group with a `split` subcommand, following the existing command group pattern (auto-discovered via `cli` attribute).
- **FR-002**: The `split` command MUST accept one or more directory path arguments to process.
- **FR-003**: The `split` command MUST support a `--recursive` / `-r` flag to walk directory trees.
- **FR-004**: The command MUST parse `.cue` files to extract global metadata (performer, album title, genre, date, songwriter, disc ID, comments) and per-track metadata (title, performer, ISRC, index positions).
- **FR-005**: The command MUST use shntool to split the source audio file at the index positions defined in the cue sheet.
- **FR-006**: The output format MUST be FLAC for all split tracks regardless of source format.
- **FR-007**: Output files MUST be named `{tracknum:02d} - {title}.flac` where tracknum is zero-padded to 2 digits and title comes from the cue sheet.
- **FR-008**: The command MUST tag each split FLAC file with metadata from the cue sheet using metaflac. Tags: ARTIST (from PERFORMER), ALBUM (from TITLE at global level), TITLE (from TITLE at track level), TRACKNUMBER, GENRE, DATE, SONGWRITER, ISRC, DISCID.
- **FR-009**: Track-level metadata MUST override global-level metadata (e.g., a track-specific PERFORMER overrides the global PERFORMER for that track's ARTIST tag).
- **FR-010**: The command MUST add ReplayGain tags to split files using `metaflac --add-replay-gain`.
- **FR-011**: The command MUST search for image files (`.jpg`, `.png`) in the source directory and embed them as cover art using metaflac. A single image is embedded as front cover. Multiple images use filename matching: "front"/"cover" patterns → type 3 (front cover), "back" patterns → type 4 (back cover).
- **FR-012**: The command MUST support `.flac`, `.wav`, `.ape`, and `.wv` source audio formats.
- **FR-013**: The command MUST support a `--remove-originals` flag that deletes the source audio file and cue file after a successful split.
- **FR-014**: The command MUST skip cue/file pairs where split output files already exist, unless `--force` is specified.
- **FR-015**: The command MUST support `--dry-run` to preview what would be split without performing any operations.
- **FR-016**: The command MUST support `--encoding` to specify the character encoding of cue files. Without it, the parser MUST attempt UTF-8 first, then fall back to Latin-1.
- **FR-017**: The command MUST sanitize track titles for use in filenames, replacing filesystem-unsafe characters.
- **FR-018**: The command MUST handle multi-FILE cue sheets where the cue references multiple source files.
- **FR-019**: The command MUST display progress using the existing Rich-based output utilities (`verbose()`, `info()`, `error()`).
- **FR-020**: The command MUST support `--verbose` / `-v` for detailed output (shntool commands, tag operations) and `--debug` for maximum verbosity.
- **FR-021**: The cue parser MUST be implemented as a standalone module (`music_commander/cue/parser.py`) reusable by future cue-related commands.

### Key Entities

- **CueSheet**: Represents a parsed cue file. Contains global metadata (performer, album, genre, date, file reference) and a list of tracks.
- **CueTrack**: Represents a single track within a cue sheet. Contains track number, title, performer (optional override), start position in samples, end position in samples (None for last track), and additional metadata (ISRC, songwriter).
- **SplitResult**: Represents the outcome of splitting one cue/file pair. Contains source path, cue path, number of tracks, list of output files, status (ok/skipped/error), error message if any.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can split a single-file CD rip with cue sheet into individually tagged FLAC tracks with a single command.
- **SC-002**: All metadata fields present in the cue sheet are accurately transferred to the split track tags.
- **SC-003**: Cover art from the album directory is automatically embedded into all split tracks.
- **SC-004**: Batch processing of an entire collection via `--recursive` finds and splits all unsplit cue/file pairs without manual intervention.
- **SC-005**: Source formats beyond FLAC (WAV, APE, WavPack) are handled transparently with FLAC output.
- **SC-006**: The cue parser is reusable for future cue-related commands within the `cue` subgroup.

## Assumptions

- shntool will be added as a dependency in the nix flake (not currently present).
- metaflac is already available (used by existing features).
- The cue parser is ported and improved from the existing `/space/Music/bin/split-albums` script, fixing known bugs (e.g., TRACKNUMBER tag name, proper encoding handling).
- ffmpeg is available but shntool is preferred for the actual splitting as it handles cue-based splits natively and accurately (frame-level precision at CD 44100Hz/75fps boundaries).
- Output is always FLAC regardless of source format. Future commands in the `cue` group could add format options if needed.
- The `cue` command group follows the same auto-discovery pattern as `bandcamp/`, `files/`, and `dev/`.
