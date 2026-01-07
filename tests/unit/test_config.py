"""Unit tests for configuration."""

from pathlib import Path

import pytest

from music_commander.config import Config, load_config
from music_commander.exceptions import ConfigParseError, ConfigValidationError


def test_default_config() -> None:
    """Test that default config has sensible values."""
    config = Config()
    assert config.colored_output is True
    assert config.default_remote is None


def test_load_missing_config(temp_dir: Path) -> None:
    """Test loading when config file doesn't exist."""
    config_path = temp_dir / "nonexistent.toml"
    config, warnings = load_config(config_path)

    assert config is not None
    assert len(warnings) > 0  # Should warn about missing file


def test_load_valid_config(sample_config: Path) -> None:
    """Test loading a valid config file."""
    config, warnings = load_config(sample_config)

    assert config.default_remote == "test-remote"
    assert config.colored_output is True


def test_load_invalid_toml(temp_dir: Path) -> None:
    """Test loading invalid TOML raises error."""
    config_path = temp_dir / "invalid.toml"
    config_path.write_text("this is not valid [ toml")

    with pytest.raises(ConfigParseError):
        load_config(config_path)


def test_config_validation_invalid_type(temp_dir: Path) -> None:
    """Test that invalid types raise validation error."""
    config_path = temp_dir / "bad_types.toml"
    config_path.write_text("""[display]
colored_output = "not a boolean"
""")

    with pytest.raises(ConfigValidationError):
        load_config(config_path)


def test_config_path_expansion() -> None:
    """Test that paths are expanded."""
    config = Config(mixxx_db=Path("~/test.sqlite"))
    config.validate()

    assert "~" not in str(config.mixxx_db)
