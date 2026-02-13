# music-commander

Manage git-annex based music collections with [Mixxx](https://mixxx.org/) DJ software integration.

A command-line tool for managing large music collections stored in git-annex, with special integration for Mixxx DJ software, Bandcamp purchase management, and audio file processing. Fetch files from commits, query your Mixxx database, sync metadata, manage Bandcamp purchases, split cue sheets, and keep your music organized across multiple storage locations.

If used correctly, you will never lose music or metadata again.

## Features

- **git-annex integration**: Fetch, drop, and manage music files across remotes with commit-based workflows
- **Mixxx database sync**: Synchronize ratings, BPM, keys, crates, and other metadata from Mixxx to git-annex
- **Bandcamp collection management**: Sync purchases, match releases to local files, download in preferred formats
- **Search DSL**: Query your music collection with a Mixxx-compatible search syntax (field filters, boolean operators, ranges)
- **Cue sheet splitting**: Parse and split cue+audio into individual tracks with metadata
- **Audio encoding/export**: Transcode between formats (FLAC, MP3, AIFF, WAV) with metadata preservation
- **File integrity checking**: Validate audio files for corruption and format issues
- **Anomalistic Records mirror**: Download and convert releases from the Anomalistic dark psy portal
- **Beautiful CLI**: Rich terminal output with progress bars, tables, and auto-paging
- **Comprehensive test suite**: Unit and integration tests with pytest
- **Reproducible builds**: Full Nix flake support for consistent environments

## Installation

### Using Nix (recommended)

```bash
# Run directly without installing
nix run github:poelzi/music-commander -- --help

# Install to your profile
nix profile install github:poelzi/music-commander

# Enter development environment (includes all system deps)
nix develop
```

### Using pip

Requires system dependencies to be installed first:

**Debian/Ubuntu:**
```bash
sudo apt install git git-annex ffmpeg libmagic1 flac vorbis-tools shntool sox
```

**Arch Linux:**
```bash
sudo pacman -S git git-annex ffmpeg file flac vorbis-tools shntool sox
```

**macOS (Homebrew):**
```bash
brew install git git-annex ffmpeg libmagic flac vorbis-tools shntool sox
```

Then install music-commander:

```bash
pip install .
# or for an isolated install:
pipx install .
```

### From Source (development)

```bash
git clone https://github.com/poelzi/music-commander
cd music-commander

# With Nix (recommended - includes all deps):
nix develop
pip install -e .

# Without Nix (requires system deps above):
pip install -e ".[dev]"
```

## Quick Start

### 1. Configure

Create `~/.config/music-commander/config.toml` (or run `music-commander init-config`):

```toml
[paths]
mixxx_db = "~/.mixxx/mixxxdb.sqlite"
music_repo = "~/Music"

[display]
colored_output = true

[git_annex]
default_remote = "nas"  # Optional: preferred remote for fetching
```

### 2. Fetch Files

```bash
# Get files from the last commit
music-commander files get-commit HEAD~1

# Get files from the last 5 commits
music-commander files get-commit HEAD~5..HEAD

# Preview without fetching
music-commander files get-commit --dry-run HEAD~3..HEAD

# Fetch from a specific remote
music-commander files get-commit --remote nas HEAD~1
```

## Usage

### mixxx sync

Sync track metadata from your Mixxx library to git-annex metadata.

Synchronizes metadata fields including rating, BPM, color, key, artist, title, album, genre, year, tracknumber, comment, and crate memberships from Mixxx to git-annex metadata on annexed files. By default, only tracks modified since the last sync are updated.

**Options:**

- `--all`, `-a`: Sync all tracks, ignoring change detection
- `--dry-run`, `-n`: Show what would be synced without making changes
- `--batch-size`, `-b`: Commit every N files (default: single commit at end)
- `PATHS`: Optional file or directory paths to filter sync

**Examples:**

```bash
# Sync tracks changed since last sync
music-commander mixxx sync

# Force sync all tracks (initial setup)
music-commander mixxx sync --all

# Preview changes without syncing
music-commander mixxx sync --dry-run

# Sync only a specific directory
music-commander mixxx sync ./darkpsy/

# Sync with commits every 1000 files
music-commander mixxx sync --all --batch-size 1000
```

**After syncing**, query tracks with git-annex:

```bash
# Find all 5-star tracks
git annex find --metadata rating=5

# Find tracks in a specific crate
git annex find --metadata crate="Festival Sets"

# Find tracks by BPM range
git annex find --metadata bpm=140.*
```

### search

Query your music collection using a Mixxx-compatible search DSL:

```bash
# Simple text search
music-commander search "dark forest"

# Field-specific filters
music-commander search "artist:Parasense bpm:>145"

# Boolean operators
music-commander search "genre:darkpsy AND NOT artist:Kindzadza"
```

### bandcamp

Manage your Bandcamp purchase collection:

```bash
# Authenticate (extracts cookies from your browser)
music-commander bandcamp auth

# Sync your purchase collection to the local cache
music-commander bandcamp sync

# Match Bandcamp purchases to local files
music-commander bandcamp match

# Download purchases in preferred format
music-commander bandcamp download

# Show collection report
music-commander bandcamp report
```

### files

File management commands:

```bash
# Fetch files from a commit/range/branch
music-commander files get-commit HEAD~1

# Drop local copies (keep on remotes)
music-commander files drop ./old-sets/

# Check file integrity
music-commander files check

# Export/transcode files
music-commander files export --format mp3-320 -o /tmp/usb-stick ./set-playlist/

# Edit metadata interactively
music-commander files edit-meta ./track.flac
```

### cue

Cue sheet operations:

```bash
# Split a cue+audio file into individual tracks
music-commander cue split album.cue
```

### Global Options

```bash
music-commander --help
music-commander --version
music-commander --config /path/to/config.toml files get-commit HEAD~1
music-commander --no-color files get-commit HEAD~1  # Disable colors
music-commander -v files get-commit HEAD~1          # Verbose output
music-commander -q files get-commit HEAD~1          # Quiet mode
```

## Configuration

### File Location

Configuration is loaded from:
- `~/.config/music-commander/config.toml` (default)
- Custom path via `--config` flag

See [config.example.toml](config.example.toml) for all available options.

### Configuration Options

```toml
[paths]
mixxx_db = "~/.mixxx/mixxxdb.sqlite"    # Mixxx database path
music_repo = "~/Music"                   # git-annex music repository
# mixxx_music_root = "~/Music"           # Override Mixxx track path root
# mixxx_backup_path = "~/mixxx-backup"   # Mixxx DB backup path

[display]
colored_output = true

[git_annex]
# default_remote = "nas"                 # Preferred remote for fetching

[bandcamp]
# default_format = "flac"               # Preferred download format
# match_threshold = 60                  # Fuzzy match threshold (0-100)

[anomalistic]
# output_dir = "~/Music/Anomalistic"    # Mirror output directory
# format = "flac"                       # Target audio format
# output_pattern = "{{artist}} - {{album}}"  # Folder structure template
# download_source = "wav"               # Source format: wav or mp3
```

### Defaults

If no config file exists, music-commander uses sensible defaults:
- `mixxx_db`: `~/.mixxx/mixxxdb.sqlite`
- `music_repo`: Current working directory
- `colored_output`: `true`
- `default_remote`: `null` (use any available remote)

## System Requirements

- **Python**: 3.13 or later
- **git**: Required
- **git-annex**: Required for annex operations
- **ffmpeg**: Required for audio encoding/transcoding
- **libmagic**: Required by python-magic for file type detection
- **Mixxx**: Optional (only needed for database sync commands)

Optional audio tools (for specific features):
- `flac`, `mp3val`, `vorbis-tools`, `shntool`, `sox`: Audio validation and processing

## Development

### Setup

```bash
# Enter Nix development shell (includes all deps)
nix develop

# Install in editable mode
pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
nix develop --command pytest

# Run with coverage
nix develop --command pytest --cov=music_commander --cov-report=html

# Run specific test file
nix develop --command pytest tests/unit/test_config.py -v

# Run integration tests only
nix develop --command pytest tests/integration/ -v
```

### Code Quality

```bash
# Type checking
nix develop --command mypy music_commander/

# Linting
nix develop --command ruff check .

# Formatting
nix develop --command ruff format .

# Run all checks (what CI runs)
nix flake check
```

### Project Structure

```
music-commander/
├── music_commander/           # Main package
│   ├── cli.py                # Click CLI framework & command discovery
│   ├── config.py             # Configuration loading (TOML)
│   ├── exceptions.py         # Exception hierarchy
│   ├── commands/             # CLI commands (auto-discovered)
│   │   ├── bandcamp/         # Bandcamp: auth, sync, match, download, repair, report
│   │   ├── files/            # Files: get, drop, check, export, edit-meta, get-commit
│   │   ├── cue/              # Cue: split
│   │   ├── mirror/           # Mirror: anomalistic
│   │   ├── dev/              # Dev: bandcamp-metrics
│   │   ├── mixxx.py          # Mixxx metadata sync
│   │   ├── search.py         # Search DSL queries
│   │   ├── view.py           # Symlink view generation
│   │   ├── rebuild_cache.py  # Cache rebuild
│   │   └── init_config.py    # Config initialization
│   ├── db/                   # Mixxx database ORM (read-only, WAL-safe)
│   ├── cache/                # Local SQLite cache for fast queries
│   ├── search/               # Lark-based search DSL parser
│   ├── bandcamp/             # Bandcamp API client & fuzzy matcher
│   ├── anomalistic/          # Anomalistic Records portal client
│   ├── cue/                  # Cue sheet parser & splitter
│   ├── view/                 # Template-based symlink views
│   └── utils/                # Git ops, output, encoding, matching
├── tests/                    # Test suite
│   ├── conftest.py           # Shared fixtures
│   ├── unit/                 # Unit tests
│   └── integration/          # Integration tests
├── flake.nix                 # Nix flake definition
├── pyproject.toml            # Python package metadata
├── config.example.toml       # Configuration template
└── README.md                 # This file
```

## Architecture

### CLI Framework

- **Click**: Command-line interface with auto-discovery of command modules
- **Rich**: Terminal output with progress bars, tables, and auto-paging
- **Global context**: Shared config and state across commands via `@pass_context`

### Database Layers

- **Mixxx DB**: Read-only SQLAlchemy ORM against Mixxx's SQLite (WAL-mode safe)
- **Cache DB**: Local SQLite cache for fast metadata queries, incrementally refreshed

### Git Integration

- **Revision parsing**: Supports commits, ranges, branches, tags
- **Annexed file detection**: Identifies symlinks to `.git/annex/objects`
- **Batch metadata**: Efficient bulk operations via `git annex metadata --batch`

### Bandcamp Integration

- **Adaptive rate limiter**: AIMD-based HTTP client for Bandcamp APIs
- **Fuzzy matching**: 4-phase matching (metadata URL, comment subdomain, folder path, global)
- **Cookie extraction**: Browser cookie access via rookiepy

## Exit Codes

- `0`: Success
- `1`: Partial failure (some files couldn't be fetched)
- `2`: Invalid revision specification
- `3`: Not a git-annex repository

## Roadmap

Future features:

- **Playlist/crate commands**: Manage Mixxx playlists and crates from CLI
- **Batch operations**: Update metadata, rate tracks in bulk
- **JSON output**: Machine-readable output with `--json` flag

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure `nix flake check` passes
5. Submit a pull request

## License

MIT License. See [LICENSE](LICENSE) for details.

## Author

Daniel Poelzleithner ([@poelzi](https://github.com/poelzi))

## Acknowledgments

- [Mixxx](https://mixxx.org/): Open-source DJ software
- [git-annex](https://git-annex.branchable.com/): Distributed file management
- [Nix](https://nixos.org/): Reproducible development environments
