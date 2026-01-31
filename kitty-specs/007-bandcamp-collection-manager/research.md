# Research: Bandcamp Collection Manager

**Feature**: 007-bandcamp-collection-manager
**Date**: 2026-01-31

## 1. Bandcamp Collection API

### Decision: Use `/api/fancollection/1/collection_items` endpoint for collection fetching

**Rationale**: This is the undocumented but well-established endpoint used by bandcampsync and other tools. It returns paginated purchase data including redownload URLs.

**Alternatives considered**:
- Official Bandcamp API (`bandcamp.com/developer`): OAuth-based, intended for labels/artists, not fan collection access. Not suitable.
- `bandcamp-api` library (RustyRin): Provides public page scraping for album/track info but does not handle authenticated collection access or downloads. Useful for supplementary metadata lookup but not for core collection functionality.
- Page scraping: More fragile than the JSON API endpoint.

**Technical details**:
- **Endpoint**: `POST https://bandcamp.com/api/fancollection/1/collection_items`
- **Payload**: `{"fan_id": <int>, "count": 100, "older_than_token": "<timestamp>:<page_ts>:a::"}`
- **Response**: JSON with `items` array (purchase records) and `redownload_urls` dict
- **Pagination**: Token-based; empty `items` array signals end
- **Authentication**: Session cookie (identity cookie) required in request headers

### Fan ID Discovery

- Load `https://bandcamp.com` with session cookie
- Extract `pageContext.identity.fanId` from the `#HomepageApp` div's `data-blob` attribute (JSON-encoded)

## 2. Download URL Resolution

### Decision: Two-step download process via redownload pages

**Rationale**: Bandcamp does not expose direct download URLs in the collection API. Download URLs must be resolved through the redownload page, which contains format-specific links.

**Flow**:
1. Collection API returns `redownload_urls` mapping `sale_item_type + sale_item_id` to a redownload page URL
2. GET the redownload page URL with session cookie
3. Extract `#pagedata` div's `data-blob` attribute → JSON with `digital_items` array
4. Each `digital_item` contains a `downloads` dict keyed by encoding format
5. Each encoding entry has a `url` field — this is the actual download URL

**Available formats** (from Bandcamp's encoding keys):
- `flac` — FLAC (lossless)
- `mp3-320` — MP3 320kbps CBR
- `mp3-v0` — MP3 V0 VBR
- `aac-hi` — AAC 256kbps
- `alac` — Apple Lossless
- `aiff-lossless` — AIFF
- `vorbis` — OGG Vorbis
- `wav` — WAV (lossless, uncompressed)

**Alternatives considered**:
- Streaming URLs (mp3-128 from trackinfo): Only provides 128kbps MP3 previews, not full-quality purchased content. This is what bandcamp-dl uses — insufficient for our needs.
- OAuth API download endpoints: Would require label/artist credentials, not fan credentials.

## 3. Authentication Strategy

### Decision: Three-method approach with credentials file storage

**Rationale**: Bandcamp has CAPTCHA on login forms preventing automated login. Session cookies are the only viable authentication mechanism for fans.

**Method 1: Browser cookie extraction (rookiepy)**
- `rookiepy` reads browser cookie databases directly (Firefox SQLite, Chrome encrypted)
- Extract the `identity` cookie from `bandcamp.com` domain
- Supports Firefox and Chrome on Linux

**Method 2: Manual config**
- User sets `session_cookie` in `[bandcamp]` section of `config.toml`
- Direct passthrough, no extraction logic needed

**Method 3: Mini-browser login**
- Use `webbrowser.open()` to launch default browser with a temporary profile URL
- After user logs in, the challenge is extracting the cookie from that session
- Implementation note: `webbrowser` stdlib opens the system browser but does NOT provide access to cookies. We need a different approach.
- Revised approach: Use a lightweight embedded approach — create a temporary Firefox profile directory, launch Firefox with that profile via `subprocess`, wait for the user to log in and close the browser, then read the cookies from the profile's `cookies.sqlite` database.
- Requires `DISPLAY` or `WAYLAND_DISPLAY` environment variable check; fail with error if headless.

**Cookie storage**: `~/.config/music-commander/bandcamp-credentials.json`
- Contains: `{"session_cookie": "...", "fan_id": <int>, "username": "...", "extracted_at": "ISO8601"}`
- Separate from config.toml (credentials vs configuration)

**Alternatives considered**:
- Keyring/secret service: Adds dependency complexity, not all Linux systems have a running keyring daemon.
- OAuth flow: Bandcamp's OAuth is for labels/artists, not fans.

## 4. Fuzzy Matching Strategy

### Decision: Use rapidfuzz with normalized token-based comparison

**Rationale**: `rapidfuzz` is a fast C++ implementation with flexible scoring. Token-based matching handles word reordering and extra punctuation well.

**Matching approach**:
- **Release-level match**: Compare normalized `(artist, album)` tuples
  - Score = weighted average of `fuzz.token_sort_ratio(local_artist, bc_artist)` (40%) + `fuzz.token_sort_ratio(local_album, bc_album)` (60%)
- **Track-level match**: Compare normalized `(artist, title)` tuples
  - Score = weighted average of `fuzz.token_sort_ratio(local_artist, bc_artist)` (40%) + `fuzz.token_sort_ratio(local_title, bc_title)` (60%)
- **Normalization**: lowercase, strip punctuation, collapse whitespace, remove common suffixes like "(Deluxe Edition)", "(Remastered)"

**Confidence tiers**:
- Exact: score >= 95
- High: score >= 80
- Low: score >= 60
- No match: score < 60

**Alternatives considered**:
- Levenshtein distance alone: Too sensitive to string length differences
- FTS5 MATCH: Good for keyword search but not for fuzzy similarity scoring
- Manual matching only: Poor UX for large collections

## 5. HTML Report with Link Refresh

### Decision: Local HTTP server for link refresh

**Rationale**: Bandcamp download URLs are time-limited (typically expire within hours). A static HTML page with direct links would become stale. A local server can refresh URLs on demand.

**Approach**:
- `bandcamp report` generates an HTML file with JavaScript that calls a local endpoint
- The command also starts a lightweight HTTP server (e.g., `http.server` based) on a random port
- When the user clicks a download link, JS calls the local server to resolve a fresh download URL
- The server uses the stored session cookie to fetch the current download URL from Bandcamp
- Server auto-shuts down after inactivity timeout or when the terminal is interrupted

**Report content**:
- Artist, album, format, purchase date
- Match status against local library (matched/unmatched)
- Filterable by match status, artist, format

**Alternatives considered**:
- Static links with manual regeneration: Poor UX, links expire quickly
- Embedded JS with CORS requests to Bandcamp: Blocked by CORS policy
- Pre-generating all download URLs at report time: URLs expire before user finishes downloading

## 6. Repair Workflow Integration

### Decision: Parse existing CheckReport JSON, match broken files, TUI selection

**Rationale**: Builds on the established `files check` output format. The check report already identifies broken files with paths and error details.

**Flow**:
1. Load CheckReport JSON (same format as `music_commander/utils/checkers.py`)
2. Filter to results with `status == "error"`
3. For each broken file, extract metadata from local cache (artist, album, title)
4. Run fuzzy matching against Bandcamp collection cache
5. Present results in Rich-based TUI with scrollable selection
6. Download confirmed replacements in requested format (or original format if no `--format`)
7. Place downloaded files alongside originals — user handles git-annex

**TUI implementation**: Use Rich's `Live` display with keyboard input for scrolling and toggling selection. Each row shows: file path, match confidence, Bandcamp release, proposed format.

**Alternatives considered**:
- Automatic replacement without confirmation: Too risky for music files
- Simple yes/no per file: Tedious for many files
- External TUI library (textual): Heavier dependency than needed

## 7. Error Handling for Scraping Fragility

### Decision: Fail-fast with diagnostic output

**Rationale**: Bandcamp's pages change without notice. When parsing fails, a clear error with the raw response helps users and developers diagnose whether the issue is a Bandcamp change or a network error.

**Approach**:
- Wrap all HTML/JSON extraction in try/except blocks
- On parse failure: log the raw response (truncated to 500 chars) alongside the error
- Raise a `BandcampParseError` (new exception class inheriting `MusicCommanderError`)
- Include the URL that was being fetched and the expected vs actual structure

## 8. New Dependencies Summary

| Package | Version | Purpose |
|---------|---------|---------|
| requests | >=2.28 | HTTP client for Bandcamp API |
| rapidfuzz | >=3.0 | Fuzzy string matching |
| rookiepy | >=0.3 | Browser cookie extraction |
| beautifulsoup4 | >=4.12 | HTML parsing for page data extraction |

Note: `beautifulsoup4` is needed for parsing Bandcamp HTML pages to extract `#pagedata` divs. The existing `lxml` or `html.parser` can serve as the BS4 backend.
