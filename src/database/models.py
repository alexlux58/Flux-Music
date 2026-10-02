"""SQLAlchemy 2.x models for the music library."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Artist(Base):
    __tablename__ = "artists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    sort_name: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    albums: Mapped[list[Album]] = relationship(back_populates="artist")
    tracks: Mapped[list[Track]] = relationship(back_populates="artist")


class Album(Base):
    __tablename__ = "albums"
    __table_args__ = (UniqueConstraint("artist_id", "title", name="uq_album_artist_title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id"))
    year: Mapped[int | None] = mapped_column(Integer)
    artwork_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    artist: Mapped[Artist | None] = relationship(back_populates="albums")
    tracks: Mapped[list[Track]] = relationship(back_populates="album")


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        UniqueConstraint("source_provider", "source_video_id", name="uq_track_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    artist_id: Mapped[int | None] = mapped_column(ForeignKey("artists.id"))
    album_id: Mapped[int | None] = mapped_column(ForeignKey("albums.id"))
    album_artist: Mapped[str | None] = mapped_column(String(512))
    track_number: Mapped[int | None] = mapped_column(Integer)
    disc_number: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int | None] = mapped_column(Integer)
    genre: Mapped[str | None] = mapped_column(String(256))
    bpm: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_provider: Mapped[str | None] = mapped_column(String(64), index=True)
    source_video_id: Mapped[str | None] = mapped_column(String(128), index=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    artwork_path: Mapped[str | None] = mapped_column(Text)
    codec: Mapped[str | None] = mapped_column(String(64))
    bitrate: Mapped[int | None] = mapped_column(Integer)
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    date_added: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_played: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    normalized_title: Mapped[str | None] = mapped_column(String(512), index=True)
    normalized_artist: Mapped[str | None] = mapped_column(String(512), index=True)

    artist: Mapped[Artist | None] = relationship(back_populates="tracks")
    album: Mapped[Album | None] = relationship(back_populates="tracks")
    playlist_entries: Mapped[list[PlaylistTrack]] = relationship(back_populates="track")


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tracks: Mapped[list[PlaylistTrack]] = relationship(
        back_populates="playlist",
        order_by="PlaylistTrack.position",
        cascade="all, delete-orphan",
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (UniqueConstraint("playlist_id", "position", name="uq_playlist_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    playlist: Mapped[Playlist] = relationship(back_populates="tracks")
    track: Mapped[Track] = relationship(back_populates="playlist_entries")


class DownloadJob(Base):
    __tablename__ = "downloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, default=new_uuid, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(String(512))
    artist: Mapped[str | None] = mapped_column(String(512))
    source_provider: Mapped[str | None] = mapped_column(String(64))
    source_video_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    speed: Mapped[str | None] = mapped_column(String(64))
    eta: Mapped[str | None] = mapped_column(String(64))
    stage: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    playlist_group: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SchemaVersion(Base):
    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
