---
work_package_id: "WP05"
subtasks:
  - "T024"
  - "T025"
  - "T026"
  - "T027"
  - "T028"
  - "T029"
  - "T030"
title: "CLI Command & Options"
phase: "Phase 1 - MVP"
lane: "done"
assignee: ""
agent: "claude"
shell_pid: "$$"
review_status: "addressed"
reviewed_by: "claude-reviewer"
history:
  - timestamp: "2026-01-07T14:30:00Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

## Review Feedback

**Status**: ❌ **Needs Changes**

**Key Issues**:
1. **Blocked by WP04 issues** - WP05 uses `sync_metadata.py` which has the same mypy errors identified in WP04 review. The command cannot be tested (`music-commander sync-metadata --help` fails with ImportError).

2. **Same 3 mypy errors as WP04**:
   - Line 18: `create_session` should be `get_session`
   - Line 264: Null safety on `last_sync_timestamp.timestamp()`
   - Line 296: Variable `track` shadows `rich.progress.track` import

**What Was Done Well**:
- All CLI options properly defined (`--all`, `--dry-run`, `--batch-size`)
- PATHS argument supports multiple paths with `nargs=-1`
- Docstring includes helpful usage examples
- Sync exceptions properly defined in `exceptions.py` (T030 complete)
- Exit codes defined per spec

**Action Items** (must complete before re-review):
- [x] Fix WP04 issues first (same file) - see WP04 review feedback
- [x] After fixes, verify `music-commander sync-metadata --help` works
- [x] Verify command appears in `music-commander --help` list

# Work Package Prompt: WP05 – CLI Command & Options

## Objectives & Success Criteria

- Create `sync-metadata` Click command with all specified options
- Implement `--all`, `--dry-run`, `--batch-size` flags
- Support positional `PATHS` argument for filtering
- Register command in CLI discovery
- Add sync-specific exceptions

**Success**: `music-commander sync-metadata --help` shows all options; basic invocation syncs metadata.

## Context & Constraints

- **Pattern**: Follow `music_commander/commands/get_commit_files.py` structure
- **Spec**: FR-001, FR-006, FR-007, FR-008, FR-010
- **Dependency**: Uses core sync logic from WP04

### Reference Command Pattern

From `get_commit_files.py`:
```python
@click.command("get-commit-files")
@click.argument("revision")
@click.option("--dry-run", "-n", is_flag=True, ...)
@pass_context
def cli(ctx: Context, revision: str, dry_run: bool) -> None:
```

## Subtasks & Detailed Guidance

### Subtask T024 – sync-metadata Command

**Purpose**: Define the main CLI command structure.

**Steps**:
1. Add `@click.command("sync-metadata")` decorator
2. Add docstring with examples for `--help` output
3. Wire to `sync_tracks()` from WP04
4. Handle exit codes per spec

**Files**: `music_commander/commands/sync_metadata.py`

**Pattern**:
```python
@click.command("sync-metadata")
@click.option("--all", "-a", "sync_all", is_flag=True, ...)
@click.option("--dry-run", "-n", is_flag=True, ...)
@click.option("--batch-size", "-b", type=int, ...)
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@pass_context
def cli(
    ctx: Context,
    sync_all: bool,
    dry_run: bool,
    batch_size: int | None,
    paths: tuple[str, ...],
) -> None:
    """Sync Mixxx library metadata to git-annex.
    
    Syncs track metadata (rating, BPM, color, key, artist, etc.) from
    your Mixxx library to git-annex metadata on annexed files.
    
    Examples:
    
        # Sync tracks changed since last sync
        music-commander sync-metadata
        
        # Force sync all tracks
        music-commander sync-metadata --all
        
        # Preview changes without syncing
        music-commander sync-metadata --dry-run
        
        # Sync specific directory
        music-commander sync-metadata ./darkpsy/
    """
```

### Subtask T025 – --all Flag

**Purpose**: Force full resync regardless of change status.

**Steps**:
1. Add `@click.option("--all", "-a", "sync_all", is_flag=True, ...)`
2. Pass to `sync_tracks(sync_all=sync_all)`
3. Document in help text

**Files**: `music_commander/commands/sync_metadata.py`

**Parallel?**: Yes - option definition is independent

**Option**:
```python
@click.option(
    "--all",
    "-a",
    "sync_all",
    is_flag=True,
    default=False,
    help="Sync all tracks, ignoring change detection",
)
```

### Subtask T026 – --dry-run Flag

**Purpose**: Preview what would be synced without making changes.

**Steps**:
1. Add `@click.option("--dry-run", "-n", is_flag=True, ...)`
2. Pass to `sync_tracks(dry_run=dry_run)`
3. In dry-run mode, show tracks but skip write/commit

**Files**: `music_commander/commands/sync_metadata.py`

**Parallel?**: Yes - option definition is independent

**Option**:
```python
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    default=False,
    help="Show what would be synced without making changes",
)
```

### Subtask T027 – --batch-size Option

**Purpose**: Control commit frequency during large syncs.

**Steps**:
1. Add `@click.option("--batch-size", "-b", type=int, ...)`
2. Pass to `sync_tracks(batch_size=batch_size)`
3. Validate: must be positive integer if provided

**Files**: `music_commander/commands/sync_metadata.py`

**Parallel?**: Yes - option definition is independent

**Option**:
```python
@click.option(
    "--batch-size",
    "-b",
    type=int,
    default=None,
    help="Commit every N files (default: commit once at end)",
)
```

### Subtask T028 – PATHS Argument

**Purpose**: Filter sync to specific files or directories.

**Steps**:
1. Add `@click.argument("paths", nargs=-1, type=click.Path(exists=True))`
2. Convert to list of Path objects
3. Pass to `sync_tracks(paths=paths)`
4. Handle both files and directories

**Files**: `music_commander/commands/sync_metadata.py`

**Parallel?**: Yes - argument definition is independent

**Argument**:
```python
@click.argument(
    "paths",
    nargs=-1,
    type=click.Path(exists=True, path_type=Path),
)
```

### Subtask T029 – Command Registration

**Purpose**: Register command with CLI discovery system.

**Steps**:
1. Ensure `cli` function is exported from module
2. Verify `music_commander/commands/__init__.py` discovers the command
3. Test with `music-commander --help`

**Files**: `music_commander/commands/__init__.py`, `music_commander/commands/sync_metadata.py`

**Discovery pattern** (from `__init__.py`):
```python
def discover_commands() -> list[click.Command]:
    """Discover and return all CLI commands."""
    # Imports command modules and returns their cli functions
```

### Subtask T030 – Sync Exceptions

**Purpose**: Add sync-specific exception classes.

**Steps**:
1. Add to `music_commander/exceptions.py`:
   - `SyncError(MusicCommanderError)` - base sync exception
   - `MixxxDatabaseError(SyncError)` - Mixxx DB access errors
   - `AnnexMetadataError(SyncError)` - git-annex metadata errors
2. Use in sync logic for appropriate error handling

**Files**: `music_commander/exceptions.py`

**Parallel?**: Yes - can be developed independently

**Definitions**:
```python
class SyncError(MusicCommanderError):
    """Base exception for sync operations."""
    pass

class MixxxDatabaseError(SyncError):
    """Error accessing Mixxx database."""
    def __init__(self, db_path: Path, message: str):
        self.db_path = db_path
        super().__init__(f"Mixxx database error ({db_path}): {message}")

class AnnexMetadataError(SyncError):
    """Error writing git-annex metadata."""
    def __init__(self, file_path: Path, message: str):
        self.file_path = file_path
        super().__init__(f"Annex metadata error ({file_path}): {message}")
```

## Definition of Done Checklist

- [ ] T024: `sync-metadata` command defined with proper docstring
- [ ] T025: `--all` flag forces full resync
- [ ] T026: `--dry-run` shows what would be synced
- [ ] T027: `--batch-size` controls commit frequency
- [ ] T028: `PATHS` argument filters to specific files/directories
- [ ] T029: Command appears in `music-commander --help`
- [ ] T030: Sync exceptions defined and used appropriately
- [ ] Help text includes usage examples
- [ ] Exit codes follow existing command patterns
- [ ] Type hints pass mypy strict mode

## Risks & Mitigations

- **Path validation edge cases**: Test with symlinks, relative paths, non-existent paths
- **Exit code consistency**: Match existing `get-commit-files` exit code pattern

## Review Guidance

- Run `music-commander sync-metadata --help` and verify all options
- Test each flag/option individually
- Verify error messages are user-friendly
- Check command registration works correctly

## Activity Log

- 2026-01-07T14:30:00Z – system – lane=planned – Prompt created.
- 2026-01-07T15:17:36Z – claude – shell_pid=1395416 – lane=for_review – Completed
- 2026-01-07T17:15:00Z – claude-reviewer – shell_pid=$$ – lane=planned – Code review: needs changes - blocked by WP04 issues (same file), CLI cannot be tested due to import error
