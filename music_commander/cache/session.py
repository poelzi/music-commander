"""Cache database session management."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.models import CacheBase

CACHE_DB_NAME = ".music-commander-cache.db"

log = logging.getLogger(__name__)


def get_cache_engine(repo_path: Path):
    """Create SQLAlchemy engine for the cache database.

    Args:
        repo_path: Path to the music repository root.

    Returns:
        SQLAlchemy engine for the cache database.
    """
    db_path = repo_path / CACHE_DB_NAME
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={
            "timeout": 30,
            "check_same_thread": False,
        },
    )
    return engine


def delete_cache(repo_path: Path) -> bool:
    """Delete the cache database file if it exists.

    Returns True if a file was deleted, False otherwise.
    """
    db_path = repo_path / CACHE_DB_NAME
    if db_path.exists():
        db_path.unlink()
        log.info("Deleted corrupt or stale cache: %s", db_path)
        return True
    return False


@contextmanager
def get_cache_session(repo_path: Path) -> Generator[Session, None, None]:
    """Create a session for the cache database.

    Auto-creates tables on first use.  If the database file is corrupt
    (e.g. truncated write), it is deleted and recreated automatically.

    Args:
        repo_path: Path to the music repository root.

    Yields:
        SQLAlchemy Session for the cache database.
    """
    try:
        yield from _open_cache_session(repo_path)
    except Exception as exc:
        # Detect SQLite corruption errors and retry once after deleting
        msg = str(exc).lower()
        if "malformed" in msg or "corrupt" in msg or "not a database" in msg:
            log.warning("Cache database appears corrupt, rebuilding: %s", exc)
            delete_cache(repo_path)
            yield from _open_cache_session(repo_path)
        else:
            raise


def _open_cache_session(repo_path: Path) -> Generator[Session, None, None]:
    """Internal helper that opens the cache session."""
    engine = get_cache_engine(repo_path)

    # Create tables if they don't exist
    CacheBase.metadata.create_all(engine)

    # Enable WAL mode for better concurrent access
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.commit()

    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
