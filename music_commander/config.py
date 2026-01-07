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
            raise ConfigValidationError(
                "git_annex.default_remote", value, "must be a string or null"
            )
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
