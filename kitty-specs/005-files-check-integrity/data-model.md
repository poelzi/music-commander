# Data Model: Files Check Integrity

**Feature**: 005-files-check-integrity
**Date**: 2026-01-30

## Entities

### CheckerSpec

Defines how to run a single checker tool.

| Field | Type | Description |
|-------|------|-------------|
| name | str | Tool name (e.g., "flac", "mp3val", "ffmpeg", "shntool", "sox", "ogginfo") |
| command | list[str] | Command template; file path appended at runtime |
| parse_result | Callable | Function that interprets subprocess result into pass/fail + error output |

### ToolResult

Result of running a single checker tool against a file.

| Field | Type | Description |
|-------|------|-------------|
| tool | str | Tool name |
| success | bool | Whether this tool passed |
| exit_code | int | Process exit code |
| output | str | Combined stderr/stdout (tool-dependent) |

### CheckResult

Outcome of checking a single file (may involve multiple tools).

| Field | Type | Description |
|-------|------|-------------|
| file | str | Relative path from repo root |
| status | str | "ok", "error", "not_present", "checker_missing" |
| tools | list[str] | Tool names used |
| errors | list[ToolResult] | Only the failing tool results (empty if status is "ok") |

**Status rules**:
- `"ok"` -- all tools passed
- `"error"` -- any tool failed (strict mode per clarification)
- `"not_present"` -- file is annexed but content not locally available
- `"checker_missing"` -- required tool not found on PATH

### CheckReport

Top-level JSON output structure.

| Field | Type | Description |
|-------|------|-------------|
| version | int | Schema version, starts at 1 |
| timestamp | str | ISO 8601 UTC start time |
| duration_seconds | float | Wall-clock run time |
| repository | str | Absolute path to repo root |
| arguments | list[str] | Original CLI arguments |
| summary | dict | Counts: {total, ok, error, not_present, checker_missing} |
| results | list[CheckResult] | Per-file results |

## JSON Output Example

```json
{
  "version": 1,
  "timestamp": "2026-01-30T15:30:00Z",
  "duration_seconds": 342.5,
  "repository": "/space/Music",
  "arguments": ["rating:>3"],
  "summary": {
    "total": 1200,
    "ok": 1195,
    "error": 3,
    "not_present": 2,
    "checker_missing": 0
  },
  "results": [
    {
      "file": "artist/album/track.flac",
      "status": "ok",
      "tools": ["flac"],
      "errors": []
    },
    {
      "file": "artist/album/broken.mp3",
      "status": "error",
      "tools": ["mp3val", "ffmpeg"],
      "errors": [
        {
          "tool": "mp3val",
          "success": false,
          "exit_code": 0,
          "output": "WARNING: MPEG stream error, resynchronized successfully"
        }
      ]
    },
    {
      "file": "artist/album/missing.flac",
      "status": "not_present",
      "tools": [],
      "errors": []
    }
  ]
}
```

## Checker Registry

Extension-to-tools mapping:

| Extension | Tools (in order) | On Missing Tool |
|-----------|-----------------|-----------------|
| .flac | flac | checker_missing |
| .mp3 | mp3val, ffmpeg | checker_missing if either is absent |
| .ogg | ogginfo, ffmpeg | checker_missing if either is absent |
| .wav | shntool, sox | checker_missing if either is absent |
| .aiff, .aif | sox | checker_missing |
| .m4a | ffmpeg | checker_missing |
| * (other) | ffmpeg | checker_missing |

**Note**: If ANY tool in the chain is unavailable, the file is marked `checker_missing`.
There is no partial fallback. This matches FR-013: "skip files of that type".
