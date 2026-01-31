# Feature Specification: Bandcamp Collection Manager

**Feature Branch**: `007-bandcamp-collection-manager`
**Created**: 2026-01-31
**Status**: Draft
**Mission**: software-dev
**Input**: User description: "Add bandcamp subcommand for managing Bandcamp purchases, downloading releases, fuzzy-matching against local library, repairing broken files, and generating download report pages."

## Clarifications

### Session 2026-01-31

- Q: Where should the Bandcamp session cookie be stored persistently? → A: In a separate credentials file under `~/.config/music-commander/`.
- Q: How should the repair confirmation flow work when multiple broken files have Bandcamp matches? → A: TUI with scrollable list where the user can browse items and select/deselect individual files for replacement.
- Q: When the mini-browser login is requested but no GUI environment is available (e.g., SSH without X/Wayland), what should happen? → A: Fail with an error message suggesting the other two authentication methods (browser cookie extraction or manual config).
- Q: When repairing a broken file, should the replacement match the original format or respect `--format`? → A: Use `--format` if provided, otherwise default to the original file's format.
- Q: How should the system handle unexpected response formats from Bandcamp (page structure changes)? → A: Fail fast with a clear error message including the raw response snippet for debugging.

## User Scenarios & Testing

### User Story 1 - Authenticate with Bandcamp (Priority: P1)

A user wants to connect music-commander to their Bandcamp account so that subsequent commands can access their purchase collection. The user can authenticate via three methods: extracting cookies from an existing browser session (Firefox/Chrome), providing a session cookie manually in config.toml, or launching a minimal browser window with a dedicated profile to log in interactively. The extracted cookie is stored for reuse across sessions.

**Why this priority**: Authentication is a prerequisite for all other Bandcamp functionality. Without a valid session, no collection data or downloads are possible.

**Independent Test**: Can be tested by running the authentication subcommand, verifying the cookie is stored, and confirming it grants access to the user's Bandcamp collection page.

**Acceptance Scenarios**:

1. **Given** the user has Firefox installed with an active Bandcamp session, **When** they run `bandcamp auth --browser firefox`, **Then** the session cookie is extracted and stored, and the user sees a confirmation message with their Bandcamp username.
2. **Given** the user has set `bandcamp.session_cookie` in config.toml, **When** they run any bandcamp subcommand, **Then** the manually provided cookie is used for authentication.
3. **Given** the user has no existing browser session, **When** they run `bandcamp auth --login`, **Then** a minimal browser window opens with a dedicated profile, the user logs in, and the cookie is extracted from that profile upon completion.
4. **Given** the stored cookie has expired, **When** the user runs any bandcamp subcommand, **Then** they receive a clear error message indicating re-authentication is needed.
5. **Given** the user is in a headless environment (SSH without X/Wayland), **When** they run `bandcamp auth --login`, **Then** the command fails with a clear error suggesting browser cookie extraction or manual config as alternatives.

---

### User Story 2 - Sync Bandcamp Collection (Priority: P1)

A user wants to fetch their entire Bandcamp purchase collection (including discography bundles and multiple purchases) and cache it locally in a dedicated SQLite table. This enables offline querying and matching against the local music library.

**Why this priority**: The local collection cache is the foundation for matching, downloading, and repair workflows. All subsequent features depend on having collection data available.

**Independent Test**: Can be tested by running the sync command and verifying the dedicated Bandcamp table is populated with purchase data including artist, album, track listings, available formats, and purchase dates.

**Acceptance Scenarios**:

1. **Given** the user is authenticated, **When** they run `bandcamp sync`, **Then** all purchases (including discography bundles expanded into individual releases) are fetched and stored in the local Bandcamp cache table.
2. **Given** the user has previously synced, **When** they run `bandcamp sync` again, **Then** only new or changed purchases are updated (incremental sync).
3. **Given** the user has 500+ purchases, **When** they run `bandcamp sync`, **Then** progress is displayed and the operation completes without errors.
4. **Given** the authentication cookie is invalid, **When** they run `bandcamp sync`, **Then** a clear authentication error is shown.

---

### User Story 3 - Match Local Library Against Bandcamp Collection (Priority: P1)

A user wants to see which of their local music files correspond to Bandcamp purchases. The system performs fuzzy matching at both release level (artist + album) and track level (artist + title) to account for tag variations, typos, and formatting differences between local metadata and Bandcamp's catalog data.

**Why this priority**: Matching is the core intelligence of the feature — it connects local files to their Bandcamp source, enabling downloads and repairs.

**Independent Test**: Can be tested by running the match command against a synced collection and local cache, verifying that known matches are found despite minor tag differences.

**Acceptance Scenarios**:

1. **Given** the Bandcamp collection is synced and the local cache is populated, **When** the user runs `bandcamp match`, **Then** matches are displayed grouped by confidence level (exact, high, low).
2. **Given** a local album has artist "DJ Shadow" and album "Endtroducing" while Bandcamp lists "Endtroducing.....", **When** matching runs, **Then** the fuzzy match identifies them as the same release.
3. **Given** a local track has a slightly different title than the Bandcamp listing, **When** track-level matching runs, **Then** the match is found with an appropriate confidence score.
4. **Given** some local files have no Bandcamp match, **When** matching runs, **Then** unmatched files are clearly reported separately.

---

### User Story 4 - Download Releases from Bandcamp (Priority: P2)

A user wants to download one or more owned releases from Bandcamp in a specific audio format. The system retrieves the download URL for the requested format and saves the files locally.

**Why this priority**: Downloading is the primary action users take after identifying their collection. It depends on authentication and collection sync being functional.

**Independent Test**: Can be tested by requesting a download of a specific owned release in a given format and verifying the files are saved correctly.

**Acceptance Scenarios**:

1. **Given** the user owns a release on Bandcamp, **When** they run `bandcamp download <query> --format flac`, **Then** the release is downloaded in FLAC format to the current directory or a specified output path.
2. **Given** the user specifies a format not available for a release, **When** they attempt to download, **Then** available formats are listed and the user is prompted to choose.
3. **Given** a download is interrupted, **When** the user retries, **Then** the download resumes or restarts cleanly.
4. **Given** the user requests multiple releases (e.g., via a search query matching several items), **When** they confirm, **Then** all matching releases are downloaded with progress indication.

---

### User Story 5 - Generate Download Report Page (Priority: P2)

A user wants an HTML report page that lists their Bandcamp purchases with direct download links in their preferred format. The page handles Bandcamp's time-limited download URLs by refreshing them automatically when accessed.

**Why this priority**: The report page provides a convenient overview and acts as a bridge for manual or bulk download workflows outside the CLI.

**Independent Test**: Can be tested by generating the report and opening it in a browser, verifying that download links work and refresh when expired.

**Acceptance Scenarios**:

1. **Given** the Bandcamp collection is synced, **When** the user runs `bandcamp report --format flac`, **Then** an HTML file is generated listing all purchases with download links in FLAC format.
2. **Given** a download link has expired, **When** the user clicks it in the report, **Then** the link is automatically refreshed (via embedded mechanism such as JS calling a local endpoint) and the download starts.
3. **Given** the user wants only unmatched or specific releases in the report, **When** they apply filters (e.g., `--unmatched` or a search query), **Then** the report contains only the filtered subset.
4. **Given** the report is opened hours after generation, **When** download links are clicked, **Then** the refresh mechanism obtains valid URLs transparently.

---

### User Story 6 - Repair Broken Bandcamp Files (Priority: P2)

A user has run `files check` and has a JSON report identifying broken audio files. They want to cross-reference those broken files against their Bandcamp collection, see which ones can be re-downloaded, and replace the broken files after confirmation.

**Why this priority**: This is the culminating use case that ties together matching, downloading, and the existing `files check` infrastructure. It depends on all previous stories.

**Independent Test**: Can be tested by providing a check report with known-broken files that have Bandcamp matches, confirming the replacement proposals are correct, and verifying that confirmed replacements download and replace the files.

**Acceptance Scenarios**:

1. **Given** a `files check` JSON report with broken files, **When** the user runs `bandcamp repair --report <path>`, **Then** the system matches broken files against the Bandcamp collection and displays a table of proposed replacements with match confidence.
2. **Given** proposed replacements are displayed in a TUI with a scrollable list, **When** the user selects/deselects individual items and confirms, **Then** only the selected files are downloaded in the appropriate format and placed alongside the broken originals (the user handles git-annex integration).
3. **Given** a broken file has no Bandcamp match, **When** the repair command runs, **Then** the file is listed as "no match found" and skipped.
4. **Given** the user runs repair with `--dry-run`, **When** the command executes, **Then** only the match results and proposed actions are shown — no downloads occur.
5. **Given** the user wants a specific format for replacements, **When** they provide `--format flac`, **Then** all replacements are downloaded in that format.
6. **Given** the user does not provide `--format`, **When** the repair downloads a replacement, **Then** the format defaults to the original broken file's format (e.g., a broken .flac is replaced with FLAC).

---

### Edge Cases

- What happens when the Bandcamp collection contains duplicate purchases of the same release? The system should deduplicate and use the most recent purchase.
- How does the system handle Bandcamp releases that have been removed or made unavailable by the artist? The system should report these as unavailable and skip them.
- What happens when fuzzy matching produces multiple candidate matches for a single local file? The system should present all candidates ranked by confidence and let the user choose.
- How does the system handle very large discography bundles (50+ releases)? Each release within the bundle should be treated as a separate cache entry.
- What happens when the local file uses a different audio format than what Bandcamp offers? The match should still work (matching is metadata-based, not format-based); format is only relevant at download time.
- How does the system handle rate limiting from Bandcamp? The system should respect rate limits with appropriate backoff and inform the user if throttled.

## Requirements

### Functional Requirements

- **FR-001**: System MUST support three authentication methods: browser cookie extraction (Firefox/Chrome), manual cookie in config.toml (`[bandcamp]` section), and interactive login via a minimal browser with a dedicated profile. The mini-browser login MUST fail with a clear error suggesting the other two methods when no GUI environment is available.
- **FR-002**: System MUST store the session cookie in a separate credentials file under `~/.config/music-commander/`, persistently across sessions, and detect when it has expired.
- **FR-003**: System MUST fetch the user's complete Bandcamp purchase collection, including individual purchases and expanded discography bundles.
- **FR-004**: System MUST store Bandcamp collection data in a dedicated SQLite table (separate from the track metadata cache), including artist, album, track listings, available download formats, and purchase metadata.
- **FR-005**: System MUST support incremental collection sync to avoid re-fetching unchanged data.
- **FR-006**: System MUST perform fuzzy matching at both release level (artist + album) and track level (artist + title) between local library metadata and Bandcamp collection entries.
- **FR-007**: System MUST present match results with confidence levels to help users assess match quality.
- **FR-008**: System MUST allow downloading owned releases in a user-specified audio format. For repair operations, the system MUST use `--format` if provided, otherwise default to the original broken file's format.
- **FR-009**: System MUST support downloading multiple releases in a single operation with progress indication.
- **FR-010**: System MUST generate an HTML report page with direct download links for Bandcamp purchases in the desired format.
- **FR-011**: The HTML report MUST handle Bandcamp's time-limited download URLs by providing an automatic refresh mechanism when links are accessed after expiration.
- **FR-012**: System MUST accept a `files check` JSON report as input for the repair workflow.
- **FR-013**: System MUST match broken files from the check report against the Bandcamp collection using fuzzy matching and display proposed replacements with confidence scores.
- **FR-014**: System MUST present repair candidates in a TUI with a scrollable list where the user can browse and select/deselect individual files before confirming the replacement operation.
- **FR-015**: System MUST support `--dry-run` mode for the repair workflow showing proposed actions without executing downloads.
- **FR-016**: System MUST NOT automatically perform git-annex operations on replacement files — the user handles annex integration.
- **FR-017**: System MUST display progress feedback for long-running operations (sync, download, matching).
- **FR-018**: System MUST handle Bandcamp rate limiting gracefully with appropriate backoff behavior.
- **FR-019**: When Bandcamp responses have unexpected formats (e.g., page structure changes), the system MUST fail fast with a clear error message that includes the raw response snippet for debugging.

### Key Entities

- **BandcampSession**: Represents the authenticated connection to Bandcamp. Contains session cookie, username, and expiration state.
- **BandcampRelease**: A purchased release in the user's collection. Contains artist, album title, track listing, available formats, purchase date, and download URL template. May be part of a discography bundle.
- **BandcampTrack**: An individual track within a release. Contains title, track number, duration.
- **CollectionMatch**: The result of matching a local library entry against a Bandcamp release or track. Contains the local file reference, the Bandcamp entity reference, match type (release or track), and confidence score.
- **RepairCandidate**: A broken file from a check report paired with its best Bandcamp match. Contains the broken file path, proposed replacement source, match confidence, and target download format.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can authenticate with Bandcamp and sync their collection in a single CLI session.
- **SC-002**: Fuzzy matching correctly identifies at least 90% of local files that have corresponding Bandcamp purchases, despite minor metadata variations.
- **SC-003**: Users can download any owned release in their preferred format with a single command.
- **SC-004**: The HTML report page provides working download links that remain functional for at least 24 hours through the refresh mechanism.
- **SC-005**: The repair workflow correctly identifies replaceable broken files from a check report and completes confirmed replacements without manual URL handling.
- **SC-006**: All operations handle collections of 1000+ purchases without degradation in responsiveness.
