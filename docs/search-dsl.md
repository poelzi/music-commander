# Search DSL Reference

music-commander uses a Mixxx-compatible search query language for finding tracks. The parser is built with Lark (Earley parser) and the grammar supports text search, field filters, boolean operators, negation, and range queries.

## Basic Text Search

Bare words perform a prefix-matched full-text search across artist, title, album, genre, and file path fields using SQLite FTS5.

```bash
# Find tracks matching "dark"
music-commander search "dark"

# Multiple words are ANDed (both must match)
music-commander search "dark forest"
```

## Quoted Strings

Use double quotes for multi-word search terms:

```bash
music-commander search '"dark forest"'
```

## Field Filters

Filter by a specific field with `field:value` syntax:

```bash
# Contains (default)
music-commander search "artist:Parasense"

# Case-insensitive
music-commander search "artist:parasense"

# Quoted value for multi-word fields
music-commander search 'artist:"Com Truise"'
```

### Available Fields

| Field | Description | Example |
|-------|-------------|---------|
| `artist` | Track artist | `artist:Kindzadza` |
| `title` | Track title | `title:Forest` |
| `album` | Album name | `album:"Dark Side"` |
| `genre` | Genre tag | `genre:darkpsy` |
| `bpm` | Beats per minute | `bpm:>140` |
| `rating` | Star rating (1-5) | `rating:5` |
| `key` | Musical key | `key:Am` |
| `year` | Release year | `year:2024` |
| `tracknumber` | Track number | `tracknumber:1` |
| `comment` | Comment field | `comment:bandcamp` |
| `color` | Track color | `color:red` |
| `file` | File path | `file:darkpsy/` |
| `crate` | Mixxx crate name | `crate:Festival` |

The `location` field is an alias for `file` (Mixxx compatibility).

## Operators

### Exact Match

Use `=` for exact (case-insensitive) matching:

```bash
music-commander search 'artist:="DJ Test"'
```

### Comparison Operators

Numeric fields support `>`, `>=`, `<`, `<=`:

```bash
music-commander search "bpm:>140"
music-commander search "rating:>=4"
music-commander search "year:<2020"
```

### Range Filter

Use `N-M` for numeric ranges (inclusive):

```bash
music-commander search "bpm:135-145"
music-commander search "rating:3-5"
```

### Empty Value

Use `""` to find tracks with empty or null fields:

```bash
music-commander search 'genre:""'
music-commander search 'artist:""'
```

## Negation

Prefix with `-` to exclude matches:

```bash
# Exclude ambient tracks
music-commander search "-genre:ambient"

# Exclude a specific artist
music-commander search "-artist:Kindzadza"

# Negate text search
music-commander search "-dark"
```

## OR Groups

Use `|` or `OR` (case-sensitive) to combine alternatives. Each side of `|` is an AND group:

```bash
# Tracks in house OR techno genre
music-commander search "genre:house | genre:techno"

# Equivalent with OR keyword
music-commander search "genre:house OR genre:techno"

# Complex: (high-rated techno) OR (high-rated house)
music-commander search "rating:>=4 genre:techno | rating:>=4 genre:house"
```

## Combined Queries

Multiple clauses in the same OR group are implicitly ANDed:

```bash
# Dark tracks with BPM > 140
music-commander search "dark bpm:>140"

# Darkpsy tracks rated 4+ from 2023
music-commander search "genre:darkpsy rating:>=4 year:2023"

# Tracks in the Festival crate with high BPM
music-commander search "crate:Festival bpm:>145"
```

## Output Formats

```bash
# Default table output
music-commander search "dark"

# File paths only (for piping)
music-commander search --format paths "dark"

# JSON output
music-commander search --format json "dark"

# Custom columns
music-commander search --columns artist,title,bpm,key "dark"

# Limit results
music-commander search --limit 20 "dark"
```

## Grammar Summary

```
query      = or_group ("|" or_group)*
or_group   = clause+
clause     = ["-"] (field_filter | text_term)
field_filter = FIELD ":" (exact | empty | range | comparison | contains)
exact      = "=" (QUOTED | WORD)
empty      = '""'
range      = NUMBER "-" NUMBER
comparison = ("<" | "<=" | ">" | ">=") NUMBER
contains   = QUOTED | WORD
text_term  = QUOTED | WORD
```
