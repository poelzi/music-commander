"""Unit tests for anomalistic config section parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from music_commander.config import Config, load_config
from music_commander.exceptions import ConfigValidationError


class TestAnomaListicConfigDefaults:
    """Tests for default anomalistic config values."""

    def test_default_output_dir(self):
        config = Config()
        assert config.anomalistic_output_dir is None

    def test_default_format(self):
        config = Config()
        assert config.anomalistic_format == "flac"

    def test_default_output_pattern(self):
        config = Config()
        assert config.anomalistic_output_pattern == "{{artist}} - {{album}}"

    def test_default_download_source(self):
        config = Config()
        assert config.anomalistic_download_source == "wav"


class TestAnomaListicConfigParsing:
    """Tests for parsing [anomalistic] section from TOML."""

    def test_parse_all_fields(self, temp_dir: Path):
        config_path = temp_dir / "config.toml"
        config_path.write_text("""[paths]
music_repo = "/tmp/music"

[anomalistic]
output_dir = "/tmp/anomalistic"
format = "mp3"
output_pattern = "[{{genre}}] {{artist}} - {{album}}"
download_source = "mp3"
""")
        config, warnings = load_config(config_path)
        assert config.anomalistic_output_dir == Path("/tmp/anomalistic")
        assert config.anomalistic_format == "mp3"
        assert config.anomalistic_output_pattern == "[{{genre}}] {{artist}} - {{album}}"
        assert config.anomalistic_download_source == "mp3"

    def test_parse_partial_fields(self, temp_dir: Path):
        config_path = temp_dir / "config.toml"
        config_path.write_text("""[paths]
music_repo = "/tmp/music"

[anomalistic]
output_dir = "/tmp/anomalistic"
""")
        config, warnings = load_config(config_path)
        assert config.anomalistic_output_dir == Path("/tmp/anomalistic")
        assert config.anomalistic_format == "flac"  # default preserved
        assert config.anomalistic_download_source == "wav"  # default preserved

    def test_missing_section_uses_defaults(self, temp_dir: Path):
        config_path = temp_dir / "config.toml"
        config_path.write_text("""[paths]
music_repo = "/tmp/music"
""")
        config, warnings = load_config(config_path)
        assert config.anomalistic_output_dir is None
        assert config.anomalistic_format == "flac"

    def test_invalid_output_dir_type(self, temp_dir: Path):
        config_path = temp_dir / "config.toml"
        config_path.write_text("""[anomalistic]
output_dir = 42
""")
        with pytest.raises(ConfigValidationError):
            load_config(config_path)

    def test_invalid_format_type(self, temp_dir: Path):
        config_path = temp_dir / "config.toml"
        config_path.write_text("""[anomalistic]
format = 42
""")
        with pytest.raises(ConfigValidationError):
            load_config(config_path)

    def test_invalid_download_source_type(self, temp_dir: Path):
        config_path = temp_dir / "config.toml"
        config_path.write_text("""[anomalistic]
download_source = 42
""")
        with pytest.raises(ConfigValidationError):
            load_config(config_path)


class TestAnomaListicConfigValidation:
    """Tests for anomalistic config validation."""

    def test_invalid_download_source_value(self):
        config = Config(anomalistic_download_source="ogg")
        warnings = config.validate()
        assert any("anomalistic.download_source" in w for w in warnings)

    def test_valid_download_source_wav(self):
        config = Config(anomalistic_download_source="wav")
        warnings = config.validate()
        assert not any("anomalistic.download_source" in w for w in warnings)

    def test_valid_download_source_mp3(self):
        config = Config(anomalistic_download_source="mp3")
        warnings = config.validate()
        assert not any("anomalistic.download_source" in w for w in warnings)

    def test_output_dir_expansion(self):
        config = Config(anomalistic_output_dir=Path("~/anomalistic"))
        config.validate()
        assert "~" not in str(config.anomalistic_output_dir)
