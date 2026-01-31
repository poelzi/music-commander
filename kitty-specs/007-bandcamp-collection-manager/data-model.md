# Data Model: Bandcamp Collection Manager

**Feature**: 007-bandcamp-collection-manager
**Date**: 2026-01-31
**Storage**: Dedicated SQLite tables in `.music-commander-cache.db` via SQLAlchemy ORM

## Entities

### BandcampRelease

A purchased release (album or single) from the user's Bandcamp collection.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| sale_item_id | int | PK | Bandcamp's unique item identifier |
| sale_item_type | str | NOT NULL | "album" or "track" |
| band_name | str | NOT NULL | Artist/band name as listed on Bandcamp |
| album_title | str | NOT NULL | Release title |
| band_id | int | nullable | Bandcamp band/artist ID |
| redownload_url | str | nullable | URL to the redownload page |
| purchase_date | str | nullable | ISO 8601 timestamp of purchase |
| is_discography | bool | NOT NULL, default false | Part of a discography bundle |
| artwork_url | str | nullable | Cover art URL |
| bandcamp_url | str | nullable | Public release URL |
| last_synced | str | NOT NULL | ISO 8601 timestamp of last sync |

**Indexes**: `ix_bc_release_band_name` on `band_name`, `ix_bc_release_album_title` on `album_title`

### BandcampTrack

An individual track within a release.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | int | PK, autoincrement | Internal row ID |
| release_id | int | FK → BandcampRelease.sale_item_id, NOT NULL | Parent release |
| title | str | NOT NULL | Track title |
| track_number | int | nullable | Position in track listing |
| duration_seconds | float | nullable | Track duration |

**Indexes**: `ix_bc_track_release_id` on `release_id`, `ix_bc_track_title` on `title`

### BandcampReleaseFormat

Available download formats for a release.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | int | PK, autoincrement | Internal row ID |
| release_id | int | FK → BandcampRelease.sale_item_id, NOT NULL | Parent release |
| encoding | str | NOT NULL | Format key (e.g., "flac", "mp3-320", "aac-hi") |

**Unique constraint**: `(release_id, encoding)`

### BandcampSyncState

Singleton tracking sync freshness (mirrors CacheState pattern).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | int | PK, default 1 | Always 1 |
| fan_id | int | NOT NULL | Authenticated user's fan ID |
| username | str | nullable | Bandcamp username |
| last_synced | str | NOT NULL | ISO 8601 timestamp |
| total_items | int | NOT NULL | Number of releases in collection |
| last_token | str | nullable | Pagination token for incremental sync |

## Credentials File

**Path**: `~/.config/music-commander/bandcamp-credentials.json`

Not stored in SQLite — separate JSON file for security isolation.

```json
{
  "session_cookie": "identity=...",
  "fan_id": 12345678,
  "username": "user",
  "extracted_at": "2026-01-31T12:00:00Z",
  "source": "browser_firefox"
}
```

## Configuration Extension

**In `config.toml`** — `[bandcamp]` section:

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| session_cookie | str | null | Manual cookie override (takes precedence over credentials file) |
| default_format | str | "flac" | Preferred download format |
| match_threshold | int | 60 | Minimum fuzzy match score (0-100) |

## Relationships

```
BandcampRelease (1) ──< (N) BandcampTrack
BandcampRelease (1) ──< (N) BandcampReleaseFormat
BandcampSyncState (singleton) tracks overall sync status
```

## State Transitions

### BandcampRelease lifecycle
- **Created**: First sync discovers purchase in collection
- **Updated**: Subsequent sync detects changes (e.g., artist renamed, new formats available)
- **Stale**: Not seen in latest sync (could indicate Bandcamp removal — retain but flag)

### Sync flow
1. Check BandcampSyncState for last_token
2. If token exists: resume pagination from that point (incremental)
3. If no token: full sync from beginning
4. On completion: update BandcampSyncState with new timestamp and total

## Integration with Existing Models

The Bandcamp models live in the same database (`.music-commander-cache.db`) but use a separate `CacheBase` or share the existing one. They do NOT have foreign key relationships to `CacheTrack` — matching is performed at query time via fuzzy comparison, not via database joins.
