# Data Model: Core Framework with Mixxx DB and git-annex

**Date**: 2026-01-06
**Feature Branch**: `001-core-framework-with`

## Entity Relationship Overview

```
┌─────────────────┐       ┌──────────────────┐
│  TrackLocation  │──1:1──│      Track       │
└─────────────────┘       └──────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                   1:N            1:N            1:N
                    │              │              │
              ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
              │    Cue    │  │ Playlist  │  │   Crate   │
              └───────────┘  │   Track   │  │   Track   │
                             └───────────┘  └───────────┘
                                   │              │
                                  N:1            N:1
                                   │              │
                             ┌─────▼─────┐  ┌─────▼─────┐
                             │ Playlist  │  │   Crate   │
                             └───────────┘  └───────────┘
```

## Entities

### TrackLocation

Physical file location for a track.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto | Unique identifier |
| location | String(512) | Unique | Full file path |
| filename | String(512) | | File name only |
| directory | String(512) | | Directory path |
| filesize | Integer | | Size in bytes |
| fs_deleted | Integer | | 1 if file missing from filesystem |
| needs_verification | Integer | | 1 if needs rescan |

### Track (library table)

Music track with metadata.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto | Unique identifier |
| artist | String(64) | | Artist name |
| title | String(64) | | Track title |
| album | String(64) | | Album name |
| year | String(16) | | Release year |
| genre | String(64) | | Genre classification |
| tracknumber | String(3) | | Track number on album |
| location | Integer | FK → TrackLocation.id | File location reference |
| comment | String(256) | | User comments |
| duration | Integer | | Length in seconds |
| bitrate | Integer | | Audio bitrate |
| samplerate | Integer | | Sample rate (Hz) |
| bpm | Float | | Beats per minute |
| key | String(8) | | Musical key |
| rating | Integer | Default 0 | 0-5 star rating |
| timesplayed | Integer | Default 0 | Play count |
| datetime_added | DateTime | Auto | When added to library |
| last_played_at | DateTime | Nullable | Last play timestamp |
| mixxx_deleted | Integer | | 1 if soft-deleted |
| color | Integer | Nullable | Track color label |
| replaygain | Float | Default 0 | ReplayGain value |
| composer | String(64) | | Composer name |
| album_artist | String | | Album artist |
| grouping | String | | Grouping tag |

### Playlist

Named, ordered collection of tracks.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto | Unique identifier |
| name | String(48) | | Playlist name |
| position | Integer | | Display order |
| hidden | Integer | Default 0 | 1 if hidden |
| locked | Integer | Default 0 | 1 if locked |
| date_created | DateTime | | Creation timestamp |
| date_modified | DateTime | | Last modification |

### PlaylistTrack

Junction table for playlist membership with ordering.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto | Unique identifier |
| playlist_id | Integer | FK → Playlist.id | Parent playlist |
| track_id | Integer | FK → Track.id | Member track |
| position | Integer | | Order within playlist |
| pl_datetime_added | DateTime | | When added to playlist |

### Crate

Unordered collection of tracks (like folders/tags).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto | Unique identifier |
| name | String(48) | Unique | Crate name |
| count | Integer | Default 0 | Track count cache |
| show | Integer | Default 1 | 1 if visible |
| locked | Integer | Default 0 | 1 if locked |
| autodj_source | Integer | Default 0 | AutoDJ source flag |

### CrateTrack

Junction table for crate membership (unordered).

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| crate_id | Integer | FK → Crate.id | Parent crate |
| track_id | Integer | FK → Track.id | Member track |
| | | Unique(crate_id, track_id) | No duplicates |

### Cue

Cue points and hot cues within tracks.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | Integer | PK, auto | Unique identifier |
| track_id | Integer | FK → Track.id, NOT NULL | Parent track |
| type | Integer | Default 0 | Cue type (0=cue, 1=loop, etc.) |
| position | Integer | Default -1 | Position in samples |
| length | Integer | Default 0 | Length (for loops) |
| hotcue | Integer | Default -1 | Hot cue number (-1=none, 0-7) |
| label | String | Default '' | Cue label text |
| color | Integer | Default 4294901760 | Cue color (ARGB) |
| source | Integer | Default 2 | Cue source |

## Configuration Entity (Application-level)

### Config

User configuration stored in `~/.config/music-commander/config.toml`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| mixxx_db | Path | ~/.mixxx/mixxxdb.sqlite | Path to Mixxx database |
| music_repo | Path | . | Path to git-annex music repo |
| colored_output | Boolean | true | Enable colored terminal output |
| default_remote | String | None | Default git-annex remote |

**TOML Structure**:
```toml
[paths]
mixxx_db = "/space/Music/Mixxx/mixxxdb.sqlite"
music_repo = "/space/Music"

[display]
colored_output = true

[git_annex]
default_remote = "nas"
```

## State Transitions

### Track Lifecycle

```
[New File] → fs_deleted=0, needs_verification=0
     │
     ▼ (file moved/deleted)
[Missing] → fs_deleted=1, needs_verification=1
     │
     ▼ (rescan finds file)
[Verified] → fs_deleted=0, needs_verification=0
     │
     ▼ (user deletes from library)
[Soft Deleted] → mixxx_deleted=1
```

### Playlist Track Ordering

When tracks are added/removed, `position` values must be recalculated:
- Insert: Shift all positions >= insert point by +1
- Delete: Shift all positions > deleted position by -1
- Move: Remove from old position, insert at new position

## Validation Rules

1. **Track.location** must reference valid TrackLocation.id
2. **PlaylistTrack** must have unique (playlist_id, track_id, position) 
3. **CrateTrack** must have unique (crate_id, track_id)
4. **Cue.hotcue** range: -1 (none) or 0-7
5. **Track.rating** range: 0-5
6. **Playlist/Crate names** must not be empty
