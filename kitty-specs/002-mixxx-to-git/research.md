# Research: Mixxx to Git-Annex Metadata Sync

**Feature**: 002-mixxx-to-git | **Date**: 2026-01-07

## 1. Mixxx Database Schema

### Decision: Use SQLite direct queries via SQLAlchemy

**Rationale**: The Mixxx database is a well-documented SQLite file. SQLAlchemy models already exist in the project for Mixxx access. Direct SQL queries are efficient for bulk metadata extraction.

**Alternatives Considered**:
- Mixxx internal API: Not accessible from external tools
- File tag reading: Would miss Mixxx-specific data (crates, ratings, colors)

### Key Tables

#### `library` Table (Primary Metadata)

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PRIMARY KEY | Unique track ID |
| `location` | INTEGER | FK to `track_locations.id` |
| `artist` | VARCHAR(64) | |
| `title` | VARCHAR(64) | |
| `album` | VARCHAR(64) | |
| `genre` | VARCHAR(64) | |
| `year` | VARCHAR(16) | |
| `tracknumber` | VARCHAR(3) | |
| `comment` | VARCHAR(256) | |
| `rating` | INTEGER | 0-5 stars (0 = unrated) |
| `bpm` | FLOAT | Beats per minute |
| `key` | VARCHAR(8) | Musical key notation |
| `color` | INTEGER | RGB value or NULL |
| `source_synchronized_ms` | INTEGER | Sync timestamp (ms) |
| `datetime_added` | DATETIME | When added to library |
| `last_played_at` | DATETIME | Last playback time |

#### `track_locations` Table (File Paths)

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PRIMARY KEY | |
| `location` | VARCHAR(512) UNIQUE | Full absolute path |
| `filename` | VARCHAR(512) | Filename only |
| `directory` | VARCHAR(512) | Directory only |

#### `crates` Table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PRIMARY KEY | |
| `name` | VARCHAR(48) UNIQUE | Crate name |

#### `crate_tracks` Junction Table

| Column | Type | Notes |
|--------|------|-------|
| `crate_id` | INTEGER | FK to `crates.id` |
| `track_id` | INTEGER | FK to `library.id` |

### Change Detection Strategy

**Decision**: Use `source_synchronized_ms` as primary change indicator

**Rationale**: 
- `source_synchronized_ms` is updated when Mixxx syncs metadata with the file
- Combined with our own "last sync" timestamp stored in git-annex, we can detect tracks modified since last sync
- For first sync (no stored timestamp), sync all tracks

**Implementation**:
1. Store last-sync timestamp in git-annex branch as metadata on a sentinel file
2. Query tracks where `source_synchronized_ms > last_sync_timestamp` OR `rating/bpm/etc changed`
3. For comprehensive detection, compare actual field values against previously stored metadata

**Fallback**: If `source_synchronized_ms` is unreliable, use `--all` flag for full resync

---

## 2. Git-Annex Metadata Batch Mode

### Decision: Use `git annex metadata --batch --json` with manual commits

**Rationale**: Batch mode keeps a single process running, avoiding startup overhead per file. JSON format provides structured I/O. Manual commit control prevents thousands of individual commits.

**Alternatives Considered**:
- Per-file `git annex metadata` calls: 10-100x slower for bulk operations
- Direct git-annex branch manipulation: Complex, risk of corruption

### Usage Pattern

**Command**: 
```bash
git -c annex.alwayscommit=false annex metadata --batch --json
```

**Input (stdin, one JSON per line)**:
```json
{"file":"relative/path/to/track.flac","fields":{"artist":["Artist Name"],"rating":["5"],"crate":["Crate1","Crate2"]}}
```

**Output (stdout, one JSON per line)**:
```json
{"command":"metadata","file":"relative/path/to/track.flac","key":"SHA256E-s...","fields":{"artist":["Artist Name"],"rating":["5"],"crate":["Crate1","Crate2"],"lastchanged":["2026-01-07@12-34-56"]},"success":true}
```

### Key Behaviors

| Behavior | Detail |
|----------|--------|
| Field replacement | Setting `{"fields":{"x":["v"]}}` replaces all previous values of `x` |
| Field removal | Setting `{"fields":{"x":[]}}` removes field entirely |
| Multi-value | Array with multiple values: `{"crate":["A","B","C"]}` |
| Empty response | Non-annexed files return empty line |
| Commit timing | With `annex.alwayscommit=false`, changes staged but not committed |

### Commit Strategy

1. Set `git -c annex.alwayscommit=false` before batch operations
2. Process all files through batch mode
3. Run `git annex merge` to commit accumulated changes
4. Single commit contains all metadata updates

### Performance Considerations

- Batch mode eliminates process startup overhead (significant for 10k+ files)
- Line-buffered output allows streaming processing
- Memory: ~1KB per file in metadata log
- For very large batches, consider chunking with periodic commits (configurable `--batch-size`)

---

## 3. Sync State Storage

### Decision: Store sync timestamp in git-annex metadata on repository-level key

**Rationale**: Git-annex metadata is shared across clones via the git-annex branch. Storing sync state there means all clones know when the last sync occurred.

**Implementation**:
- Create/use a sentinel file `.music-commander-sync-state` in repo root
- Store metadata: `{"sync-timestamp":["2026-01-07T12:34:56Z"]}`
- On sync start, read this timestamp
- On sync complete, update this timestamp

**Alternative Considered**:
- Local config file: Not shared across clones
- Git notes: More complex to manage

---

## 4. Path Matching

### Decision: Strip `music_repo` config prefix, match as relative paths

**Rationale**: Mixxx stores absolute paths like `/home/user/Music/artist/track.flac`. The git-annex repo may be at `/home/user/Music`. Stripping the repo path gives relative paths that work across machines.

**Implementation**:
```python
mixxx_path = "/home/user/Music/artist/track.flac"
repo_path = config.music_repo  # "/home/user/Music"
relative_path = Path(mixxx_path).relative_to(repo_path)  # "artist/track.flac"
```

**Edge Cases**:
- Mixxx path not under repo: Skip with warning
- Path case sensitivity: Match filesystem behavior (case-sensitive on Linux)

---

## 5. Field Mapping

### Decision: Direct field name mapping with value normalization

| Mixxx Column | Git-Annex Field | Normalization |
|--------------|-----------------|---------------|
| `rating` | `rating` | 0→skip, 1-5→"1"-"5" |
| `bpm` | `bpm` | Float→string, 2 decimals |
| `color` | `color` | INT→hex "#RRGGBB" |
| `key` | `key` | As-is |
| `artist` | `artist` | As-is |
| `title` | `title` | As-is |
| `album` | `album` | As-is |
| `genre` | `genre` | As-is |
| `year` | `year` | As-is |
| `tracknumber` | `tracknumber` | As-is |
| `comment` | `comment` | As-is |
| crate membership | `crate` | Multi-value array |

**Special Handling**:
- NULL/empty values: Skip field (don't set empty)
- Rating 0: Considered "unrated", skip
- Color NULL: Skip field
- Crate names: Sanitize special characters for git-annex compatibility

---

## Sources

- [Mixxx Schema XML](https://github.com/mixxxdj/mixxx/blob/main/res/schema.xml)
- [Mixxx Library Wiki](https://github.com/mixxxdj/mixxx/wiki/Library-Rewrite-Using-Sqlite)
- [git-annex-metadata man page](https://git-annex.branchable.com/git-annex-metadata/)
- [git-annex metadata design](https://git-annex.branchable.com/design/metadata/)
