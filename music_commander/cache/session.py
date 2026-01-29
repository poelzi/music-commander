"""Cache database session management."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.models import CacheBase

CACHE_DB_NAME = ".music-commander-cache.db"


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


@contextmanager
def get_cache_session(repo_path: Path) -> Generator[Session, None, None]:
    """Create a session for the cache database.

    Auto-creates tables on first use.

    Args:
        repo_path: Path to the music repository root.

    Yields:
        SQLAlchemy Session for the cache database.
    """
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
