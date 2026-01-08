# Data Model: Mixxx to Git-Annex Metadata Sync

**Feature**: 002-mixxx-to-git | **Date**: 2026-01-07

## Entities

### TrackMetadata

Represents metadata for a single track extracted from Mixxx database.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `file_path` | `Path` | `track_locations.location` | Absolute path in Mixxx |
| `relative_path` | `Path` | Computed | Path relative to `music_repo` |
| `rating` | `int \| None` | `library.rating` | 0-5, 0 means unrated |
| `bpm` | `float \| None` | `library.bpm` | Beats per minute |
| `color` | `int \| None` | `library.color` | RGB integer |
| `key` | `str \| None` | `library.key` | Musical key notation |
| `artist` | `str \| None` | `library.artist` | |
| `title` | `str \| None` | `library.title` | |
| `album` | `str \| None` | `library.album` | |
| `genre` | `str \| None` | `library.genre` | |
| `year` | `str \| None` | `library.year` | |
| `tracknumber` | `str \| None` | `library.tracknumber` | |
| `comment` | `str \| None` | `library.comment` | |
| `crates` | `list[str]` | `crates` + `crate_tracks` | Crate names |
| `source_synchronized_ms` | `int \| None` | `library.source_synchronized_ms` | Change timestamp |

**Validation Rules**:
- `rating` must be 0-5
- `bpm` must be positive if present
- `color` must be valid RGB (0x000000-0xFFFFFF) if present
- `file_path` must exist and be under `music_repo`

### AnnexMetadataFields

Git-annex metadata field mapping for a track.

| Field | Type | Format | Notes |
|-------|------|--------|-------|
| `rating` | `str` | "1"-"5" | Skip if unrated (0) |
| `bpm` | `str` | "120.00" | 2 decimal places |
| `color` | `str` | "#RRGGBB" | Hex format |
| `key` | `str` | As-is | e.g., "Am", "G#" |
| `artist` | `str` | As-is | |
| `title` | `str` | As-is | |
| `album` | `str` | As-is | |
| `genre` | `str` | As-is | |
| `year` | `str` | As-is | |
| `tracknumber` | `str` | As-is | |
| `comment` | `str` | As-is | |
| `crate` | `list[str]` | Multi-value | All crate names |

**Transformation Rules**:
- NULL/empty values → field omitted (not set)
- `rating=0` → field omitted
- `color` INT → hex string "#RRGGBB"
- `bpm` float → string with 2 decimals
- Crate names sanitized for git-annex compatibility

### SyncState

Persisted sync state stored in git-annex metadata.

| Field | Type | Storage | Notes |
|-------|------|---------|-------|
| `last_sync_timestamp` | `datetime` | git-annex metadata | ISO 8601 format |
| `tracks_synced` | `int` | git-annex metadata | Count from last sync |

**Storage Location**: Metadata on `.music-commander-sync-state` sentinel file in repo root.

### SyncResult

Result of a sync operation.

| Field | Type | Notes |
|-------|------|-------|
| `synced` | `list[Path]` | Successfully synced files |
| `skipped` | `list[tuple[Path, str]]` | Skipped files with reason |
| `failed` | `list[tuple[Path, str]]` | Failed files with error |
| `total_requested` | `int` | Total files attempted |

**Computed Properties**:
- `success`: `len(failed) == 0`
- `summary()`: Human-readable summary string

## Relationships

```
TrackMetadata (Mixxx DB)
    │
    ├── file_path → track_locations.location
    │
    ├── metadata fields → library table columns
    │
    └── crates → crates + crate_tracks (M:N junction)
           │
           └── crate names (list)

TrackMetadata ──transform──> AnnexMetadataFields
                                    │
                                    └── git annex metadata --batch --json
                                              │
                                              └── git-annex branch (committed)
```

## State Transitions

### Sync Operation Flow

```
[Idle] 
   │
   ▼ sync-metadata invoked
[Loading Config]
   │
   ▼ config loaded
[Reading Sync State]
   │
   ├── first run → sync all tracks
   │
   └── previous sync → filter by timestamp
   │
   ▼
[Querying Mixxx DB]
   │
   ▼ tracks identified
[Matching Paths]
   │
   ├── path not in repo → skip with warning
   │
   └── path matched → continue
   │
   ▼
[Transforming Metadata]
   │
   ▼ fields mapped
[Writing to Git-Annex] (batch mode)
   │
   ├── per-file success → add to synced
   │
   └── per-file failure → add to failed
   │
   ▼
[Committing Changes]
   │
   ▼
[Updating Sync State]
   │
   ▼
[Reporting Summary]
   │
   ▼
[Done]
```

### Track Sync States

| State | Condition | Action |
|-------|-----------|--------|
| Unchanged | `source_synchronized_ms <= last_sync` | Skip (unless `--all`) |
| Modified | `source_synchronized_ms > last_sync` | Sync |
| New | No previous sync state | Sync |
| Missing | File not in repo | Skip with warning |
| Failed | Batch mode error | Log and continue |
