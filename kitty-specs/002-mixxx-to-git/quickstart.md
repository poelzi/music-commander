# Quickstart: Mixxx to Git-Annex Metadata Sync

## Prerequisites

- Mixxx DJ software with a configured library
- Git-annex repository containing your music collection
- `music-commander` installed and configured

## Configuration

Ensure your `~/.config/music-commander/config.toml` has:

```toml
[paths]
mixxx_db = "~/.mixxx/mixxxdb.sqlite"
music_repo = "~/Music"  # Your git-annex repo path
```

## Basic Usage

### Sync Changed Tracks

Sync metadata for tracks modified since the last sync:

```bash
music-commander sync-metadata
```

### Full Resync

Force sync all tracks regardless of change status:

```bash
music-commander sync-metadata --all
```

### Preview Changes (Dry Run)

See what would be synced without making changes:

```bash
music-commander sync-metadata --dry-run
```

### Sync Specific Files

Sync only specific files or directories:

```bash
# Single file
music-commander sync-metadata path/to/track.flac

# Directory
music-commander sync-metadata darkpsy/

# Multiple paths
music-commander sync-metadata album1/ album2/ track.mp3
```

## CLI Options

| Option | Short | Description |
|--------|-------|-------------|
| `--all` | `-a` | Sync all tracks, ignore change detection |
| `--dry-run` | `-n` | Preview without making changes |
| `--batch-size N` | `-b N` | Commit every N files (default: all at once) |

## Querying Synced Metadata

After syncing, use git-annex to query your collection:

```bash
# Find all 5-star tracks
git annex find --metadata rating=5

# Find tracks in a specific crate
git annex find --metadata crate=Festival

# Find tracks by artist
git annex find --metadata artist="The Artist"

# Combine queries
git annex find --metadata rating=5 --metadata genre=Psytrance
```

## Metadata Fields

| Mixxx Field | Git-Annex Field | Example Value |
|-------------|-----------------|---------------|
| Rating | `rating` | "5" |
| BPM | `bpm` | "145.00" |
| Color | `color` | "#FF5500" |
| Key | `key` | "Am" |
| Artist | `artist` | "Artist Name" |
| Title | `title` | "Track Title" |
| Album | `album` | "Album Name" |
| Genre | `genre` | "Psytrance" |
| Year | `year` | "2024" |
| Track # | `tracknumber` | "5" |
| Comment | `comment` | "Great track!" |
| Crates | `crate` | "Festival", "DarkPsy" |

## Example Workflow

1. **Rate and organize tracks in Mixxx**
   - Add ratings, set colors, organize into crates

2. **Sync to git-annex**
   ```bash
   music-commander sync-metadata
   ```

3. **Push to remote**
   ```bash
   git annex sync --content
   ```

4. **On another machine, pull and query**
   ```bash
   git annex sync
   git annex find --metadata rating=5
   ```
