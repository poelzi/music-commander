"""SQLAlchemy ORM models for Mixxx database."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
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
    track: Mapped[Track | None] = relationship(
        "Track", back_populates="track_location", uselist=False
    )

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
    crate_entries: Mapped[list[CrateTrack]] = relationship("CrateTrack", back_populates="track")

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
        return (
            f"<PlaylistTrack(playlist_id={self.playlist_id}, "
            f"track_id={self.track_id}, position={self.position})>"
        )


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

    crate_id: Mapped[int] = mapped_column(Integer, ForeignKey("crates.id"), primary_key=True)
    track_id: Mapped[int] = mapped_column(Integer, ForeignKey("library.id"), primary_key=True)

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
