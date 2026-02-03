---
work_package_id: WP06
title: Duplicate Detection
lane: "for_review"
dependencies:
- WP01
- WP02
base_branch: 009-anomalistic-portal-mirror-WP02
base_commit: 020517a2213a4c278dfd373b525d79daddc5bbdf
created_at: '2026-02-03T16:59:51.749045+00:00'
subtasks:
- T033
- T034
- T035
- T036
- T037
- T038
phase: Phase 2 - Enhancement
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

# Work Package Prompt: WP06 – Duplicate Detection

## ⚠️ IMPORTANT: Review Feedback Status

- **Has review feedback?**: Check the `review_status` field above.

---

## Review Feedback

**Reviewed by**: Daniel Poelzleithner
**Status**: ❌ Changes Requested
**Date**: 2026-02-03

**Issue 1**: Dependency declaration mismatch. WP06 depends on WP01 in frontmatter, but it imports cache models and uses match_release from `music_commander/utils/matching.py` (WP01) and is intended to build on WP02 (per prompt). Please update dependencies to include WP02 and base on WP02.


## Objectives & Success Criteria

1. Previously-downloaded releases detected via cache DB URL lookup and skipped.
2. Releases already in collection (from other sources) detected via comment field scan and fuzzy matching.
3. `--force` flag bypasses all duplicate checks.
4. Detection is fast enough for 278 releases (should add <1 second overhead per release).

## Context & Constraints

- **Spec**: User Story 5 (Duplicate Detection and Skip).
- **Shared matching**: `music_commander/utils/matching.py` — `match_release()` function.
- **Cache models**: `AnomaListicRelease` (download_status field), `CacheTrack` (comment field).
- **Threshold**: Use existing `bandcamp_match_threshold` config value (default 60) for fuzzy matching. Could add a separate `anomalistic_match_threshold` if needed.

## Implementation Command

```bash
spec-kitty implement WP06 --base WP02
```

## Subtasks & Detailed Guidance

### Subtask T033 – URL-based cache lookup

- **Purpose**: Check if a release was already downloaded by this tool.
- **Steps**:
  1. Create `music_commander/anomalistic/dedup.py`.
  2. Implement:
     ```python
     def check_cache_url(session, release_url: str) -> bool:
         """Check if release URL exists in anomalistic_releases with status 'downloaded'."""
         result = session.query(AnomaListicRelease).filter(
             AnomaListicRelease.release_url == release_url,
             AnomaListicRelease.download_status == "downloaded",
         ).first()
         return result is not None
     ```
- **Files**: Create `music_commander/anomalistic/dedup.py`.
- **Parallel?**: Yes — independent check.

### Subtask T034 – Comment-field scan

- **Purpose**: Check if tracks with this release URL in their comment tag already exist.
- **Steps**:
  1. Implement:
     ```python
     def check_comment_url(session, release_url: str) -> bool:
         """Check if any CacheTrack has this URL in its comment field."""
         result = session.query(CacheTrack).filter(
             CacheTrack.comment.contains(release_url),
         ).first()
         return result is not None
     ```
  2. This catches releases downloaded by this tool or manually tagged.
- **Files**: `music_commander/anomalistic/dedup.py`.
- **Parallel?**: Yes — independent check.

### Subtask T035 – Fuzzy artist+album matching

- **Purpose**: Detect releases already in the collection from other sources (e.g., Bandcamp).
- **Steps**:
  1. Implement:
     ```python
     from music_commander.utils.matching import match_release

     def check_fuzzy_match(
         session,
         artist: str,
         album: str,
         threshold: int = 60,
     ) -> tuple[bool, float, str | None]:
         """Fuzzy match against existing collection.
         Returns (is_match, best_score, matched_album_desc).
         """
         # Load distinct (artist, album) pairs from CacheTrack
         # For efficiency, query distinct albums grouped by artist
         local_albums = session.query(
             CacheTrack.artist, CacheTrack.album
         ).distinct().all()

         best_score = 0.0
         best_match = None
         for local_artist, local_album in local_albums:
             if not local_artist or not local_album:
                 continue
             score = match_release(local_artist, local_album, artist, album)
             if score > best_score:
                 best_score = score
                 best_match = f"{local_artist} - {local_album}"

         return (best_score >= threshold, best_score, best_match)
     ```
  2. Cache the local album list for the duration of the sync (don't re-query per release).
- **Files**: `music_commander/anomalistic/dedup.py`.
- **Parallel?**: Yes — independent check.
- **Notes**: For 278 releases × ~10,000 local albums, this is O(n*m) comparisons. If too slow, consider pre-normalizing local albums and using a cutoff. In practice, with `rapidfuzz`, this should be fast enough.

### Subtask T036 – Duplicate decision logic

- **Purpose**: Combine all detection signals into a skip/download decision.
- **Steps**:
  1. Implement:
     ```python
     @dataclass
     class DedupResult:
         should_skip: bool
         reason: str | None  # "cached", "comment_match", "fuzzy_match (score: 85.2)"
         match_details: str | None  # e.g., "Matched: Artist - Album"

     def check_duplicate(
         session,
         release_url: str,
         artist: str,
         album: str,
         threshold: int = 60,
     ) -> DedupResult:
         # Priority order:
         # 1. URL cache check (fastest, most reliable)
         if check_cache_url(session, release_url):
             return DedupResult(True, "cached", None)
         # 2. Comment field scan
         if check_comment_url(session, release_url):
             return DedupResult(True, "comment_match", None)
         # 3. Fuzzy matching (slowest)
         is_match, score, details = check_fuzzy_match(session, artist, album, threshold)
         if is_match:
             return DedupResult(True, f"fuzzy_match (score: {score:.1f})", details)
         return DedupResult(False, None, None)
     ```
- **Files**: `music_commander/anomalistic/dedup.py`.

### Subtask T037 – `--force` flag bypass

- **Purpose**: Allow users to re-download everything regardless of duplicates.
- **Steps**:
  1. In the orchestration layer (WP07), when `--force` is True, skip calling `check_duplicate()` entirely.
  2. This is primarily a WP07 concern, but the dedup module should document that callers can bypass it.
- **Files**: `music_commander/anomalistic/dedup.py` (docstring), main integration in WP07.

### Subtask T038 – Unit tests for duplicate detection

- **Purpose**: Verify all three detection strategies and the combined decision logic.
- **Steps**:
  1. Create `tests/unit/test_anomalistic_dedup.py`.
  2. Test `check_cache_url()`: release in cache → True, not in cache → False.
  3. Test `check_comment_url()`: track with URL in comment → True, without → False.
  4. Test `check_fuzzy_match()`:
     - Exact match → high score, True.
     - Similar but different → above/below threshold.
     - No match → False.
  5. Test `check_duplicate()` priority: cached beats fuzzy.
  6. Use in-memory SQLite for test DB sessions.
- **Files**: Create `tests/unit/test_anomalistic_dedup.py`.

## Risks & Mitigations

- **False positive fuzzy matches**: Use conservative threshold (60). Log match score at verbose level so users can diagnose.
- **Performance with large collections**: Pre-load local albums once, not per-release. If still slow, consider indexing normalized names.

## Review Guidance

- Verify duplicate detection doesn't block legitimate re-downloads (only when `--force` is absent).
- Verify fuzzy matching threshold is reasonable (test with similar but different releases).
- Verify cache URL check uses exact match (not substring).

## Activity Log

- 2026-02-03T14:54:20Z – system – lane=planned – Prompt created.
- 2026-02-03T17:03:14Z – unknown – shell_pid=2973915 – lane=for_review – Moved to for_review
- 2026-02-03T22:09:26Z – OpenCode – shell_pid=2983876 – lane=doing – Started review via workflow command
- 2026-02-03T22:10:05Z – OpenCode – shell_pid=2983876 – lane=planned – Moved to planned
