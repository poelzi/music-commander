# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-02-13

### Added

- CLI framework with auto-discovered commands via Click
- git-annex integration: fetch, drop, and manage music files across remotes
- Mixxx database sync: synchronize ratings, BPM, keys, crates, and metadata to git-annex
- Bandcamp collection management: sync purchases, match releases to local files, download in preferred formats
- Search DSL: Mixxx-compatible query syntax with field filters, boolean operators, and range queries
- Cue sheet splitting: parse and split cue+audio into individual tracks with metadata
- Anomalistic Records mirror: download and convert releases from the portal
- File integrity checking with pluggable checker framework
- Rich terminal output with progress bars, tables, and auto-paging
- TOML-based configuration with `init-config` command
- `check-deps` command for verifying system tool availability
- Comprehensive unit and integration test suite
- Full Nix flake support for reproducible builds and development
- Documentation: installation, configuration, commands, search DSL, Bandcamp workflow, git-annex guide, troubleshooting, contributing, and release process

### Security

- Credential files (`bandcamp-credentials.json`) created with 0o600 permissions
- Configuration directories created with 0o700 permissions
- Atomic file writes for credentials to prevent partial exposure
