# Research: Files Check Integrity

**Feature**: 005-files-check-integrity
**Date**: 2026-01-30

## Tool Selection Per Format

### FLAC: `flac -t -s -w`

- **Decision**: Use native FLAC decoder with test mode
- **Rationale**: Full stream decode + MD5 verification. FLAC embeds an MD5 checksum of raw audio at encode time. `-t` decodes every sample and compares. `-s` suppresses output on success. `-w` treats warnings as errors (catches historical MD5 mismatch bug).
- **Success**: exit code 0
- **Failure**: non-zero exit code; errors on stderr
- **Nixpkgs**: `flac` (already in devShell)
- **Alternatives**: None better exists for FLAC

### MP3: `mp3val` (structural) + `ffmpeg` (full decode)

- **Decision**: Two-tier check. Both always run; any failure = error.
- **Rationale**: mp3val validates MPEG frame structure, VBR headers, tag consistency (16 error types). ffmpeg does full decode catching bitstream corruption. Together they cover structural and audio-level issues.
- **mp3val success**: stdout contains "No problems found" and no WARNING/PROBLEM lines
- **mp3val failure**: stdout contains WARNING or PROBLEM lines (exit code is unreliable, always 0)
- **ffmpeg success**: exit code 0 AND empty stderr
- **ffmpeg failure**: non-zero exit code OR non-empty stderr
- **Nixpkgs**: `mp3val` (0.1.8), `ffmpeg` (already present)
- **Alternatives**: mpck (not in nixpkgs), mp3check (not in nixpkgs)

### OGG Vorbis: `ogginfo` + `ffmpeg` (full decode)

- **Decision**: Two-tier check
- **Rationale**: ogginfo validates Ogg framing, page sequences, Vorbis headers. ffmpeg does full Vorbis decode for bitstream-level corruption.
- **ogginfo success**: exit code 0
- **ogginfo failure**: exit code 1 (flawed counter incremented)
- **Nixpkgs**: `vorbis-tools` (provides ogginfo, 1.4.3)
- **Alternatives**: oggz-validate (liboggz) -- less common

### WAV: `shntool len` (structural) + `sox` (full decode)

- **Decision**: Two-tier check. NOT ffmpeg for WAV.
- **Rationale**: KBNL research found ffmpeg MISSED truncated WAV files. shntool detected ALL damaged WAV files in their corpus. sox provides full decode verification.
- **shntool success**: problems column shows `-` (no issues)
- **shntool failure**: problems column contains indicators: `t` (truncated), `j` (junk appended), `i` (header inconsistent), `a` (not block-aligned), `h` (non-canonical header)
- **sox success**: exit code 0
- **Nixpkgs**: `shntool` (3.0.10), `sox` (already available)
- **Alternatives**: ffmpeg (unreliable for WAV truncation)

### AIFF: `sox`

- **Decision**: sox full decode
- **Rationale**: No dedicated AIFF validator exists. sox has native first-class AIFF support.
- **Command**: `sox <file> -n stat`
- **Success**: exit code 0
- **Nixpkgs**: `sox`
- **Alternatives**: ffmpeg (less native AIFF support)

### M4A/AAC: `ffmpeg`

- **Decision**: ffmpeg full decode (no dedicated validator exists)
- **Command**: `ffmpeg -v error -i <file> -f null -`
- **Success**: exit code 0 AND empty stderr
- **Nixpkgs**: `ffmpeg`
- **Alternatives**: faad2 (no test mode, less convenient)

### Unknown formats: `ffmpeg`

- **Decision**: ffmpeg fallback for any unrecognized extension
- **Rationale**: ffmpeg supports virtually every audio format

## Parallelism

- **Decision**: `concurrent.futures.ThreadPoolExecutor`
- **Rationale**: Each check is I/O-bound (subprocess call). ThreadPoolExecutor is simpler than ProcessPoolExecutor (no pickling). asyncio adds complexity without benefit since we're not doing network I/O.
- **Thread safety**: Each thread runs independent subprocess calls. Results collected via Future objects. Progress display updated from main thread via callback or post-completion processing.

## SIGINT Handling

- **Decision**: `try/finally` pattern
- **Rationale**: Python raises `KeyboardInterrupt` on SIGINT. `try/finally` ensures JSON report is written with partial results. Rich `Live` context manager handles display cleanup automatically.
- **Alternative**: `signal.signal(SIGINT, handler)` -- more complex, not needed since `try/finally` suffices.

## Path vs Query Auto-Detection

- **Decision**: Check `Path(arg).exists()` relative to CWD, then relative to repo root
- **Rationale**: Users naturally type paths to existing files/dirs or search terms. Existing files/dirs are unambiguous. Non-existing args are search terms.
- **Edge case**: A search term that happens to match a file name on disk. This is unlikely for the music-commander search syntax (e.g., `artist:Basinski` won't match a file). If it occurs, the path interpretation takes precedence (user can quote or use explicit search syntax).
