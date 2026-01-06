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
    stmt = select(Track).options(joinedload(Track.track_location)).where(Track.id == track_id)
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
