# Data Model: Anomalistic Portal Mirror

**Feature**: 009-anomalistic-portal-mirror
**Date**: 2026-02-03

## Entities

### AnomaListicRelease

Represents a release from the Dark Psy Portal. Stored in the cache database.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| post_id | integer | PK | WordPress post ID from the REST API |
| artist | text | NOT NULL | Parsed artist name (or "Various Artists") |
| album_title | text | NOT NULL | Parsed album title |
| release_url | text | NOT NULL, UNIQUE | Full URL to the portal release page |
| download_url_wav | text | nullable | Direct URL to WAV archive |
| download_url_mp3 | text | nullable | Direct URL to MP3 archive |
| genres | text | NOT NULL, default "" | Comma-separated genre names |
| labels | text | NOT NULL, default "" | Comma-separated label names |
| release_date | text | nullable | ISO date string from WordPress publish date |
| cover_art_url | text | nullable | URL to cover art image |
| credits | text | nullable | Mastering/artwork credits extracted from content |
| download_status | text | NOT NULL, default "pending" | One of: pending, downloaded, failed, skipped |
| output_path | text | nullable | Relative path to the downloaded/converted release folder |
| last_synced | text | NOT NULL | ISO timestamp of last sync |

**Indexes**:
- `ix_al_release_artist` on `artist`
- `ix_al_release_album_title` on `album_title`
- `ix_al_release_url` on `release_url` (unique)

### AnomaListicTrack

Represents an individual track within a release. Populated after archive extraction.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | integer | PK, autoincrement | Internal ID |
| release_id | integer | FK → anomalistic_releases.post_id, NOT NULL | Parent release |
| title | text | NOT NULL | Track title |
| track_number | integer | nullable | Track position in release |
| artist | text | nullable | Track-level artist (for compilations) |
| file_path | text | nullable | Relative path to converted file |
| duration_seconds | float | nullable | Track duration |

**Indexes**:
- `ix_al_track_release_id` on `release_id`

### PortalCategory (in-memory only)

Categories fetched from the WordPress API. Not persisted in the cache DB — fetched fresh each run and used for classification during processing.

| Field | Type | Description |
|-------|------|-------------|
| id | integer | WordPress category ID |
| name | text | Display name (e.g., "DarkPsy", "Anomalistic Records") |
| slug | text | URL slug |
| type | enum | One of: genre, label, ignored |
| count | integer | Number of releases in this category |

## Relationships

```
AnomaListicRelease 1 ──── * AnomaListicTrack
     (post_id)              (release_id → post_id)
```

## State Transitions

### AnomaListicRelease.download_status

```
pending → downloaded    (successful download + conversion)
pending → failed        (download error, extraction error, or conversion error)
pending → skipped       (duplicate detected via URL or fuzzy match)
failed → downloaded     (retry on next run with --force or after fixing issue)
failed → skipped        (duplicate detected on retry)
skipped → downloaded    (re-run with --force)
```

## Configuration Entity

New `[anomalistic]` section in `~/.config/music-commander/config.toml`:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| output_dir | path | `<music_repo>/Anomalistic/` | Base directory for downloaded releases |
| format | string | `"flac"` | Target audio format (must match an encoder preset name) |
| output_pattern | string | `"{{artist}} - {{album}}"` | Jinja2 folder pattern for release directories |
| download_source | string | `"wav"` | Preferred download source: `"wav"` or `"mp3"` |

## meta.json Schema (per release)

Written to disk alongside converted tracks. Not stored in DB.

```json
{
  "artist": "XianZai",
  "album": "Irrational Conjunction",
  "url": "https://darkpsyportal.anomalisticrecords.com/xianzai-irrational-conjunction/",
  "genres": ["DarkPsy", "Experimental"],
  "labels": ["Anomalistic Records"],
  "release_date": "2023-05-09",
  "cover_art_url": "https://darkpsyportal.anomalisticrecords.com/wp-content/uploads/2023/05/...",
  "credits": "Mastered at Optinervear Studio; Artwork by XianZai (Carl Abdo)",
  "download_source": "wav",
  "download_url": "https://www.anomalisticrecords.com/xianzai/XianZai%20-%20Irrational%20Conjunction%20-%20WAV.zip",
  "tracks": [
    {
      "number": 1,
      "title": "Track Title",
      "artist": null,
      "bpm": null
    }
  ],
  "mirrored_at": "2026-02-03T12:00:00Z"
}
```
