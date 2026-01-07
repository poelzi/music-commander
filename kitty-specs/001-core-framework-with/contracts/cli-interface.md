# CLI Interface Contract

**Date**: 2026-01-06
**Feature Branch**: `001-core-framework-with`

## Command Structure

```
music-commander [GLOBAL OPTIONS] <COMMAND> [COMMAND OPTIONS] [ARGS]
```

## Global Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config`, `-c` | PATH | ~/.config/music-commander/config.toml | Config file path |
| `--no-color` | FLAG | false | Disable colored output |
| `--verbose`, `-v` | FLAG | false | Enable verbose output |
| `--quiet`, `-q` | FLAG | false | Suppress non-error output |
| `--help` | FLAG | | Show help and exit |
| `--version` | FLAG | | Show version and exit |

## Commands

### get-commit-files

Fetch git-annexed files from specified commits, ranges, branches, or tags.

```
music-commander get-commit-files [OPTIONS] <REVISION>
```

**Arguments**:

| Argument | Required | Description |
|----------|----------|-------------|
| REVISION | Yes | Git revision spec (commit, range, branch, or tag) |

**Options**:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run`, `-n` | FLAG | false | Show files without fetching |
| `--remote`, `-r` | STRING | config default | Preferred git-annex remote |
| `--jobs`, `-j` | INT | 1 | Parallel fetch jobs |

**Examples**:

```bash
# Single commit
music-commander get-commit-files HEAD~1

# Commit range
music-commander get-commit-files HEAD~5..HEAD

# Branch (unique commits)
music-commander get-commit-files feature/new-tracks

# Tag
music-commander get-commit-files v2025-summer-set

# Dry run
music-commander get-commit-files --dry-run HEAD~3..HEAD
```

**Output Format**:

```
Fetching 15 annexed files from 3 commits...

  [1/15] tracks/Artist - Song.flac
         ████████████████████░░░░░ 80% 12.5 MB/s ETA 0:05

Summary:
  Fetched:  12 files (1.2 GB)
  Present:   2 files (skipped)
  Failed:    1 file
    - tracks/Missing.flac: Remote unavailable

Exit code: 1 (some files failed)
```

**Exit Codes**:

| Code | Meaning |
|------|---------|
| 0 | All files fetched successfully |
| 1 | Some files failed to fetch |
| 2 | Invalid revision specification |
| 3 | Not a git-annex repository |

## Error Messages

All errors written to stderr with format:

```
Error: <message>
  Hint: <actionable suggestion>
```

**Examples**:

```
Error: Not a git-annex repository
  Hint: Run 'git annex init' to initialize, or use --repo to specify a different path

Error: Invalid revision 'nonexistent-branch'
  Hint: Check branch name with 'git branch -a' or use a commit hash

Error: Config file has invalid syntax at line 5
  Hint: Check TOML syntax - missing closing quote on 'mixxx_db' value
```

## JSON Output Mode (Future)

When `--json` flag is implemented (SHOULD per constitution):

```json
{
  "command": "get-commit-files",
  "revision": "HEAD~3..HEAD",
  "results": {
    "fetched": [
      {"path": "tracks/Artist - Song.flac", "size": 52428800}
    ],
    "present": [
      {"path": "tracks/Other.flac", "size": 31457280}
    ],
    "failed": [
      {"path": "tracks/Missing.flac", "error": "Remote unavailable"}
    ]
  },
  "summary": {
    "fetched_count": 12,
    "fetched_bytes": 1288490188,
    "present_count": 2,
    "failed_count": 1
  },
  "exit_code": 1
}
```
