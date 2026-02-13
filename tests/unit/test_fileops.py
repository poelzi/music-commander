"""Unit tests for secure file operation helpers."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from music_commander.utils.fileops import secure_atomic_write, secure_mkdir


class TestSecureMkdir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "subdir"
        secure_mkdir(target)
        assert target.is_dir()

    def test_sets_700_permissions(self, tmp_path: Path) -> None:
        target = tmp_path / "secure"
        secure_mkdir(target)
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o700

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        secure_mkdir(target)
        assert target.is_dir()
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o700

    def test_tightens_existing_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "loose"
        target.mkdir(mode=0o755)
        secure_mkdir(target)
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o700

    def test_idempotent(self, tmp_path: Path) -> None:
        target = tmp_path / "idem"
        secure_mkdir(target)
        secure_mkdir(target)
        assert target.is_dir()
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o700


class TestSecureAtomicWrite:
    def test_writes_content(self, tmp_path: Path) -> None:
        target = tmp_path / "file.txt"
        secure_atomic_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_sets_600_permissions(self, tmp_path: Path) -> None:
        target = tmp_path / "secret.json"
        secure_atomic_write(target, '{"key": "value"}')
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600

    def test_parent_directory_700(self, tmp_path: Path) -> None:
        target = tmp_path / "config" / "creds.json"
        secure_atomic_write(target, "data")
        parent_mode = stat.S_IMODE(target.parent.stat().st_mode)
        assert parent_mode == 0o700

    def test_atomic_no_partial_on_error(self, tmp_path: Path) -> None:
        target = tmp_path / "atomic.txt"
        secure_atomic_write(target, "original")

        class WriteError(Exception):
            pass

        # Monkey-patch to force an error during write
        original_write = os.write
        call_count = 0

        def failing_write(fd: int, data: bytes) -> int:
            nonlocal call_count
            call_count += 1
            raise WriteError("simulated write failure")

        try:
            os.write = failing_write  # type: ignore[assignment]
            try:
                secure_atomic_write(target, "should not appear")
            except WriteError:
                pass
        finally:
            os.write = original_write

        # Original content should be preserved
        assert target.read_text() == "original"

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "overwrite.txt"
        secure_atomic_write(target, "first")
        secure_atomic_write(target, "second")
        assert target.read_text() == "second"
        mode = stat.S_IMODE(target.stat().st_mode)
        assert mode == 0o600


class TestCredentialFilePermissions:
    def test_save_credentials_file_permissions(self, tmp_path: Path) -> None:
        from music_commander.bandcamp.credentials import (
            BandcampCredentials,
            save_credentials,
        )

        creds = BandcampCredentials(
            session_cookie="test-cookie",
            fan_id=12345,
            username="testuser",
        )
        save_credentials(creds, config_dir=tmp_path)

        creds_file = tmp_path / "bandcamp-credentials.json"
        assert creds_file.exists()
        mode = stat.S_IMODE(creds_file.stat().st_mode)
        assert mode == 0o600

        dir_mode = stat.S_IMODE(tmp_path.stat().st_mode)
        assert dir_mode == 0o700


class TestInitConfigPermissions:
    def test_init_config_file_permissions(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from music_commander.commands.init_config import cli

        output = tmp_path / "config.toml"
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", str(output)], standalone_mode=False)
        assert result.exception is None or result.exit_code == 0
        assert output.exists()
        mode = stat.S_IMODE(output.stat().st_mode)
        assert mode == 0o600
