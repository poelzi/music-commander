# Feature Specification: Anomalistic Portal Mirror

**Feature Branch**: `009-anomalistic-portal-mirror`
**Created**: 2026-02-03
**Status**: Draft
**Input**: User description: "Create a download/mirror tool for darkpsyportal.anomalisticrecords.com"

## Clarifications

### Session 2026-02-03

- Q: How should the tool parse artist vs. album from the post title? → A: Split on em-dash/en-dash/hyphen; treat left side as artist, right side as album. Recognize `V/A` and `VA` prefixes as "Various Artists" indicator; when no dash is present, treat entire title as album with artist "Various Artists".
- Q: How should download links be extracted from each release? → A: Parse download URLs from the HTML content field returned by the WordPress REST API. No separate page fetch needed per release.
- Q: Should the tool apply rate limiting or concurrent download limits? → A: No rate limiting, but downloads are sequential (one at a time). No parallelism for archive downloads.

## User Scenarios & Testing

### User Story 1 - Mirror All Releases (Priority: P1)

A user runs `music-commander mirror anomalistic` and the tool fetches the full release catalog from the Dark Psy Portal via the WordPress REST API, downloads the WAV zip for each release, extracts tracks, converts them to the configured format (FLAC by default), writes them into the configured folder structure, and creates a `meta.json` per release with all scraped metadata. Already-downloaded releases are skipped.

**Why this priority**: This is the core feature — bulk downloading and converting the catalog. Everything else builds on this.

**Independent Test**: Run `mirror anomalistic` against the live portal. Verify releases are downloaded, extracted, converted, and organized into the correct folder structure with `meta.json` files.

**Acceptance Scenarios**:

1. **Given** a fresh run with no prior downloads, **When** the user runs `mirror anomalistic`, **Then** all releases from the portal are downloaded, extracted, converted to the configured format, and placed in the configured output directory following the folder pattern.
2. **Given** a previous successful run, **When** the user runs `mirror anomalistic` again, **Then** already-downloaded releases are skipped and only new releases are fetched.
3. **Given** the portal has 278 releases, **When** the sync completes, **Then** a summary is displayed showing how many releases were downloaded, skipped, and failed.

---

### User Story 2 - Configurable Output Format and Folder Structure (Priority: P1)

A user configures the `[anomalistic]` section in their config file to specify the preferred audio format (e.g., `flac`, `mp3`, `opus`) and a folder pattern (e.g., `{{genre}}/[{{label}}]/{{artist}} - {{album}}`). The tool uses these settings to determine where and how to store downloaded releases.

**Why this priority**: Without configuration, the tool cannot adapt to different collection organizations. This is inseparable from the download workflow.

**Independent Test**: Set different format and pattern values in config, run a download, and verify output matches the configured structure and format.

**Acceptance Scenarios**:

1. **Given** config sets `format = "flac"` and `output_pattern = "{{genre}}/{{artist}} - {{album}}"`, **When** a DarkPsy release by "XianZai" titled "Irrational Conjunction" is downloaded, **Then** tracks are stored as FLAC files under `DarkPsy/XianZai - Irrational Conjunction/`.
2. **Given** config sets `format = "opus"`, **When** a WAV release is downloaded, **Then** tracks are converted to Opus format using the existing encoder presets.
3. **Given** no `[anomalistic]` section in config, **When** the user runs the mirror, **Then** default values are used: FLAC format, single flat folder per release.
4. **Given** a pattern with `{{label}}` but the release has no label category, **When** the folder path is computed, **Then** the label portion and its surrounding brackets are omitted.

---

### User Story 3 - Genre and Label Classification (Priority: P1)

The tool fetches WordPress categories from the portal API, classifies each as either a genre (DarkPsy, Psycore, Hi-Tech, Experimental, Forest, etc.) or a label (Anomalistic Records, Scared Evil Records, etc.), and assigns genre and label metadata to each release based on its category tags. The primary genre (first genre in the category list) is used for folder placement. Labels are stored as metadata tags.

**Why this priority**: Genre classification drives the folder structure and is core to organization.

**Independent Test**: Download a release tagged with multiple categories. Verify the primary genre is used for folder placement and all labels appear in `meta.json`.

**Acceptance Scenarios**:

1. **Given** a release with categories [3, 21, 9, 8] (All Releases, Anomalistic Records, DarkPsy, Experimental), **When** processed, **Then** the primary genre is "DarkPsy", the secondary genre is "Experimental", the label is "Anomalistic Records", and category 3 (All Releases) is ignored.
2. **Given** a release with only category [3] (All Releases), **When** processed, **Then** genre defaults to "Unknown" and label defaults to empty.
3. **Given** the genres page lists categories like Squirrel, Swamp, ForestCore alongside major genres, **When** categories are classified, **Then** all known style categories are recognized as genres and all record label categories are recognized as labels.

---

### User Story 4 - Release Metadata Capture (Priority: P1)

For each downloaded release, the tool creates a `meta.json` file containing: artist, album title, release URL, tracklist (with BPMs if available), genres, labels, cover art URL, mastering credits, artwork credits, release date, download format, and any other metadata scraped from the release page.

**Why this priority**: Metadata preservation is essential for collection management and future matching.

**Independent Test**: Download a release, open its `meta.json`, and verify all available metadata fields are populated.

**Acceptance Scenarios**:

1. **Given** a release page with artist, title, tracklist, credits, and cover art, **When** the release is downloaded, **Then** `meta.json` contains all of these fields.
2. **Given** a compilation (V/A) release with multiple track artists, **When** the release is downloaded, **Then** `meta.json` includes per-track artist attribution.
3. **Given** the release URL is `https://darkpsyportal.anomalisticrecords.com/xianzai-irrational-conjunction/`, **When** the release is downloaded, **Then** `meta.json` contains the full URL and the converted audio files have the URL embedded as a comment tag.

---

### User Story 5 - Duplicate Detection and Skip (Priority: P2)

Before downloading, the tool checks whether a release already exists in the local collection by: (1) checking the cache DB for the release URL in the comment field, (2) fuzzy-matching artist and album title against existing cache tracks using the shared matching logic from the bandcamp matcher. If a match is found, the release is skipped with a message.

**Why this priority**: Prevents wasted bandwidth and disk space on re-downloads. Important for incremental use but the tool is functional without it (just re-downloads).

**Independent Test**: Download a release, then run the mirror again. Verify the release is skipped on the second run. Also manually place a matching release in the collection and verify it is detected as a duplicate.

**Acceptance Scenarios**:

1. **Given** a release was previously downloaded and its URL is in the cache, **When** the mirror runs, **Then** the release is skipped with a "already downloaded" message.
2. **Given** a release exists in the local collection (matched by artist + album title fuzzy match) but was obtained from a different source, **When** the mirror runs, **Then** the release is flagged as a potential duplicate and skipped.
3. **Given** `--force` is passed, **When** the mirror runs, **Then** duplicate detection is bypassed and all releases are re-downloaded.

---

### User Story 6 - RAR and ZIP Archive Extraction (Priority: P2)

Some releases are distributed as ZIP files and others as RAR files. The tool detects the archive format and extracts accordingly using standard zip handling and `unrar` (free implementation) for RAR files.

**Why this priority**: Both formats exist on the portal. Without RAR support, some releases cannot be mirrored.

**Independent Test**: Download a release distributed as a RAR archive. Verify it is extracted correctly and tracks are converted.

**Acceptance Scenarios**:

1. **Given** a release download is a ZIP file, **When** extracted, **Then** all audio files inside are found and converted.
2. **Given** a release download is a RAR file, **When** extracted, **Then** `unrar` is used to extract and all audio files are found and converted.
3. **Given** `unrar` is not installed, **When** a RAR file is encountered, **Then** an error message indicates that `unrar` is required and provides installation guidance.

---

### User Story 7 - Conversion with URL Comment Tagging (Priority: P2)

When converting downloaded WAV/MP3 files to the target format, the tool embeds the release URL as a comment tag in each output file. This uses the existing encoder/conversion infrastructure.

**Why this priority**: The URL comment enables future duplicate detection and provenance tracking. Reuses existing code.

**Independent Test**: Download and convert a release. Inspect the output files' comment tags and verify the release URL is present.

**Acceptance Scenarios**:

1. **Given** a WAV file from a release at `https://darkpsyportal.anomalisticrecords.com/some-release/`, **When** converted to FLAC, **Then** the FLAC file's COMMENT tag contains the release URL.
2. **Given** the target format is `mp3`, **When** converted, **Then** the MP3 file's comment tag contains the release URL.
3. **Given** the download is already in the target format (e.g., downloading MP3 when config says `mp3`), **When** processed, **Then** the comment tag is still added to the file.

---

### Edge Cases

- What happens when a release download link is dead (404)?
  - The release is skipped, an error is logged, and the summary reflects the failure.
- What happens when the portal is unreachable?
  - The tool exits with a clear error message indicating the portal cannot be reached.
- What happens when a release has no download links?
  - The release is skipped with a warning.
- What happens when a release has only MP3 downloads but the user wants FLAC?
  - The MP3 is downloaded and stored as-is (lossy-to-lossless conversion is not performed). A warning is displayed.
- What happens when the archive contains non-audio files (artwork, NFO, etc.)?
  - Non-audio files are ignored during conversion but artwork images are preserved in the release folder.
- What happens when the folder pattern produces a path that already exists?
  - The existing folder is reused; individual files are not overwritten unless `--force` is specified.
- What happens when a release has no genre categories?
  - The genre defaults to "Unknown" for folder placement.

## Requirements

### Functional Requirements

- **FR-001**: System MUST fetch the full release catalog from the Dark Psy Portal WordPress REST API (`wp-json/wp/v2/posts` and `wp-json/wp/v2/categories`).
- **FR-002**: System MUST classify WordPress categories into genres (music styles) and labels (record labels) using a known-genres list, treating "All Releases", "Uncategorized", and "P" as ignored categories.
- **FR-003**: System MUST download release archives (ZIP or RAR) from the portal's download links.
- **FR-004**: System MUST extract both ZIP and RAR archives. RAR extraction MUST use `unrar` (free implementation).
- **FR-005**: System MUST convert extracted audio files to the user-configured format using the existing encoder preset system.
- **FR-006**: System MUST embed the release page URL as a comment tag in every converted audio file.
- **FR-007**: System MUST create a `meta.json` file per release containing: artist, album title, release URL, tracklist, genres, labels, cover art URL, credits, release date, and download source format.
- **FR-008**: System MUST organize output files according to a user-configurable folder pattern supporting template variables: `{{genre}}`, `{{label}}`, `{{artist}}`, `{{album}}`, `{{year}}`.
- **FR-009**: System MUST check the cache database before downloading to detect previously-mirrored releases (by URL in comment field).
- **FR-010**: System MUST perform fuzzy artist+album matching against existing collection tracks to detect duplicates from other sources, reusing shared matching logic from the bandcamp matcher module.
- **FR-011**: System MUST store mirrored release and track metadata in dedicated `AnomaListicRelease` and `AnomaListicTrack` cache database tables.
- **FR-012**: System MUST support a `--force` flag to bypass duplicate detection and re-download all releases.
- **FR-013**: System MUST add an `[anomalistic]` configuration section with keys for: output directory, format, folder pattern, and download source preference (WAV or MP3).
- **FR-014**: System MUST register as a new top-level `mirror` command group with `anomalistic` as a subcommand.
- **FR-015**: System MUST handle pagination of the WordPress REST API to fetch all releases (not just the first page).
- **FR-016**: System MUST display progress during download and conversion.
- **FR-017**: System MUST add `unrar` as a system dependency.
- **FR-018**: System MUST select the primary genre (first genre category in the API response) for folder placement when a release has multiple genres.
- **FR-019**: System MUST parse artist and album title from WordPress post titles by splitting on em-dash, en-dash, or hyphen delimiters. The left side is the artist, the right side is the album. Titles prefixed with `V/A` or `VA` MUST be recognized as "Various Artists" compilations. Titles with no delimiter MUST default to artist "Various Artists" with the full title as album.
- **FR-020**: System MUST extract download URLs (ZIP/RAR archive links) from the rendered HTML content field of the WordPress REST API response, without fetching individual release pages.
- **FR-021**: System MUST download archives sequentially (one at a time) without parallelism or artificial rate limiting.

### Key Entities

- **AnomaListicRelease**: A release from the Dark Psy Portal. Key attributes: portal post ID, artist, album title, release URL, download URLs (WAV, MP3), genres (list), labels (list), release date, cover art URL, credits, download status, last synced timestamp.
- **AnomaListicTrack**: An individual track within a release. Key attributes: release reference, title, track number, artist (for compilations), file path, duration.
- **PortalCategory**: A WordPress category from the portal, classified as genre, label, or ignored. Key attributes: category ID, name, slug, type (genre/label/ignored), release count.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users can mirror the full Dark Psy Portal catalog (~278 releases) in a single command invocation.
- **SC-002**: Subsequent runs complete within seconds for an already-mirrored catalog (all releases skipped via cache check).
- **SC-003**: Every mirrored release has a complete `meta.json` with all available metadata fields populated.
- **SC-004**: Every converted audio file contains the source release URL in its comment tag.
- **SC-005**: Releases are organized according to the user's configured folder pattern with correct genre and label classification.
- **SC-006**: Both ZIP and RAR archives are extracted without user intervention.
- **SC-007**: Duplicate releases obtained from other sources (e.g., Bandcamp) are detected via fuzzy matching and skipped.
