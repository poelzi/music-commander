# Quickstart: music-commander

## Prerequisites

- Nix with flakes enabled
- git-annex installed (provided by dev shell)
- A git-annex managed music repository

## Installation

### Using Nix (recommended)

```bash
# Run directly
nix run github:poelzi/musicCommander

# Install to profile
nix profile install github:poelzi/musicCommander

# Enter development shell
nix develop
```

### From Source

```bash
git clone https://github.com/poelzi/musicCommander
cd musicCommander
nix develop  # Enter dev shell with all dependencies
```

## Configuration

Create `~/.config/music-commander/config.toml`:

```toml
[paths]
mixxx_db = "/path/to/mixxxdb.sqlite"
music_repo = "/path/to/music/repo"

[display]
colored_output = true

[git_annex]
default_remote = "nas"
```

## Basic Usage

### Fetch files from recent commits

```bash
# Get files from last commit
music-commander get-commit-files HEAD~1

# Get files from last 5 commits
music-commander get-commit-files HEAD~5..HEAD

# Preview without fetching
music-commander get-commit-files --dry-run HEAD~3..HEAD
```

### Fetch files from a branch

```bash
# Get all files unique to a feature branch
music-commander get-commit-files feature/summer-playlist
```

### Fetch files from a tag

```bash
# Get files from a tagged release
music-commander get-commit-files v2025-summer-set
```

## Common Workflows

### Before a DJ Set

Fetch all tracks added since your last gig:

```bash
cd /path/to/music/repo
music-commander get-commit-files last-gig..HEAD
git tag -a "$(date +%Y-%m-%d)-gig" -m "Pre-gig sync"
```

### Syncing from a Collaborator

```bash
git fetch origin
music-commander get-commit-files origin/main
```

## Getting Help

```bash
# General help
music-commander --help

# Command-specific help
music-commander get-commit-files --help
```

## Next Steps

- Explore Mixxx library commands (coming soon)
- Configure multiple remotes for redundancy
- Set up automated sync scripts
