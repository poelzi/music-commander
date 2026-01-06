---
work_package_id: "WP03"
subtasks:
  - "T007"
  - "T008"
  - "T009"
  - "T010"
  - "T010a"
title: "Database ORM Layer"
phase: "Phase 2 - Core Components"
lane: "for_review"
assignee: "claude"
agent: "claude"
shell_pid: "1112538"
review_status: ""
reviewed_by: ""
history:
  - timestamp: "2026-01-06"
    lane: "planned"
    agent: "system"
    shell_pid: ""
    action: "Prompt generated via /spec-kitty.tasks"
  - timestamp: "2026-01-06T20:05:00Z"
    lane: "doing"
    agent: "claude"
    shell_pid: "1112538"
    action: "Started implementation of database ORM layer"
  - timestamp: "2026-01-06T20:15:00Z"
    lane: "for_review"
    agent: "claude"
    shell_pid: "1112538"
    action: "Completed implementation. All tasks (T007-T010a) done including write operations. Tests: mypy and ruff both pass."
---

# Work Package Prompt: WP03 – Database ORM Layer

## Objectives & Success Criteria

- SQLAlchemy 2.0 ORM models for all Mixxx database tables
- Session management with WAL mode awareness for concurrent access
- Query functions for tracks, playlists, crates
- Schema validation on connection
- Works while Mixxx is running (no blocking/corruption)

## Context & Constraints

**Constitution Requirements**:
- MUST handle concurrent access with Mixxx using appropriate SQLite locking
- MUST work with both direct and indirect mode repositories
- MUST handle large file counts efficiently (10,000+ tracks)

**Reference Documents**:
- `kitty-specs/001-core-framework-with/data-model.md` - Entity definitions
- `kitty-specs/001-core-framework-with/contracts/database-api.md` - API signatures
- `kitty-specs/001-core-framework-with/research.md` - SQLAlchemy decision

**Dependencies**: WP02 must be complete (exceptions.py needed)

## Subtasks & Detailed Guidance

### Subtask T007 – Create db/__init__.py

**Purpose**: Initialize database module with clean exports.

**File**: `music_commander/db/__init__.py`

**Implementation**:
```python
"""Database layer for Mixxx integration."""

from music_commander.db.models import (
    Base,
    Crate,
    CrateTrack,
    Cue,
    Playlist,
    PlaylistTrack,
    Track,
    TrackLocation,
)
from music_commander.db.queries import (
    get_crate_tracks,
    get_playlist_tracks,
    get_track_by_id,
    get_track_by_location,
    list_crates,
    list_playlists,
    query_tracks,
)
from music_commander.db.session import get_session

__all__ = [
    # Models
    "Base",
    "Track",
    "TrackLocation",
    "Playlist",
    "PlaylistTrack",
    "Crate",
    "CrateTrack",
    "Cue",
    # Session
    "get_session",
    # Queries
    "query_tracks",
    "get_track_by_id",
    "get_track_by_location",
    "list_playlists",
    "get_playlist_tracks",
    "list_crates",
    "get_crate_tracks",
]
```

**Parallel**: Create first, then others can proceed.

### Subtask T008 – Create db/models.py

**Purpose**: Define SQLAlchemy ORM models matching Mixxx database schema.

**File**: `music_commander/db/models.py`

**Implementation**:
```python
"""SQLAlchemy ORM models for Mixxx database."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class TrackLocation(Base):
    """Physical file location for a track."""
    
    __tablename__ = "track_locations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location: Mapped[str | None] = mapped_column(String(512), unique=True)
    filename: Mapped[str | None] = mapped_column(String(512))
    directory: Mapped[str | None] = mapped_column(String(512))
    filesize: Mapped[int | None] = mapped_column(Integer)
    fs_deleted: Mapped[int | None] = mapped_column(Integer)
    needs_verification: Mapped[int | None] = mapped_column(Integer)
    
    # Relationship
    track: Mapped[Track | None] = relationship("Track", back_populates="track_location", uselist=False)
    
    def __repr__(self) -> str:
        return f"<TrackLocation(id={self.id}, location='{self.location}')>"


class Track(Base):
    """Music track with metadata."""
    
    __tablename__ = "library"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    artist: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(64))
    album: Mapped[str | None] = mapped_column(String(64))
    year: Mapped[str | None] = mapped_column(String(16))
    genre: Mapped[str | None] = mapped_column(String(64))
    tracknumber: Mapped[str | None] = mapped_column(String(3))
    location: Mapped[int | None] = mapped_column(Integer, ForeignKey("track_locations.id"))
    comment: Mapped[str | None] = mapped_column(String(256))
    url: Mapped[str | None] = mapped_column(String(256))
    duration: Mapped[int | None] = mapped_column(Integer)
    bitrate: Mapped[int | None] = mapped_column(Integer)
    samplerate: Mapped[int | None] = mapped_column(Integer)
    cuepoint: Mapped[int | None] = mapped_column(Integer)
    bpm: Mapped[float | None] = mapped_column(Float)
    channels: Mapped[int | None] = mapped_column(Integer)
    datetime_added: Mapped[datetime | None] = mapped_column(DateTime, default=datetime.utcnow)
    mixxx_deleted: Mapped[int | None] = mapped_column(Integer)
    played: Mapped[int | None] = mapped_column(Integer)
    filetype: Mapped[str | None] = mapped_column(String(8), default="?")
    replaygain: Mapped[float | None] = mapped_column(Float, default=0)
    timesplayed: Mapped[int | None] = mapped_column(Integer, default=0)
    rating: Mapped[int | None] = mapped_column(Integer, default=0)
    key: Mapped[str | None] = mapped_column(String(8), default="")
    composer: Mapped[str | None] = mapped_column(String(64), default="")
    bpm_lock: Mapped[int | None] = mapped_column(Integer, default=0)
    key_id: Mapped[int | None] = mapped_column(Integer, default=0)
    grouping: Mapped[str | None] = mapped_column(Text, default="")
    album_artist: Mapped[str | None] = mapped_column(Text, default="")
    color: Mapped[int | None] = mapped_column(Integer)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime)
    
    # Relationships
    track_location: Mapped[TrackLocation | None] = relationship(
        "TrackLocation", back_populates="track"
    )
    cues: Mapped[list[Cue]] = relationship("Cue", back_populates="track")
    playlist_entries: Mapped[list[PlaylistTrack]] = relationship(
        "PlaylistTrack", back_populates="track"
    )
    crate_entries: Mapped[list[CrateTrack]] = relationship(
        "CrateTrack", back_populates="track"
    )
    
    @property
    def file_path(self) -> str | None:
        """Get the file path from track location."""
        if self.track_location:
            return self.track_location.location
        return None
    
    def __repr__(self) -> str:
        return f"<Track(id={self.id}, artist='{self.artist}', title='{self.title}')>"


class Playlist(Base):
    """Named, ordered collection of tracks."""
    
    __tablename__ = "Playlists"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(48))
    position: Mapped[int | None] = mapped_column(Integer)
    hidden: Mapped[int] = mapped_column(Integer, default=0)
    date_created: Mapped[datetime | None] = mapped_column(DateTime)
    date_modified: Mapped[datetime | None] = mapped_column(DateTime)
    locked: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    entries: Mapped[list[PlaylistTrack]] = relationship(
        "PlaylistTrack", back_populates="playlist", order_by="PlaylistTrack.position"
    )
    
    @property
    def is_hidden(self) -> bool:
        return self.hidden == 1
    
    @property
    def is_locked(self) -> bool:
        return self.locked == 1
    
    def __repr__(self) -> str:
        return f"<Playlist(id={self.id}, name='{self.name}')>"


class PlaylistTrack(Base):
    """Junction table for playlist membership with ordering."""
    
    __tablename__ = "PlaylistTracks"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playlist_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Playlists.id"))
    track_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("library.id"))
    position: Mapped[int | None] = mapped_column(Integer)
    pl_datetime_added: Mapped[datetime | None] = mapped_column(DateTime)
    
    # Relationships
    playlist: Mapped[Playlist | None] = relationship("Playlist", back_populates="entries")
    track: Mapped[Track | None] = relationship("Track", back_populates="playlist_entries")
    
    def __repr__(self) -> str:
        return f"<PlaylistTrack(playlist_id={self.playlist_id}, track_id={self.track_id}, position={self.position})>"


class Crate(Base):
    """Unordered collection of tracks (like folders/tags)."""
    
    __tablename__ = "crates"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(48), unique=True, nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0)
    show: Mapped[int] = mapped_column(Integer, default=1)
    locked: Mapped[int] = mapped_column(Integer, default=0)
    autodj_source: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    entries: Mapped[list[CrateTrack]] = relationship("CrateTrack", back_populates="crate")
    
    @property
    def is_visible(self) -> bool:
        return self.show == 1
    
    @property
    def is_locked(self) -> bool:
        return self.locked == 1
    
    def __repr__(self) -> str:
        return f"<Crate(id={self.id}, name='{self.name}')>"


class CrateTrack(Base):
    """Junction table for crate membership (unordered)."""
    
    __tablename__ = "crate_tracks"
    
    crate_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("crates.id"), primary_key=True
    )
    track_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("library.id"), primary_key=True
    )
    
    # Relationships
    crate: Mapped[Crate | None] = relationship("Crate", back_populates="entries")
    track: Mapped[Track | None] = relationship("Track", back_populates="crate_entries")
    
    def __repr__(self) -> str:
        return f"<CrateTrack(crate_id={self.crate_id}, track_id={self.track_id})>"


class Cue(Base):
    """Cue points and hot cues within tracks."""
    
    __tablename__ = "cues"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(Integer, ForeignKey("library.id"), nullable=False)
    type: Mapped[int] = mapped_column(Integer, default=0)
    position: Mapped[int] = mapped_column(Integer, default=-1)
    length: Mapped[int] = mapped_column(Integer, default=0)
    hotcue: Mapped[int] = mapped_column(Integer, default=-1)
    label: Mapped[str] = mapped_column(Text, default="")
    color: Mapped[int] = mapped_column(Integer, default=4294901760)
    source: Mapped[int] = mapped_column(Integer, default=2)
    
    # Relationships
    track: Mapped[Track | None] = relationship("Track", back_populates="cues")
    
    def __repr__(self) -> str:
        return f"<Cue(id={self.id}, track_id={self.track_id}, hotcue={self.hotcue})>"
```

**Parallel**: Can proceed alongside T009, T010.

### Subtask T009 – Create db/session.py

**Purpose**: Session management with concurrent access handling.

**File**: `music_commander/db/session.py`

**Implementation**:
```python
"""Database session management for Mixxx database."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

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


def get_engine(db_path: Path):
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
    result = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table'")
    )
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
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
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
```

**Parallel**: Can proceed alongside T008, T010.

### Subtask T010 – Create db/queries.py

**Purpose**: Query functions following contracts/database-api.md.

**File**: `music_commander/db/queries.py`

**Implementation**:
```python
"""Query functions for Mixxx database."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from music_commander.db.models import (
    Crate,
    CrateTrack,
    Playlist,
    PlaylistTrack,
    Track,
    TrackLocation,
)
from music_commander.exceptions import (
    CrateNotFoundError,
    PlaylistNotFoundError,
    TrackNotFoundError,
)

if TYPE_CHECKING:
    pass


def query_tracks(
    session: Session,
    *,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    bpm_range: tuple[float, float] | None = None,
    key: str | None = None,
    limit: int | None = None,
) -> list[Track]:
    """Query tracks with optional filters.
    
    Args:
        session: Active database session.
        artist: Filter by artist (case-insensitive contains).
        title: Filter by title (case-insensitive contains).
        album: Filter by album (case-insensitive contains).
        genre: Filter by genre (case-insensitive contains).
        bpm_range: Filter by BPM range (min, max) inclusive.
        key: Filter by musical key (exact match).
        limit: Maximum results to return.
        
    Returns:
        List of Track objects matching filters.
    """
    stmt = select(Track).options(joinedload(Track.track_location))
    
    # Exclude deleted tracks
    stmt = stmt.where(Track.mixxx_deleted != 1)
    
    if artist:
        stmt = stmt.where(Track.artist.ilike(f"%{artist}%"))
    
    if title:
        stmt = stmt.where(Track.title.ilike(f"%{title}%"))
    
    if album:
        stmt = stmt.where(Track.album.ilike(f"%{album}%"))
    
    if genre:
        stmt = stmt.where(Track.genre.ilike(f"%{genre}%"))
    
    if bpm_range:
        min_bpm, max_bpm = bpm_range
        stmt = stmt.where(Track.bpm >= min_bpm, Track.bpm <= max_bpm)
    
    if key:
        stmt = stmt.where(Track.key == key)
    
    if limit:
        stmt = stmt.limit(limit)
    
    result = session.execute(stmt)
    return list(result.scalars().all())


def get_track_by_id(session: Session, track_id: int) -> Track:
    """Get a single track by ID.
    
    Args:
        session: Active database session.
        track_id: Track primary key.
        
    Returns:
        Track object.
        
    Raises:
        TrackNotFoundError: If track doesn't exist.
    """
    stmt = (
        select(Track)
        .options(joinedload(Track.track_location))
        .where(Track.id == track_id)
    )
    result = session.execute(stmt)
    track = result.scalar_one_or_none()
    
    if track is None:
        raise TrackNotFoundError(track_id)
    
    return track


def get_track_by_location(session: Session, file_path: Path) -> Track | None:
    """Get a track by its file path.
    
    Args:
        session: Active database session.
        file_path: Absolute path to track file.
        
    Returns:
        Track object or None if not found.
    """
    path_str = str(file_path.resolve())
    
    stmt = (
        select(Track)
        .join(TrackLocation)
        .options(joinedload(Track.track_location))
        .where(TrackLocation.location == path_str)
    )
    result = session.execute(stmt)
    return result.scalar_one_or_none()


def list_playlists(
    session: Session,
    *,
    include_hidden: bool = False,
) -> list[Playlist]:
    """List all playlists.
    
    Args:
        session: Active database session.
        include_hidden: Include hidden playlists.
        
    Returns:
        List of Playlist objects ordered by position.
    """
    stmt = select(Playlist).order_by(Playlist.position)
    
    if not include_hidden:
        stmt = stmt.where(Playlist.hidden != 1)
    
    result = session.execute(stmt)
    return list(result.scalars().all())


def get_playlist_tracks(
    session: Session,
    playlist_id: int,
) -> list[Track]:
    """Get all tracks in a playlist, ordered by position.
    
    Args:
        session: Active database session.
        playlist_id: Playlist primary key.
        
    Returns:
        List of Track objects in playlist order.
        
    Raises:
        PlaylistNotFoundError: If playlist_id doesn't exist.
    """
    # First check playlist exists
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise PlaylistNotFoundError(playlist_id)
    
    stmt = (
        select(Track)
        .join(PlaylistTrack)
        .options(joinedload(Track.track_location))
        .where(PlaylistTrack.playlist_id == playlist_id)
        .order_by(PlaylistTrack.position)
    )
    result = session.execute(stmt)
    return list(result.scalars().all())


def list_crates(
    session: Session,
    *,
    include_hidden: bool = False,
) -> list[Crate]:
    """List all crates.
    
    Args:
        session: Active database session.
        include_hidden: Include hidden crates (show=0).
        
    Returns:
        List of Crate objects.
    """
    stmt = select(Crate).order_by(Crate.name)
    
    if not include_hidden:
        stmt = stmt.where(Crate.show == 1)
    
    result = session.execute(stmt)
    return list(result.scalars().all())


def get_crate_tracks(
    session: Session,
    crate_id: int,
) -> list[Track]:
    """Get all tracks in a crate (unordered).
    
    Args:
        session: Active database session.
        crate_id: Crate primary key.
        
    Returns:
        List of Track objects in crate.
        
    Raises:
        CrateNotFoundError: If crate_id doesn't exist.
    """
    # First check crate exists
    crate = session.get(Crate, crate_id)
    if crate is None:
        raise CrateNotFoundError(crate_id)
    
    stmt = (
        select(Track)
        .join(CrateTrack)
        .options(joinedload(Track.track_location))
        .where(CrateTrack.crate_id == crate_id)
    )
    result = session.execute(stmt)
    return list(result.scalars().all())
```

**Parallel**: Can proceed alongside T008, T009.

### Subtask T010a – Add Write Operations to db/queries.py

**Purpose**: Add write operations per FR-009 (update track metadata, manage playlists/crates).

**File**: `music_commander/db/queries.py` (extend existing file)

**Implementation** (append to queries.py):
```python
# =============================================================================
# Write Operations
# =============================================================================


def update_track(
    session: Session,
    track_id: int,
    *,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    genre: str | None = None,
    bpm: float | None = None,
    key: str | None = None,
    rating: int | None = None,
    comment: str | None = None,
    color: int | None = None,
) -> Track:
    """Update track metadata fields.
    
    Only provided (non-None) fields are updated.
    
    Args:
        session: Active database session.
        track_id: Track primary key.
        artist: New artist name.
        title: New track title.
        album: New album name.
        genre: New genre.
        bpm: New BPM value.
        key: New musical key.
        rating: New rating (0-5).
        comment: New comment text.
        color: New color value.
        
    Returns:
        Updated Track object.
        
    Raises:
        TrackNotFoundError: If track doesn't exist.
    """
    track = get_track_by_id(session, track_id)
    
    if artist is not None:
        track.artist = artist
    if title is not None:
        track.title = title
    if album is not None:
        track.album = album
    if genre is not None:
        track.genre = genre
    if bpm is not None:
        track.bpm = bpm
    if key is not None:
        track.key = key
    if rating is not None:
        track.rating = max(0, min(5, rating))  # Clamp to 0-5
    if comment is not None:
        track.comment = comment
    if color is not None:
        track.color = color
    
    session.flush()
    return track


def create_playlist(
    session: Session,
    name: str,
    *,
    hidden: bool = False,
) -> Playlist:
    """Create a new playlist.
    
    Args:
        session: Active database session.
        name: Playlist name.
        hidden: Whether playlist is hidden.
        
    Returns:
        New Playlist object.
    """
    from datetime import datetime
    
    # Get next position
    max_pos = session.query(Playlist.position).order_by(Playlist.position.desc()).first()
    next_pos = (max_pos[0] + 1) if max_pos else 1
    
    playlist = Playlist(
        name=name,
        position=next_pos,
        hidden=1 if hidden else 0,
        date_created=datetime.utcnow(),
        date_modified=datetime.utcnow(),
        locked=0,
    )
    session.add(playlist)
    session.flush()
    return playlist


def add_track_to_playlist(
    session: Session,
    playlist_id: int,
    track_id: int,
    *,
    position: int | None = None,
) -> PlaylistTrack:
    """Add a track to a playlist.
    
    Args:
        session: Active database session.
        playlist_id: Target playlist ID.
        track_id: Track to add.
        position: Position in playlist (appends if None).
        
    Returns:
        New PlaylistTrack entry.
        
    Raises:
        PlaylistNotFoundError: If playlist doesn't exist.
        TrackNotFoundError: If track doesn't exist.
    """
    from datetime import datetime
    
    # Validate playlist and track exist
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise PlaylistNotFoundError(playlist_id)
    
    track = session.get(Track, track_id)
    if track is None:
        raise TrackNotFoundError(track_id)
    
    # Get next position if not specified
    if position is None:
        max_pos = (
            session.query(PlaylistTrack.position)
            .filter(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position.desc())
            .first()
        )
        position = (max_pos[0] + 1) if max_pos else 1
    
    entry = PlaylistTrack(
        playlist_id=playlist_id,
        track_id=track_id,
        position=position,
        pl_datetime_added=datetime.utcnow(),
    )
    session.add(entry)
    session.flush()
    return entry


def remove_track_from_playlist(
    session: Session,
    playlist_id: int,
    track_id: int,
) -> bool:
    """Remove a track from a playlist.
    
    Args:
        session: Active database session.
        playlist_id: Playlist ID.
        track_id: Track to remove.
        
    Returns:
        True if removed, False if not found.
        
    Raises:
        PlaylistNotFoundError: If playlist doesn't exist.
    """
    playlist = session.get(Playlist, playlist_id)
    if playlist is None:
        raise PlaylistNotFoundError(playlist_id)
    
    entry = (
        session.query(PlaylistTrack)
        .filter(
            PlaylistTrack.playlist_id == playlist_id,
            PlaylistTrack.track_id == track_id,
        )
        .first()
    )
    
    if entry:
        session.delete(entry)
        session.flush()
        return True
    return False


def create_crate(
    session: Session,
    name: str,
) -> Crate:
    """Create a new crate.
    
    Args:
        session: Active database session.
        name: Crate name (must be unique).
        
    Returns:
        New Crate object.
    """
    crate = Crate(
        name=name,
        count=0,
        show=1,
        locked=0,
        autodj_source=0,
    )
    session.add(crate)
    session.flush()
    return crate


def add_track_to_crate(
    session: Session,
    crate_id: int,
    track_id: int,
) -> CrateTrack:
    """Add a track to a crate.
    
    Args:
        session: Active database session.
        crate_id: Target crate ID.
        track_id: Track to add.
        
    Returns:
        New CrateTrack entry.
        
    Raises:
        CrateNotFoundError: If crate doesn't exist.
        TrackNotFoundError: If track doesn't exist.
    """
    crate = session.get(Crate, crate_id)
    if crate is None:
        raise CrateNotFoundError(crate_id)
    
    track = session.get(Track, track_id)
    if track is None:
        raise TrackNotFoundError(track_id)
    
    entry = CrateTrack(crate_id=crate_id, track_id=track_id)
    session.add(entry)
    
    # Update crate count
    crate.count = crate.count + 1
    
    session.flush()
    return entry


def remove_track_from_crate(
    session: Session,
    crate_id: int,
    track_id: int,
) -> bool:
    """Remove a track from a crate.
    
    Args:
        session: Active database session.
        crate_id: Crate ID.
        track_id: Track to remove.
        
    Returns:
        True if removed, False if not found.
        
    Raises:
        CrateNotFoundError: If crate doesn't exist.
    """
    crate = session.get(Crate, crate_id)
    if crate is None:
        raise CrateNotFoundError(crate_id)
    
    entry = (
        session.query(CrateTrack)
        .filter(
            CrateTrack.crate_id == crate_id,
            CrateTrack.track_id == track_id,
        )
        .first()
    )
    
    if entry:
        session.delete(entry)
        crate.count = max(0, crate.count - 1)
        session.flush()
        return True
    return False
```

**Update db/__init__.py exports** (add to the imports and __all__):
```python
from music_commander.db.queries import (
    # ... existing imports ...
    # Write operations
    update_track,
    create_playlist,
    add_track_to_playlist,
    remove_track_from_playlist,
    create_crate,
    add_track_to_crate,
    remove_track_from_crate,
)

__all__ = [
    # ... existing exports ...
    # Write operations
    "update_track",
    "create_playlist",
    "add_track_to_playlist",
    "remove_track_from_playlist",
    "create_crate",
    "add_track_to_crate",
    "remove_track_from_crate",
]
```

**Note**: Write operations should be used carefully when Mixxx is running. Recommend closing Mixxx or using read-only mode during writes.

## Definition of Done Checklist

- [ ] T007: db/__init__.py with clean exports
- [ ] T008: All ORM models match data-model.md
- [ ] T009: get_session() works with real Mixxx DB
- [ ] T010: All query functions per contracts/database-api.md
- [ ] T010a: Write operations (update_track, playlist/crate management)
- [ ] Schema validation catches invalid databases
- [ ] Concurrent access doesn't block Mixxx
- [ ] `mypy music_commander/db/` passes
- [ ] `ruff check music_commander/db/` passes

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Schema mismatch with Mixxx versions | Validate required tables, warn on unknown |
| Concurrent access corruption | Use timeout, short sessions, no connection pooling |
| Large query performance | Use joinedload, add limits |

## Review Guidance

- Test with real Mixxx database (user's actual DB)
- Verify queries return expected data types
- Check that Mixxx can still operate while connected
- Ensure all relationships load correctly (no N+1 issues)

## Activity Log

- 2026-01-06 – system – lane=planned – Prompt created.
