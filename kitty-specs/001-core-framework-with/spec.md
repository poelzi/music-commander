# Feature Specification: Core Framework with Mixxx DB and git-annex

**Feature Branch**: `001-core-framework-with`  
**Created**: 2026-01-06  
**Status**: Draft  
**Input**: User description: "Create core musicCommander framework with Mixxx database abstraction, config system, CLI subcommand architecture, and get-commit-files command"

## User Scenarios & Testing

### User Story 1 - Retrieve Music Files from Git Commits (Priority: P1)

A DJ wants to retrieve music files that were added or modified in specific git commits, so they can ensure those tracks are available locally before a gig.

**Why this priority**: This is the first concrete command that delivers immediate value - fetching annexed files based on git history is core to managing a large distributed music collection.

**Independent Test**: Can be fully tested by running `music-commander get-commit-files HEAD~3..HEAD` in a git-annex music repository and verifying the referenced files are fetched.

**Acceptance Scenarios**:

1. **Given** a git-annex music repository with some files not present locally, **When** user runs `music-commander get-commit-files HEAD~1`, **Then** all annexed files modified in that commit are fetched via `git annex get`
2. **Given** a commit range `HEAD~5..HEAD`, **When** user runs `music-commander get-commit-files HEAD~5..HEAD`, **Then** all annexed files across all commits in that range are fetched
3. **Given** a branch name `feature/new-tracks`, **When** user runs `music-commander get-commit-files feature/new-tracks`, **Then** all annexed files from commits unique to that branch (not on current branch) are fetched by computing the symmetric difference
4. **Given** a tag `v2025-summer-set`, **When** user runs `music-commander get-commit-files v2025-summer-set`, **Then** all annexed files from that tagged commit are fetched
5. **Given** some files fail to fetch (remote unavailable), **When** command completes, **Then** user sees a summary of successful and failed fetches with clear error messages

---

### User Story 2 - Configure Default Settings (Priority: P1)

A user wants to configure default paths and preferences once, so they don't have to specify them on every command.

**Why this priority**: Essential for usability - without configuration, every command would need explicit paths to databases and repositories.

**Independent Test**: Can be tested by creating a config file and verifying commands use those defaults.

**Acceptance Scenarios**:

1. **Given** no config file exists, **When** user runs any command, **Then** sensible defaults are used and a message suggests creating a config file
2. **Given** a config file at `~/.config/music-commander/config.toml`, **When** user runs a command, **Then** values from config are used as defaults
3. **Given** config specifies `mixxx_db = "/space/Music/Mixxx/mixxxdb.sqlite"`, **When** user runs a Mixxx-related command without `--db` flag, **Then** that path is used
4. **Given** config specifies `colored_output = false`, **When** user runs any command, **Then** output has no ANSI color codes
5. **Given** a command-line flag conflicts with config, **When** user runs command with explicit flag, **Then** command-line flag takes precedence

---

### User Story 3 - Query Mixxx Library (Priority: P2)

A user wants to query their Mixxx library to find tracks, playlists, and crates, so they can manage their collection programmatically.

**Why this priority**: The database abstraction layer enables all future Mixxx-related features. Without it, no Mixxx integration is possible.

**Independent Test**: Can be tested by running queries against the Mixxx database and verifying correct results.

**Acceptance Scenarios**:

1. **Given** a valid Mixxx database path, **When** application connects, **Then** connection succeeds and schema is validated
2. **Given** tracks exist in the library table, **When** querying tracks, **Then** all track metadata (artist, title, album, BPM, key, location) is accessible
3. **Given** playlists exist with associated tracks, **When** querying a playlist, **Then** all tracks in that playlist are returned in order
4. **Given** crates exist with associated tracks, **When** querying a crate, **Then** all tracks in that crate are returned
5. **Given** Mixxx is running and has the database open, **When** application performs read operations, **Then** reads succeed without blocking Mixxx
6. **Given** Mixxx is running, **When** application performs write operations, **Then** writes use proper locking and do not corrupt the database

---

### User Story 4 - Modify Mixxx Library Data (Priority: P3)

A user wants to update track metadata, manage playlists, and organize crates via the command line.

**Why this priority**: Write operations extend the read capability but are less immediately critical than querying.

**Independent Test**: Can be tested by modifying data and verifying changes persist correctly in the database.

**Acceptance Scenarios**:

1. **Given** a track exists in the library, **When** user updates its metadata (e.g., BPM, key, rating), **Then** changes are persisted and visible in Mixxx after refresh
2. **Given** a playlist exists, **When** user adds or removes tracks, **Then** playlist is updated correctly with proper ordering
3. **Given** a crate exists, **When** user adds or removes tracks, **Then** crate membership is updated correctly
4. **Given** a new playlist name, **When** user creates a playlist, **Then** playlist is created and available in Mixxx
5. **Given** concurrent Mixxx access, **When** writes occur, **Then** database integrity is maintained via proper transaction handling

---

### User Story 5 - Extensible Subcommand Architecture (Priority: P1)

A developer wants to add new subcommands by creating dedicated files, so the codebase remains organized and maintainable.

**Why this priority**: The architecture foundation enables all future commands. Without good structure, the project becomes unmaintainable.

**Independent Test**: Can be tested by adding a new command file and verifying it's automatically discovered and registered.

**Acceptance Scenarios**:

1. **Given** a new Python file in the commands directory with proper structure, **When** application starts, **Then** command is automatically discovered and available
2. **Given** any command, **When** user runs `music-commander <command> --help`, **Then** help text with usage, arguments, and options is displayed
3. **Given** no arguments, **When** user runs `music-commander`, **Then** list of available commands with descriptions is shown
4. **Given** `--help` flag, **When** user runs `music-commander --help`, **Then** global options and command list are displayed
5. **Given** colored output is enabled, **When** user runs any command, **Then** output uses colors for improved readability (errors in red, success in green, headers in bold)

---

### Edge Cases

- What happens when the Mixxx database file doesn't exist or is corrupted?
- How does the system handle git commits that reference files no longer in the repository?
- What happens when git-annex remotes are unreachable?
- How does the system behave when run outside a git-annex repository?
- What happens when config file has invalid TOML syntax?
- How are symlinked paths handled in track locations?

## Requirements

### Functional Requirements

#### Configuration System
- **FR-001**: System MUST read configuration from `~/.config/music-commander/config.toml` if it exists
- **FR-002**: System MUST support these configuration keys: `mixxx_db` (path), `music_repo` (path), `colored_output` (boolean), `default_remote` (string)
- **FR-003**: Command-line flags MUST override configuration file values
- **FR-004**: System MUST provide sensible defaults when no config exists
- **FR-005**: System MUST validate configuration values on startup and report clear errors for invalid entries

#### Mixxx Database Abstraction
- **FR-006**: System MUST connect to Mixxx SQLite database using SQLAlchemy ORM
- **FR-007**: System MUST provide ORM models for: `library` (tracks), `track_locations`, `Playlists`, `PlaylistTracks`, `crates`, `crate_tracks`, `cues`
- **FR-008**: System MUST support read operations: query tracks, list playlists, list crates, get playlist/crate contents
- **FR-009**: System MUST support write operations: update track metadata, create/modify playlists, manage crate membership
- **FR-010**: System MUST handle concurrent access with Mixxx using appropriate SQLite locking (WAL mode awareness)
- **FR-011**: System MUST validate database schema compatibility on connection

#### CLI Framework
- **FR-012**: System MUST use a subcommand-based CLI structure
- **FR-013**: Each subcommand MUST be implemented in a dedicated Python file for maintainability
- **FR-014**: System MUST auto-discover commands from the commands directory
- **FR-015**: System MUST provide colored terminal output (with ability to disable)
- **FR-016**: System MUST output errors to stderr with actionable messages
- **FR-017**: All commands MUST support `--help` with clear descriptions

#### get-commit-files Command
- **FR-018**: Command MUST accept a git revision specification (commit hash, range, branch, or tag)
- **FR-019**: Command MUST identify all files added, removed, or changed in the specified revision(s)
- **FR-019a**: For single commits: files changed in that commit
- **FR-019b**: For ranges (A..B): files changed across all commits in range
- **FR-019c**: For branch names: files from commits unique to that branch (not reachable from current HEAD)
- **FR-020**: Command MUST filter to only annexed files (skip regular git files)
- **FR-021**: Command MUST execute `git annex get` for identified files
- **FR-022**: Command MUST report progress during fetch operations
- **FR-023**: Command MUST summarize results: files fetched, already present, failed
- **FR-024**: Command MUST support `--dry-run` to show what would be fetched without fetching
- **FR-025**: Command MUST continue fetching remaining files after individual failures (no fail-fast)
- **FR-026**: Command MUST exit with non-zero code if any files failed to fetch

### Key Entities

- **Track**: Represents a music file with metadata (artist, title, album, BPM, key, duration, rating, file location)
- **TrackLocation**: Physical file path information for a track
- **Playlist**: Ordered collection of tracks with name and timestamps
- **Crate**: Unordered collection of tracks (like folders/tags)
- **Cue**: Marker point within a track (hot cues, loop points)
- **Configuration**: User preferences and default paths

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can fetch annexed files for any valid git revision in under 5 seconds (excluding actual file transfer time)
- **SC-002**: Configuration changes take effect immediately without application restart
- **SC-003**: Database queries for libraries with 10,000+ tracks complete in under 2 seconds
- **SC-004**: Adding a new subcommand requires creating only one file with no modifications to existing code
- **SC-005**: All commands provide helpful error messages that guide users to resolution
- **SC-006**: System handles concurrent Mixxx access without database corruption or blocking Mixxx operations
- **SC-007**: Test coverage for core modules exceeds 80%

## Clarifications

### Session 2026-01-06

- Q: For branch names, what should the comparison base be? → A: Get all files from commits unique to that branch (not reachable from current HEAD)
- Q: How should the command handle git-annex remote failures? → A: Continue fetching all possible files, then exit with error code if any failed

## Assumptions

- User has git-annex installed and configured on their system
- Mixxx database schema follows the documented structure (validated against Mixxx 2.3+)
- Music repository is a valid git-annex repository
- User has appropriate filesystem permissions for config directory and music files
- TOML is an acceptable configuration format (simple, human-readable)
- SQLAlchemy is an appropriate ORM choice for this use case
