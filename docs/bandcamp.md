# Bandcamp Workflow

music-commander integrates with Bandcamp to manage your purchase collection: authenticate, sync purchases, match against local files, download in preferred formats, and generate reports.

## Overview

The typical workflow is:

1. **Authenticate** -- Extract Bandcamp session cookies from your browser
2. **Sync** -- Fetch your purchase collection from the Bandcamp API
3. **Match** -- Fuzzy-match purchases to files already in your library
4. **Tag** -- Write match metadata to git-annex
5. **Download** -- Fetch unmatched releases in your preferred format
6. **Report** -- Generate an HTML overview of your collection

## Step 1: Authenticate

music-commander needs your Bandcamp session cookie. It extracts this from your browser automatically:

```bash
# Auto-detect browser (tries Firefox, then Chrome)
music-commander bandcamp auth

# Specify browser
music-commander bandcamp auth --browser firefox

# Open browser for login first, then extract
music-commander bandcamp auth --login

# Check current auth status
music-commander bandcamp auth --status
```

Cookie extraction uses [rookiepy](https://github.com/nicr3d/rookiepy) to read browser cookies without needing to export them manually.

### Privacy Note

- music-commander only reads the Bandcamp `identity` cookie from your browser's cookie store
- The cookie is used solely for authenticated API requests to `bandcamp.com`
- Cookies are not stored on disk by default; they are extracted fresh on each `auth` invocation
- You can manually set a cookie in your config file if you prefer: `[bandcamp] session_cookie = "..."`

## Step 2: Sync Collection

Fetch your purchase history from Bandcamp's API:

```bash
# Incremental sync (only new purchases)
music-commander bandcamp sync

# Full re-sync
music-commander bandcamp sync --full
```

This populates the local cache database with release metadata: artist, album, track listings, sale type, and redownload URLs.

## Step 3: Match Releases

Match Bandcamp purchases to files in your git-annex repository:

```bash
# Run matching
music-commander bandcamp match

# Show only unmatched releases
music-commander bandcamp match --missing

# Adjust match confidence threshold (default: 60)
music-commander bandcamp match --threshold 70
```

### Matching Algorithm

Matching runs in 4 phases, from most to least precise:

1. **Phase 0 -- Metadata URL**: Checks if any track's git-annex metadata contains the exact Bandcamp URL
2. **Phase 0.5 -- Comment subdomain**: Checks if the Bandcamp subdomain appears in track comment fields
3. **Phase 1 -- Folder path**: Matches the Bandcamp artist/album against local folder names using fuzzy string matching (rapidfuzz)
4. **Phase 2 -- Global**: Matches individual tracks against all unmatched files globally using fuzzy matching

Each phase claims matched files so they are not re-matched in later phases.

### Writing Match Results

To persist match results as git-annex metadata:

```bash
music-commander bandcamp match --tag
music-commander bandcamp match --tag --dry-run  # Preview first
```

This writes `bandcamp_sale_id` and `bandcamp_url` fields to matched files.

## Step 4: Download

Download releases that are not yet in your library:

```bash
# Download all unmatched
music-commander bandcamp download

# Filter by query
music-commander bandcamp download "artist name"

# Choose format (default: flac)
music-commander bandcamp download --format mp3-320

# Custom output directory
music-commander bandcamp download --output ./bandcamp-downloads/
```

### Supported Formats

| Format key | Description |
|-----------|-------------|
| `flac` | FLAC (lossless) |
| `mp3-320` | MP3 320kbps CBR |
| `mp3-v0` | MP3 V0 VBR |
| `aac-hi` | AAC high quality |
| `vorbis` | Ogg Vorbis |
| `alac` | Apple Lossless |
| `wav` | WAV (uncompressed) |
| `aiff-lossless` | AIFF (uncompressed) |

Downloads use the authenticated client session with adaptive rate limiting (AIMD algorithm) to avoid hitting Bandcamp's rate limits.

## Step 5: Repair Broken Files

If `files check` found corrupt files that came from Bandcamp, you can re-download them:

```bash
# First, run integrity check and save report
music-commander files check --output report.json

# Then repair using Bandcamp
music-commander bandcamp repair --report report.json
music-commander bandcamp repair --report report.json --dry-run  # Preview
```

## Step 6: Generate Report

Create an HTML report of your Bandcamp collection:

```bash
# Full report with local download server
music-commander bandcamp report

# Static HTML only (no server)
music-commander bandcamp report --no-server

# Only unmatched releases
music-commander bandcamp report --unmatched

# Filter by query
music-commander bandcamp report "genre:darkpsy"
```

When run with a server (default), the report includes direct download links that resolve through a local HTTP server. The server auto-shuts down after 30 minutes of inactivity.

## Rate Limiting

The Bandcamp client uses an Adaptive Increase / Multiplicative Decrease (AIMD) rate limiter:

- Starts with 0.1s between requests
- On success: decreases interval by 0.1s (floor: 0.05s)
- On rate limit (HTTP 429/503): multiplies interval by 1.2x (ceiling: 30s)
- Respects `Retry-After` headers
- Retries up to 5 times with exponential backoff
