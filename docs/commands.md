# Command Reference

All commands support `--help` for detailed usage. Global options (`--config`, `--repo`, `--no-color`, `-v`, `-q`, `--pager/--no-pager`, `--version`) apply to any command.

## Top-Level Commands

### `init-config`

Create a configuration file with all available options and documentation comments.

```bash
music-commander init-config                    # Default location
music-commander init-config -o ./config.toml   # Custom path
music-commander init-config --force            # Overwrite existing
```

### `check-deps`

Check availability of all external tool dependencies. Prints a table showing which tools are found, their paths, and which commands need them.

```bash
music-commander check-deps
```

Exit code 1 if any required tools are missing.

### `rebuild-cache`

Rebuild the local metadata cache from scratch. Normally the cache refreshes incrementally; use this if the cache becomes corrupted or out of sync.

```bash
music-commander rebuild-cache
```

### `search`

Search tracks using the Mixxx-compatible query DSL. See [Search DSL](search-dsl.md) for full syntax.

```bash
music-commander search "artist:Parasense bpm:>145"
music-commander search --format paths "genre:darkpsy"
music-commander search --format json --limit 50 "rating:5"
music-commander search --columns artist,title,bpm,key "dark"
```

**Options:** `--format` (table/paths/json), `--rebuild-cache`, `--limit`, `--columns`, `--clip`, `--sort`

### `view`

Create a symlink directory tree from search results using Jinja2 templates.

```bash
music-commander view --pattern "{{artist}}/{{album}}" --output ./my-view "genre:darkpsy"
music-commander view --pattern "{{bpm|round_to(5)}}/{{artist}} - {{title}}" --output ./bpm-view "rating:>=4"
```

**Options:** `--pattern` (required, Jinja2 template), `--output` (required), `--absolute`, `--rebuild-cache`, `--no-cleanup`, `--include-missing`, `--get`

Template variables: `artist`, `title`, `album`, `genre`, `bpm`, `rating`, `key`, `year`, `tracknumber`, `comment`, `color`, `crate`, `file`, `filename`, `ext`. Custom filter: `round_to(n)`.

### `help`

Show help for any command or command group.

```bash
music-commander help files get-commit
```

---

## `mixxx` -- Mixxx Integration

### `mixxx sync`

Sync metadata from your Mixxx library to git-annex. Synchronizes: rating, BPM, color, key, artist, title, album, genre, year, tracknumber, comment, and crate memberships.

```bash
music-commander mixxx sync                     # Changed tracks only
music-commander mixxx sync --all               # All tracks
music-commander mixxx sync --dry-run           # Preview
music-commander mixxx sync --batch-size 1000   # Commit every 1000 files
music-commander mixxx sync ./darkpsy/          # Filter by path
```

**Options:** `--all/-a`, `--dry-run/-n`, `--batch-size/-b`, `PATHS...`

### `mixxx backup`

Backup the Mixxx database to the git-annex repository.

```bash
music-commander mixxx backup
music-commander mixxx backup --path ./backups/
music-commander mixxx backup --message "Pre-sync backup"
```

**Options:** `--path`, `--message`

---

## `bandcamp` -- Bandcamp Collection

See [Bandcamp Workflow](bandcamp.md) for an end-to-end guide.

### `bandcamp auth`

Authenticate with Bandcamp by extracting session cookies from your browser.

```bash
music-commander bandcamp auth                  # Auto-detect browser
music-commander bandcamp auth --browser firefox
music-commander bandcamp auth --login          # Open browser for login
music-commander bandcamp auth --status         # Check auth status
```

**Options:** `--browser` (firefox/chrome), `--login`, `--status`

### `bandcamp sync`

Sync your Bandcamp purchase collection to the local cache database.

```bash
music-commander bandcamp sync                  # Incremental sync
music-commander bandcamp sync --full           # Full re-sync
```

**Options:** `--full`

### `bandcamp match`

Match Bandcamp releases against files in your local library using multi-phase fuzzy matching.

```bash
music-commander bandcamp match
music-commander bandcamp match --threshold 70  # Higher confidence
music-commander bandcamp match --missing       # Show unmatched only
music-commander bandcamp match --tag           # Write match metadata to git-annex
music-commander bandcamp match --dry-run       # Preview without tagging
```

**Options:** `--output`, `--threshold`, `--limit`, `--tag`, `--dry-run`, `--missing`, `--max-width`, `--record-metrics`

### `bandcamp download`

Download releases from your Bandcamp collection.

```bash
music-commander bandcamp download              # Download all unmatched
music-commander bandcamp download "artist name"
music-commander bandcamp download --format mp3-320
music-commander bandcamp download --output ./downloads/
```

**Options:** `--format`, `--output`, `--yes` (skip confirmation)

### `bandcamp repair`

Re-download broken files identified by `files check` using Bandcamp purchases.

```bash
music-commander bandcamp repair --report check-results.json
music-commander bandcamp repair --report check-results.json --dry-run
music-commander bandcamp repair --report check-results.json --format flac
```

**Options:** `--report` (required, JSON from `files check`), `--format`, `--dry-run`, `--threshold`

### `bandcamp report`

Generate an HTML report of your Bandcamp collection with download links.

```bash
music-commander bandcamp report                    # Full report with local server
music-commander bandcamp report --no-server        # Static HTML only
music-commander bandcamp report --unmatched        # Only unmatched releases
music-commander bandcamp report "query"            # Filter by search query
music-commander bandcamp report --output report.html
```

**Options:** `--format`, `--output`, `--unmatched`, `--no-server`

---

## `files` -- File Management

### `files get`

Fetch files matching a search query from git-annex remotes.

```bash
music-commander files get "genre:darkpsy rating:5"
music-commander files get --dry-run "artist:Parasense"
music-commander files get --remote nas "bpm:>145"
```

**Options:** `--dry-run`, `--remote`, `--jobs`, `--verbose`

### `files get-commit`

Fetch git-annexed files from commits, ranges, branches, or tags.

```bash
music-commander files get-commit HEAD~1
music-commander files get-commit HEAD~5..HEAD
music-commander files get-commit v1.0
music-commander files get-commit --dry-run HEAD~3..HEAD
music-commander files get-commit --remote nas HEAD~1
```

**Options:** `--dry-run`, `--remote`, `--jobs`, `--verbose`

### `files drop`

Drop local copies of files (content remains on remotes).

```bash
music-commander files drop "genre:ambient"
music-commander files drop --dry-run ./old-sets/
```

**Options:** `--dry-run`, `--force`, `--verbose`

### `files check`

Check integrity of audio files using format-specific tools. Outputs a JSON report.

```bash
music-commander files check
music-commander files check --output report.json
music-commander files check --jobs 4           # Parallel checking
music-commander files check --continue         # Resume interrupted check
music-commander files check --flac-multichannel-check  # Pioneer CDJ compat
```

**Options:** `--dry-run`, `--jobs`, `--verbose`, `--output`, `--flac-multichannel-check`, `--continue`

### `files export`

Export/transcode audio files to a specified format with metadata.

```bash
music-commander files export --format mp3-320 --pattern "{{artist}}/{{title}}" --output /tmp/usb
music-commander files export --format flac --pattern "{{artist}} - {{album}}/{{tracknumber}} - {{title}}" --output ./export ./my-tracks/
```

Format presets: `mp3-320`, `mp3-v0`, `flac`, `flac-pioneer`, `aiff`, `aiff-pioneer`, `wav`, `wav-pioneer`

**Options:** `--format`, `--pattern` (required, Jinja2), `--output` (required), `--force`, `--dry-run`, `--jobs`, `--verbose`

### `files edit-meta`

Open audio files in an external tag editor.

```bash
music-commander files edit-meta ./track.flac
music-commander files edit-meta --editor puddletag ./album/
```

**Options:** `--dry-run`, `--verbose`, `--editor`

---

## `cue` -- CUE Sheet Processing

### `cue split`

Split single-file CD rips into individual FLAC tracks using shntool with ffmpeg fallback.

```bash
music-commander cue split ./album-rips/
music-commander cue split --recursive ./music/
music-commander cue split --dry-run ./album/
music-commander cue split --remove-originals ./album/
```

Supports FLAC, WAV, APE, and WavPack source formats.

**Options:** `--recursive/-r`, `--remove-originals`, `--force`, `--dry-run/-n`, `--encoding`, `--verbose/-v`

---

## `mirror` -- External Portals

### `mirror anomalistic`

Mirror releases from the Anomalistic dark psy portal. Downloads, converts, and organizes releases.

```bash
music-commander mirror anomalistic
music-commander mirror anomalistic --force     # Re-download existing
```

**Options:** `--force`

---

## `dev` -- Developer Tools

### `dev bandcamp-metrics show`

Display historical Bandcamp match metrics collected with `bandcamp match --record-metrics`.

```bash
music-commander dev bandcamp-metrics show
music-commander dev bandcamp-metrics show --last 10
music-commander dev bandcamp-metrics show --format json
```

**Options:** `--last`, `--format` (table/json/csv)

### `dev bandcamp-metrics diff`

Compare the last two metric entries and highlight changes.

```bash
music-commander dev bandcamp-metrics diff
```
