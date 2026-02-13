# music-commander Documentation

music-commander is a CLI tool for managing git-annex based music collections. It bridges Mixxx DJ software, Bandcamp purchases, and audio file workflows into a single command-line interface built on top of git-annex's content-addressed storage.

## Key Concepts

**git-annex repository** -- Your music lives in a git repo where large files are managed by git-annex. Files can exist on multiple remotes (NAS, external drives, cloud) while only the ones you need are present locally. Metadata (ratings, BPM, crates) is stored in the git-annex branch alongside your files.

**Mixxx integration** -- music-commander reads your Mixxx DJ software database and syncs track metadata (ratings, BPM, keys, crates, colors) into git-annex metadata fields. This makes your DJ library metadata portable and version-controlled.

**Cache database** -- A local SQLite cache (`<repo>/.music-commander-cache.db`) indexes your collection for fast search queries. It refreshes incrementally by checking the git-annex branch HEAD.

**Bandcamp integration** -- Authenticate with Bandcamp, sync your purchase collection, fuzzy-match purchases against local files, download in your preferred format, and generate HTML reports.

**Search DSL** -- A Mixxx-compatible query language lets you find tracks by artist, title, BPM range, rating, crate, and more. Supports field filters, boolean operators, negation, and ranges.

## Documentation

| Page | Description |
|------|-------------|
| [Installation](installation.md) | System requirements, Nix and pip installation, development setup |
| [Configuration](configuration.md) | All config file options with defaults and explanations |
| [Commands](commands.md) | Full reference for every CLI command and subcommand |
| [Search DSL](search-dsl.md) | Query language grammar, operators, field filters, examples |
| [Bandcamp Workflow](bandcamp.md) | End-to-end guide: auth, sync, match, download, report |
| [Git-Annex How-To](howto-annex.md) | Using git-annex with large music libraries, size filters, remotes |
| [Troubleshooting](troubleshooting.md) | Common issues and solutions |
| [Contributing](contributing.md) | Development environment, testing, code quality |
| [Release Process](release-process.md) | How to cut a release, gate checks, versioning |

## Quick Links

- [README](../README.md) -- Project overview and quick start
- [Example config](../config.example.toml) -- Annotated configuration template
- [GitHub repository](https://github.com/poelzi/music-commander)
