# Work Packages: Files Check Integrity

**Inputs**: Design documents from `kitty-specs/005-files-check-integrity/`
**Prerequisites**: plan.md (required), spec.md (user stories), research.md, data-model.md

**Organization**: Fine-grained subtasks (`Txxx`) roll up into work packages (`WPxx`). Each work package is independently deliverable.

---

## Work Package WP01: Nix Dependencies & Checker Registry (Priority: P0)

**Goal**: Add checker tool dependencies to flake.nix and implement the checker registry module with all format-specific parsers.
**Independent Test**: Import `checkers` module; verify tool availability detection and result parsing logic with unit tests.
**Prompt**: `tasks/WP01-nix-deps-and-checker-registry.md`

### Included Subtasks
- [x] T001 Add `mp3val`, `shntool`, `vorbis-tools`, `sox` to `flake.nix` devShell `buildInputs`
- [x] T002 Create `music_commander/utils/checkers.py` with data classes: `CheckerSpec`, `ToolResult`, `CheckResult`, `CheckReport`
- [x] T003 [P] Implement `CHECKER_REGISTRY` mapping extensions to checker specs
- [x] T004 [P] Implement tool-specific result parsers: `_parse_flac_result`, `_parse_mp3val_result`, `_parse_ffmpeg_result`, `_parse_shntool_result`, `_parse_sox_result`, `_parse_ogginfo_result`
- [x] T005 Implement `check_file(repo_path, file_path) -> CheckResult` function
- [x] T006 Implement `check_tool_available(tool_name) -> bool` using `shutil.which()`
- [x] T007 Implement `write_report(report, output_path)` JSON serializer
- [x] T008 Add unit tests in `tests/unit/test_checkers.py`

### Implementation Notes
- Each `CheckerSpec` holds tool name, command template list, and a parser callable.
- `check_file()` looks up extension in registry, checks tool availability, runs each tool via `subprocess.run()`, aggregates `ToolResult` entries into a `CheckResult`.
- ffmpeg parser must check BOTH exit code AND stderr content (non-empty stderr = error even with exit 0).
- mp3val parser must scan stdout for `WARNING` or `PROBLEM` lines (exit code is unreliable).
- shntool parser must parse the problems column output for indicator characters (t/j/i/a/h).
- For unknown extensions, fall back to ffmpeg.
- `write_report()` serializes `CheckReport` to JSON using dataclass-to-dict conversion.

### Parallel Opportunities
- T003 and T004 can proceed in parallel (registry structure vs parser implementations).

### Dependencies
- None (starting package).

### Risks & Mitigations
- shntool output format parsing may be fragile. Mitigate with thorough unit tests using captured output samples.

---

## Work Package WP02: Shared Auto-Detect Utility (Priority: P0)

**Goal**: Implement `resolve_args_to_files()` in `search_ops.py` -- a shared utility that auto-detects whether CLI arguments are file paths or search query terms.
**Independent Test**: Call `resolve_args_to_files()` with mixed paths and query terms; verify correct classification and file resolution.
**Prompt**: `tasks/WP02-auto-detect-utility.md`

### Included Subtasks
- [x] T009 Implement `resolve_args_to_files()` in `music_commander/utils/search_ops.py`
- [x] T010 Implement directory recursive scanning for path arguments
- [x] T011 Implement "list all annexed files" fallback when no args provided
- [x] T012 Add unit tests in `tests/unit/test_search_ops_resolve.py`

### Implementation Notes
- For each positional argument: check if `Path(arg)` exists relative to CWD, then relative to repo root. If it exists as a file or directory, treat as path. Otherwise, treat as search query term.
- Directories are scanned recursively for all files (not just audio -- filtering happens later).
- Query terms are joined with spaces and passed to existing `execute_search_files()`.
- If no args: use `git annex find` or walk the repo to list all annexed files.
- Deduplicate merged results.

### Parallel Opportunities
- Can proceed in parallel with WP01 (different files).

### Dependencies
- None (independent utility).

### Risks & Mitigations
- Edge case: search term matching an existing filename. Mitigate by documenting that path takes precedence; music-commander search syntax (e.g., `artist:Basinski`) is unlikely to match real files.

---

## Work Package WP03: Files Check Command (Priority: P1) -- MVP

**Goal**: Implement the `files check` CLI command with single-threaded checking, progress display, and JSON report output.
**Independent Test**: Run `music-cmd files check` on a repo with mixed audio files; verify progress display, correct tool selection, and JSON output file.
**Prompt**: `tasks/WP03-files-check-command.md`

### Included Subtasks
- [x] T013 Register `files check` subcommand in `music_commander/commands/get_commit_files.py` with Click decorators
- [x] T014 Implement argument resolution: no args (all files), path/query auto-detect via `resolve_args_to_files()`
- [x] T015 Implement file filtering: annexed files only, separate present vs not-present
- [x] T016 Implement tool availability pre-check with warnings for missing tools
- [x] T017 Implement `--dry-run` mode: list files with their checker tool
- [x] T018 Implement main check loop with `MultilineFileProgress(operation="Checking")`
- [x] T019 Implement JSON report writing with `try/finally` for SIGINT safety
- [x] T020 Implement summary table display using `show_operation_summary()` pattern
- [x] T021 Add `--output` / `-o` option for custom output path
- [x] T022 Add `--verbose` / `-v` option to show per-file checker commands

### Implementation Notes
- Follow the exact pattern of `files get` and `files drop` commands for Click registration, context handling, and exit codes.
- Use `MultilineFileProgress(operation="Checking")` -- completed label auto-derives to "Checked".
- `try/finally` wraps the check loop: the `finally` block calls `write_report()` so partial results are saved on Ctrl+C.
- Exit codes: 0 = all ok, 1 = some errors (matches existing EXIT_PARTIAL_FAILURE pattern).
- Summary table reuses `show_operation_summary()` or a similar Rich table.

### Parallel Opportunities
- None within this WP (sequential implementation).

### Dependencies
- Depends on WP01 (checker registry) and WP02 (auto-detect utility).

### Risks & Mitigations
- Large file lists may cause slow startup when checking tool availability. Mitigate by checking each tool once (cache result).

---

## Work Package WP04: Parallel Checking with --jobs (Priority: P2)

**Goal**: Add `--jobs N` support using `concurrent.futures.ThreadPoolExecutor` for parallel file checking.
**Independent Test**: Run `music-cmd files check --jobs 4`; verify multiple files checked concurrently, results are complete and consistent, progress display works correctly.
**Prompt**: `tasks/WP04-parallel-checking.md`

### Included Subtasks
- [ ] T023 Implement `ThreadPoolExecutor`-based parallel check loop
- [ ] T024 Implement thread-safe result collection with progress callbacks
- [ ] T025 Ensure `MultilineFileProgress` handles concurrent `start_file`/`complete_file` calls
- [ ] T026 Add `--jobs` / `-J` Click option (default 1; jobs=1 uses sequential loop)

### Implementation Notes
- When `--jobs > 1`, submit `check_file()` calls to a `ThreadPoolExecutor(max_workers=jobs)`.
- Use `as_completed()` to process results as they finish, calling `progress.complete_file()` for each.
- `MultilineFileProgress` already supports multiple in-flight files (live region shows all). Thread safety: `start_file` and `complete_file` must be called from the main thread. Use a callback pattern or process futures from the main thread loop.
- When `--jobs == 1`, use the simpler sequential loop from WP03 (no executor overhead).

### Parallel Opportunities
- None within this WP.

### Dependencies
- Depends on WP03 (base command must work sequentially first).

### Risks & Mitigations
- Thread safety of Rich Live display. Mitigate by ensuring all progress calls happen from the main thread (process futures in main loop, not in worker threads).

---

## Work Package WP05: Tests & Polish (Priority: P3)

**Goal**: Add integration-style tests for the `files check` command and polish edge cases.
**Independent Test**: `pytest tests/` passes with new test files; edge cases (missing tools, zero-byte files, interruption) handled correctly.
**Prompt**: `tasks/WP05-tests-and-polish.md`

### Included Subtasks
- [ ] T027 Add CLI integration tests in `tests/integration/test_check_command.py` (mock subprocess calls)
- [ ] T028 Test edge case: missing checker tool (verify "checker_missing" status)
- [ ] T029 Test edge case: unrecognized file extension (verify ffmpeg fallback)
- [ ] T030 Test edge case: not-present annexed file (verify "not_present" status)
- [ ] T031 Test JSON report structure validation
- [ ] T032 Test `--dry-run` output format
- [ ] T033 Verify `resolve_args_to_files()` integration with `files check`

### Implementation Notes
- Mock `subprocess.run()` calls to avoid requiring actual checker tools in CI.
- Use the existing test patterns from `tests/integration/test_get_commit_files.py`.
- Verify JSON report matches the schema defined in `data-model.md`.

### Parallel Opportunities
- T027-T033 are all independent test files; can be written in parallel.

### Dependencies
- Depends on WP03 (command exists) and WP04 (parallel mode).

### Risks & Mitigations
- Mocking subprocess may miss real tool behavior. Mitigate with captured real output samples in test fixtures.

---

## Dependency & Execution Summary

- **Sequence**: WP01 + WP02 (parallel) -> WP03 -> WP04 -> WP05
- **Parallelization**: WP01 and WP02 can proceed concurrently (different files/modules).
- **MVP Scope**: WP01 + WP02 + WP03 constitute the minimal working feature.

---

## Subtask Index (Reference)

| Subtask ID | Summary | Work Package | Priority | Parallel? |
|------------|---------|--------------|----------|-----------|
| T001 | Add Nix deps to flake.nix | WP01 | P0 | No |
| T002 | Create checkers.py data classes | WP01 | P0 | No |
| T003 | Implement CHECKER_REGISTRY | WP01 | P0 | Yes |
| T004 | Implement tool-specific parsers | WP01 | P0 | Yes |
| T005 | Implement check_file() | WP01 | P0 | No |
| T006 | Implement check_tool_available() | WP01 | P0 | No |
| T007 | Implement write_report() | WP01 | P0 | No |
| T008 | Unit tests for checkers module | WP01 | P0 | No |
| T009 | Implement resolve_args_to_files() | WP02 | P0 | No |
| T010 | Directory recursive scanning | WP02 | P0 | No |
| T011 | List all annexed files fallback | WP02 | P0 | No |
| T012 | Unit tests for resolve utility | WP02 | P0 | No |
| T013 | Register files check subcommand | WP03 | P1 | No |
| T014 | Argument resolution logic | WP03 | P1 | No |
| T015 | File filtering (annexed, present) | WP03 | P1 | No |
| T016 | Tool availability pre-check | WP03 | P1 | No |
| T017 | Dry-run mode | WP03 | P1 | No |
| T018 | Main check loop with progress | WP03 | P1 | No |
| T019 | JSON report with SIGINT safety | WP03 | P1 | No |
| T020 | Summary table display | WP03 | P1 | No |
| T021 | --output option | WP03 | P1 | No |
| T022 | --verbose option | WP03 | P1 | No |
| T023 | ThreadPoolExecutor parallel loop | WP04 | P2 | No |
| T024 | Thread-safe result collection | WP04 | P2 | No |
| T025 | MultilineFileProgress concurrency | WP04 | P2 | No |
| T026 | --jobs Click option | WP04 | P2 | No |
| T027 | CLI integration tests | WP05 | P3 | Yes |
| T028 | Test: missing checker tool | WP05 | P3 | Yes |
| T029 | Test: unrecognized extension | WP05 | P3 | Yes |
| T030 | Test: not-present annexed file | WP05 | P3 | Yes |
| T031 | Test: JSON report structure | WP05 | P3 | Yes |
| T032 | Test: dry-run output | WP05 | P3 | Yes |
| T033 | Test: resolve_args integration | WP05 | P3 | Yes |
