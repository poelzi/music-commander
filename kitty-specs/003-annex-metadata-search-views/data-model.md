# Data Model: Annex Metadata Search & Symlink Views

**Date**: 2026-01-29
**Feature**: 003-annex-metadata-search-views

## Entities

### MetadataCache (SQLite table: `tracks`)

Local SQLite cache of git-annex metadata for fast querying.

| Field | Type | Description |
|-------|------|-------------|
| key | TEXT PRIMARY KEY | Git-annex key (e.g., `SHA256E-s6850832--1f59...mp3`) |
| file | TEXT NOT NULL | Relative path in repo |
| artist | TEXT | Artist name |
| title | TEXT | Track title |
| album | TEXT | Album name |
| genre | TEXT | Genre |
| bpm | REAL | BPM as float |
| rating | INTEGER | Rating (1-5, NULL if unrated) |
| key_musical | TEXT | Musical key (e.g., `Am`, `C#m`) |
| year | TEXT | Year |
| tracknumber | TEXT | Track number |
| comment | TEXT | Comment |
| color | TEXT | Hex color |

### TrackCrates (SQLite table: `track_crates`)

Multi-value crate memberships (one row per track-crate pair).

| Field | Type | Description |
|-------|------|-------------|
| key | TEXT NOT NULL | FK to tracks.key |
| crate | TEXT NOT NULL | Crate name |

Composite primary key: `(key, crate)`

### CacheState (SQLite table: `cache_state`)

Tracks the last-known state of the git-annex branch for incremental updates.

| Field | Type | Description |
|-------|------|-------------|
| id | INTEGER PRIMARY KEY | Always 1 (singleton) |
| annex_branch_commit | TEXT | Last-seen commit hash of `git-annex` branch |
| last_updated | TEXT | ISO timestamp of last cache refresh |
| track_count | INTEGER | Number of tracks in cache |

## Indexes

- `tracks`: Full-text search index (FTS5) on `artist`, `title`, `album`, `genre`, `file`
- `tracks`: Index on `bpm`, `rating`, `year` for numeric range queries
- `track_crates`: Index on `crate` for crate filtering

## Search Query AST

Parsed representation of a Mixxx-compatible search string.

```
SearchQuery
  ├── OrGroup[]           # Top-level OR groups separated by | or OR
  │     └── AndClause[]   # Implicitly ANDed terms within a group
  │           ├── TextTerm(value, negated)                          # Bare word: "dark"
  │           └── FieldFilter(field, op, value, value_end, negated) # field:value, field:>N, field:="exact"
  └── (empty = match all)

Operators: contains (default text), = (exact), >, <, >=, <=, range (N-M), empty ("")
Note: ExactFilter is not a separate node — exact match is FieldFilter with op="=".
value_end is only set for the "range" operator (N-M).
```

## View Template Context

Variables available in Jinja2 templates:

| Variable | Type | Source |
|----------|------|--------|
| `artist` | str | tracks.artist |
| `title` | str | tracks.title |
| `album` | str | tracks.album |
| `genre` | str | tracks.genre |
| `bpm` | float | tracks.bpm |
| `rating` | int | tracks.rating |
| `key` | str | tracks.key_musical |
| `year` | str | tracks.year |
| `tracknumber` | str | tracks.tracknumber |
| `comment` | str | tracks.comment |
| `color` | str | tracks.color |
| `crate` | str | Expanded per-value from track_crates |
| `file` | str | Relative file path |
| `filename` | str | Filename without directory |
| `ext` | str | File extension |

Custom Jinja2 filters:
- `round_to(n)`: Round number to nearest N (e.g., `{{ bpm | round_to(10) }}`)

Missing values render as `"Unknown"` unless overridden with Jinja2 `default` filter.
