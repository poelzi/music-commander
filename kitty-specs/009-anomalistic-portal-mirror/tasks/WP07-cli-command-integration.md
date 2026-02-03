---
work_package_id: WP07
title: CLI Command and Integration
lane: "for_review"
dependencies:
- WP01
base_branch: 009-anomalistic-portal-mirror-WP01
base_commit: 020517a2213a4c278dfd373b525d79daddc5bbdf
created_at: '2026-02-03T17:04:21.344567+00:00'
subtasks:
- T039
- T040
- T041
- T042
- T043
- T044
- T045
- T046
phase: Phase 2 - Integration
assignee: ''
agent: "OpenCode"
shell_pid: "2983876"
review_status: "has_feedback"
reviewed_by: "Daniel Poelzleithner"
history:
- timestamp: '2026-02-03T14:54:20Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP07 – CLI Command and Integration

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check the `review_status` field above.

---

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-03

**Issue 1**: Dependency declaration mismatch. WP07 frontmatter lists only `WP01`, but the implementation imports and relies on WP02–WP06 modules (client/category/parser/downloader/converter/dedup), and the prompt says base WP06. Please update dependencies to include WP02–WP06 and base on WP06.


## Objectives & Success Criteria

1. `music-commander mirror anomalistic` command is registered and discoverable.
2. Full orchestration: fetch catalog → dedup → download → extract → convert → organize → meta.json → cache update.
3. Rich progress display for each phase.
4. Summary output with downloaded/skipped/failed counts.
5. `--force` flag bypasses duplicate detection.
6. Graceful handling of interrupts and partial failures.

## Context & Constraints

- **Spec**: All user stories culminate here.
- **Plan**: Project structure shows `commands/mirror/__init__.py` + `commands/mirror/anomalistic.py`.
- **Constitution**: Click CLI, Rich output, pytest tests.
- **Patterns**: Follow `commands/bandcamp/` structure for group registration, exit codes, context passing.

## Implementation Command

```bash
spec-kitty implement WP07 --base WP06
```

## Subtasks & Detailed Guidance

### Subtask T039 – Create `mirror` command group

- **Purpose**: Register the new top-level `mirror` group for CLI auto-discovery.
- **Steps**:
  1. Create `music_commander/commands/mirror/__init__.py`:
     ```python
     """Mirror commands for syncing with external music portals."""

     import click

     EXIT_SUCCESS = 0
     EXIT_MIRROR_ERROR = 1

     @click.group("mirror")
     def cli() -> None:
         """Mirror releases from external music portals."""
         pass

     from music_commander.commands.mirror import anomalistic as _anomalistic  # noqa: E402, F401
     ```
  2. The CLI auto-discovery system will find `commands/mirror/` and register `cli`.
- **Files**: Create `music_commander/commands/mirror/__init__.py`.

### Subtask T040 – Implement `anomalistic` CLI command

- **Purpose**: The main user-facing command for mirroring the Dark Psy Portal.
- **Steps**:
  1. Create `music_commander/commands/mirror/anomalistic.py`:
     ```python
     import click
     from music_commander.commands.mirror import cli, EXIT_SUCCESS, EXIT_MIRROR_ERROR
     from music_commander.utils.context import pass_context

     @cli.command("anomalistic")
     @click.option("--force", is_flag=True, help="Re-download all releases, bypassing duplicate detection.")
     @pass_context
     def anomalistic(ctx, force: bool) -> None:
         """Mirror releases from the Anomalistic Dark Psy Portal."""
         config = ctx.config
         # Determine output directory
         output_dir = config.anomalistic_output_dir or (config.music_repo / "Anomalistic")
         output_dir.mkdir(parents=True, exist_ok=True)
         # ... orchestration (T041)
     ```
- **Files**: Create `music_commander/commands/mirror/anomalistic.py`.

### Subtask T041 – Main orchestration flow

- **Purpose**: Wire all components together into the end-to-end mirror workflow.
- **Steps**:
  1. In the `anomalistic` command function, implement:
     ```python
     # Phase 1: Fetch catalog
     client = AnomaListicClient()
     info("Fetching categories...")
     raw_categories = client.fetch_categories()
     categories = classify_categories(raw_categories)
     info(f"Found {len([c for c in categories.values() if c.type == CategoryType.GENRE])} genres, "
          f"{len([c for c in categories.values() if c.type == CategoryType.LABEL])} labels")

     info("Fetching releases...")
     releases = list(client.iter_releases())
     info(f"Found {len(releases)} releases")

     # Phase 2: Process each release
     stats = {"downloaded": 0, "skipped": 0, "failed": 0}

     with get_cache_session(config.music_repo) as session:
         for post in releases:
             try:
                 # Parse release
                 parsed = parse_release_content(post)
                 genre_names = get_release_genres(post["categories"], categories)
                 label_names = get_release_labels(post["categories"], categories)
                 primary_genre = genre_names[0] if genre_names else "Unknown"
                 primary_label = label_names[0] if label_names else ""

                 # Dedup check (unless --force)
                 if not force:
                     dedup = check_duplicate(session, post["link"], parsed.artist, parsed.album)
                     if dedup.should_skip:
                         verbose(f"Skipping {parsed.artist} - {parsed.album}: {dedup.reason}")
                         stats["skipped"] += 1
                         continue

                 # Select download URL
                 source_pref = config.anomalistic_download_source
                 download_url = parsed.download_urls.get(source_pref) or next(iter(parsed.download_urls.values()), None)
                 if not download_url:
                     warning(f"No download URL for {parsed.artist} - {parsed.album}")
                     stats["failed"] += 1
                     continue

                 # Download
                 archive_path = download_archive(download_url, tmp_dir, progress_callback)

                 # Extract
                 fmt = detect_archive_format(archive_path)
                 extract_dir = extract_zip(archive_path, tmp_extract) if fmt == "zip" else extract_rar(archive_path, tmp_extract)

                 # Discover audio files
                 audio_files = discover_audio_files(extract_dir)

                 # Render output path
                 rel_path = render_output_path(
                     config.anomalistic_output_pattern,
                     genre=primary_genre, label=primary_label,
                     artist=parsed.artist, album=parsed.album,
                     year=post["date"][:4],
                 )
                 final_dir = output_dir / rel_path
                 final_dir.mkdir(parents=True, exist_ok=True)

                 # Convert
                 preset = get_preset(config.anomalistic_format)
                 converted = convert_release(audio_files, final_dir, preset, post["link"])

                 # Write meta.json
                 write_meta_json(final_dir, ...)

                 # Update cache
                 update_cache(session, post, parsed, primary_genre, label_names, final_dir)

                 stats["downloaded"] += 1
                 success(f"Downloaded: {parsed.artist} - {parsed.album}")

             except Exception as e:
                 error(f"Failed: {parsed.artist} - {parsed.album}: {e}")
                 stats["failed"] += 1
                 continue

     # Phase 3: Summary
     ```
  2. Use temp directories for download and extraction, clean up after each release.
  3. Commit cache session after each successful release (not at the end).
- **Files**: `music_commander/commands/mirror/anomalistic.py`.

### Subtask T042 – Rich progress display (covers FR-016)

- **Purpose**: Show user-friendly progress for long-running operations (FR-016).
- **Steps**:
  1. Use Rich `Progress` for:
     - Catalog fetch: spinner + "Fetching releases..."
     - Per-release download: progress bar with bytes downloaded / total.
     - Per-release conversion: progress bar with files converted.
  2. Use existing `info()`, `verbose()`, `success()`, `warning()`, `error()` for status messages.
  3. Consider using `MultilineFileProgress` from `utils/output.py` if appropriate, or a simpler `Progress` bar.
- **Files**: `music_commander/commands/mirror/anomalistic.py`.

### Subtask T043 – Summary output

- **Purpose**: Display final statistics after the mirror completes.
- **Steps**:
  1. After processing all releases, display:
     ```
     Mirror complete:
       Downloaded: 15
       Skipped:    260 (cached)
       Failed:     3
     ```
  2. If any failures, list them with brief error messages.
  3. Return `EXIT_SUCCESS` if no failures, `EXIT_MIRROR_ERROR` if any failures.
- **Files**: `music_commander/commands/mirror/anomalistic.py`.

### Subtask T044 – `--force` CLI flag

- **Purpose**: Allow re-downloading all releases.
- **Steps**: Already defined in T040's `@click.option`. In T041 orchestration, pass `force` to skip dedup checks.
- **Files**: `music_commander/commands/mirror/anomalistic.py`.

### Subtask T045 – Verbose output integration

- **Purpose**: Show detailed info when `-v` flag is used.
- **Steps**:
  1. Use `verbose()` for:
     - Per-release processing status.
     - Dedup check results and scores.
     - Download URL selection.
     - Conversion details.
  2. Use `debug()` for:
     - Raw API responses.
     - ffmpeg command details.
     - File path computations.
- **Files**: `music_commander/commands/mirror/anomalistic.py`.

### Subtask T046 – Unit/integration tests for CLI command

- **Purpose**: Verify command registration and basic orchestration.
- **Steps**:
  1. Create `tests/unit/test_mirror_command.py`.
  2. Test that `mirror` group is registered in CLI auto-discovery.
  3. Test `anomalistic` command is a subcommand of `mirror`.
  4. Test with `click.testing.CliRunner` — mock all network calls.
  5. Test `--force` flag is passed through.
  6. Test `--help` output includes expected options.
- **Files**: Create `tests/unit/test_mirror_command.py`.

## Risks & Mitigations

- **Long-running operation**: Handle `KeyboardInterrupt` — save progress, clean up temp files, display partial summary.
- **Temp file accumulation**: Use `tempfile.TemporaryDirectory()` for per-release extraction; auto-cleaned.
- **Memory**: Don't load all 278 releases into memory at once if possible — process as iterator. (But fetching the catalog list is only ~278 items, fine in memory.)

## Review Guidance

- Verify `mirror` group appears in `music-commander --help` output.
- Verify `anomalistic` appears in `music-commander mirror --help`.
- Verify graceful handling of KeyboardInterrupt mid-download.
- Verify cache is updated per-release (not just at the end) so partial runs are resumable.
- Verify temp files are cleaned up even on failure.

## Activity Log

- 2026-02-03T14:54:20Z – system – lane=planned – Prompt created.
- 2026-02-03T17:10:11Z – unknown – shell_pid=2977585 – lane=for_review – Moved to for_review
- 2026-02-03T22:10:30Z – OpenCode – shell_pid=2983876 – lane=doing – Started review via workflow command
- 2026-02-03T22:11:03Z – OpenCode – shell_pid=2983876 – lane=planned – Moved to planned
