---
work_package_id: WP05
title: Conversion Pipeline and Comment Tagging
lane: "done"
dependencies:
- WP01
base_branch: 009-anomalistic-portal-mirror-WP01
base_commit: ca42f1c8b77039bc7bff2cf6e21c01703a4a9d2f
created_at: '2026-02-03T16:47:01.015231+00:00'
subtasks:
- T026
- T026a
- T026b
- T027
- T028
- T029
- T030
- T031
- T032
phase: Phase 1 - Core Features
assignee: ''
agent: "claude-code"
shell_pid: "3076891"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-03T14:54:20Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP05 – Conversion Pipeline and Comment Tagging

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check the `review_status` field above.

---

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-03

**Issue 1**: Dependency declaration mismatch. WP05 frontmatter lists only `WP01`, but the implementation imports and relies on WP04 (`music_commander.anomalistic.downloader.discover_artwork`) and the prompt says `spec-kitty implement WP05 --base WP04`. Please update dependencies to include WP04 (and WP02/WP03 if required by actual imports) and base on WP04.

**Issue 2**: `discover_artwork()` is used as if it returns a single Path, but WP04 T024a requires returning a list of artwork files for embedding. Once WP04 is corrected, WP05 must be updated to handle a list (select best for embedding, but preserve the full list for future steps) so the integration aligns with the spec.


## Objectives & Success Criteria

1. `build_ffmpeg_command()` accepts optional `extra_metadata` without breaking existing callers.
2. Audio files converted to configured format with release URL in comment tag.
3. Folder pattern rendered via Jinja2 with filesystem-safe sanitization.
4. `meta.json` written per release with all available metadata.
5. Edge cases handled: same-format conversion (still tags), lossy source for lossless target (warn + keep).

## Context & Constraints

- **Research**: R5 (comment metadata), R8 (folder patterns).
- **Data Model**: `data-model.md` — meta.json schema.
- **Encoder**: `music_commander/utils/encoder.py` — existing `FormatPreset`, `build_ffmpeg_command()`, `export_file()`.
- **Jinja2**: Already a dependency; use `Environment(undefined=StrictUndefined)`.

## Implementation Command

```bash
spec-kitty implement WP05 --base WP04
```

## Subtasks & Detailed Guidance

### Subtask T026 – Extend `build_ffmpeg_command()` with `extra_metadata`

- **Purpose**: Allow callers to inject custom metadata tags into ffmpeg commands.
- **Steps**:
  1. In `music_commander/utils/encoder.py`, add parameter to `build_ffmpeg_command()`:
     ```python
     def build_ffmpeg_command(
         input_path: Path,
         output_path: Path,
         preset: FormatPreset,
         source_info: SourceInfo,
         cover_path: Path | None = None,
         *,
         stream_copy: bool = False,
         extra_metadata: dict[str, str] | None = None,  # NEW
     ) -> list[str]:
     ```
  2. After the `-map_metadata 0` line, insert:
     ```python
     if extra_metadata:
         for key, value in extra_metadata.items():
             cmd.extend(["-metadata", f"{key}={value}"])
     ```
  3. Ensure default `None` doesn't change behavior for existing callers.
- **Files**: `music_commander/utils/encoder.py`.
- **Notes**: This is a backward-compatible change. Existing tests should still pass.

### Subtask T026a – Download cover art from portal URL

- **Purpose**: Download the cover art image from the portal when the archive doesn't contain artwork.
- **Steps**:
  1. Implement:
     ```python
     def download_cover_art(cover_art_url: str | None, output_dir: Path) -> Path | None:
         """Download cover art image from URL. Returns path to saved image or None."""
         if not cover_art_url:
             return None
         resp = requests.get(cover_art_url, timeout=30)
         resp.raise_for_status()
         # Derive extension from URL or Content-Type
         ext = Path(urlparse(cover_art_url).path).suffix or ".jpg"
         cover_path = output_dir / f"cover{ext}"
         cover_path.write_bytes(resp.content)
         return cover_path
     ```
  2. Called after extraction, only if `discover_artwork()` from WP04 returned no results.
- **Files**: `music_commander/anomalistic/converter.py`.
- **Parallel?**: Yes — independent of encoding logic.

### Subtask T026b – Embed cover art into converted audio files

- **Purpose**: Embed cover art as front cover in every converted audio file (FR-023).
- **Steps**:
  1. The existing `build_ffmpeg_command()` already supports `cover_path` parameter for embedding cover art. Use it.
  2. Artwork priority:
     - First: artwork found in the extracted archive (from `discover_artwork()` in WP04 T024a).
     - Fallback: downloaded cover art from portal URL (T026a).
     - If neither available: encode without cover art.
  3. In conversion orchestration (T027), pass the resolved `cover_path` to `build_ffmpeg_command()`.
  4. Copy the artwork file to the output folder as `cover.jpg`/`cover.png` alongside the converted tracks.
- **Files**: `music_commander/anomalistic/converter.py`.
- **Parallel?**: No — integrates into conversion pipeline.
- **Notes**: The existing encoder already handles cover art embedding via ffmpeg's `-i cover.jpg -map 0:a -map 1:0 -codec:v:0 copy -disposition:v:0 attached_pic` pattern.

### Subtask T027 – Implement conversion orchestration in `music_commander/anomalistic/converter.py`

- **Purpose**: Convert extracted audio files to target format with URL comment tagging.
- **Steps**:
  1. Create `music_commander/anomalistic/converter.py`.
  2. Implement:
     ```python
     def convert_release(
         audio_files: list[Path],
         output_dir: Path,
         preset: FormatPreset,
         release_url: str,
         verbose: bool = False,
     ) -> list[Path]:
         # For each audio file:
         #   1. Probe source with ffprobe (use existing probe_source())
         #   2. Determine output filename (same stem + preset.container)
         #   3. Build ffmpeg command with extra_metadata={"comment": release_url}
         #   4. Run ffmpeg
         #   5. Collect output paths
         # Return list of converted file paths
     ```
  3. Look up preset from config format string using existing `PRESETS` dict or `get_preset()`.
- **Files**: Create `music_commander/anomalistic/converter.py`.

### Subtask T028 – Implement folder pattern rendering

- **Purpose**: Render the user's output pattern into a filesystem path.
- **Steps**:
  1. In `music_commander/anomalistic/converter.py` (or a utils function):
     ```python
     from jinja2 import Environment, StrictUndefined

     _UNSAFE_CHARS = re.compile(r'[<>:"|?*]')

     def render_output_path(
         pattern: str,
         genre: str,
         label: str,
         artist: str,
         album: str,
         year: str,
     ) -> Path:
         env = Environment(undefined=StrictUndefined)
         template = env.from_string(pattern)
         rendered = template.render(
             genre=genre, label=label, artist=artist,
             album=album, year=year,
         )
         # Sanitize each path component
         parts = []
         for part in Path(rendered).parts:
             clean = _UNSAFE_CHARS.sub("", part).strip(". ")
             if clean:
                 parts.append(clean)
         return Path(*parts) if parts else Path("Unknown")
     ```
  2. Handle empty variables gracefully (Jinja2 `{% if %}` in user patterns).
- **Files**: `music_commander/anomalistic/converter.py`.
- **Parallel?**: Yes — independent function.

### Subtask T029 – Implement `meta.json` generation

- **Purpose**: Write release metadata to a JSON file alongside converted tracks.
- **Steps**:
  1. Implement:
     ```python
     def write_meta_json(
         output_dir: Path,
         artist: str,
         album: str,
         release_url: str,
         genres: list[str],
         labels: list[str],
         release_date: str | None,
         cover_art_url: str | None,
         credits: str | None,
         download_source: str,
         download_url: str,
         tracks: list[dict],
     ) -> Path:
         meta = {
             "artist": artist,
             "album": album,
             "url": release_url,
             "genres": genres,
             "labels": labels,
             "release_date": release_date,
             "cover_art_url": cover_art_url,
             "credits": credits,
             "download_source": download_source,
             "download_url": download_url,
             "tracks": tracks,
             "mirrored_at": datetime.now(timezone.utc).isoformat(),
         }
         meta_path = output_dir / "meta.json"
         meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
         return meta_path
     ```
- **Files**: `music_commander/anomalistic/converter.py`.
- **Parallel?**: Yes — independent function.

### Subtask T030 – Handle format-match edge case

- **Purpose**: When download format matches target format, still process to add comment tag.
- **Steps**:
  1. In conversion orchestration, if source format matches target preset:
     - Still run ffmpeg with `-codec:a copy` (stream copy) + `-metadata comment=URL`.
     - This avoids re-encoding but still adds the comment.
  2. Use existing `can_copy()` from encoder.py to detect this case.
- **Files**: `music_commander/anomalistic/converter.py`.

### Subtask T031 – Handle lossy-when-lossless-requested edge case

- **Purpose**: When only MP3 is available but user wants FLAC, don't upscale.
- **Steps**:
  1. If source is lossy (MP3) and target is lossless (FLAC):
     - Log warning: "Source is MP3 (lossy), keeping as MP3 instead of converting to FLAC"
     - Add comment tag to the MP3 file (stream copy + metadata).
     - Do NOT convert lossy → lossless.
  2. Detect via `probe_source()` codec info.
- **Files**: `music_commander/anomalistic/converter.py`.

### Subtask T032 – Unit tests for conversion

- **Purpose**: Verify conversion orchestration, pattern rendering, and meta.json.
- **Steps**:
  1. Create `tests/unit/test_anomalistic_converter.py`.
  2. Test `render_output_path()`:
     - Pattern with all variables.
     - Pattern with `{% if %}` optional segments.
     - Filesystem-unsafe characters in variable values.
     - Empty genre → "Unknown" fallback.
  3. Test `write_meta_json()`: verify JSON structure and encoding.
  4. Test `build_ffmpeg_command()` extra_metadata: verify `-metadata comment=URL` in command.
  5. Mock ffmpeg subprocess for conversion orchestration tests.
- **Files**: Create `tests/unit/test_anomalistic_converter.py`.

## Risks & Mitigations

- **Encoder change breaks existing exports**: Default `extra_metadata=None` ensures backward compatibility. Run existing encoder tests.
- **Jinja2 template errors**: Validate pattern at config load time; provide clear error message.
- **ffmpeg failures on exotic formats**: Catch per-file, log error, continue.

## Review Guidance

- Verify `build_ffmpeg_command()` change is backward-compatible (all existing callers unaffected).
- Verify meta.json matches `data-model.md` schema exactly.
- Verify filesystem sanitization handles all POSIX and Windows reserved characters.
- Verify lossy→lossless detection works correctly.

## Activity Log

- 2026-02-03T14:54:20Z – system – lane=planned – Prompt created.
- 2026-02-03T16:54:42Z – unknown – shell_pid=2968231 – lane=for_review – Moved to for_review
- 2026-02-03T22:07:07Z – OpenCode – shell_pid=2983876 – lane=doing – Started review via workflow command
- 2026-02-03T22:08:01Z – OpenCode – shell_pid=2983876 – lane=planned – Moved to planned
- 2026-02-03T22:51:50Z – claude-code – shell_pid=3076891 – lane=doing – Started review via workflow command
- 2026-02-03T22:54:19Z – claude-code – shell_pid=3076891 – lane=done – Review passed: All subtasks verified. extra_metadata backward compatible, converter orchestration correct, Jinja2 sanitization thorough, meta.json structure correct, lossy→lossless and format-match edge cases handled, artwork list handling aligned with WP04. 44 tests pass.
