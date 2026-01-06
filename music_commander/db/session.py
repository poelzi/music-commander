"""Database session management for Mixxx database."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import sqlalchemy.engine
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.exceptions import (
    DatabaseConnectionError,
    DatabaseNotFoundError,
    SchemaVersionError,
)

# Required tables for schema validation
REQUIRED_TABLES = {
    "library",
    "track_locations",
    "Playlists",
    "PlaylistTracks",
    "crates",
    "crate_tracks",
    "cues",
}


def get_engine(db_path: Path) -> sqlalchemy.engine.Engine:
    """Create SQLAlchemy engine for Mixxx database.

    Args:
        db_path: Path to mixxxdb.sqlite

    Returns:
        SQLAlchemy engine configured for concurrent access.

    Raises:
        DatabaseNotFoundError: If database file doesn't exist.
    """
    db_path = db_path.expanduser().resolve()

    if not db_path.exists():
        raise DatabaseNotFoundError(db_path)

    # SQLite connection with WAL mode awareness
    # - timeout: wait up to 30s for locks
    # - check_same_thread: False for connection pooling
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={
            "timeout": 30,
            "check_same_thread": False,
        },
        # Use NullPool to avoid keeping connections open
        poolclass=None,
    )

    return engine


def validate_schema(session: Session) -> None:
    """Validate that database has expected Mixxx schema.

    Args:
        session: Active database session.

    Raises:
        SchemaVersionError: If required tables are missing.
    """
    # Get list of tables
    result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
    existing_tables = {row[0] for row in result}

    missing = REQUIRED_TABLES - existing_tables
    if missing:
        raise SchemaVersionError(
            f"Missing required tables: {', '.join(sorted(missing))}. "
            f"Is this a valid Mixxx database?"
        )


@contextmanager
def get_session(db_path: Path) -> Generator[Session, None, None]:
    """Create a database session for Mixxx database operations.

    This is a context manager that handles session lifecycle:
    - Creates engine and session
    - Validates schema on first use
    - Commits on success, rolls back on error
    - Closes session when done

    Args:
        db_path: Path to mixxxdb.sqlite

    Yields:
        SQLAlchemy Session configured for concurrent access.

    Raises:
        DatabaseNotFoundError: If database file doesn't exist.
        SchemaVersionError: If database schema is incompatible.
        DatabaseConnectionError: If connection fails.

    Example:
        with get_session(Path("~/.mixxx/mixxxdb.sqlite")) as session:
            tracks = session.query(Track).all()
    """
    try:
        engine = get_engine(db_path)
    except Exception as e:
        if isinstance(e, DatabaseNotFoundError):
            raise
        raise DatabaseConnectionError(f"Failed to connect: {e}") from e

    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    try:
        # Validate schema on first query
        validate_schema(session)
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
