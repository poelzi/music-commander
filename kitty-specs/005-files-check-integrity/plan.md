# Implementation Plan: Files Check Integrity

**Branch**: `005-files-check-integrity` | **Date**: 2026-01-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `kitty-specs/005-files-check-integrity/spec.md`

## Summary

Add a `files check` command that validates audio file integrity using format-specific tools (flac, mp3val, ogginfo, shntool, sox, ffmpeg). The command outputs a JSON report file for downstream automated repair. It follows the same architectural pattern as the existing `files get` and `files drop` commands: Click subcommand, shared search utilities, `MultilineFileProgress` for live output. New additions: a checker registry, a shared path-vs-query auto-detect utility, JSON report writer, and `concurrent.futures` for parallel checking.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: Click (CLI), Rich (output), subprocess (tool execution), concurrent.futures (parallelism)
**Storage**: JSON output file (no database)
**Testing**: pytest
**Target Platform**: Linux (Nix)
**Project Type**: Single CLI application (existing codebase extension)
**Performance Goals**: Must handle 100k+ files; `--jobs N` for parallelism
**Constraints**: External checker tools must be on PATH; graceful degradation if missing
**Scale/Scope**: ~4 new/modified source files, ~1 nix file change

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Python 3.13+**: Pass -- using Python 3.13
- **Click CLI framework**: Pass -- new command registered under existing `files` group
- **Rich for terminal output**: Pass -- uses `MultilineFileProgress` (Rich Live + Progress)
- **pytest for testing**: Pass -- unit tests for checker module and command
- **Every CLI command must have unit tests**: Pass -- will include tests
- **Every utility module must have unit tests**: Pass -- checker utility will have tests
- **100k+ tracks without degradation**: Pass -- per-file subprocess with optional parallelism; no in-memory accumulation beyond result list
- **Nix flake for packaging**: Pass -- new system deps added to flake.nix
- **No external services**: Pass -- all tools run locally

No violations. No complexity tracking needed.

## Project Structure

### Documentation (this feature)

```
kitty-specs/005-files-check-integrity/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research (tool commands, output parsing)
├── data-model.md        # Phase 1 data model (CheckResult, CheckReport)
└── tasks.md             # Phase 2 output (NOT created by /spec-kitty.plan)
```

### Source Code (repository root)

```
music_commander/
├── commands/
│   └── get_commit_files.py     # MODIFY: add `files check` subcommand
├── utils/
│   ├── search_ops.py           # MODIFY: add path-vs-query auto-detect utility
│   ├── checkers.py             # NEW: checker registry, per-format tool runners
│   └── output.py               # NO CHANGE (MultilineFileProgress already updated)
flake.nix                       # MODIFY: add mp3val, shntool, vorbis-tools, sox

tests/
├── unit/
│   ├── test_checkers.py        # NEW: unit tests for checker registry + runners
│   └── test_check_command.py   # NEW: unit tests for files check CLI
```

**Structure Decision**: Follows existing single-project layout. New checker logic isolated in `music_commander/utils/checkers.py`. Command added to existing `get_commit_files.py` where the `files` group is defined.

## Phase 0: Research

### Tool Command Formats and Output Parsing

Research completed during specification. Key findings consolidated:

**Decision**: Use format-specific tools with ffmpeg as universal fallback.

| Format | Tool(s) | Command | Success Detection |
|--------|---------|---------|-------------------|
| FLAC | flac | `flac -t -s -w <file>` | exit code 0 |
| MP3 | mp3val + ffmpeg | `mp3val <file>` then `ffmpeg -v error -i <file> -f null -` | mp3val: no WARNING/PROBLEM lines; ffmpeg: exit 0 AND empty stderr |
| OGG | ogginfo + ffmpeg | `ogginfo <file>` then `ffmpeg ...` | ogginfo: exit 0; ffmpeg: exit 0 AND empty stderr |
| WAV | shntool + sox | `shntool len <file>` then `sox <file> -n stat` | shntool: no problem indicators (t/j/i/a/h); sox: exit 0 |
| AIFF | sox | `sox <file> -n stat` | exit 0 |
| M4A | ffmpeg | `ffmpeg -v error -i <file> -f null -` | exit 0 AND empty stderr |
| Other | ffmpeg | `ffmpeg -v error -i <file> -f null -` | exit 0 AND empty stderr |

**Rationale**: Format-specific tools provide deeper validation than a generic decoder. FLAC's built-in MD5 checksum is uniquely thorough. shntool catches WAV truncation that ffmpeg misses (per KBNL research). mp3val catches structural issues ffmpeg tolerates.

**Alternatives considered**: Using ffmpeg only (simpler but misses format-specific issues); using sox for everything (lacks mp3val's structural analysis and FLAC MD5 verification).

### Parallelism Strategy

**Decision**: Use `concurrent.futures.ThreadPoolExecutor` with `--jobs N`.

**Rationale**: Each check is a subprocess call (I/O-bound, not CPU-bound). ThreadPoolExecutor is simpler than ProcessPoolExecutor for I/O-bound work and avoids pickling issues. The `MultilineFileProgress` methods are called from the main thread after futures complete; a thread-safe result collection feeds the progress display.

**Alternative considered**: `asyncio` with `subprocess` -- more complex, no benefit for this use case since we're not doing network I/O.

### Path vs Query Auto-Detection

**Decision**: Implement `resolve_args_to_files()` in `music_commander/utils/search_ops.py`.

**Logic**: For each positional argument, check if it resolves to an existing file or directory (relative to CWD or repo root). If yes, collect files (recursing into directories). If no, treat as search query terms and pass to `execute_search_files()`. Arguments can be mixed -- paths and query terms can coexist.

**Rationale**: Simpler UX than requiring `--query` or `--path` flags. Matches user mental model: "check these files" vs "check files matching this query".

### SIGINT Handling

**Decision**: Use `try/finally` around the main check loop to write partial results on interruption.

**Rationale**: Python raises `KeyboardInterrupt` on SIGINT. A `try/finally` block in the check function ensures the JSON report is written even on interruption. No explicit signal handler needed -- context managers handle cleanup of the progress display.

## Phase 1: Design

### Data Model

**CheckResult** (per-file result):
```
file: str           # Relative path from repo root
status: str         # "ok" | "error" | "not_present" | "checker_missing"
tools: list[str]    # Tool names used, e.g. ["mp3val", "ffmpeg"]
errors: list[dict]  # Per-tool errors: [{"tool": "mp3val", "output": "...", "exit_code": 1}]
```

**CheckReport** (top-level output):
```
version: int                # Schema version (1)
timestamp: str              # ISO 8601 start time
duration_seconds: float     # Total wall-clock time
repository: str             # Absolute repo path
arguments: list[str]        # Original CLI arguments
summary: dict               # {total, ok, error, not_present, checker_missing}
results: list[CheckResult]  # Per-file results
```

### Checker Registry Design

`music_commander/utils/checkers.py` contains:

1. **`CHECKER_REGISTRY`**: Dict mapping file extensions to lists of checker specs:
   ```python
   CHECKER_REGISTRY: dict[str, list[CheckerSpec]] = {
       ".flac": [CheckerSpec("flac", ["flac", "-t", "-s", "-w"], ...)],
       ".mp3": [CheckerSpec("mp3val", ["mp3val"], ...), CheckerSpec("ffmpeg", ...)],
       ...
   }
   ```

2. **`CheckerSpec`**: Dataclass holding tool name, command template, and a result parser function.

3. **`check_file(repo_path, file_path) -> CheckResult`**: Looks up extension in registry, runs each tool, aggregates results. Falls back to ffmpeg for unknown extensions.

4. **`check_tool_available(tool_name) -> bool`**: Uses `shutil.which()` to verify tool is on PATH.

5. **Tool-specific parsers**:
   - `_parse_flac_result(proc)` -- check exit code
   - `_parse_mp3val_result(proc)` -- scan stdout for WARNING/PROBLEM lines
   - `_parse_ffmpeg_result(proc)` -- check exit code AND stderr content
   - `_parse_shntool_result(proc)` -- parse problem column for indicators
   - `_parse_sox_result(proc)` -- check exit code
   - `_parse_ogginfo_result(proc)` -- check exit code

### Command Design

`files check` subcommand in `music_commander/commands/get_commit_files.py`:

**Click registration**: `@cli.command("check")` with:
- `@click.argument("args", nargs=-1)` -- optional, auto-detected
- `--dry-run` / `-n`
- `--jobs` / `-J` (default 1)
- `--output` / `-o` (default `<repo>/.music-commander-check-results.json`)
- `--verbose` / `-v`

**Execution flow**:
1. Validate git-annex repo
2. Resolve args: auto-detect paths vs query (or list all annexed files if no args)
3. Filter to annexed files only
4. Separate present vs not-present files
5. Check tool availability, warn about missing tools
6. If `--dry-run`: list files with their checker tool and exit
7. Run checks with `MultilineFileProgress(operation="Checking")`
8. If `--jobs > 1`: use `ThreadPoolExecutor` to run `check_file()` concurrently
9. Write JSON report
10. Show summary table
11. Exit with appropriate code (0 = all ok, 1 = some errors)

### Shared Utility: `resolve_args_to_files()`

Added to `music_commander/utils/search_ops.py`:

```python
def resolve_args_to_files(
    ctx: Context,
    args: tuple[str, ...],
    config: Config,
    *,
    require_present: bool = True,
    verbose: bool = False,
) -> list[Path] | None:
```

**Logic**:
- Split args into paths (exist on disk) and query terms (don't exist)
- For paths: resolve files, recurse directories
- For query terms: join and pass to `execute_search_files()`
- Merge and deduplicate results
- If no args provided: return all annexed files in repo

### Nix Changes

Add to `flake.nix` devShell `buildInputs`:
```nix
pkgs.mp3val
pkgs.shntool
pkgs.vorbis-tools  # provides ogginfo
pkgs.sox
```

These are system dependencies (not Python packages), so they go in `buildInputs` alongside `pkgs.git-annex` and `pkgs.ffmpeg`.

### Constitution Re-Check (Post-Design)

- **Python 3.13+**: Pass
- **Click CLI**: Pass -- standard subcommand registration
- **Rich output**: Pass -- uses existing MultilineFileProgress
- **pytest tests**: Pass -- test files planned
- **100k+ tracks**: Pass -- per-file subprocess, no large in-memory structures beyond result list; ThreadPoolExecutor bounds concurrency
- **Nix flake**: Pass -- deps added to devShell
- **No external services**: Pass

All gates pass. No violations.
