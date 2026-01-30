# Feature Specification: Files Check Integrity

**Feature Branch**: `005-files-check-integrity`
**Created**: 2026-01-30
**Status**: Draft
**Input**: User description: "add a 'files check' command that checks the files for problems. depending on the filetype use 'flac -t' or other file format checkers that they are up to spec. Ensure nix has the deps. The command should create a output file that can be used later for automatic repair progress."

## User Scenarios & Testing

### User Story 1 - Check All Present Files (Priority: P1)

A user wants to verify the integrity of their entire local music collection. They run `music-cmd files check` with no arguments. The tool scans all locally-present annexed files, runs format-specific integrity checks, displays live progress, and writes a JSON results file listing every file's status.

**Why this priority**: This is the core use case -- bulk integrity checking of the full collection. Without this, the feature has no value.

**Independent Test**: Run `music-cmd files check` in a repository containing files of various formats. Verify each file is checked with the correct tool, progress is displayed, and the output JSON file is written.

**Acceptance Scenarios**:

1. **Given** a git-annex repository with locally-present FLAC, MP3, OGG, WAV, AIFF, and M4A files, **When** the user runs `music-cmd files check`, **Then** each file is validated using its format-specific tool and results are displayed with live progress (Fetching/Fetched-style output).
2. **Given** some annexed files are not locally present, **When** the user runs `music-cmd files check`, **Then** unavailable files are reported as "not present" in the output and skipped (not treated as errors).
3. **Given** the check completes, **When** results are written, **Then** a JSON file is created at a deterministic location containing the status, tool used, and any error messages for every file processed.

---

### User Story 2 - Check Files by Search Query (Priority: P2)

A user wants to check only a subset of files -- for example, all FLAC files by a specific artist, or all files with a certain rating. They provide a search query: `music-cmd files check "artist:Basinski"`.

**Why this priority**: Targeted checking is essential for large collections where full scans are impractical. Reuses existing search infrastructure.

**Independent Test**: Run `music-cmd files check "genre:ambient"` and verify only matching files are checked.

**Acceptance Scenarios**:

1. **Given** a search query, **When** the user runs `music-cmd files check "rating:>=4"`, **Then** only files matching the query are checked.
2. **Given** no files match the query, **When** the check runs, **Then** an informational message is shown and the command exits cleanly.

---

### User Story 3 - Check Files by Path (Priority: P2)

A user wants to check specific files or all files in a directory. They provide file paths or directory paths: `music-cmd files check path/to/album/`.

**Why this priority**: Direct path-based checking complements search-based selection for quick spot checks and directory-level validation.

**Independent Test**: Run `music-cmd files check path/to/file.flac path/to/directory/` and verify the specified file and all files in the directory (recursively) are checked.

**Acceptance Scenarios**:

1. **Given** a file path argument, **When** the user runs `music-cmd files check track.flac`, **Then** only that file is checked.
2. **Given** a directory path argument, **When** the user runs `music-cmd files check some/album/`, **Then** all audio files in that directory (recursively) are checked.
3. **Given** a mix of file and directory paths, **When** the check runs, **Then** all specified files and all files within specified directories are checked.

---

### User Story 4 - Parallel Checking with Jobs (Priority: P3)

A user with a large collection wants to speed up checking by running multiple checks in parallel: `music-cmd files check --jobs 4`.

**Why this priority**: Performance optimization for large collections. The core functionality works without this.

**Independent Test**: Run with `--jobs 4` and verify multiple files are checked concurrently and results remain correct.

**Acceptance Scenarios**:

1. **Given** `--jobs N` is specified, **When** the check runs, **Then** up to N files are checked concurrently.
2. **Given** parallel checking, **When** results are written, **Then** the output JSON file is complete and consistent (no missing or duplicate entries).

---

### User Story 5 - JSON Output for Automated Repair (Priority: P1)

A user runs `files check` and later uses the output file to drive an automated repair workflow. The output file must contain sufficient information to identify broken files, the nature of each failure, and the tool that detected it.

**Why this priority**: The output file is the primary deliverable for downstream automation. Without a well-structured output, the check results cannot be acted upon.

**Independent Test**: Run `files check`, read the output JSON, and verify it contains all necessary fields for each file (path, status, checker tool, error output).

**Acceptance Scenarios**:

1. **Given** a completed check, **When** the output file is read, **Then** each entry contains: file path, check status (ok/error/not_present), tool used, and raw error output (if any).
2. **Given** a file that fails validation, **When** its entry is read, **Then** the error message from the checking tool is preserved verbatim for diagnosis.
3. **Given** the output file exists from a previous run, **When** `files check` runs again, **Then** the file is overwritten with fresh results.

---

### User Story 6 - Dry Run (Priority: P3)

A user wants to preview which files would be checked and with which tool without actually running the checks: `music-cmd files check --dry-run`.

**Why this priority**: Useful for verification but not essential for core functionality.

**Independent Test**: Run with `--dry-run` and verify files are listed with their checker tool but no actual validation occurs.

**Acceptance Scenarios**:

1. **Given** `--dry-run` is specified, **When** the command runs, **Then** files are listed with their associated checker tool but no validation is performed and no output file is written.

---

### Edge Cases

- What happens when a required checker tool is not installed? The command reports which tool is missing, skips files of that type, and marks them with a clear status in the output (e.g., "checker_missing").
- What happens when a file has an unrecognized extension? The ffmpeg fallback is used.
- What happens when a file is a broken symlink (annexed but not present)? It is logged as "not_present" and skipped.
- What happens when the check is interrupted (Ctrl+C)? Partial results gathered so far are written to the output file so progress is not lost.
- What happens with zero-byte files? They are reported as errors.

## Requirements

### Functional Requirements

- **FR-001**: The command MUST be registered as `files check` under the existing `files` command group.
- **FR-002**: With no arguments, the command MUST check all locally-present annexed files in the repository.
- **FR-003**: The command MUST accept an optional search query (same syntax as `files get`) to filter files.
- **FR-004**: The command MUST accept optional file/directory path arguments for direct path-based selection. Directories MUST be scanned recursively.
- **FR-005**: The command MUST select the checking tool based on file extension:
  - `.flac` -> `flac -t -s -w`
  - `.mp3` -> `mp3val` (structural) then `ffmpeg` (full decode)
  - `.ogg` -> `ogginfo` then `ffmpeg` (full decode)
  - `.wav` -> `shntool len` (structural) then `sox` (full decode)
  - `.aiff` / `.aif` -> `sox` (full decode)
  - `.m4a` -> `ffmpeg` (full decode)
  - All other extensions -> `ffmpeg` (full decode)
- **FR-006**: The command MUST write a JSON output file containing results for every file processed.
- **FR-007**: The command MUST display live progress using the existing `MultilineFileProgress` pattern (in-flight files shown above progress bar, completed files logged permanently).
- **FR-008**: Files that are not locally present MUST be reported as "not_present" in the output and logged as informational during the run.
- **FR-009**: The command MUST support `--jobs N` for parallel file checking (default 1).
- **FR-010**: The command MUST support `--dry-run` to preview files and their checker tools without running checks.
- **FR-011**: The command MUST support `--output` / `-o` to specify a custom output file path. Default location: `<repo>/.music-commander-check-results.json`.
- **FR-012**: The command MUST support `--verbose` / `-v` to show per-file checker commands and output.
- **FR-013**: If a required checker tool is not available on PATH, the command MUST skip files of that type, report the missing tool, and mark entries as "checker_missing" in the output.
- **FR-014**: The Nix flake MUST include all required checker tools as dependencies: `mp3val`, `shntool`, `vorbis-tools` (provides `ogginfo`), `sox`. (`flac` and `ffmpeg` are already present.)
- **FR-015**: On interruption (SIGINT), partial results MUST be written to the output file.
- **FR-016**: The JSON output file MUST overwrite any existing file at the same path.

### Key Entities

- **CheckResult**: Represents the outcome of checking a single file. Contains: file path (relative to repo), status (ok/error/not_present/checker_missing), checker tool(s) used, raw error output (if any), timestamp.
- **CheckReport**: The top-level output structure. Contains: list of CheckResult entries, summary counts (total, ok, errors, not_present, checker_missing), run metadata (start time, end time, repository path, command arguments).

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can check all locally-present files in their collection with a single command and receive per-file pass/fail results.
- **SC-002**: The JSON output file contains sufficient detail for each failed file to diagnose and drive automated repair.
- **SC-003**: Format-specific tools are used for each supported audio format, providing deeper validation than a generic decoder.
- **SC-004**: Parallel checking with `--jobs N` reduces wall-clock time proportionally for I/O-bound checks.
- **SC-005**: Files not present locally are clearly distinguished from files that failed validation.

## Assumptions

- The user's Nix environment provides all checker tools. Non-Nix environments may lack some tools; the command degrades gracefully by skipping unsupported formats.
- File format is determined by extension, not by probing file contents (consistent with how the rest of music-commander operates).
- The ffmpeg fallback checks both exit code AND stderr output to detect non-fatal errors that ffmpeg reports but does not fail on.
- For formats with two-tier checking (MP3: mp3val + ffmpeg; OGG: ogginfo + ffmpeg; WAV: shntool + sox), both tools run and errors from either are reported.
