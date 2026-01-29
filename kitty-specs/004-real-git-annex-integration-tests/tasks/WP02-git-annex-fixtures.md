---
work_package_id: WP02
title: Git-Annex Test Fixtures
lane: "doing"
dependencies: [WP01]
base_branch: 004-real-git-annex-integration-tests-WP01
base_commit: 5a6a7ce1c4a3537341653cbebb467c93b65208d3
created_at: '2026-01-29T18:42:46.937381+00:00'
subtasks:
- T007
- T008
- T009
- T010
- T011
phase: Phase 0 - Setup
assignee: ''
agent: "claude-opus"
shell_pid: "323047"
review_status: ''
reviewed_by: ''
history:
- timestamp: '2026-01-29T17:54:16Z'
  lane: planned
  agent: system
  shell_pid: ''
  action: Prompt generated via /spec-kitty.tasks
---

# Work Package Prompt: WP02 - Git-Annex Test Fixtures

## Objectives & Success Criteria

- Create session-scoped pytest fixtures that initialize real git-annex repos
- Origin repo contains 6 synthetic audio files with git-annex metadata
- Partial clone has only 3 of 6 files fetched
- Cache session fixtures provide ready-to-query SQLAlchemy sessions

**Done when**: Fixtures create valid repos where `git annex find` vs `git annex find --include='*'` return different counts in the partial clone.

## Context & Constraints

- **Plan**: `kitty-specs/004-real-git-annex-integration-tests/plan.md` (track metadata table)
- **Existing fixtures**: `tests/conftest.py` has a basic `git_annex_repo` fixture — do not modify it
- Session-scoped fixtures share state across all tests — tests must not mutate repo content
- `build_cache(repo_path, session)` needs only a Path and SQLAlchemy Session

**Implementation command**: `spec-kitty implement WP02 --base WP01`

## Subtasks & Detailed Guidance

### Subtask T007 - `audio_files` session-scoped fixture

- **Purpose**: Generate all 6 audio files once per test session.
- **Steps**:
  1. Use `tmp_path_factory.mktemp("audio")` for the output directory
  2. Call the WAV generation + ffmpeg conversion + tagging helpers from WP01
  3. Generate 6 files per the plan's track metadata table:

     | File | Format | Artist | Title | Genre | BPM | Rating | Crate |
     |------|--------|--------|-------|-------|-----|--------|-------|
     | track01.mp3 | mp3 | AlphaArtist | DarkPulse | Darkpsy | 148 | 5 | Festival |
     | track02.mp3 | mp3 | BetaArtist | NightVibe | Techno | 130 | 4 | Club |
     | track03.flac | flac | GammaArtist | ForestDawn | Psytrance | 145 | 5 | Festival |
     | track04.flac | flac | DeltaArtist | DeepSpace | Ambient | 80 | 3 | Chill |
     | track05.aiff | aiff | EpsilonArtist | RhythmStorm | DnB | 174 | 4 | Club |
     | track06.aiff | aiff | ZetaArtist | SilentWave | Ambient | 70 | 2 | Chill |

  4. Return a dict mapping filename to Path
- **Files**: `tests/integration/conftest.py`

### Subtask T008 - `origin_repo` session-scoped fixture

- **Purpose**: Create a git-annex repo with all 6 files and metadata.
- **Steps**:
  1. `tmp_path_factory.mktemp("origin")` for repo dir
  2. `git init`, `git config user.email/name`, `git annex init "origin"`
  3. Copy audio files into repo (e.g., under `tracks/` subdirectory)
  4. `git annex add tracks/`
  5. `git commit -m "Add tracks"`
  6. For each file, set git-annex metadata:
     ```bash
     git annex metadata tracks/<file> \
       -s artist=<val> -s title=<val> -s genre=<val> \
       -s bpm=<val> -s rating=<val> -s crate=<val>
     ```
  7. Return repo Path
- **Files**: `tests/integration/conftest.py`
- **Notes**: git-annex metadata is separate from audio file tags — both must be set

### Subtask T009 - `partial_clone` session-scoped fixture

- **Purpose**: Clone with only half the files present.
- **Steps**:
  1. `tmp_path_factory.mktemp("clone")` for clone dir
  2. `git clone <origin_path> <clone_path>`
  3. `git annex init "clone"` in the clone
  4. Sort files alphabetically, `git annex get` the first 3 (track01.mp3, track02.mp3, track03.flac)
  5. Return clone Path
- **Files**: `tests/integration/conftest.py`
- **Notes**: After clone, all files appear as broken symlinks. `git annex get` fetches content for selected files.

### Subtask T010 - `origin_cache_session` fixture

- **Purpose**: Provide a ready-to-query cache built from the origin repo.
- **Steps**:
  1. Create in-memory SQLAlchemy engine + session
  2. `CacheBase.metadata.create_all(engine)`
  3. `build_cache(origin_repo, session)`
  4. Yield session
  5. Session cleanup on teardown
- **Files**: `tests/integration/conftest.py`
- **Notes**: Can be session-scoped since cache is read-only during tests

### Subtask T011 - `clone_cache_session` fixture

- **Purpose**: Provide a ready-to-query cache built from the partial clone.
- **Steps**: Same as T010 but using `partial_clone` path.
- **Files**: `tests/integration/conftest.py`
- **Notes**: This is the primary fixture for testing `--include-missing` behavior

## Risks & Mitigations

- **git-annex clone remote setup**: May need `git annex enableremote` — test whether plain `git clone` + `git annex init` is sufficient
- **Metadata propagation to clone**: git-annex metadata lives on the `git-annex` branch which is shared via clone — verify metadata is accessible in clone
- **Session fixture teardown**: Use `yield` pattern to ensure session cleanup

## Review Guidance

- After fixture creation, manually verify:
  - `git annex find` in clone returns 3 files
  - `git annex find --include='*'` in clone returns 6 files
  - `git annex metadata` in clone shows metadata for all 6 files
- Verify cache sessions have correct `present` field values

## Activity Log

- 2026-01-29T17:54:16Z - system - lane=planned - Prompt created.
- 2026-01-29T18:45:41Z – unknown – shell_pid=311044 – lane=for_review – Moved to for_review
- 2026-01-29T20:31:03Z – claude-opus – shell_pid=323047 – lane=doing – Started review via workflow command
