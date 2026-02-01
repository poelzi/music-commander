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
        mixxx_music_root: Optional root path for Mixxx track locations.
            When set, paths in Mixxx DB are made relative to this path
            instead of music_repo. Useful when Mixxx stores paths like
            /home/user/Music but the git-annex repo is at /space/Music.
        colored_output: Whether to use colored terminal output.
        default_remote: Default git-annex remote for operations.
        config_path: Path where config was loaded from (None if defaults).
    """

    mixxx_db: Path = field(default_factory=get_default_mixxx_db_path)
    music_repo: Path = field(default_factory=Path.cwd)
    mixxx_music_root: Path | None = None
    mixxx_backup_path: Path | None = None
    colored_output: bool = True
    default_remote: str | None = None
    flac_multichannel_check: bool = False
    meta_editor: str | None = None
    bandcamp_session_cookie: str | None = None
    bandcamp_default_format: str = "flac"
    bandcamp_match_threshold: int = 60
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
        if self.mixxx_music_root is not None:
            # Use absolute() instead of resolve() to preserve symlinks.
            # Mixxx stores paths using the symlink path, so we must match that.
            self.mixxx_music_root = Path(str(self.mixxx_music_root.expanduser().absolute()))

        # Check if paths exist (warnings, not errors - might be created later)
        if not self.mixxx_db.exists():
            warnings.append(f"Mixxx database not found: {self.mixxx_db}")

        if not self.music_repo.exists():
            warnings.append(f"Music repository not found: {self.music_repo}")
        elif not (self.music_repo / ".git").exists():
            warnings.append(f"Music repository is not a git repo: {self.music_repo}")

        if not 0 <= self.bandcamp_match_threshold <= 100:
            warnings.append(
                f"bandcamp.match_threshold={self.bandcamp_match_threshold} "
                f"is outside valid range 0-100"
            )

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
            f"Create config with: music-commander init-config"
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

    if "mixxx_music_root" in paths:
        value = paths["mixxx_music_root"]
        if not isinstance(value, str):
            raise ConfigValidationError("paths.mixxx_music_root", value, "must be a string path")
        config.mixxx_music_root = Path(value)

    if "mixxx_backup_path" in paths:
        value = paths["mixxx_backup_path"]
        if not isinstance(value, str):
            raise ConfigValidationError("paths.mixxx_backup_path", value, "must be a string path")
        config.mixxx_backup_path = Path(value)

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

    # Parse [checks] section
    checks = data.get("checks", {})
    if "flac_multichannel" in checks:
        value = checks["flac_multichannel"]
        if not isinstance(value, bool):
            raise ConfigValidationError("checks.flac_multichannel", value, "must be a boolean")
        config.flac_multichannel_check = value

    # Parse [editors] section
    editors = data.get("editors", {})
    if "meta_editor" in editors:
        value = editors["meta_editor"]
        if value is not None and not isinstance(value, str):
            raise ConfigValidationError("editors.meta_editor", value, "must be a string or null")
        config.meta_editor = value
    # Parse [bandcamp] section
    bandcamp = data.get("bandcamp", {})
    if "session_cookie" in bandcamp:
        value = bandcamp["session_cookie"]
        if value is not None and not isinstance(value, str):
            raise ConfigValidationError(
                "bandcamp.session_cookie", value, "must be a string or null"
            )
        config.bandcamp_session_cookie = value

    if "default_format" in bandcamp:
        value = bandcamp["default_format"]
        if not isinstance(value, str):
            raise ConfigValidationError("bandcamp.default_format", value, "must be a string")
        config.bandcamp_default_format = value

    if "match_threshold" in bandcamp:
        value = bandcamp["match_threshold"]
        if not isinstance(value, int):
            raise ConfigValidationError("bandcamp.match_threshold", value, "must be an integer")
        config.bandcamp_match_threshold = value

    # Parse [bandcamp] section
    bandcamp = data.get("bandcamp", {})
    if "session_cookie" in bandcamp:
        value = bandcamp["session_cookie"]
        if value is not None and not isinstance(value, str):
            raise ConfigValidationError(
                "bandcamp.session_cookie", value, "must be a string or null"
            )
        config.bandcamp_session_cookie = value

    if "default_format" in bandcamp:
        value = bandcamp["default_format"]
        if not isinstance(value, str):
            raise ConfigValidationError("bandcamp.default_format", value, "must be a string")
        config.bandcamp_default_format = value

    if "match_threshold" in bandcamp:
        value = bandcamp["match_threshold"]
        if not isinstance(value, int):
            raise ConfigValidationError("bandcamp.match_threshold", value, "must be an integer")
        config.bandcamp_match_threshold = value

    # Parse [bandcamp] section
    bandcamp = data.get("bandcamp", {})
    if "session_cookie" in bandcamp:
        value = bandcamp["session_cookie"]
        if value is not None and not isinstance(value, str):
            raise ConfigValidationError(
                "bandcamp.session_cookie", value, "must be a string or null"
            )
        config.bandcamp_session_cookie = value

    if "default_format" in bandcamp:
        value = bandcamp["default_format"]
        if not isinstance(value, str):
            raise ConfigValidationError("bandcamp.default_format", value, "must be a string")
        config.bandcamp_default_format = value

    if "match_threshold" in bandcamp:
        value = bandcamp["match_threshold"]
        if not isinstance(value, int):
            raise ConfigValidationError("bandcamp.match_threshold", value, "must be an integer")
        config.bandcamp_match_threshold = value

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

    if config.mixxx_music_root is not None:
        data["paths"]["mixxx_music_root"] = str(config.mixxx_music_root)

    if config.default_remote is not None:
        data["git_annex"] = {"default_remote": config.default_remote}

    if config.flac_multichannel_check:
        data["checks"] = {"flac_multichannel": True}

    if config.meta_editor is not None:
        data["editors"] = {"meta_editor": config.meta_editor}
    # Build [bandcamp] section (only if non-default values)
    bandcamp_data: dict[str, Any] = {}
    if config.bandcamp_session_cookie is not None:
        bandcamp_data["session_cookie"] = config.bandcamp_session_cookie
    if config.bandcamp_default_format != "flac":
        bandcamp_data["default_format"] = config.bandcamp_default_format
    if config.bandcamp_match_threshold != 60:
        bandcamp_data["match_threshold"] = config.bandcamp_match_threshold
    if bandcamp_data:
        data["bandcamp"] = bandcamp_data

    # Build [bandcamp] section (only if non-default values)
    bandcamp_data: dict[str, Any] = {}
    if config.bandcamp_session_cookie is not None:
        bandcamp_data["session_cookie"] = config.bandcamp_session_cookie
    if config.bandcamp_default_format != "flac":
        bandcamp_data["default_format"] = config.bandcamp_default_format
    if config.bandcamp_match_threshold != 60:
        bandcamp_data["match_threshold"] = config.bandcamp_match_threshold
    if bandcamp_data:
        data["bandcamp"] = bandcamp_data

    # Build [bandcamp] section (only if non-default values)
    bandcamp_data: dict[str, Any] = {}
    if config.bandcamp_session_cookie is not None:
        bandcamp_data["session_cookie"] = config.bandcamp_session_cookie
    if config.bandcamp_default_format != "flac":
        bandcamp_data["default_format"] = config.bandcamp_default_format
    if config.bandcamp_match_threshold != 60:
        bandcamp_data["match_threshold"] = config.bandcamp_match_threshold
    if bandcamp_data:
        data["bandcamp"] = bandcamp_data

    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)
