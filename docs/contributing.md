# Contributing

## Development Environment

The recommended way to set up a development environment is with Nix:

```bash
git clone https://github.com/poelzi/music-commander
cd music-commander
nix develop
pip install -e .
```

This provides all system dependencies (git-annex, ffmpeg, shntool, etc.) and Python packages in an isolated shell.

Without Nix, install system dependencies manually (see [Installation](installation.md)) and then:

```bash
pip install -e ".[dev]"
```

## Testing

**Every code change must include tests.** Tests live in `tests/unit/` and `tests/integration/`.

```bash
# Run all tests
nix develop --command pytest

# Run unit tests only
nix develop --command pytest tests/unit/ -v

# Run a specific test file
nix develop --command pytest tests/unit/test_config.py -v

# Run tests matching a name
nix develop --command pytest -k "test_search"

# Run with coverage
nix develop --command pytest --cov=music_commander --cov-report=html
```

### Test Patterns

- **CLI commands**: Use Click's `CliRunner` with `@patch` to mock dependencies. See `tests/unit/test_cmd_cue_split.py` for examples.
- **Logic/algorithms**: Direct function testing with factory helpers. See `tests/unit/test_bandcamp_matcher.py`.
- **Integration tests**: Use fixtures from `tests/integration/conftest.py` that create real git-annex repos and audio files.

## Code Quality

All checks must pass before submitting:

```bash
# Linting
nix develop --command ruff check .

# Auto-format
nix develop --command ruff format .

# Type checking
nix develop --command mypy music_commander/

# All checks (CI equivalent)
nix flake check
```

### Style

- Python 3.13+ features are encouraged
- `from __future__ import annotations` in every file
- Type annotations on all functions (strict mypy)
- Line length: 100 characters (ruff)
- Import sorting: isort-compatible (ruff `I` rules)

## Architecture

### Command Auto-Discovery

Each module in `music_commander/commands/` that exports a `cli` attribute (Click command or group) is auto-registered. To add a new command:

1. Create `music_commander/commands/my_command.py`
2. Define a Click command or group named `cli`
3. It will be auto-discovered on import

Subgroups (`bandcamp/`, `files/`, `cue/`, `mirror/`, `dev/`) follow the same pattern with their own `__init__.py` defining the group.

### Key Conventions

- `@pass_context` for commands that need config access
- `sale_item_type` values from Bandcamp API are acquisition methods (`p`=purchase, `r`=redeemed, `c`=code, `i`=bundle-item, `s`=sub-item), not content types
- Cache DB path: `<music_repo>/.music-commander-cache.db`
- Output utilities: `info()`, `success()`, `warning()`, `error()`, `verbose()`, `debug()`

## Pull Request Workflow

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with tests
4. Ensure all checks pass: `nix flake check`
5. Submit a pull request with a clear description of changes

## Reporting Issues

File issues at [github.com/poelzi/music-commander/issues](https://github.com/poelzi/music-commander/issues).
