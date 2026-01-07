---
work_package_id: "WP02"
subtasks:
  - "T005"
  - "T006"
title: "Configuration & Exceptions"
phase: "Phase 1 - Foundation"
lane: "done"
assignee: "claude"
agent: "claude-reviewer"
shell_pid: "1302500"
review_status: "approved without changes"
reviewed_by: "claude-reviewer"
history:
  - timestamp: "2026-01-06"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
  - timestamp: "2026-01-06T19:55:00Z"
    lane: "doing"
    agent: "claude"
    shell_pid: "1112538"
    action: "Started implementation of configuration and exceptions"
  - timestamp: "2026-01-06T20:00:00Z"
    lane: "for_review"
    agent: "claude"
    shell_pid: "1112538"
    action: "Completed implementation. All tasks (T005-T006) done. Tests: mypy and ruff both pass."
---

# Work Package Prompt: WP02 – Configuration & Exceptions

## Objectives & Success Criteria

- Implement complete exception hierarchy for all error types
- Config loads from `~/.config/music-commander/config.toml` when present
- Sensible defaults used when no config file exists
- Config validation catches invalid paths and types
- Type hints and mypy compliance throughout

## Context & Constraints

**Constitution Requirements**:
- Type hints MUST be used for all public interfaces
- Code MUST pass mypy type checking
- MUST provide sensible defaults while allowing configuration overrides

**Reference Documents**:
- `kitty-specs/001-core-framework-with/spec.md` - FR-001 through FR-005
- `kitty-specs/001-core-framework-with/contracts/database-api.md` - Exception hierarchy
- `kitty-specs/001-core-framework-with/research.md` - Config format decision (TOML)

**Dependencies**: WP01 must be complete (package structure exists)

## Subtasks & Detailed Guidance

### Subtask T005 – Create exceptions.py

**Purpose**: Define exception hierarchy for consistent error handling across the application.

**Steps**:
1. Create `music_commander/exceptions.py`
2. Define base exception class
3. Define category-specific exceptions
4. Include docstrings for all exceptions

**File**: `music_commander/exceptions.py`

**Implementation**:
```python
"""Exception hierarchy for music-commander."""

from pathlib import Path


class MusicCommanderError(Exception):
    """Base exception for all music-commander errors.
    
    All exceptions in this package inherit from this class,
    allowing callers to catch all music-commander errors with
    a single except clause.
    """
    pass


# Configuration Errors
class ConfigError(MusicCommanderError):
    """Configuration-related errors."""
    pass


class ConfigNotFoundError(ConfigError):
    """Configuration file not found (non-fatal, defaults used)."""
    
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Config file not found: {path}")


class ConfigParseError(ConfigError):
    """Configuration file has invalid syntax."""
    
    def __init__(self, path: Path, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Invalid config at {path}: {detail}")


class ConfigValidationError(ConfigError):
    """Configuration value is invalid."""
    
    def __init__(self, key: str, value: object, reason: str) -> None:
        self.key = key
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid config value for '{key}': {reason}")


# Database Errors
class DatabaseError(MusicCommanderError):
    """Database-related errors."""
    pass


class DatabaseNotFoundError(DatabaseError):
    """Database file doesn't exist."""
    
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Database not found: {path}")


class SchemaVersionError(DatabaseError):
    """Database schema is incompatible."""
    
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"Incompatible database schema: {detail}")


class DatabaseConnectionError(DatabaseError):
    """Failed to connect to database."""
    pass


# Entity Not Found Errors
class NotFoundError(MusicCommanderError):
    """Requested entity not found."""
    pass


class TrackNotFoundError(NotFoundError):
    """Track doesn't exist."""
    
    def __init__(self, track_id: int) -> None:
        self.track_id = track_id
        super().__init__(f"Track not found: {track_id}")


class PlaylistNotFoundError(NotFoundError):
    """Playlist doesn't exist."""
    
    def __init__(self, playlist_id: int) -> None:
        self.playlist_id = playlist_id
        super().__init__(f"Playlist not found: {playlist_id}")


class CrateNotFoundError(NotFoundError):
    """Crate doesn't exist."""
    
    def __init__(self, crate_id: int) -> None:
        self.crate_id = crate_id
        super().__init__(f"Crate not found: {crate_id}")


# Validation Errors
class ValidationError(MusicCommanderError):
    """Invalid input value."""
    
    def __init__(self, field: str, value: object, reason: str) -> None:
        self.field = field
        self.value = value
        self.reason = reason
        super().__init__(f"Invalid {field}: {reason}")


# Lock Errors
class LockedError(MusicCommanderError):
    """Entity is locked and cannot be modified."""
    pass


class PlaylistLockedError(LockedError):
    """Playlist is locked."""
    
    def __init__(self, playlist_id: int, name: str) -> None:
        self.playlist_id = playlist_id
        self.name = name
        super().__init__(f"Playlist '{name}' is locked")


class CrateLockedError(LockedError):
    """Crate is locked."""
    
    def __init__(self, crate_id: int, name: str) -> None:
        self.crate_id = crate_id
        self.name = name
        super().__init__(f"Crate '{name}' is locked")


# Git/Annex Errors
class GitError(MusicCommanderError):
    """Git-related errors."""
    pass


class NotGitRepoError(GitError):
    """Not a git repository."""
    
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Not a git repository: {path}")


class NotGitAnnexRepoError(GitError):
    """Not a git-annex repository."""
    
    def __init__(self, path: Path) -> None:
        self.path = path
        super().__init__(f"Not a git-annex repository: {path}")


class InvalidRevisionError(GitError):
    """Invalid git revision specification."""
    
    def __init__(self, revision: str) -> None:
        self.revision = revision
        super().__init__(f"Invalid revision: {revision}")


class AnnexGetError(GitError):
    """Failed to get file from git-annex."""
    
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to get {path}: {reason}")
```

**Parallel**: Can proceed alongside T006.

### Subtask T006 – Create config.py

**Purpose**: Implement configuration loading with TOML support and validation.

**Steps**:
1. Create `music_commander/config.py`
2. Define Config dataclass with all settings
3. Implement load_config() with defaults
4. Implement save_config() for future use
5. Add path validation

**File**: `music_commander/config.py`

**Implementation**:
```python
"""Configuration management for music-commander."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w

from music_commander.exceptions import (
    ConfigParseError,
    ConfigValidationError,
)


def get_default_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".config" / "music-commander" / "config.toml"


def get_default_mixxx_db_path() -> Path:
    """Get the default Mixxx database path."""
    return Path.home() / ".mixxx" / "mixxxdb.sqlite"


@dataclass
class Config:
    """Application configuration.
    
    Attributes:
        mixxx_db: Path to Mixxx SQLite database.
        music_repo: Path to git-annex music repository.
        colored_output: Whether to use colored terminal output.
        default_remote: Default git-annex remote for operations.
        config_path: Path where config was loaded from (None if defaults).
    """
    
    mixxx_db: Path = field(default_factory=get_default_mixxx_db_path)
    music_repo: Path = field(default_factory=Path.cwd)
    colored_output: bool = True
    default_remote: str | None = None
    config_path: Path | None = None
    
    def validate(self) -> list[str]:
        """Validate configuration values.
        
        Returns:
            List of warning messages for non-fatal issues.
            
        Raises:
            ConfigValidationError: If a critical validation fails.
        """
        warnings: list[str] = []
        
        # Expand user paths
        self.mixxx_db = self.mixxx_db.expanduser().resolve()
        self.music_repo = self.music_repo.expanduser().resolve()
        
        # Check if paths exist (warnings, not errors - might be created later)
        if not self.mixxx_db.exists():
            warnings.append(f"Mixxx database not found: {self.mixxx_db}")
        
        if not self.music_repo.exists():
            warnings.append(f"Music repository not found: {self.music_repo}")
        elif not (self.music_repo / ".git").exists():
            warnings.append(f"Music repository is not a git repo: {self.music_repo}")
        
        return warnings


def load_config(config_path: Path | None = None) -> tuple[Config, list[str]]:
    """Load configuration from file or use defaults.
    
    Args:
        config_path: Explicit config file path. If None, uses default location.
        
    Returns:
        Tuple of (Config object, list of warning messages).
        
    Raises:
        ConfigParseError: If config file exists but has invalid syntax.
        ConfigValidationError: If config values are invalid.
    """
    warnings: list[str] = []
    
    if config_path is None:
        config_path = get_default_config_path()
    
    config_path = config_path.expanduser().resolve()
    
    if not config_path.exists():
        # Use defaults
        config = Config()
        warnings.append(
            f"No config file found at {config_path}. Using defaults. "
            f"Create config with: mkdir -p {config_path.parent} && "
            f"music-commander config init"
        )
        config_warnings = config.validate()
        return config, warnings + config_warnings
    
    # Load from file
    try:
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigParseError(config_path, str(e)) from e
    
    config = _parse_config_dict(data, config_path)
    config_warnings = config.validate()
    
    return config, warnings + config_warnings


def _parse_config_dict(data: dict[str, Any], config_path: Path) -> Config:
    """Parse configuration dictionary into Config object."""
    config = Config(config_path=config_path)
    
    # Parse [paths] section
    paths = data.get("paths", {})
    if "mixxx_db" in paths:
        value = paths["mixxx_db"]
        if not isinstance(value, str):
            raise ConfigValidationError("paths.mixxx_db", value, "must be a string path")
        config.mixxx_db = Path(value)
    
    if "music_repo" in paths:
        value = paths["music_repo"]
        if not isinstance(value, str):
            raise ConfigValidationError("paths.music_repo", value, "must be a string path")
        config.music_repo = Path(value)
    
    # Parse [display] section
    display = data.get("display", {})
    if "colored_output" in display:
        value = display["colored_output"]
        if not isinstance(value, bool):
            raise ConfigValidationError("display.colored_output", value, "must be a boolean")
        config.colored_output = value
    
    # Parse [git_annex] section
    git_annex = data.get("git_annex", {})
    if "default_remote" in git_annex:
        value = git_annex["default_remote"]
        if value is not None and not isinstance(value, str):
            raise ConfigValidationError("git_annex.default_remote", value, "must be a string or null")
        config.default_remote = value
    
    return config


def save_config(config: Config, config_path: Path | None = None) -> None:
    """Save configuration to file.
    
    Args:
        config: Configuration to save.
        config_path: Path to save to. If None, uses config.config_path or default.
    """
    if config_path is None:
        config_path = config.config_path or get_default_config_path()
    
    config_path = config_path.expanduser().resolve()
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Build TOML structure
    data: dict[str, Any] = {
        "paths": {
            "mixxx_db": str(config.mixxx_db),
            "music_repo": str(config.music_repo),
        },
        "display": {
            "colored_output": config.colored_output,
        },
    }
    
    if config.default_remote is not None:
        data["git_annex"] = {"default_remote": config.default_remote}
    
    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)
```

**Parallel**: Can proceed alongside T005.

## Definition of Done Checklist

- [ ] T005: exceptions.py with complete hierarchy
- [ ] T006: config.py with load/save/validate
- [ ] All exceptions have proper docstrings
- [ ] Config loads from TOML correctly
- [ ] Missing config file returns defaults with warning
- [ ] Invalid TOML raises ConfigParseError
- [ ] Invalid values raise ConfigValidationError
- [ ] Paths are expanded and resolved
- [ ] `mypy music_commander/` passes
- [ ] `ruff check music_commander/` passes

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Path expansion edge cases | Use Path.expanduser().resolve() consistently |
| TOML parsing errors unclear | Wrap in ConfigParseError with line info |
| Config schema evolution | Document current version, add migration later |

## Review Guidance

- Verify exception hierarchy matches contracts/database-api.md
- Test config loading with missing file, valid file, invalid file
- Ensure type hints are complete and mypy passes
- Check that warnings are informative but non-blocking

## Activity Log

- 2026-01-06 – system – lane=planned – Prompt created.
- 2026-01-07T11:02:11Z – claude-reviewer – shell_pid=1302500 – lane=done – Code review complete: exceptions.py and config.py verified - mypy passes, ruff passes, config load/parse/validate tests pass
