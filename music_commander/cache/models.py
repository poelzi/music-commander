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
