# Release Process

## Pre-Release Checks

All gate checks must pass before cutting a release:

```bash
# Enter dev environment
nix develop

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy music_commander/

# Full Nix-level checks (tests + lint + types)
nix flake check
```

## Versioning

The project uses semantic versioning. The version is defined in:

- `music_commander/__init__.py` -- `__version__` string
- `pyproject.toml` -- `[project] version`

Both must be updated together.

## Cutting a Release

1. Ensure `main` is clean and all checks pass
2. Update version in `music_commander/__init__.py` and `pyproject.toml`
3. Update changelog (if maintained)
4. Commit: `git commit -m "Release vX.Y.Z"`
5. Tag: `git tag vX.Y.Z`
6. Push: `git push origin main --tags`

## Nix Flake

The Nix flake (`flake.nix`) builds the package and runs checks. After a release:

- Users can install with `nix profile install github:poelzi/music-commander`
- The flake lock should be updated periodically: `nix flake update`

## Package Distribution

- **Nix**: Primary distribution method via the flake
- **pip**: `pip install .` from source or `pip install music-commander` if published to PyPI
- **pipx**: `pipx install .` for isolated installs
