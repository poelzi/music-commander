---
work_package_id: "WP01"
subtasks:
  - "T001"
  - "T002"
  - "T003"
  - "T004"
  - "T005"
  - "T006"
title: "Dependencies & Audio Generation Infrastructure"
phase: "Phase 0 - Setup"
lane: "for_review"
assignee: ""
agent: "claude-opus"
shell_pid: "308628"
review_status: ""
reviewed_by: ""
dependencies: []
history:
  - timestamp: "2026-01-29T17:54:16Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP01 - Dependencies & Audio Generation Infrastructure

## Objectives & Success Criteria

- Add `ffmpeg` and `mutagen` to the nix dev shell and pyproject.toml
- Create audio file generation utilities that produce valid mp3, flac, and aiff files with tags and artwork
- All helpers should be importable from `tests/integration/conftest.py`

**Done when**: Running the audio generation helper produces 6 valid audio files with correct embedded tags and artwork, readable by mutagen.

## Context & Constraints

- **Constitution**: Python 3.13+, nix flake for packaging
- **Plan**: `kitty-specs/004-real-git-annex-integration-tests/plan.md`
- **Research**: `kitty-specs/004-real-git-annex-integration-tests/research.md`
- ffmpeg must be available in PATH (nix provides it)
- No numpy/scipy — use Python stdlib `wave` + `struct` only for WAV generation
- mutagen handles all tagging (ID3 for mp3/aiff, VorbisComment for flac)

**Implementation command**: `spec-kitty implement WP01`

## Subtasks & Detailed Guidance

### Subtask T001 - Add ffmpeg to flake.nix

- **Purpose**: Make ffmpeg available in the nix dev shell for audio format conversion.
- **Steps**: Add `pkgs.ffmpeg` to `devShells.default.buildInputs` in `flake.nix`.
- **Files**: `flake.nix`
- **Parallel?**: Yes (with T002)

### Subtask T002 - Add mutagen to flake.nix and pyproject.toml

- **Purpose**: Make mutagen available for audio file tagging in tests.
- **Steps**:
  1. Add `mutagen` to the `devDeps` function in `flake.nix`
  2. Add `"mutagen>=1.45"` to `[project.optional-dependencies] dev` in `pyproject.toml`
- **Files**: `flake.nix`, `pyproject.toml`
- **Parallel?**: Yes (with T001)

### Subtask T003 - Create tests/integration/__init__.py

- **Purpose**: Make the integration test directory a Python package.
- **Steps**: Create empty `tests/integration/__init__.py`
- **Files**: `tests/integration/__init__.py`
- **Parallel?**: No

### Subtask T004 - WAV generation + ffmpeg conversion helper

- **Purpose**: Generate synthetic audio files in all three formats.
- **Steps**:
  1. Create a function `generate_wav(path: Path, duration_s: float = 0.5, freq_hz: int = 440)` using Python `wave` + `struct` modules
  2. Generate 44100Hz, mono, 16-bit PCM sine wave
  3. Create a function `convert_audio(wav_path: Path, output_path: Path)` that shells out to `ffmpeg -y -i <wav> <output>` with appropriate flags
  4. For mp3: `ffmpeg -y -i input.wav -q:a 2 output.mp3`
  5. For flac: `ffmpeg -y -i input.wav output.flac`
  6. For aiff: `ffmpeg -y -i input.wav output.aiff`
- **Files**: `tests/integration/conftest.py`
- **Parallel?**: No (T006 and T005 build on this)

### Subtask T005 - Mutagen tagging helper

- **Purpose**: Write metadata tags and artwork to audio files.
- **Steps**:
  1. Create a function `tag_audio_file(path: Path, metadata: dict, artwork_png: bytes)` that:
     - Detects format from extension
     - For `.mp3`: Use `mutagen.mp3.MP3` + `mutagen.id3` to set ID3 tags (TIT2, TPE1, TALB, TCON, TBPM, TDRC, TRCK) and APIC frame for artwork
     - For `.flac`: Use `mutagen.flac.FLAC` to set VorbisComment tags and `flac.add_picture()` for artwork
     - For `.aiff`: Use `mutagen.aiff.AIFF` + ID3 tags (same as mp3)
  2. Metadata dict keys: `artist`, `title`, `album`, `genre`, `bpm`, `year`, `tracknumber`
- **Files**: `tests/integration/conftest.py`
- **Parallel?**: No (depends on T004)

### Subtask T006 - Minimal PNG artwork generator

- **Purpose**: Generate a valid PNG image without any image library.
- **Steps**:
  1. Create a function `generate_png(width: int = 8, height: int = 8, color: tuple = (255, 0, 0)) -> bytes`
  2. Construct a minimal valid PNG with:
     - PNG signature (8 bytes)
     - IHDR chunk (13 bytes data: width, height, bit depth=8, color type=2 RGB)
     - IDAT chunk (zlib-compressed raw RGB scanlines with filter byte 0 per row)
     - IEND chunk
  3. Use `zlib.compress()` for IDAT data
  4. Use `struct.pack()` for chunk headers and CRC
- **Files**: `tests/integration/conftest.py`
- **Parallel?**: No (feeds into T005)
- **Notes**: CRC32 must be computed over chunk type + chunk data using `zlib.crc32()`

## Risks & Mitigations

- **ffmpeg not found**: Guard with `shutil.which("ffmpeg")` check; skip tests if missing
- **mutagen format differences**: MP3 uses ID3 frames (e.g., `TIT2`), FLAC uses VorbisComment (e.g., `title`), AIFF uses ID3 — handle each separately
- **PNG validity**: Incorrect CRC or chunk structure causes mutagen to reject artwork — test PNG independently

## Review Guidance

- Verify `nix develop -c ffmpeg -version` works after flake.nix changes
- Verify `nix develop -c python -c "import mutagen"` works
- Run audio generation helper manually and inspect output files with `ffprobe` and `mutagen`
- Check that all 3 formats have correct tags and embedded artwork

## Activity Log

- 2026-01-29T17:54:16Z - system - lane=planned - Prompt created.
- 2026-01-29T18:39:13Z – claude-opus – shell_pid=308628 – lane=doing – Started implementation via workflow command
- 2026-01-29T18:42:07Z – claude-opus – shell_pid=308628 – lane=for_review – Ready for review: ffmpeg+mutagen deps added, audio generation helpers implemented and verified
