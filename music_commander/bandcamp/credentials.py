"""Bandcamp credentials file management.

Handles reading and writing the session cookie and associated metadata
to a dedicated credentials file at ~/.config/music-commander/bandcamp-credentials.json.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

CREDENTIALS_FILENAME = "bandcamp-credentials.json"


@dataclass
class BandcampCredentials:
    """Stored Bandcamp authentication credentials."""

    session_cookie: str
    fan_id: int
    username: str | None = None
    extracted_at: str = ""
    source: str = ""


def get_credentials_path(config_dir: Path | None = None) -> Path:
    """Return the path to the Bandcamp credentials file.

    Args:
        config_dir: Override config directory. Defaults to ~/.config/music-commander/.
    """
    if config_dir is None:
        config_dir = Path.home() / ".config" / "music-commander"
    return config_dir / CREDENTIALS_FILENAME


def load_credentials(config_dir: Path | None = None) -> BandcampCredentials | None:
    """Load credentials from the JSON file.

    Returns:
        BandcampCredentials if file exists and is valid, None otherwise.
    """
    path = get_credentials_path(config_dir)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict) or "session_cookie" not in data or "fan_id" not in data:
        return None

    return BandcampCredentials(
        session_cookie=data["session_cookie"],
        fan_id=data["fan_id"],
        username=data.get("username"),
        extracted_at=data.get("extracted_at", ""),
        source=data.get("source", ""),
    )


def save_credentials(creds: BandcampCredentials, config_dir: Path | None = None) -> None:
    """Save credentials to the JSON file atomically.

    Uses a temporary file and rename to avoid partial writes.
    """
    path = get_credentials_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = asdict(creds)
    content = json.dumps(data, indent=2) + "\n"

    # Atomic write: write to temp file in same directory, then rename
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".bandcamp-creds-", suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(content)
        Path(tmp_path).replace(path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise
