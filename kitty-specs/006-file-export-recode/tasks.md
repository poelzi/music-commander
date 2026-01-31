# Work Packages: File Export Recode

**Inputs**: Design documents from `kitty-specs/006-file-export-recode/`
**Prerequisites**: plan.md (required), spec.md (user stories), research.md, data-model.md

**Organization**: Fine-grained subtasks (`Txxx`) roll up into work packages (`WPxx`). Each work package is independently deliverable.

---

## Work Package WP01: Encoder Module -- Presets & Probing (Priority: P0)

**Goal**: Create `music_commander/utils/encoder.py` with format preset definitions, source file probing, cover art detection, and copy-vs-recode decision logic.
**Independent Test**: Import `encoder` module; verify preset lookup, ffprobe parsing, cover art detection, and copy decision logic with unit tests.
**Prompt**: `tasks/WP01-encoder-presets-and-probing.md`

### Included Subtasks
- [x] T001 Create `FormatPreset` frozen dataclass and `PRESETS` registry with all 8 presets, plus `EXTENSION_TO_PRESET` mapping
- [x] T002 Create `SourceInfo` dataclass and implement `probe_source(file_path)` using ffprobe JSON output
- [x] T003 [P] Implement `find_cover_art(file_path)` to search source directory for external cover files
- [x] T004 [P] Implement `can_copy(source_info, preset)` to compare source parameters against preset requirements

### Implementation Notes
- `FormatPreset` fields: name, codec, container, ffmpeg_args, sample_rate, bit_depth, channels, post_commands, supports_cover_art (see data-model.md).
- `PRESETS` is a `dict[str, FormatPreset]` mapping preset names to instances. All 8 presets defined per plan.md preset table.
- `EXTENSION_TO_PRESET` maps `.mp3` -> `"mp3-320"`, `.flac` -> `"flac"`, `.aiff`/`.aif` -> `"aiff"`, `.wav` -> `"wav"`.
- `probe_source()` runs `ffprobe -v quiet -select_streams a:0 -show_entries stream=codec_name,bits_per_raw_sample,sample_fmt,sample_rate,channels -print_format json`. Parse `bits_per_raw_sample` first; fall back to `sample_fmt` mapping (`s16`/`s16p` -> 16, `s24` -> 24, `s32`/`s32p` -> 32, `flt`/`fltp` -> 32). Check embedded art with `ffprobe -v quiet -select_streams v -show_entries stream=codec_name -of csv=p=0`.
- `find_cover_art()` searches: `cover.jpg`, `cover.png`, `folder.jpg`, `folder.png`, `front.jpg`, `front.png` (case-insensitive).
- `can_copy()`: returns True if source codec matches preset codec AND (preset.sample_rate is None OR matches source) AND same for bit_depth AND channels.

### Parallel Opportunities
- T003 and T004 can proceed in parallel (independent functions).

### Dependencies
- None (starting package).

### Risks & Mitigations
- ffprobe `bits_per_raw_sample` may be empty for some codecs (e.g., MP3). Fall back to `sample_fmt` parsing. If both fail, assume 16-bit.
- Codec name comparison: ffprobe reports `mp3` not `libmp3lame`. Map preset codec names to ffprobe codec names for comparison in `can_copy()`.

---

## Work Package WP02: Encoder Module -- Encoding & Export Logic (Priority: P0)

**Goal**: Implement the core encoding pipeline: ffmpeg command building, single-file export orchestration, temp file safety, post-processing, and report writing.
**Independent Test**: Mock ffmpeg subprocess; verify `export_file()` produces correct commands for encode, stream-copy, and file-copy paths.
**Prompt**: `tasks/WP02-encoder-export-logic.md`

### Included Subtasks
- [x] T005 Implement `build_ffmpeg_command(input, output, preset, source_info, cover_path)` for all encoding scenarios
- [x] T006 Implement `export_file(file_path, output_path, preset, repo_path, *, verbose)` orchestrating probe -> decide -> encode/copy -> post-process
- [x] T007 Create `ExportResult` and `ExportReport` dataclasses and implement `write_export_report()`

### Implementation Notes
- `build_ffmpeg_command()` handles 4 scenarios per plan.md: (1) full encode without cover, (2) full encode with external cover, (3) stream copy without cover, (4) stream copy with external cover. For source files with embedded art, use `-map 0:a -map 0:v` to preserve it. Always include `-map_metadata 0` and `-y` (overwrite).
- `export_file()` flow: probe source -> find cover art if no embedded art -> check `can_copy()` -> if copy-eligible and no art needed: `shutil.copy2()` -> if copy-eligible but needs art: stream copy via ffmpeg -> else: full encode. After ffmpeg, run `post_commands` if preset has them. Write to temp file (`.tmp` suffix in same dir), rename on success.
- For `flac-pioneer`: post-processing is `["metaflac", "--remove-tag=WAVEFORMATEXTENSIBLE_CHANNEL_MASK", output_path]`.
- `ExportResult` and `ExportReport` follow data-model.md exactly. `write_export_report()` uses `dataclasses.asdict()` + `json.dump()` with atomic write (temp file + rename).
- AIFF/WAV non-pioneer presets: probe source bit depth and select matching PCM codec (`pcm_s16be`/`pcm_s24be` for AIFF, `pcm_s16le`/`pcm_s24le` for WAV). Default to 16-bit if detection fails.

### Parallel Opportunities
- T005 and T007 can proceed in parallel (command builder vs data classes).

### Dependencies
- **Depends on WP01**: Uses `FormatPreset`, `SourceInfo`, `probe_source()`, `find_cover_art()`, `can_copy()`.

### Risks & Mitigations
- ffmpeg may fail silently for some formats. Check both exit code and stderr.
- Temp file rename may fail cross-filesystem. Mitigate by writing temp in same directory as output.

---

## Work Package WP03: Encoder Unit Tests (Priority: P1)

**Goal**: Comprehensive unit tests for all encoder.py functions with mocked subprocess calls.
**Independent Test**: `pytest tests/unit/test_encoder.py -v` passes all tests.
**Prompt**: `tasks/WP03-encoder-unit-tests.md`

### Included Subtasks
- [ ] T008 Unit tests for FormatPreset registry, probe_source, find_cover_art, can_copy, build_ffmpeg_command, export_file, write_export_report

### Implementation Notes
- Test `PRESETS` registry: all 8 presets present, correct codec/container/args.
- Test `EXTENSION_TO_PRESET`: all 5 extension mappings correct.
- Test `probe_source()`: mock ffprobe JSON output for FLAC 16/44.1, FLAC 24/96, MP3, WAV; test fallback when `bits_per_raw_sample` is empty; test embedded art detection.
- Test `find_cover_art()`: directory with cover.jpg, folder.png, no cover files, case sensitivity.
- Test `can_copy()`: matching source (True), mismatched sample rate (False), preset with None fields (True), codec mismatch (False).
- Test `build_ffmpeg_command()`: encode-only, encode-with-cover, stream-copy, stream-copy-with-cover, embedded-art-preservation.
- Test `export_file()`: mock subprocess for full encode, stream copy, file copy, error case, post-processing.
- Test `write_export_report()`: verify JSON structure and atomic write.
- Use `unittest.mock.patch` for subprocess.run and shutil.copy2.

### Parallel Opportunities
- None (single subtask).

### Dependencies
- **Depends on WP02**: Tests the functions implemented in WP01+WP02.

### Risks & Mitigations
- None significant.

---

## Work Package WP04: Export CLI Command -- Core (Priority: P1)

**Goal**: Implement the `files export` Click command with template path rendering, incremental mode, sequential processing, progress display, and summary output.
**Independent Test**: Run `music-cmd files export "rating:>=4" -p "{{ artist }}/{{ title }}" -o /tmp/export --format mp3-320` and verify files are exported with progress display and summary.
**Prompt**: `tasks/WP04-export-cli-core.md`

### Included Subtasks
- [ ] T009 Register `files export` Click command with all options: `--format/-f`, `--pattern/-p`, `--output/-o`, `--force`, `--jobs`, `--verbose`, `--dry-run`
- [ ] T010 Implement preset resolution: explicit `--format`, auto-detect from template extension via `EXTENSION_TO_PRESET`, extension conflict warning
- [ ] T011 [P] Integrate template path rendering using `render_path()` and `sanitize_rendered_path()` from view module; duplicate resolution with `_make_unique_path()`
- [ ] T012 [P] Implement incremental mode: skip existing files, mtime comparison for re-export, `--force` override
- [ ] T013 Implement `_export_files_sequential()` with `MultilineFileProgress`
- [ ] T015 Implement summary display with OK/Copied/Skipped/Error counts in respective colors, exit code logic (only errors cause exit 1)

### Implementation Notes
- CLI options follow existing `check` command patterns. `--format` is optional (auto-detected from template). `--pattern` and `--output` are required.
- Preset resolution order: (1) `--format` flag, (2) config `export_format` (future), (3) auto-detect from template extension. If `--format` and template extension conflict, warn but use template as-is.
- Reuse `resolve_args_to_files()` from `search_ops.py` for argument handling.
- Reuse `render_path()` + `sanitize_rendered_path()` from `view/template.py` and `view/symlinks.py`. The rendered path gets the preset's container extension appended if the template has no extension (FR-006b).
- For each file: render output path, check incremental (skip if exists and source not newer), call `export_file()`.
- Progress: `MultilineFileProgress(total=len(files), operation="Exporting")`. Call `complete_file(file_path, success=..., message=..., status=result.status)`.
- Summary: table with OK, Copied, Skipped, Error, Not Present counts. Show failed files with error messages. Exit 1 only if errors > 0.
- Report: `ExportReport` written to output dir as `.music-commander-export-report.json` (or `--report` path). Written in `finally` block for SIGINT safety.

### Parallel Opportunities
- T011 and T012 can proceed in parallel (template rendering vs incremental logic).

### Dependencies
- **Depends on WP02**: Uses `export_file()`, `ExportResult`, `ExportReport`, `write_export_report()`.

### Risks & Mitigations
- Template rendering with metadata requires cache lookup. Ensure tracks are loaded from cache before rendering.
- Path sanitization must handle edge cases (empty fields, very long paths).

---

## Work Package WP05: Parallel Export, Dry-Run & Integration Tests (Priority: P2)

**Goal**: Add parallel export support, dry-run mode, and integration tests for the complete export pipeline.
**Independent Test**: Run `music-cmd files export --jobs 4 --dry-run` and verify output; run integration test suite.
**Prompt**: `tasks/WP05-parallel-dryrun-tests.md`

### Included Subtasks
- [ ] T014 Implement `_export_files_parallel()` with `ThreadPoolExecutor`, `as_completed()`, and SIGINT handling (cancel futures, shutdown, clean up temp files)
- [ ] T016 Implement `--dry-run` support: preview files, source format, target format, copy-vs-recode decision, without running ffmpeg
- [ ] T017 Integration tests for export CLI: format selection, incremental skip, dry-run output, warning on extension conflict, parallel execution, JSON report structure

### Implementation Notes
- `_export_files_parallel()` follows `_check_files_parallel()` exactly: `ThreadPoolExecutor(max_workers=jobs)`, submit all, `as_completed()` loop, `KeyboardInterrupt` handler cancels + `shutdown(wait=False, cancel_futures=True)`.
- Dry-run: for each file, probe source, compute output path, determine action (encode/copy/skip), display in table format. Do not run ffmpeg. Show totals at end.
- Integration tests: use mocked subprocess for ffmpeg/ffprobe calls. Test scenarios:
  - `--format mp3-320` selects correct preset
  - Auto-detect format from `.flac` template extension
  - Extension conflict warning (`--format flac` with `.mp3` template)
  - Incremental skip when output exists
  - `--force` re-exports existing files
  - `--dry-run` shows preview without encoding
  - `--jobs 4` runs parallel
  - JSON report has correct structure and summary counts
  - Exit code 0 when only copies/skips, exit code 1 on errors

### Parallel Opportunities
- T014, T016, and T017 can proceed in parallel (different concerns/files).

### Dependencies
- **Depends on WP04**: Extends the CLI command with parallel and dry-run capabilities.

### Risks & Mitigations
- SIGINT during parallel export may leave temp files. Mitigate with temp file cleanup in the interrupt handler.
- Integration test complexity. Mitigate by reusing test patterns from `test_check_command.py`.
