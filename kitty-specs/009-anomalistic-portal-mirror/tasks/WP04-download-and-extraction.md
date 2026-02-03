---
work_package_id: "WP04"
subtasks:
  - "T020"
  - "T021"
  - "T022"
  - "T023"
  - "T024"
  - "T024a"
  - "T025"
title: "Download and Archive Extraction"
phase: "Phase 1 - Core Features"
lane: "planned"
assignee: ""
agent: ""
shell_pid: ""
review_status: ""
reviewed_by: ""
dependencies: ["WP02"]
history:
  - timestamp: "2026-02-03T14:54:20Z"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
---

# Work Package Prompt: WP04 – Download and Archive Extraction

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check the `review_status` field above.

---

## Review Feedback

*[This section is empty initially.]*

---

## Objectives & Success Criteria

1. Archives (ZIP/RAR) downloaded with temp file pattern and atomic rename.
2. ZIP extraction via stdlib `zipfile`.
3. RAR extraction via `unrar` subprocess.
4. Archive format auto-detected from extension/magic.
5. Audio files discovered and listed from extracted contents.
6. Graceful error handling for corrupt archives, missing `unrar`, dead links.

## Context & Constraints

- **Research**: R6 (unrar-free).
- **Downloads are sequential** — one at a time, no parallelism.
- **Temp file pattern**: `.filename.tmp` → rename on success, delete on failure.
- **Follow bandcamp downloader patterns** from `music_commander/bandcamp/downloader.py`.

## Implementation Command

```bash
spec-kitty implement WP04 --base WP02
```

## Subtasks & Detailed Guidance

### Subtask T020 – Implement archive download in `music_commander/anomalistic/downloader.py`

- **Purpose**: Download archive files from the portal with progress and temp file safety.
- **Steps**:
  1. Create `music_commander/anomalistic/downloader.py`.
  2. Implement:
     ```python
     def download_archive(
         url: str,
         output_dir: Path,
         progress_callback: Callable[[int, int | None], None] | None = None,
     ) -> Path:
         # 1. HEAD request to get Content-Length (optional, for progress)
         # 2. Derive filename from URL (url-decode, extract last path segment)
         # 3. Create temp path: output_dir / f".{filename}.tmp"
         # 4. Stream GET with chunk_size=8192
         # 5. Call progress_callback(downloaded_bytes, total_bytes) per chunk
         # 6. On success: atomic rename tmp → final
         # 7. On KeyboardInterrupt/Exception: delete tmp, re-raise
         # 8. Return final Path
     ```
  3. Use `requests.Session` (can share with client or create new).
- **Files**: Create `music_commander/anomalistic/downloader.py`.

### Subtask T021 – Implement ZIP extraction

- **Purpose**: Extract ZIP archives to a release directory.
- **Steps**:
  1. Implement:
     ```python
     def extract_zip(archive_path: Path, output_dir: Path) -> Path:
         extract_dir = output_dir  # or a subdirectory
         extract_dir.mkdir(parents=True, exist_ok=True)
         with zipfile.ZipFile(archive_path, "r") as zf:
             zf.extractall(extract_dir)
         archive_path.unlink()  # Remove archive after extraction
         return extract_dir
     ```
  2. Handle nested directories: if ZIP contains a single top-level directory, use its contents directly.
- **Files**: `music_commander/anomalistic/downloader.py`.
- **Parallel?**: Yes — different code path from T022.

### Subtask T022 – Implement RAR extraction via `unrar`

- **Purpose**: Extract RAR archives using the free `unrar` binary.
- **Steps**:
  1. Implement:
     ```python
     def extract_rar(archive_path: Path, output_dir: Path) -> Path:
         output_dir.mkdir(parents=True, exist_ok=True)
         try:
             result = subprocess.run(
                 ["unrar", "x", "-o+", str(archive_path), str(output_dir) + "/"],
                 capture_output=True, text=True, check=True,
             )
         except FileNotFoundError:
             raise AnomaListicError(
                 "unrar not found. Install unrar-free: nix develop or apt install unrar-free"
             )
         except subprocess.CalledProcessError as e:
             raise AnomaListicError(f"RAR extraction failed: {e.stderr}")
         archive_path.unlink()
         return output_dir
     ```
- **Files**: `music_commander/anomalistic/downloader.py`.
- **Parallel?**: Yes — different code path from T021.

### Subtask T023 – Implement archive format detection

- **Purpose**: Determine if a downloaded file is ZIP or RAR.
- **Steps**:
  1. Implement:
     ```python
     def detect_archive_format(file_path: Path) -> str:
         suffix = file_path.suffix.lower()
         if suffix == ".zip" or zipfile.is_zipfile(file_path):
             return "zip"
         elif suffix == ".rar":
             return "rar"
         else:
             raise AnomaListicError(f"Unknown archive format: {file_path}")
     ```
- **Files**: `music_commander/anomalistic/downloader.py`.

### Subtask T024 – Implement audio file discovery

- **Purpose**: Find audio files in an extracted directory.
- **Steps**:
  1. Implement:
     ```python
     AUDIO_EXTENSIONS = frozenset({".wav", ".mp3", ".flac", ".aif", ".aiff", ".ogg", ".opus"})

     def discover_audio_files(directory: Path) -> list[Path]:
         audio_files = []
         for f in sorted(directory.rglob("*")):
             if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
                 audio_files.append(f)
         return audio_files
     ```
  2. Sort by filename to preserve track order.
  3. Ignore non-audio files (images, NFO, text).
- **Files**: `music_commander/anomalistic/downloader.py`.

### Subtask T024a – Discover and preserve artwork files from archive

- **Purpose**: Find artwork images in extracted archives and copy them to the output folder for later embedding into audio files.
- **Steps**:
  1. Implement:
     ```python
     ARTWORK_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

     def discover_artwork(directory: Path) -> list[Path]:
         """Find artwork image files in an extracted archive directory."""
         artwork = []
         for f in sorted(directory.rglob("*")):
             if f.is_file() and f.suffix.lower() in ARTWORK_EXTENSIONS:
                 artwork.append(f)
         return artwork
     ```
  2. Prefer files matching common cover art names: `cover.*`, `front.*`, `folder.*`, `artwork.*`. If multiple images found, select the best candidate (largest file or matching name pattern).
- **Files**: `music_commander/anomalistic/downloader.py`.
- **Parallel?**: Yes — independent of audio file discovery.
- **Notes**: The artwork list is passed to WP05 conversion for embedding.

### Subtask T025 – Unit tests for downloader

- **Purpose**: Verify download, extraction, and discovery logic.
- **Steps**:
  1. Create `tests/unit/test_anomalistic_downloader.py`.
  2. Test download with mocked HTTP (verify temp file pattern, atomic rename).
  3. Test ZIP extraction with a small real ZIP fixture.
  4. Test RAR extraction with mocked `subprocess.run` (verify command args).
  5. Test `detect_archive_format()` with various extensions.
  6. Test `discover_audio_files()` with a directory containing mixed file types.
  7. Test error handling: download 404, corrupt ZIP, missing `unrar`.
- **Files**: Create `tests/unit/test_anomalistic_downloader.py`.

## Risks & Mitigations

- **`unrar` not available in test environment**: Mock subprocess calls in unit tests. Integration tests require `nix develop`.
- **Corrupt archives**: Catch `zipfile.BadZipFile` and `subprocess.CalledProcessError`, mark release as failed.
- **Nested directory structures in archives**: Some ZIPs may contain a single top-level folder; handle by detecting and flattening.

## Review Guidance

- Verify temp file cleanup on all error paths (KeyboardInterrupt, HTTP error, extraction error).
- Verify `unrar` error message includes installation guidance.
- Check that audio file discovery doesn't include hidden files (`.DS_Store`, `._` files).

## Activity Log

- 2026-02-03T14:54:20Z – system – lane=planned – Prompt created.
