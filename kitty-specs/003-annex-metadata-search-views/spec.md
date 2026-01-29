# Feature Specification: Annex Metadata Search & Symlink Views

**Feature Branch**: `003-annex-metadata-search-views`
**Created**: 2026-01-29
**Status**: Draft
**Input**: User description: "Add search capabilities similar to the Mixxx tracks DB, but based on git-annex metadata and filename. Add capabilities to export git-annex views based on filtering by this search, creating a symlink folder tree organized by a Jinja2 path template."

## User Scenarios & Testing

### User Story 1 - Search Tracks by Metadata (Priority: P1)

A DJ wants to find tracks in their git-annex music repository by searching metadata fields (artist, genre, BPM, rating, key, etc.) using Mixxx-compatible search syntax. The search runs against git-annex metadata, so it works on any clone of the repository without needing Mixxx installed.

**Why this priority**: Search is the foundational capability. Without it, view export has nothing to filter on.

**Independent Test**: Run a search query from the CLI and verify matching tracks are listed.

**Acceptance Scenarios**:

1. **Given** a git-annex repo with synced metadata, **When** the user runs `music-cmd search "artist:Basinski"`, **Then** all tracks with artist containing "Basinski" are listed.
2. **Given** tracks with various BPM values, **When** the user runs `music-cmd search "bpm:>140 genre:psytrance"`, **Then** only psytrance tracks above 140 BPM are returned.
3. **Given** tracks with ratings, **When** the user runs `music-cmd search "rating:>=4 -genre:ambient"`, **Then** 4+ star tracks are listed, excluding ambient genre.
4. **Given** a repo with metadata, **When** the user runs `music-cmd search "dark psy"`, **Then** tracks matching "dark" AND "psy" across artist/title/album/genre/filename are returned.

---

### User Story 2 - Create Symlink View from Search (Priority: P1)

A DJ wants to create a directory of symlinks organized by a custom folder/filename pattern, filtered by a search query. This allows browsing a curated subset of the library in file managers, media players, or DJ software that reads folder structures.

**Why this priority**: This is the primary deliverable — the symlink view is the main output the user wants.

**Independent Test**: Run a view command and verify symlinks are created in the correct directory structure, pointing to the actual files.

**Acceptance Scenarios**:

1. **Given** a search query and Jinja2 path template, **When** the user runs `music-cmd view "rating:>=4" --pattern "{{ genre }}/{{ artist }} - {{ title }}"  --output ./my-view`, **Then** a symlink tree is created under `./my-view` with genre subdirectories containing symlinks named `artist - title` pointing to the original annexed files.
2. **Given** a pattern with numeric transforms, **When** the user uses `--pattern "{{ bpm | round_to(10) }}/{{ bpm }} - {{ artist }} - {{ title }}"`, **Then** BPM values are rounded to the nearest 10 for directory grouping (e.g., `140/142.50 - Artist - Track.flac`).
3. **Given** a track with missing metadata (e.g., no genre), **When** the view is generated, **Then** the missing field renders as "Unknown" in the path.
4. **Given** an output directory that already has a previous view, **When** the view command runs again, **Then** the old symlinks are cleaned up and replaced with the new view.

---

### User Story 3 - Search with OR and Negation (Priority: P2)

A DJ wants to combine search criteria using OR logic and negation, matching the Mixxx 2.5 search syntax they are familiar with.

**Why this priority**: Extends search expressiveness. Core AND search is P1; OR and advanced operators are secondary.

**Independent Test**: Run queries using OR, negation, and range operators and verify correct results.

**Acceptance Scenarios**:

1. **Given** tracks in various genres, **When** the user searches `"genre:house | genre:techno"`, **Then** tracks matching either genre are returned.
2. **Given** tracks with various BPM, **When** the user searches `"bpm:140-160"`, **Then** tracks within the inclusive BPM range are returned.
3. **Given** a search with negation, **When** the user searches `"genre:psy -genre:progressive"`, **Then** psy tracks are returned, excluding those also tagged progressive.
4. **Given** a search for empty fields, **When** the user searches `'genre:""'`, **Then** tracks without a genre are returned.

---

### User Story 4 - Search Output Formats (Priority: P3)

A DJ wants search results displayed in different formats: a Rich table for terminal browsing, or a plain list of file paths for piping to other tools.

**Why this priority**: Nice-to-have output flexibility. The default table format is sufficient for MVP.

**Independent Test**: Run search with different output format flags and verify output.

**Acceptance Scenarios**:

1. **Given** a search query, **When** run without flags, **Then** results are displayed in a Rich table with columns for relevant metadata fields.
2. **Given** a search query, **When** run with `--format paths`, **Then** only relative file paths are printed, one per line.
3. **Given** a search query, **When** run with `--format json`, **Then** results are output as a JSON array of objects with all metadata fields.

---

### Edge Cases

- What happens when a Jinja2 template references a metadata field that doesn't exist for any track? Renders as "Unknown".
- What happens when two tracks produce the same symlink path from the template? A numeric suffix is appended (e.g., `track.flac`, `track_1.flac`).
- What happens when the output directory is inside the git-annex repo? It should work but warn the user that the symlinks may interfere with git operations. Recommend using a path outside the repo or adding it to `.gitignore`.
- What happens when the query matches zero tracks? Display a message "No tracks match the query" and create no symlinks.
- What happens with special characters in metadata values used in paths? Sanitize to filesystem-safe characters (replace `/`, `\0` etc.).
- How are file extensions handled in the pattern? The original file extension is always preserved and appended to the final path segment.

## Requirements

### Functional Requirements

#### Search

- **FR-001**: System MUST support Mixxx-compatible search syntax for querying git-annex metadata.
- **FR-002**: System MUST support text field filtering with partial match: `artist:value`, `genre:value`, `title:value`, `album:value`, `comment:value`, `crate:value`, `location:value`.
- **FR-003**: System MUST support exact text match with `=` operator: `artist:="Exact Name"`.
- **FR-004**: System MUST support numeric field filtering with comparison operators (`>`, `<`, `>=`, `<=`): `bpm:>140`, `rating:>=4`, `year:<2010`.
- **FR-005**: System MUST support numeric range syntax: `bpm:140-160`, `rating:3-5`.
- **FR-006**: System MUST support negation with `-` prefix: `-genre:ambient`.
- **FR-007**: System MUST support OR logic with `|` or `OR` (case-sensitive): `genre:house | genre:techno`.
- **FR-008**: System MUST support bare-word full-text search across artist, title, album, genre, and filename: `"dark psy"` matches any track with both words in any of those fields.
- **FR-009**: System MUST support searching for empty metadata fields: `genre:""`.
- **FR-010**: System MUST support quoted multi-word arguments: `artist:"Com Truise"`.
- **FR-011**: System MUST read metadata from git-annex (not the Mixxx SQLite database), so it works on any clone.

#### View Export

- **FR-012**: System MUST create a symlink directory tree based on a Jinja2 path template applied to search results.
- **FR-013**: System MUST support Jinja2 variable substitution for all git-annex metadata fields: `{{ artist }}`, `{{ title }}`, `{{ album }}`, `{{ genre }}`, `{{ bpm }}`, `{{ rating }}`, `{{ key }}`, `{{ year }}`, `{{ tracknumber }}`, `{{ comment }}`, `{{ crate }}`.
- **FR-014**: System MUST support Jinja2 filters, including built-in filters (`round`, `lower`, `upper`, `default`, `truncate`, etc.) and custom filters (`round_to(n)` for rounding to nearest N).
- **FR-015**: System MUST create intermediate directories as needed from the template path.
- **FR-016**: System MUST preserve the original file extension on the final symlink.
- **FR-017**: System MUST handle duplicate symlink paths by appending a numeric suffix.
- **FR-018**: System MUST clean up an existing view directory before regenerating (remove old symlinks and empty directories).
- **FR-019**: System MUST render missing metadata values as "Unknown" by default (configurable via Jinja2 `default` filter).
- **FR-020**: System MUST sanitize rendered path segments to be filesystem-safe.
- **FR-021**: System MUST accept a user-specified output directory for the symlink tree.

### Key Entities

- **SearchQuery**: A parsed representation of the user's search string, containing text terms, field filters (with operator and value), negations, and OR groups.
- **ViewTemplate**: A Jinja2 template string that maps track metadata to a filesystem path structure.
- **TrackResult**: A track's metadata as read from git-annex, including all synced fields plus the file's relative path.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can search their git-annex music library by metadata fields and see results within seconds for repositories up to 100,000 tracks.
- **SC-002**: Users can create a symlink view of filtered tracks organized by a custom pattern in a single command.
- **SC-003**: All Mixxx 2.5 search operators (text, numeric comparison, range, negation, OR, exact match, empty field) are supported and produce correct results.
- **SC-004**: Generated symlink trees correctly point to the original annexed files and are browsable in file managers.
- **SC-005**: The search and view commands work on any git-annex clone without requiring Mixxx to be installed.
