# Data Model: File Export Recode

**Feature**: 006-file-export-recode
**Date**: 2026-01-31

## Entities

### FormatPreset (frozen dataclass)

Defines a target encoding format with all parameters needed to build ffmpeg commands.

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Preset identifier (e.g., "mp3-320", "flac-pioneer") |
| `codec` | `str` | ffmpeg audio codec name (e.g., "libmp3lame", "flac", "pcm_s16be") |
| `container` | `str` | Output file extension including dot (e.g., ".mp3", ".flac") |
| `ffmpeg_args` | `list[str]` | Additional ffmpeg arguments (e.g., ["-b:a", "320k"]) |
| `sample_rate` | `int \| None` | Target sample rate in Hz, or None to preserve source |
| `bit_depth` | `int \| None` | Target bit depth, or None to preserve source |
| `channels` | `int \| None` | Target channel count, or None to preserve source |
| `post_commands` | `list[list[str]] \| None` | Post-processing commands (e.g., metaflac tag removal) |
| `supports_cover_art` | `bool` | Whether the container supports embedded cover art |

**Identity**: Unique by `name`.

**Lifecycle**: Static — defined at module load time, never modified.

### SourceInfo (dataclass)

Probed parameters of a source audio file.

| Field | Type | Description |
|-------|------|-------------|
| `codec_name` | `str` | Source codec (e.g., "flac", "mp3", "pcm_s16le") |
| `sample_rate` | `int` | Sample rate in Hz |
| `bit_depth` | `int` | Bits per sample (16, 24, 32) |
| `channels` | `int` | Number of audio channels |
| `has_cover_art` | `bool` | Whether embedded cover art was detected |

**Identity**: Transient — created per-file during export, not persisted.

### ExportResult (dataclass)

Result of exporting a single file.

| Field | Type | Description |
|-------|------|-------------|
| `source` | `str` | Source file path (relative to repo root) |
| `output` | `str` | Output file path (relative to output directory) |
| `status` | `str` | One of: "ok", "copied", "skipped", "error", "not_present" |
| `preset` | `str` | Format preset name used |
| `action` | `str` | One of: "encoded", "stream_copied", "file_copied", "skipped", "error" |
| `duration_seconds` | `float` | Time taken for this file |
| `error_message` | `str \| None` | Error details if status is "error" |

**Status values**:
- `ok`: Successfully encoded/converted
- `copied`: File copied (stream copy or file copy) — source already matched target
- `skipped`: Output already exists (incremental mode)
- `error`: Encoding failed
- `not_present`: Source file not locally available

**Action values** (more granular than status):
- `encoded`: Full re-encode via ffmpeg
- `stream_copied`: ffmpeg stream copy (codec matched but needed art/metadata changes)
- `file_copied`: Direct file copy (everything matched, no changes needed)
- `skipped`: Skipped due to incremental mode
- `error`: Failed

### ExportReport (dataclass)

Top-level report for an export run.

| Field | Type | Description |
|-------|------|-------------|
| `version` | `int` | Always 1 |
| `timestamp` | `str` | ISO 8601 timestamp |
| `duration_seconds` | `float` | Total wall-clock duration |
| `repository` | `str` | Source repository path |
| `output_dir` | `str` | Output directory path |
| `preset` | `str` | Format preset name |
| `arguments` | `list[str]` | CLI arguments |
| `summary` | `dict` | Counts: total, ok, copied, skipped, error, not_present |
| `results` | `list[ExportResult]` | Per-file results |

## Relationships

```
FormatPreset (1) --used-by--> (*) ExportResult
SourceInfo (1) --probed-for--> (1) ExportResult
ExportResult (*) --aggregated-in--> (1) ExportReport
```

## Preset Registry

Module-level constant mapping preset names to FormatPreset instances:

```
PRESETS: dict[str, FormatPreset]
  "mp3-320"      -> FormatPreset(codec="libmp3lame", container=".mp3", ...)
  "mp3-v0"       -> FormatPreset(codec="libmp3lame", container=".mp3", ...)
  "flac"         -> FormatPreset(codec="flac", container=".flac", ...)
  "flac-pioneer"  -> FormatPreset(codec="flac", container=".flac", ..., post_commands=[...])
  "aiff"         -> FormatPreset(codec="pcm_s16be", container=".aiff", ...)
  "aiff-pioneer"  -> FormatPreset(codec="pcm_s16be", container=".aiff", ...)
  "wav"          -> FormatPreset(codec="pcm_s16le", container=".wav", ...)
  "wav-pioneer"   -> FormatPreset(codec="pcm_s16le", container=".wav", ...)

EXTENSION_TO_PRESET: dict[str, str]
  ".mp3"  -> "mp3-320"
  ".flac" -> "flac"
  ".aiff" -> "aiff"
  ".aif"  -> "aiff"
  ".wav"  -> "wav"
```

## Key Functions (encoder.py)

| Function | Input | Output | Description |
|----------|-------|--------|-------------|
| `probe_source(file_path)` | `Path` | `SourceInfo` | Run ffprobe, parse JSON |
| `find_cover_art(file_path)` | `Path` | `Path \| None` | Search directory for cover files |
| `can_copy(source_info, preset)` | `SourceInfo, FormatPreset` | `bool` | Check if source matches target |
| `build_ffmpeg_command(input, output, preset, source_info, cover_path)` | various | `list[str]` | Build complete ffmpeg command |
| `export_file(file_path, output_path, preset, repo_path, *, verbose)` | various | `ExportResult` | Export a single file (probe, decide, encode/copy) |

## State Transitions (per file)

```
[start] -> probe_source()
         -> find_cover_art() if source has no embedded art
         -> can_copy() decision
            |
            +-> matches & no art needed -> file_copy -> [ok/copied]
            +-> matches & needs art     -> stream_copy -> [ok/copied]
            +-> doesn't match           -> full_encode -> [ok]
            +-> ffmpeg fails            -> [error]
         -> post_commands (if preset has them)
         -> rename temp -> final
```
