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
