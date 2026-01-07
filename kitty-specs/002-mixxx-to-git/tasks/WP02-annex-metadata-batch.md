---
work_package_id: "WP02"
subtasks:
  - "T006"
  - "T007"
  - "T008"
  - "T009"
  - "T010"
  - "T011"
title: "Git-Annex Metadata Batch Wrapper"
phase: "Phase 0 - Foundation"
lane: "doing"
assignee: ""
agent: "claude"
shell_pid: "1395416"
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-07T14:30:00Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP02 – Git-Annex Metadata Batch Wrapper

## Objectives & Success Criteria

- Create Python wrapper for `git annex metadata --batch --json` subprocess
- Implement context manager for clean subprocess lifecycle
- Provide `set_metadata()` and `get_metadata()` methods
- Control commits with `annex.alwayscommit=false` and manual merge
- Implement field value transformations (rating, color, bpm)

**Success**: Wrapper can efficiently set/get metadata on hundreds of files through a single long-running subprocess.

## Context & Constraints

- **Research**: See `kitty-specs/002-mixxx-to-git/research.md` for batch mode details
- **Performance goal**: 1000 tracks in <60 seconds (SC-001)
- **Commit goal**: 10,000 tracks = max 10 commits (SC-002)

### Git-Annex Batch Mode Reference

**Command**:
```bash
git -c annex.alwayscommit=false annex metadata --batch --json
```

**Input (stdin)**: One JSON per line
```json
{"file":"relative/path.flac","fields":{"artist":["Name"],"rating":["5"]}}
```

**Output (stdout)**: One JSON per line
```json
{"command":"metadata","file":"path.flac","success":true,"fields":{...}}
```

## Subtasks & Detailed Guidance

### Subtask T006 – Batch Process Manager Class

**Purpose**: Manage the long-running `git annex metadata --batch --json` subprocess.

**Steps**:
1. Create `music_commander/utils/annex_metadata.py`
2. Define `AnnexMetadataBatch` class with `repo_path` parameter
3. Store subprocess handle as instance variable
4. Implement `start()` method to launch subprocess

**Files**: `music_commander/utils/annex_metadata.py` (new file)

**Subprocess command**:
```python
cmd = ["git", "-c", "annex.alwayscommit=false", "annex", "metadata", "--batch", "--json"]
proc = subprocess.Popen(
    cmd,
    cwd=repo_path,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,  # Line buffered
)
```

### Subtask T007 – Context Manager Lifecycle

**Purpose**: Ensure subprocess is properly started and terminated.

**Steps**:
1. Implement `__enter__()` to start subprocess and return self
2. Implement `__exit__()` to close stdin, wait for termination, commit changes
3. Handle exceptions gracefully (terminate subprocess on error)
4. Call `git annex merge` after batch processing to commit changes

**Files**: `music_commander/utils/annex_metadata.py`

**Pattern**:
```python
def __enter__(self):
    self.start()
    return self

def __exit__(self, exc_type, exc_val, exc_tb):
    if self._proc:
        self._proc.stdin.close()
        self._proc.wait()
    # Commit accumulated changes
    subprocess.run(["git", "annex", "merge"], cwd=self.repo_path, check=True)
    return False
```

### Subtask T008 – set_metadata Method

**Purpose**: Write metadata for a single file via batch mode.

**Steps**:
1. Implement `set_metadata(file_path: Path, fields: dict[str, list[str]]) -> bool`
2. Build JSON input: `{"file": str(file_path), "fields": fields}`
3. Write JSON + newline to stdin, flush
4. Read response line from stdout
5. Parse JSON and return `success` field

**Files**: `music_commander/utils/annex_metadata.py`

**Field format**: All values must be lists of strings
```python
{"file": "artist/track.flac", "fields": {"rating": ["5"], "crate": ["A", "B"]}}
```

### Subtask T009 – get_metadata Method

**Purpose**: Read existing metadata for a file.

**Steps**:
1. Implement `get_metadata(file_path: Path) -> dict[str, list[str]] | None`
2. Build JSON input: `{"file": str(file_path)}` (no fields = query mode)
3. Write to stdin, read response
4. Return `fields` dict from response, or None if file not annexed

**Files**: `music_commander/utils/annex_metadata.py`

**Parallel?**: Yes - can be developed alongside T008

### Subtask T010 – Commit Control

**Purpose**: Batch all changes into minimal commits.

**Steps**:
1. Use `annex.alwayscommit=false` in subprocess command (done in T006)
2. Implement optional `commit()` method to force commit mid-batch
3. Support `--batch-size` by calling commit every N files
4. Final commit happens in `__exit__()` via `git annex merge`

**Files**: `music_commander/utils/annex_metadata.py`

**Commit command**:
```python
def commit(self, message: str = "Sync metadata from Mixxx"):
    subprocess.run(["git", "annex", "merge"], cwd=self.repo_path, check=True)
```

### Subtask T011 – Field Value Transformations

**Purpose**: Convert Mixxx values to git-annex format.

**Steps**:
1. Add helper functions for value transformation:
   - `transform_rating(rating: int | None) -> str | None` - 0→None, 1-5→"1"-"5"
   - `transform_color(color: int | None) -> str | None` - int→"#RRGGBB"
   - `transform_bpm(bpm: float | None) -> str | None` - float→"120.00"
2. Add `build_annex_fields(track: TrackMetadata) -> dict[str, list[str]]`

**Files**: `music_commander/utils/annex_metadata.py`

**Parallel?**: Yes - can be developed independently

**Transformations**:
```python
def transform_color(color: int | None) -> str | None:
    if color is None:
        return None
    return f"#{color:06X}"

def transform_bpm(bpm: float | None) -> str | None:
    if bpm is None or bpm <= 0:
        return None
    return f"{bpm:.2f}"

def transform_rating(rating: int | None) -> str | None:
    if rating is None or rating == 0:
        return None
    return str(rating)
```

## Definition of Done Checklist

- [ ] T006: `AnnexMetadataBatch` class launches subprocess correctly
- [ ] T007: Context manager properly starts/stops subprocess and commits
- [ ] T008: `set_metadata()` writes metadata and returns success status
- [ ] T009: `get_metadata()` reads existing metadata correctly
- [ ] T010: Changes batched into single commit by default
- [ ] T011: All field transformations implemented (rating, color, bpm)
- [ ] Subprocess handles EOF and errors gracefully
- [ ] Type hints pass mypy strict mode

## Risks & Mitigations

- **Subprocess hangs**: Implement timeout in `wait()` call
- **JSON parse errors**: Wrap in try/except, log malformed responses
- **Non-annexed files**: Return empty response (empty line), handle gracefully

## Review Guidance

- Verify subprocess is properly terminated on exceptions
- Check that `annex.alwayscommit=false` is passed correctly
- Test with non-annexed files (should return empty/None)
- Verify commit happens only once at end of batch

## Activity Log

- 2026-01-07T14:30:00Z – system – lane=planned – Prompt created.
- 2026-01-07T15:13:55Z – claude – shell_pid=1395416 – lane=doing – Started implementation - Git-annex metadata batch wrapper
