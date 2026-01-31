# music-commander

Manage git-annex based music collections with Mixxx DJ software integration.

A command-line tool for managing large music collections stored in git-annex, with special integration for Mixxx DJ software. Fetch files from commits, query your Mixxx database, and keep your music organized across multiple storage locations.

## Features

- **git-annex integration**: Fetch music files from commits, branches, ranges, or tags
- **Mixxx database access**: Query and manage your Mixxx library programmatically (ORM layer)
- **Reproducible builds**: Full Nix flake support for consistent environments
- **Beautiful CLI**: Colored output with Rich, progress bars, helpful error messages
- **Type-safe**: Fully type-hinted Python 3.13+ with strict mypy checking
- **Well-tested**: 80%+ test coverage with pytest

## Installation

### Using Nix (recommended)

```bash
# Run directly without installing
nix run github:poelzi/musicCommander -- --help

# Install to your profile
nix profile install github:poelzi/musicCommander

# Enter development environment
nix develop
```

### From Source

```bash
git clone https://github.com/poelzi/musicCommander
cd musicCommander
nix develop
pip install -e .
```

## Quick Start

### 1. Configure

Create `~/.config/music-commander/config.toml`:

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

### mixxx sync Command

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
/

# Find tracks in a specific crate
git annex find --metadata crate="Festival Sets"

# Find tracks by BPM range
git annex find --metadata bpm=140.*
```

### files get-commit Command

Fetch git-annexed files from any git revision.

**Revision Types:**

- **Single commit**: `HEAD~1`, `abc123` (commit hash)
- **Commit range**: `HEAD~5..HEAD`, `v1.0..v2.0`
- **Branch**: `feature/new-tracks` (files unique to that branch)
- **Tag**: `v2025-summer-set`

**Options:**

- `--dry-run`, `-n`: Show files without fetching
- `--remote`, `-r`: Preferred git-annex remote
- `--jobs`, `-j`: Parallel fetch jobs (not yet implemented)

**Examples:**

```bash
# Fetch files from a feature branch
music-commander files get-commit feature/summer-playlist

# Fetch files from a tagged release
music-commander files get-commit v2025-summer-set

# Preview files in a commit range
music-commander files get-commit --dry-run main..feature-branch
```

### Global Options

```bash
music-commander --help
music-commander --version
music-commander --config /path/to/config.toml get-commit-files HEAD~1
music-commander --no-color get-commit-files HEAD~1  # Disable colors
music-commander -v get-commit-files HEAD~1          # Verbose output
music-commander -q get-commit-files HEAD~1          # Quiet mode
```

## Configuration

### File Location

Configuration is loaded from:
- `~/.config/music-commander/config.toml` (default)
- Custom path via `--config` flag

### Configuration Options

```toml
[paths]
# Path to Mixxx database (required for DB commands)
mixxx_db = "~/.mixxx/mixxxdb.sqlite"

# Path to git-annex music repository (required for files get-commit)
music_repo = "~/Music"

[display]
# Enable/disable colored terminal output
colored_output = true

[git_annex]
# Default remote for git-annex get operations (optional)
default_remote = "nas"
```

### Defaults

If no config file exists, music-commander uses sensible defaults:
- `mixxx_db`: `~/.mixxx/mixxxdb.sqlite`
- `music_repo`: Current working directory
- `colored_output`: `true`
- `default_remote`: `null` (use any available remote)

## Development

### Setup

```bash
# Enter Nix development shell
nix develop

# Install in editable mode
pip install -e .
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=music_commander --cov-report=html

# Run specific test file
pytest tests/unit/test_config.py -v

# Run integration tests only
pytest tests/integration/ -v
```

### Code Quality

```bash
# Type checking
mypy music_commander/

# Linting
ruff check .

# Formatting
ruff format .

# Run all checks (what CI runs)
nix flake check
```

### Project Structure

```
music-commander/
├── music_commander/         # Main package
│   ├── cli.py              # Click CLI framework
│   ├── config.py           # Configuration loading
│   ├── exceptions.py       # Exception hierarchy
│   ├── commands/           # CLI commands (auto-discovered)
│   │   └── files.py
│   ├── db/                 # Mixxx database ORM
│   │   ├── models.py       # SQLAlchemy models
│   │   ├── session.py      # Session management
│   │   └── queries.py      # Query functions
│   └── utils/              # Utilities
│       ├── git.py          # Git/git-annex operations
│       └── output.py       # Rich console helpers
├── tests/                  # Test suite
│   ├── conftest.py         # Shared fixtures
│   ├── unit/               # Unit tests
│   └── integration/        # Integration tests
├── flake.nix              # Nix flake definition
├── pyproject.toml         # Python package metadata
└── README.md              # This file
```

## Architecture

### CLI Framework

- **Click**: Command-line interface with auto-discovery
- **Rich**: Beautiful terminal output with progress bars and tables
- **Global context**: Shared config and state across commands

### Database Layer

- **SQLAlchemy 2.0**: ORM for Mixxx database
- **Read-only by default**: Respects Mixxx's concurrent access patterns
- **WAL mode aware**: Safe for use while Mixxx is running

### Git Integration

- **Revision parsing**: Supports commits, ranges, branches, tags
- **Annexed file detection**: Identifies symlinks to `.git/annex/objects`
- **Progress tracking**: Rich progress bars for long-running operations

## Exit Codes

- `0`: Success
- `1`: Partial failure (some files couldn't be fetched)
- `2`: Invalid revision specification
- `3`: Not a git-annex repository

## Requirements

- **Python**: 3.13 or later
- **git-annex**: Required for annex operations
- **Mixxx**: Optional (only needed for database commands)

### Python Dependencies

- `click >= 8.0`: CLI framework
- `rich >= 13.0`: Terminal output
- `sqlalchemy >= 2.0`: Database ORM
- `tomli-w >= 1.0`: TOML writing

## Roadmap

Future features (see `plan.md` for details):

- **Playlist/crate commands**: Manage Mixxx playlists and crates from CLI
- **Track queries**: Search and filter tracks by BPM, key, rating, etc.
- **Batch operations**: Update metadata, rate tracks in bulk
- **JSON output**: Machine-readable output with `--json` flag
- **Config command**: Interactive config file creation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure `nix flake check` passes
5. Submit a pull request

## License

[Add your license here]

## Author

Daniel Poelzleithner (@poelzi)

## Acknowledgments

- **Mixxx**: Amazing open-source DJ software
- **git-annex**: Powerful distributed file management
- **Nix**: Reproducible development environments
