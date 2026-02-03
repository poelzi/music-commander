# Research: CUE Sheet Splitter

**Feature**: 008-cue-sheet-splitter
**Date**: 2026-02-03

## R1: shntool splitting capabilities

**Question**: What formats does shntool support and how does it handle cue-based splitting?

**Findings**:
- shntool `split` command natively supports cue sheet splitting via `-f <cuefile>`
- Output naming via `-t` format string: `%n` for track number, `%t` for title
- `-o flac` outputs FLAC; `-O never` prevents overwriting existing files
- Supported input formats depend on available helper programs (flac, mac, wavpack, ffmpeg)
- shntool operates at the byte level for WAV/FLAC, ensuring lossless splitting at exact CD frame boundaries

**Decision**: Use shntool for FLAC and WAV sources. For APE (`.ape`) and WavPack (`.wv`), check if shntool can handle them (it can if `mac` and `wavpack` decoders are in PATH). If shntool fails, fall back to ffmpeg-based splitting using timestamps parsed from the cue sheet.

## R2: Existing codebase patterns for subprocess execution

**Question**: How does the codebase handle external tool invocation?

**Findings**:
- `subprocess.check_call` and `subprocess.run` are used throughout (e.g., `music_commander/utils/git.py`, `music_commander/utils/encoder.py`)
- `encoder.py` has `build_ffmpeg_command()` and `export_file()` patterns for ffmpeg invocation
- `checkers.py` checks for tool availability before running (e.g., shntool presence check)
- Error handling wraps `CalledProcessError` with user-friendly messages

**Decision**: Follow the same subprocess patterns. Check for shntool/metaflac availability at command start. Use `subprocess.run` with capture for error reporting.

## R3: Encoding detection for cue files

**Question**: What encodings are common for cue files and how to handle them?

**Findings**:
- Cue files from different sources use various encodings: UTF-8, Latin-1, CP1252, Shift-JIS (Japanese CDs)
- The existing script only tries a single encoding and raises on failure
- Python's `open()` with explicit encoding + fallback chain is the standard approach
- chardet/charset-normalizer could auto-detect but adds a dependency

**Decision**: Try UTF-8 first, then Latin-1 as fallback (covers most Western music). Provide `--encoding` flag for explicit override. No auto-detection library needed.

## R4: Nix flake dependency addition

**Question**: How to add shntool to the nix flake?

**Findings**:
- `flake.nix` already includes runtime and dev dependencies
- shntool is available in nixpkgs as `shntool`
- It needs to be added alongside existing audio tools (ffmpeg, flac, etc.)

**Decision**: Add `shntool` to the nix flake `buildInputs` or `nativeBuildInputs` where other audio tools are listed.
