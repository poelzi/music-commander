# Database API Contract

**Date**: 2026-01-06
**Feature Branch**: `001-core-framework-with`

## Session Management

### get_session

Create a database session for Mixxx database operations.

```python
def get_session(db_path: Path | None = None) -> Session:
    """
    Create a SQLAlchemy session for the Mixxx database.
    
    Args:
        db_path: Path to mixxxdb.sqlite. Uses config default if None.
        
    Returns:
        SQLAlchemy Session configured for concurrent access.
        
    Raises:
        DatabaseNotFoundError: If database file doesn't exist.
        SchemaVersionError: If database schema is incompatible.
    """
```

### Context Manager Pattern

```python
with get_session() as session:
    tracks = session.query(Track).filter_by(artist="Artist").all()
```

## Track Operations

### query_tracks

```python
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
    """
    Query tracks with optional filters.
    
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
```

### get_track_by_id

```python
def get_track_by_id(session: Session, track_id: int) -> Track | None:
    """
    Get a single track by ID.
    
    Args:
        session: Active database session.
        track_id: Track primary key.
        
    Returns:
        Track object or None if not found.
    """
```

### get_track_by_location

```python
def get_track_by_location(session: Session, file_path: Path) -> Track | None:
    """
    Get a track by its file path.
    
    Args:
        session: Active database session.
        file_path: Absolute path to track file.
        
    Returns:
        Track object or None if not found.
    """
```

### update_track

```python
def update_track(
    session: Session,
    track_id: int,
    *,
    bpm: float | None = None,
    key: str | None = None,
    rating: int | None = None,
    comment: str | None = None,
    genre: str | None = None,
) -> Track:
    """
    Update track metadata.
    
    Args:
        session: Active database session.
        track_id: Track to update.
        **kwargs: Fields to update (only non-None values applied).
        
    Returns:
        Updated Track object.
        
    Raises:
        TrackNotFoundError: If track_id doesn't exist.
        ValidationError: If values are out of range (e.g., rating > 5).
    """
```

## Playlist Operations

### list_playlists

```python
def list_playlists(
    session: Session,
    *,
    include_hidden: bool = False,
) -> list[Playlist]:
    """
    List all playlists.
    
    Args:
        session: Active database session.
        include_hidden: Include hidden playlists.
        
    Returns:
        List of Playlist objects ordered by position.
    """
```

### get_playlist_tracks

```python
def get_playlist_tracks(
    session: Session,
    playlist_id: int,
) -> list[Track]:
    """
    Get all tracks in a playlist, ordered by position.
    
    Args:
        session: Active database session.
        playlist_id: Playlist primary key.
        
    Returns:
        List of Track objects in playlist order.
        
    Raises:
        PlaylistNotFoundError: If playlist_id doesn't exist.
    """
```

### create_playlist

```python
def create_playlist(
    session: Session,
    name: str,
    *,
    hidden: bool = False,
) -> Playlist:
    """
    Create a new playlist.
    
    Args:
        session: Active database session.
        name: Playlist name.
        hidden: Whether playlist is hidden.
        
    Returns:
        New Playlist object.
        
    Raises:
        ValidationError: If name is empty.
    """
```

### add_track_to_playlist

```python
def add_track_to_playlist(
    session: Session,
    playlist_id: int,
    track_id: int,
    position: int | None = None,
) -> PlaylistTrack:
    """
    Add a track to a playlist.
    
    Args:
        session: Active database session.
        playlist_id: Target playlist.
        track_id: Track to add.
        position: Insert position (None = append at end).
        
    Returns:
        New PlaylistTrack junction object.
        
    Raises:
        PlaylistNotFoundError: If playlist doesn't exist.
        TrackNotFoundError: If track doesn't exist.
        PlaylistLockedError: If playlist is locked.
    """
```

### remove_track_from_playlist

```python
def remove_track_from_playlist(
    session: Session,
    playlist_id: int,
    track_id: int,
) -> None:
    """
    Remove a track from a playlist.
    
    Args:
        session: Active database session.
        playlist_id: Target playlist.
        track_id: Track to remove.
        
    Raises:
        PlaylistNotFoundError: If playlist doesn't exist.
        TrackNotInPlaylistError: If track not in playlist.
        PlaylistLockedError: If playlist is locked.
    """
```

## Crate Operations

### list_crates

```python
def list_crates(
    session: Session,
    *,
    include_hidden: bool = False,
) -> list[Crate]:
    """
    List all crates.
    
    Args:
        session: Active database session.
        include_hidden: Include hidden crates (show=0).
        
    Returns:
        List of Crate objects.
    """
```

### get_crate_tracks

```python
def get_crate_tracks(
    session: Session,
    crate_id: int,
) -> list[Track]:
    """
    Get all tracks in a crate (unordered).
    
    Args:
        session: Active database session.
        crate_id: Crate primary key.
        
    Returns:
        List of Track objects in crate.
        
    Raises:
        CrateNotFoundError: If crate_id doesn't exist.
    """
```

### add_track_to_crate / remove_track_from_crate

```python
def add_track_to_crate(session: Session, crate_id: int, track_id: int) -> None:
    """Add track to crate. Raises CrateNotFoundError, TrackNotFoundError, CrateLockedError."""

def remove_track_from_crate(session: Session, crate_id: int, track_id: int) -> None:
    """Remove track from crate. Raises CrateNotFoundError, TrackNotInCrateError, CrateLockedError."""
```

## Exception Hierarchy

```python
class MusicCommanderError(Exception):
    """Base exception for all music-commander errors."""

class DatabaseError(MusicCommanderError):
    """Database-related errors."""

class DatabaseNotFoundError(DatabaseError):
    """Database file doesn't exist."""

class SchemaVersionError(DatabaseError):
    """Database schema is incompatible."""

class NotFoundError(MusicCommanderError):
    """Requested entity not found."""

class TrackNotFoundError(NotFoundError):
    """Track doesn't exist."""

class PlaylistNotFoundError(NotFoundError):
    """Playlist doesn't exist."""

class CrateNotFoundError(NotFoundError):
    """Crate doesn't exist."""

class ValidationError(MusicCommanderError):
    """Invalid input value."""

class LockedError(MusicCommanderError):
    """Entity is locked and cannot be modified."""

class PlaylistLockedError(LockedError):
    """Playlist is locked."""

class CrateLockedError(LockedError):
    """Crate is locked."""
```
