# music-commander

Manage git-annex based music collections with Mixxx DJ software integration.

A command-line tool for managing large music collections stored in git-annex, with special integration for Mixxx DJ software. Fetch files from commits, query your Mixxx database, and keep your music organized across multiple storage locations.

## Features

- **git-annex integration**: Fetch music files from commits, branches, ranges, or tags
- **Mixxx database access**: Query and manage your Mixxx library programmatically (ORM layer)
- **Reproducible builds**: Full Nix flake support for consistent environments
- **Beautiful CLI**: Colored output with Rich, progress bars, helpful error messages
- **Type-safe**: Fully type-hinted Python 3.11+ with strict mypy checking
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
music-commander get-commit-files HEAD~1

# Get files from the last 5 commits
music-commander get-commit-files HEAD~5..HEAD

# Preview without fetching
music-commander get-commit-files --dry-run HEAD~3..HEAD

# Fetch from a specific remote
music-commander get-commit-files --remote nas HEAD~1
```

## Usage

### get-commit-files Command

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
music-commander get-commit-files feature/summer-playlist

# Fetch files from a tagged release
music-commander get-commit-files v2025-summer-set

# Preview files in a commit range
music-commander get-commit-files --dry-run main..feature-branch
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

# Path to git-annex music repository (required for get-commit-files)
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
│   │   └── get_commit_files.py
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

- **Python**: 3.11 or later
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
