"""SQLAlchemy ORM models for the local metadata cache."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CacheBase(DeclarativeBase):
    """Base class for cache ORM models."""

    pass


class CacheTrack(CacheBase):
    """Cached metadata for a single git-annex track."""

    __tablename__ = "tracks"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    file: Mapped[str | None] = mapped_column(Text, nullable=True)
    artist: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    album: Mapped[str | None] = mapped_column(Text)
    genre: Mapped[str | None] = mapped_column(Text)
    bpm: Mapped[float | None] = mapped_column(Float)
    rating: Mapped[int | None] = mapped_column(Integer)
    key_musical: Mapped[str | None] = mapped_column(String(32))
    year: Mapped[str | None] = mapped_column(String(16))
    tracknumber: Mapped[str | None] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(String(32))
    present: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    __table_args__ = (
        Index("ix_tracks_bpm", "bpm"),
        Index("ix_tracks_rating", "rating"),
        Index("ix_tracks_year", "year"),
    )

    def __repr__(self) -> str:
        return f"<CacheTrack(key='{self.key[:30]}...', file='{self.file}')>"


class TrackCrate(CacheBase):
    """Multi-value crate membership for a cached track."""

    __tablename__ = "track_crates"

    key: Mapped[str] = mapped_column(
        String(512),
        primary_key=True,
    )
    crate: Mapped[str] = mapped_column(String(256), primary_key=True)

    __table_args__ = (Index("ix_track_crates_crate", "crate"),)

    def __repr__(self) -> str:
        return f"<TrackCrate(key='{self.key[:30]}...', crate='{self.crate}')>"


class CacheState(CacheBase):
    """Singleton row tracking cache freshness."""

    __tablename__ = "cache_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    annex_branch_commit: Mapped[str | None] = mapped_column(String(64))
    last_updated: Mapped[str | None] = mapped_column(String(32))
    track_count: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self) -> str:
        return f"<CacheState(commit='{self.annex_branch_commit}', tracks={self.track_count})>"


# Bandcamp collection models


class BandcampRelease(CacheBase):
    """A purchased release from the user's Bandcamp collection."""

    __tablename__ = "bandcamp_releases"

    sale_item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sale_item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    band_name: Mapped[str] = mapped_column(Text, nullable=False)
    album_title: Mapped[str] = mapped_column(Text, nullable=False)
    band_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redownload_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    purchase_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_discography: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    artwork_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bandcamp_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        Index("ix_bc_release_band_name", "band_name"),
        Index("ix_bc_release_album_title", "album_title"),
    )

    def __repr__(self) -> str:
        return (
            f"<BandcampRelease(id={self.sale_item_id}, "
            f"artist='{self.band_name}', album='{self.album_title}')>"
        )


class BandcampTrack(CacheBase):
    """An individual track within a Bandcamp release."""

    __tablename__ = "bandcamp_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    track_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        Index("ix_bc_track_release_id", "release_id"),
        Index("ix_bc_track_title", "title"),
    )

    def __repr__(self) -> str:
        return f"<BandcampTrack(id={self.id}, title='{self.title}')>"


class BandcampReleaseFormat(CacheBase):
    """An available download format for a Bandcamp release."""

    __tablename__ = "bandcamp_release_formats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[int] = mapped_column(Integer, nullable=False)
    encoding: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        Index(
            "ix_bc_format_release_encoding",
            "release_id",
            "encoding",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<BandcampReleaseFormat(release={self.release_id}, encoding='{self.encoding}')>"


class BandcampSyncState(CacheBase):
    """Singleton tracking Bandcamp collection sync freshness."""

    __tablename__ = "bandcamp_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    fan_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced: Mapped[str] = mapped_column(String(64), nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_token: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<BandcampSyncState(fan_id={self.fan_id}, "
            f"items={self.total_items}, synced='{self.last_synced}')>"
        )
