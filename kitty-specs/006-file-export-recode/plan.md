# Implementation Plan: File Export Recode

**Branch**: `006-file-export-recode` | **Date**: 2026-01-31 | **Spec**: [spec.md](spec.md)

## Summary

Add a `files export` command that recodes audio files to specified format presets using ffmpeg. Follows existing patterns from `files check` (parallel execution, progress, SIGINT handling) and `files view` (Jinja2 template paths, duplicate resolution). Encoding logic lives in a new `music_commander/utils/encoder.py` module, analogous to `checkers.py`.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: Click (CLI), Rich (output), Jinja2 (templates), ffmpeg/ffprobe (encoding/probing), metaflac (FLAC tag stripping)
**Storage**: Filesystem (output directory), no database changes
**Testing**: pytest with subprocess mocking
**Target Platform**: Linux (Nix flake)
**Project Type**: Single project — extends existing CLI
**Performance Goals**: Encoding is I/O/CPU-bound by ffmpeg; parallelism via `--jobs N`
**Constraints**: Must work with git-annex symlinks; Pioneer DJ player compatibility for `*-pioneer` presets
**Scale/Scope**: Handle 100,000+ track repositories per constitution

## Constitution Check

*GATE: Validated against `.kittify/memory/constitution.md`*

- **Python 3.13+**: Compliant — no new language introduced
- **Click CLI**: Compliant — `files export` registered under existing `files` group
- **Rich output**: Compliant — reuses `MultilineFileProgress`
- **Nix flake**: Compliant — ffmpeg, metaflac already in dev shell; ffprobe comes with ffmpeg
- **Testing**: Compliant — unit tests for encoder module, integration tests for CLI
- **100k+ tracks**: Compliant — streaming file processing, no in-memory collection of all files
- **No external services**: Compliant — all local processing
- **Works without Mixxx**: Compliant — uses git-annex metadata via cache

No constitution violations.

## Project Structure

### Documentation (this feature)

```
kitty-specs/006-file-export-recode/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── spec.md              # Feature specification
├── checklists/
│   └── requirements.md  # Spec quality checklist
├── research/
└── tasks/
```

### Source Code (repository root)

```
music_commander/
├── commands/
│   └── files.py              # Add export command, _export_files_sequential/_parallel
├── utils/
│   └── encoder.py            # NEW: FormatPreset, ExportResult, ExportReport, export_file()
└── view/
    ├── template.py           # Reuse render_path() (no changes)
    └── symlinks.py           # Reuse _make_unique_path(), sanitize_rendered_path() (no changes)

tests/
├── unit/
│   └── test_encoder.py       # NEW: Tests for encoder module
└── integration/
    └── test_export_command.py # NEW: Tests for export CLI
```

**Structure Decision**: Follows existing single-project layout. New `encoder.py` utility module mirrors the `checkers.py` pattern. Export command logic lives in `files.py` alongside `check` and wires to `view/` utilities for template rendering.

## Key Design Decisions

### 1. FormatPreset as frozen dataclass

Each preset is a frozen dataclass containing: name, codec, container extension, ffmpeg audio codec arg, additional ffmpeg args, target bit depth/sample rate/channels (None = preserve source), and optional post-processing steps. Defined as module-level constants in `encoder.py`.

### 2. Copy-vs-recode decision via ffprobe

Before encoding, probe the source file with `ffprobe -v quiet -select_streams a:0 -show_entries stream=codec_name,bits_per_raw_sample,sample_fmt,sample_rate,channels -of json`. Compare against preset requirements. If all match, use stream copy (`-codec:a copy`) or file copy. If source has no embedded art and external art exists, use ffmpeg stream copy (not file copy) to embed art.

### 3. Cover art embedding

Two paths:
- Source has embedded art: ffmpeg `-map 0:a -map 0:v` preserves it
- Source has no embedded art, external cover found: ffmpeg `-i source -i cover -map 0:a -map 1:0 -disposition:v:0 attached_pic`
- WAV: No standard cover art support; skip embedding for WAV containers

Cover art file search order: `cover.jpg`, `cover.png`, `folder.jpg`, `folder.png`, `front.jpg`, `front.png` in the source file's directory.

### 4. Pioneer FLAC post-processing

After any ffmpeg encode to FLAC (including `flac` preset, not just `flac-pioneer`), run `metaflac --remove-tag=WAVEFORMATEXTENSIBLE_CHANNEL_MASK` as a post-processing step for `flac-pioneer` only. The regular `flac` preset preserves the tag since it only affects Pioneer hardware.

### 5. Extension conflict handling

If `--format` is specified and the template extension differs from the preset's container format, print a warning and proceed with the user-defined template. If the template has no extension, append the preset's container extension automatically.

### 6. Incremental mode

Default behavior: skip files whose output path already exists. Compare source mtime vs destination mtime; re-export if source is newer. `--force` overrides to re-export everything.

### 7. Parallel execution

Same pattern as `_check_files_parallel()`: `ThreadPoolExecutor` with `as_completed()`, SIGINT handling via cancel + `shutdown(wait=False, cancel_futures=True)`. Each worker calls `export_file()` which runs ffmpeg as a subprocess.

### 8. SIGINT cleanup

On interruption: cancel pending futures, kill running ffmpeg processes (subprocess timeout), remove partially written output files (write to temp file then rename on success), show summary of completed work.

### 9. Preset auto-detection from template extension

When `--format` is not specified, extract extension from the template pattern string. Map `.mp3` → `mp3-320`, `.flac` → `flac`, `.aiff`/`.aif` → `aiff`, `.wav` → `wav`. Error if no extension or unrecognized.

## ffmpeg Command Patterns

### Encoding (no cover art changes)
```
ffmpeg -i {input} {codec_args} {format_args} -map_metadata 0 {extra_args} {output}
```

### Encoding with external cover art
```
ffmpeg -i {input} -i {cover} -map 0:a -map 1:0 {codec_args} {format_args}
       -codec:v:0 copy -disposition:v:0 attached_pic -map_metadata 0 {extra_args} {output}
```

### Stream copy (format matches, no cover changes needed)
```
ffmpeg -i {input} -codec:a copy -map_metadata 0 {output}
```

### Stream copy with cover art
```
ffmpeg -i {input} -i {cover} -map 0:a -map 1:0 -codec:a copy
       -codec:v:0 copy -disposition:v:0 attached_pic -map_metadata 0 {output}
```

### Preset-specific ffmpeg args

| Preset | `-codec:a` | Additional args |
|--------|-----------|-----------------|
| `mp3-320` | `libmp3lame` | `-b:a 320k -id3v2_version 3` |
| `mp3-v0` | `libmp3lame` | `-q:a 0 -id3v2_version 3` |
| `flac` | `flac` | `-compression_level 8` |
| `flac-pioneer` | `flac` | `-sample_fmt s16 -ar 44100 -ac 2 -compression_level 8` + post: `metaflac --remove-tag=WAVEFORMATEXTENSIBLE_CHANNEL_MASK` |
| `aiff` | `pcm_s16be` | `-write_id3v2 1` |
| `aiff-pioneer` | `pcm_s16be` | `-ar 44100 -ac 2 -write_id3v2 1` |
| `wav` | `pcm_s16le` | `-rf64 auto` |
| `wav-pioneer` | `pcm_s16le` | `-ar 44100 -ac 2 -rf64 auto` |

## Complexity Tracking

No constitution violations — this section is not applicable.
