# Feature Specification: Files Export Recode

**Feature Branch**: `006-file-export-recode`
**Created**: 2026-01-31
**Status**: Draft
**Input**: User description: "Add a file export recoding feature. Like view but it will recode the files in the specified format. Create a list of format definitions, like mp3-320, aiff, flac, flac-pioneer (16 bit, 2 channels no multichannel, 44.1 kHz - full Pioneer compatible). Format can be specified on encoding. Make sure all metatags and cover are transferred. Use ffmpeg as the backend. If no cover art is embedded and a cover file exists, embed the file. Files already in the correct format can be copied. Add incremental skip-existing support. Also add aiff-pioneer and wav-pioneer for downscaling to 16-bit 44.1kHz stereo."

## User Scenarios & Testing

### User Story 1 - Export Collection in a Specific Format (Priority: P1)

A user wants to export their music collection (or a subset) to a specific format for use on a DJ player. They run `music-cmd files export "rating:>=3" -p "{{ genre }}/{{ artist }} - {{ title }}" -o /mnt/usb --format flac-pioneer`. The tool searches for matching files, recodes each to the specified format using ffmpeg, writes them to the output directory following the template pattern, and transfers all metadata and cover art.

**Why this priority**: This is the core use case -- exporting files in a target format with metadata preservation.

**Independent Test**: Run `music-cmd files export "rating:>=4" -p "{{ artist }}/{{ title }}" -o /tmp/export --format mp3-320` and verify files are recoded to MP3 320kbps with metadata and cover art intact.

**Acceptance Scenarios**:

1. **Given** a git-annex repository with FLAC files, **When** the user runs `music-cmd files export "artist:Basinski" -p "{{ artist }} - {{ title }}" -o /tmp/export --format mp3-320`, **Then** each matching file is recoded to MP3 320kbps CBR, placed in the output directory following the template, with all metadata tags and cover art preserved.
2. **Given** a mix of file formats (FLAC, MP3, WAV), **When** the user exports with `--format flac-pioneer`, **Then** all files are converted to FLAC with 16-bit depth, 44.1kHz sample rate, stereo, and no WAVEFORMATEXTENSIBLE_CHANNEL_MASK tag.
3. **Given** the export completes, **When** the user inspects the output files, **Then** metadata fields (artist, title, album, genre, year, tracknumber, comment, BPM, key, etc.) are present in the output files.

---

### User Story 2 - Auto-detect Format from Extension (Priority: P2)

A user wants to export without specifying a format preset. The tool infers the best preset from the output file extension. For example, files ending in `.flac` use the `flac` preset, `.mp3` uses `mp3-320`, `.aiff` uses `aiff`.

**Why this priority**: Convenience feature that reduces command-line verbosity for common cases.

**Independent Test**: Run `music-cmd files export query -p "{{ title }}.mp3" -o /tmp/export` without `--format` and verify the mp3-320 preset is used.

**Acceptance Scenarios**:

1. **Given** no `--format` is specified and the template ends in `.mp3`, **When** the export runs, **Then** the `mp3-320` preset is used.
2. **Given** no `--format` is specified and the template ends in `.flac`, **When** the export runs, **Then** the `flac` preset is used.
3. **Given** no `--format` is specified and the template has no extension or an unrecognized extension, **When** the export runs, **Then** the command reports an error asking the user to specify `--format` explicitly.

---

### User Story 3 - Copy Instead of Recode (Priority: P2)

A user exports to FLAC format, and some source files are already FLAC files that match the target parameters (same bit depth, sample rate, channels). These files are copied directly instead of being re-encoded, preserving quality and saving time.

**Why this priority**: Avoiding unnecessary transcoding preserves quality and significantly speeds up exports when source and target formats overlap.

**Independent Test**: Export FLAC files with `--format flac` and verify matching files are copied (not re-encoded) by checking file checksums or encoding speed.

**Acceptance Scenarios**:

1. **Given** a source file is already in the target format with matching parameters (bit depth, sample rate, channels), **When** the export runs, **Then** the file is copied directly without re-encoding.
2. **Given** a source FLAC file at 24-bit/96kHz and the target is `flac-pioneer` (16-bit/44.1kHz), **When** the export runs, **Then** the file is re-encoded to match the target parameters.
3. **Given** a source MP3-320 file and the target is `mp3-320`, **When** the export runs, **Then** the file is copied directly.

---

### User Story 4 - Incremental Export (Priority: P2)

A user runs the export command multiple times. Files that already exist in the output directory with the correct name are skipped, making subsequent runs fast.

**Why this priority**: Essential for maintaining USB drives or external collections that are periodically updated.

**Independent Test**: Run the export twice. Verify the second run completes faster and skips already-exported files.

**Acceptance Scenarios**:

1. **Given** a file already exists at the target path, **When** the export runs, **Then** the file is skipped and reported as "skipped" in the output.
2. **Given** `--force` is specified, **When** the export runs, **Then** all files are re-exported regardless of existing output.
3. **Given** the source file has been modified since the last export, **When** the export runs, **Then** the file is re-exported (mtime comparison).

---

### User Story 5 - Cover Art Embedding (Priority: P2)

A user has files where cover art is stored as an external file (e.g., `cover.jpg`, `folder.jpg`) in the same directory rather than embedded in the audio file. During export, the tool finds and embeds this external cover art into the output files.

**Why this priority**: Many collections have external cover art, especially for FLAC files. DJ players typically need embedded art.

**Independent Test**: Export a FLAC file that has no embedded cover but has a `cover.jpg` in its directory. Verify the output file contains the embedded cover art.

**Acceptance Scenarios**:

1. **Given** a source file with embedded cover art, **When** the export runs, **Then** the cover art is preserved in the output file.
2. **Given** a source file without embedded cover art but with a `cover.jpg` or `folder.jpg` in the same directory, **When** the export runs, **Then** the external cover art is embedded in the output file.
3. **Given** a source file without any cover art (embedded or external), **When** the export runs, **Then** the file is exported without cover art and no error is raised.

---

### User Story 6 - Parallel Export with Jobs (Priority: P3)

A user wants to speed up the export by running multiple ffmpeg processes in parallel: `music-cmd files export query -o /tmp/export --format mp3-320 --jobs 4`.

**Why this priority**: Performance optimization for large exports. Core functionality works without this.

**Independent Test**: Run with `--jobs 4` and verify multiple files are converted concurrently.

**Acceptance Scenarios**:

1. **Given** `--jobs N` is specified, **When** the export runs, **Then** up to N files are converted concurrently.
2. **Given** parallel export, **When** interrupted with Ctrl+C, **Then** running ffmpeg processes are terminated and partial output files are cleaned up.

---

### Edge Cases

- What happens when the output directory does not exist? It is created automatically (including parent directories).
- What happens when two source files resolve to the same output path? A numeric suffix is appended (same as `view` command duplicate handling).
- What happens when ffmpeg is not available? The command reports the error and exits before processing any files.
- What happens when a source file is not locally present (annexed but dropped)? It is skipped and reported as "not_present".
- What happens when export is interrupted (Ctrl+C)? Running ffmpeg processes are killed, partially written output files are removed, and a summary of completed files is shown.
- What happens when the source file is corrupt? The ffmpeg error is reported, the file is marked as "error", and the export continues with remaining files.
- What happens when disk space runs out? The ffmpeg error is reported, and the export stops with an appropriate message.

## Requirements

### Functional Requirements

- **FR-001**: The command MUST be registered as `files export` under the existing `files` command group.
- **FR-002**: The command MUST accept a search query and/or file/directory path arguments (same auto-detection as `files check` and `files view`).
- **FR-003**: The command MUST require a `--pattern` / `-p` option specifying a Jinja2 template for output file paths (same template system as `files view`).
- **FR-004**: The command MUST require a `--output` / `-o` option specifying the base output directory.
- **FR-005**: The command MUST support a `--format` / `-f` option to select a format preset.
- **FR-006**: If `--format` is not specified, the command MUST infer the preset from the file extension in the template pattern. If no extension or an unrecognized extension is present, the command MUST exit with an error.
- **FR-007**: The command MUST use ffmpeg as the encoding backend for all format conversions.
- **FR-008**: The command MUST transfer all metadata tags from the source to the output file.
- **FR-009**: The command MUST preserve embedded cover art from source files in the output.
- **FR-010**: If a source file has no embedded cover art, the command MUST search for external cover art files in the source file's directory (`cover.jpg`, `cover.png`, `folder.jpg`, `folder.png`, `front.jpg`, `front.png`) and embed the first one found.
- **FR-011**: Files that are already in the correct format and match all target parameters (codec, bit depth, sample rate, channels) MUST be copied directly instead of re-encoded.
- **FR-012**: By default, the command MUST skip files whose output path already exists (incremental mode). A `--force` flag MUST override this to re-export all files.
- **FR-013**: For incremental mode, the command SHOULD compare source and destination modification times to detect changed source files that need re-export.
- **FR-014**: The command MUST support `--jobs N` for parallel encoding (default 1).
- **FR-015**: The command MUST support `--dry-run` to preview which files would be exported, their source format, target format, and whether they would be copied or re-encoded.
- **FR-016**: The command MUST display live progress using the existing `MultilineFileProgress` pattern.
- **FR-017**: The command MUST support `--verbose` / `-v` to show ffmpeg commands and output.
- **FR-018**: On interruption (SIGINT), the command MUST terminate running ffmpeg processes, remove partially written output files, and show a summary of completed work.
- **FR-019**: Output directories MUST be created automatically as needed.
- **FR-020**: Duplicate output paths (from template collisions) MUST be resolved by appending a numeric suffix, consistent with the `view` command.

### Format Presets

The following presets MUST be supported:

| Preset | Codec | Container | Bit Rate / Depth | Sample Rate | Channels | Notes |
|--------|-------|-----------|------------------|-------------|----------|-------|
| `mp3-320` | LAME MP3 | .mp3 | 320 kbps CBR | source | source | `-b:a 320k` |
| `mp3-v0` | LAME MP3 | .mp3 | VBR V0 (~245 kbps) | source | source | `-q:a 0` |
| `flac` | FLAC | .flac | source | source | source | Lossless copy of source parameters |
| `flac-pioneer` | FLAC | .flac | 16-bit | 44100 Hz | 2 (stereo) | No WAVEFORMATEXTENSIBLE_CHANNEL_MASK; Pioneer DJ compatible |
| `aiff` | PCM | .aiff | source | source | source | Uncompressed, preserves source parameters |
| `aiff-pioneer` | PCM | .aiff | 16-bit | 44100 Hz | 2 (stereo) | Pioneer DJ compatible |
| `wav` | PCM | .wav | source | source | source | Uncompressed, preserves source parameters |
| `wav-pioneer` | PCM | .wav | 16-bit | 44100 Hz | 2 (stereo) | Pioneer DJ compatible |

**Extension-to-preset mapping** (when `--format` is not specified):

| Extension | Default Preset |
|-----------|---------------|
| `.mp3` | `mp3-320` |
| `.flac` | `flac` |
| `.aiff` / `.aif` | `aiff` |
| `.wav` | `wav` |

### Pioneer-specific Requirements

- **FR-P01**: The `flac-pioneer` preset MUST produce files with exactly 2 channels, 16-bit sample depth, and 44100 Hz sample rate.
- **FR-P02**: The `flac-pioneer` preset MUST NOT include a `WAVEFORMATEXTENSIBLE_CHANNEL_MASK` vorbis comment tag in the output file. If ffmpeg adds this tag, it MUST be stripped using `metaflac --remove-tag=WAVEFORMATEXTENSIBLE_CHANNEL_MASK` as a post-processing step.
- **FR-P03**: The `aiff-pioneer` and `wav-pioneer` presets MUST produce files with exactly 2 channels, 16-bit sample depth, and 44100 Hz sample rate.

### Key Entities

- **FormatPreset**: Defines the target encoding parameters for a format. Contains: name, codec, container extension, ffmpeg arguments, bit depth (optional), sample rate (optional), channels (optional), post-processing steps (optional).
- **ExportResult**: Represents the outcome of exporting a single file. Contains: source path, output path, status (ok/copied/skipped/error/not_present), format preset used, duration, error message (if any).
- **ExportReport**: Top-level output structure. Contains: list of ExportResult entries, summary counts (total, ok, copied, skipped, error, not_present), run metadata (start time, end time, format preset, output directory).

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can export their music collection to any supported format with a single command, with all metadata and cover art preserved.
- **SC-002**: Pioneer DJ players can play files exported with the `*-pioneer` presets without multichannel or format compatibility issues.
- **SC-003**: Files already in the correct format are copied instead of re-encoded, preserving quality and saving time.
- **SC-004**: Incremental exports skip already-exported files, making repeated exports efficient.
- **SC-005**: External cover art files are automatically discovered and embedded when no embedded art exists.
- **SC-006**: The template system from `files view` is reused for consistent output path generation.

## Clarifications

### Session 2026-01-31

- Q: What template system should be used for output paths? → A: Same Jinja2 template system as the `files view` command, with all the same variables (artist, title, album, genre, etc.) and filters available.
- Q: What encoding backend should be used? → A: ffmpeg for all conversions.
- Q: Should external cover art be embedded? → A: Yes, if no cover art is embedded in the source file and a cover file exists in the same directory, embed it.
- Q: Should files already in the correct format be re-encoded? → A: No, files already matching the target format can be copied directly.
- Q: What format should the output file extension be? → A: Determined by the format preset. The template should include the extension, or it will be appended based on the preset's container format.
- Q: What happens when no `--format` is specified? → A: Infer the best preset from the file extension in the template pattern. Use the extension-to-preset mapping table.
- Q: Should there be Pioneer-specific presets beyond `flac-pioneer`? → A: Yes, `aiff-pioneer` and `wav-pioneer` for downcoding to 16-bit 44.1kHz stereo.

## Assumptions

- ffmpeg is available in the Nix environment (already a dependency).
- metaflac is available for the FLAC multichannel mask stripping post-processing step (already a dependency).
- The Jinja2 template rendering and path sanitization code from `files view` can be reused directly.
- File format detection for the "copy instead of recode" optimization uses ffprobe to check source file parameters against the target preset.
- Metadata mapping between formats is handled by ffmpeg's built-in metadata copying (`-map_metadata 0`).
- For formats that don't support certain metadata fields, ffmpeg silently drops unsupported tags (acceptable behavior).
