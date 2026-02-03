"""Cache database session management."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, sessionmaker

from music_commander.cache.models import (
    BandcampRelease,
    BandcampReleaseFormat,
    BandcampSyncState,
    BandcampTrack,
    CacheBase,
    CacheState,
    CacheTrack,
    TrackCrate,
)

CACHE_DB_NAME = ".music-commander-cache.db"

log = logging.getLogger(__name__)

# All ORM models for schema evolution
_ALL_MODELS = [
    CacheTrack,
    TrackCrate,
    CacheState,
    BandcampRelease,
    BandcampTrack,
    BandcampReleaseFormat,
    BandcampSyncState,
]


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


def clear_cache_tables(session: Session) -> None:
    """Clear only the cache tables (tracks, crates, state), preserving Bandcamp data.

    Use this instead of delete_cache() when you want to rebuild the track
    cache without losing expensive Bandcamp sync data.
    """
    session.execute(text("DELETE FROM track_crates"))
    session.execute(text("DELETE FROM tracks"))
    session.execute(text("DELETE FROM cache_state"))
    # FTS5 table is cleared during build_cache
    try:
        session.execute(text("DELETE FROM tracks_fts"))
    except Exception:
        pass  # FTS5 table may not exist yet
    session.commit()


@contextmanager
def get_cache_session(repo_path: Path) -> Generator[Session, None, None]:
    """Create a session for the cache database.

    Auto-creates tables on first use.  If the database file is corrupt
    (e.g. truncated write), it is deleted and recreated automatically.

    New columns and indexes are auto-added to existing tables via
    schema evolution (no migrations needed).

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

    # Create missing tables
    CacheBase.metadata.create_all(engine)

    # Auto-add missing columns and indexes to existing tables
    _ensure_schema(engine)

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


def _ensure_schema(engine) -> None:
    """Auto-add missing columns and indexes to existing tables.

    Handles the case where code declares new columns but the database
    was created by an older version. Only supports additive changes
    (new columns, new indexes). Column type changes and removals are
    ignored — they require a manual DB delete.
    """
    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for model in _ALL_MODELS:
        table_name = model.__tablename__
        if table_name not in existing_tables:
            continue  # create_all() already handled new tables

        # Add missing columns
        existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
        for column in model.__table__.columns:
            if column.name in existing_cols:
                continue
            col_type = column.type.compile(engine.dialect)
            nullable = "" if column.nullable else " NOT NULL"
            default = ""
            if column.server_default is not None:
                default = f" DEFAULT {column.server_default.arg}"
            ddl = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {col_type}{nullable}{default}"
            with engine.begin() as conn:
                conn.execute(text(ddl))
            log.info("Schema evolution: added column %s.%s", table_name, column.name)

        # Add missing indexes
        existing_indexes = {idx["name"] for idx in inspector.get_indexes(table_name)}
        for index in model.__table__.indexes:
            if index.name not in existing_indexes:
                try:
                    index.create(engine)
                    log.info("Schema evolution: created index %s on %s", index.name, table_name)
                except Exception:
                    # Index creation can fail if columns don't exist yet
                    # (shouldn't happen since we add columns first, but be safe)
                    log.debug("Could not create index %s on %s", index.name, table_name)
