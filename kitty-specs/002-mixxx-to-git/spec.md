# Feature Specification: Mixxx to Git-Annex Metadata Sync

**Feature Branch**: `002-mixxx-to-git`  
**Created**: 2026-01-07  
**Status**: Draft  
**Input**: Sync Mixxx library metadata to git-annex metadata on music files

## User Scenarios & Testing

### User Story 1 - Sync Changed Tracks (Priority: P1)

As a DJ with a large music collection in git-annex, I want to sync metadata from Mixxx to my annexed files so that the metadata travels with the files when I clone/sync the repository to other machines.

**Why this priority**: This is the core functionality - syncing metadata for tracks that have been modified in Mixxx since the last sync. Most common use case for day-to-day workflow.

**Independent Test**: Run sync command after rating a few tracks in Mixxx, verify git-annex metadata is updated for only those tracks.

**Acceptance Scenarios**:

1. **Given** I have rated 5 tracks in Mixxx since last sync, **When** I run `music-commander sync-metadata`, **Then** only those 5 tracks have their git-annex metadata updated
2. **Given** I have never run a sync before, **When** I run `music-commander sync-metadata`, **Then** all tracks with Mixxx metadata are synced
3. **Given** no tracks have changed in Mixxx since last sync, **When** I run `music-commander sync-metadata`, **Then** the command reports "No changes to sync" and exits cleanly

---

### User Story 2 - Full Resync (Priority: P2)

As a user who wants to ensure all metadata is synchronized, I want to force a full resync of all tracks regardless of change status.

**Why this priority**: Important for initial setup, recovery scenarios, or when change tracking state is uncertain.

**Independent Test**: Run sync with `--all` flag and verify all tracks in Mixxx library have metadata applied.

**Acceptance Scenarios**:

1. **Given** I have 1000 tracks in my Mixxx library, **When** I run `music-commander sync-metadata --all`, **Then** all 1000 tracks have their git-annex metadata updated
2. **Given** some tracks already have git-annex metadata, **When** I run `sync-metadata --all`, **Then** existing metadata is overwritten with current Mixxx values

---

### User Story 3 - Sync Specific Files (Priority: P2)

As a user, I want to sync metadata for specific files or paths so I can update just a subset of my collection.

**Why this priority**: Useful for targeted updates, testing, or when working with specific albums/artists.

**Independent Test**: Run sync with file path arguments and verify only specified files are updated.

**Acceptance Scenarios**:

1. **Given** I specify a directory path, **When** I run `music-commander sync-metadata ./darkpsy/`, **Then** only files under that directory are synced
2. **Given** I specify individual files, **When** I run `music-commander sync-metadata track1.flac track2.flac`, **Then** only those files are synced

---

### User Story 4 - Dry Run Preview (Priority: P2)

As a user, I want to preview what would be synced without making changes so I can verify the sync scope before committing.

**Why this priority**: Safety feature to prevent unintended bulk changes.

**Independent Test**: Run sync with `--dry-run` and verify no git-annex metadata is modified.

**Acceptance Scenarios**:

1. **Given** tracks have changed in Mixxx, **When** I run `music-commander sync-metadata --dry-run`, **Then** I see a list of files that would be updated without any actual changes
2. **Given** I run dry-run, **When** I check git-annex metadata afterward, **Then** no metadata has been modified

---

### User Story 5 - Batched Commits (Priority: P1)

As a user with a large library, I want metadata changes to be batched efficiently so that my git history doesn't become bloated with thousands of individual commits.

**Why this priority**: Critical for repository health and performance. Without batching, syncing 10,000 tracks could create 10,000+ commits.

**Independent Test**: Sync 100 tracks and verify they result in a single or small number of commits.

**Acceptance Scenarios**:

1. **Given** I sync 500 tracks, **When** the sync completes, **Then** the changes are committed in a single batch (or configurable batch size)
2. **Given** I want to control batch size, **When** I run `sync-metadata --batch-size 100`, **Then** commits are created for every 100 files processed

---

### User Story 6 - Crate Sync as Tags (Priority: P3)

As a DJ who organizes tracks into crates, I want my Mixxx crates to be synced as git-annex metadata tags so I can query files by crate across machines.

**Why this priority**: Nice-to-have organizational feature, but core metadata (rating, BPM, etc.) is more critical.

**Independent Test**: Add track to a crate in Mixxx, sync, verify git-annex metadata includes crate name as tag.

**Acceptance Scenarios**:

1. **Given** a track is in crates "DarkPsy" and "Festival", **When** I sync metadata, **Then** git-annex metadata includes `crate=DarkPsy crate=Festival`
2. **Given** a track is removed from a crate in Mixxx, **When** I sync, **Then** that crate tag is removed from git-annex metadata

---

### Edge Cases

- What happens when a file exists in Mixxx but not in git-annex repository? → Skip with warning
- What happens when a file is in git-annex but not in Mixxx database? → Not touched (only sync from Mixxx)
- How does system handle special characters in crate names? → Sanitize for git-annex compatibility
- What happens if git-annex metadata command fails for a file? → Log error, continue with remaining files, report summary at end
- What happens with very long metadata values? → Truncate if necessary with warning
- How is "last sync time" tracked? → Store timestamp in git-annex branch metadata (shared across clones)

## Requirements

### Functional Requirements

- **FR-001**: System MUST provide a `sync-metadata` CLI command
- **FR-002**: System MUST read track metadata from Mixxx SQLite database (rating, BPM, color, key, artist, title, album, comment, genre, year, track number)
- **FR-003**: System MUST read crate membership for each track from Mixxx database
- **FR-004**: System MUST write metadata to git-annex using `git annex metadata` command
- **FR-005**: System MUST track last sync timestamp in git-annex branch metadata to identify changed tracks (state shared across clones)
- **FR-006**: System MUST support `--all` flag to force full resync regardless of change status
- **FR-007**: System MUST support `--dry-run` flag to preview changes without applying them
- **FR-008**: System MUST support specifying file paths as positional arguments to limit sync scope
- **FR-009**: System MUST batch metadata updates to minimize git commits
- **FR-010**: System MUST support `--batch-size` option to control commit batching
- **FR-011**: System MUST map Mixxx database fields to git-annex metadata fields
- **FR-012**: System MUST handle tracks that exist in Mixxx but not in repository (skip with warning)
- **FR-013**: System MUST overwrite existing git-annex metadata with Mixxx values (no conflict prompts)
- **FR-014**: System MUST report summary of synced/skipped/failed files at completion
- **FR-015**: System MUST be designed to support future bidirectional sync (git-annex → Mixxx)
- **FR-016**: System MUST match Mixxx paths to repository files by stripping a configurable prefix (music_repo) and comparing relative paths

### Metadata Field Mapping

- **Mixxx `rating`** → git-annex `rating` (1-5 scale)
- **Mixxx `bpm`** → git-annex `bpm` (decimal)
- **Mixxx `color`** → git-annex `color` (hex or name)
- **Mixxx `key`** → git-annex `key` (musical key notation)
- **Mixxx `artist`** → git-annex `artist`
- **Mixxx `title`** → git-annex `title`
- **Mixxx `album`** → git-annex `album`
- **Mixxx `genre`** → git-annex `genre`
- **Mixxx `year`** → git-annex `year`
- **Mixxx `tracknumber`** → git-annex `tracknumber`
- **Mixxx `comment`** → git-annex `comment`
- **Mixxx crate membership** → git-annex `crate` (multi-value field)

### Key Entities

- **Track**: A music file managed by both Mixxx and git-annex, identified by file path
- **Mixxx Library Entry**: Database record containing track metadata and library statistics
- **Crate**: A user-defined collection of tracks in Mixxx (many-to-many relationship)
- **Sync State**: Persisted record of last sync timestamp and potentially per-file sync status
- **Git-Annex Metadata**: Key-value pairs attached to annexed files

## Clarifications

### Session 2026-01-07

- Q: Where should sync state (last sync timestamp) be stored? → A: Git-annex branch metadata (shared across clones)
- Q: How should Mixxx absolute paths be matched to repository files? → A: Strip configurable prefix and match relative paths

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can sync metadata for 1000 tracks in under 60 seconds
- **SC-002**: Syncing 10,000 tracks produces no more than 10 git commits (default batching)
- **SC-003**: Users can verify sync results with `--dry-run` before committing changes
- **SC-004**: Changed track detection correctly identifies 95%+ of modified tracks
- **SC-005**: Metadata is queryable via standard git-annex commands (e.g., `git annex find --metadata rating=5`)
- **SC-006**: System provides clear progress indication during sync operations
- **SC-007**: Failed file syncs do not abort the entire operation; summary reports success/failure counts
