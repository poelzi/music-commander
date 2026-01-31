# Research: File Export Recode

**Feature**: 006-file-export-recode
**Date**: 2026-01-31

## Decision 1: Encoding Backend

**Decision**: ffmpeg for all format conversions
**Rationale**: Already a project dependency in the Nix flake. Supports all target formats. Handles metadata copying natively with `-map_metadata 0`. ffprobe (bundled with ffmpeg) provides source file parameter detection.
**Alternatives considered**: sox (limited format support, no MP3 encoding), lame/oggenc (single-format tools, would need multiple backends)

## Decision 2: Source Parameter Detection

**Decision**: Use ffprobe JSON output to detect source codec, bit depth, sample rate, and channels
**Rationale**: ffprobe is bundled with ffmpeg (no additional dependency). JSON output mode (`-of json`) is easy to parse. Single command gets all needed parameters.
**Command**: `ffprobe -v quiet -select_streams a:0 -show_entries stream=codec_name,bits_per_raw_sample,sample_fmt,sample_rate,channels -print_format json {file}`
**Alternatives considered**: mediainfo (not in Nix deps), format-specific tools like metaflac (only works for FLAC)

## Decision 3: Cover Art Detection

**Decision**: Use ffprobe to check for embedded video/image streams; search directory for external covers
**Rationale**: ffprobe can detect embedded art by checking for video streams (`-select_streams v`). External cover search uses a priority-ordered filename list.
**Embedded art check**: `ffprobe -v quiet -select_streams v -show_entries stream=codec_name -of csv=p=0 {file}` — non-empty output means art exists
**External cover search order**: `cover.jpg`, `cover.png`, `folder.jpg`, `folder.png`, `front.jpg`, `front.png`
**Alternatives considered**: Reading tag metadata directly (format-specific, more complex)

## Decision 4: Copy-vs-Recode Strategy

**Decision**: Three-tier strategy based on source parameters and cover art needs
**Rationale**: Avoids unnecessary transcoding (quality preservation) while still handling cover art embedding.

1. **File copy** (`cp`): Source matches target in all parameters AND has embedded art (or no art needed) AND no post-processing needed
2. **Stream copy** (`ffmpeg -codec:a copy`): Source codec matches but needs cover art embedding or container change
3. **Full recode** (`ffmpeg` with codec args): Source doesn't match target parameters

**Special case**: `flac-pioneer` always needs `metaflac` post-processing even for stream copy, so never uses plain file copy.

**Alternatives considered**: Always re-encode (simpler but wasteful), always stream copy (can't change parameters)

## Decision 5: Pioneer FLAC Compatibility

**Decision**: Post-process with `metaflac --remove-tag=WAVEFORMATEXTENSIBLE_CHANNEL_MASK` for `flac-pioneer` preset only
**Rationale**: ffmpeg adds `WAVEFORMATEXTENSIBLE_CHANNEL_MASK=0x0003` to FLAC output for stereo files. Pioneer CDJ/XDJ players fail to read files with this tag. The `metaflac` tool can strip it without re-encoding. Only applied to `flac-pioneer` since regular FLAC users may not care about Pioneer compatibility.
**Alternatives considered**: Patching ffmpeg (not practical), using flac encoder directly (loses metadata mapping convenience)

## Decision 6: Module Architecture

**Decision**: New `music_commander/utils/encoder.py` module following `checkers.py` patterns
**Rationale**: Separation of concerns — encoding logic is independent of CLI wiring. Mirrors the established project pattern where `checkers.py` defines data structures and file-level operations, and `files.py` handles CLI, progress, and parallelism.
**Key structures**: `FormatPreset` (frozen dataclass), `ExportResult` (per-file result), `ExportReport` (summary)
**Alternatives considered**: Inline in files.py (too large, not testable in isolation), separate command file (inconsistent with check being in files.py)

## Decision 7: Temporary File Strategy for SIGINT Safety

**Decision**: Write ffmpeg output to a temporary file (same directory, `.tmp` suffix), rename to final path on success
**Rationale**: If ffmpeg is interrupted or fails, the temp file is cleaned up rather than leaving a corrupt file at the final path. Rename is atomic on the same filesystem.
**Alternatives considered**: Write directly to final path and delete on failure (race condition with SIGINT), use tempfile module (cross-filesystem rename issues)

## Decision 8: WAV Cover Art

**Decision**: Skip cover art embedding for WAV containers
**Rationale**: WAV has no standard mechanism for embedded cover art. While some players can read ID3v2 chunks in WAV, support is inconsistent and Pioneer players don't use it. Better to not embed than to produce files with non-standard metadata.
**Alternatives considered**: Write ID3v2 chunk in WAV (non-standard, poor player support)

## Decision 9: AIFF/WAV Bit Depth for Non-Pioneer Presets

**Decision**: The `aiff` and `wav` presets preserve source bit depth by using appropriate PCM codec variant
**Rationale**: For lossless formats, preserving the original bit depth is important. ffmpeg's `pcm_s16be`/`pcm_s24be` (AIFF) and `pcm_s16le`/`pcm_s24le` (WAV) handle this. The encoder should probe source bit depth and select the matching codec.
**Implementation**: Probe `bits_per_raw_sample` or `sample_fmt` from ffprobe. Map to `pcm_s{depth}{endian}`. Default to 16-bit if detection fails.
**Alternatives considered**: Always use 16-bit (lossy for 24-bit sources), always use 32-bit (wastes space)
