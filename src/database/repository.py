"""Repository layer — GUI and services talk to this, not SQLAlchemy directly."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from src.database.models import (
    Album,
    Artist,
    DownloadJob,
    Playlist,
    PlaylistTrack,
    Setting,
    Track,
    new_uuid,
)


def normalize_text(value: str | None) -> str:
    text = (value or "").casefold().strip()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text)


class LibraryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_artist(self, name: str) -> Artist:
        clean = name.strip() or "Unknown Artist"
        existing = self.session.execute(
            select(Artist).where(Artist.name == clean)
        ).scalar_one_or_none()
        if existing:
            return existing
        artist = Artist(name=clean, sort_name=clean.casefold())
        self.session.add(artist)
        self.session.flush()
        return artist

    def get_or_create_album(
        self, title: str, artist: Artist | None, year: int | None = None
    ) -> Album:
        clean = title.strip() or "Unknown Album"
        stmt: Select[tuple[Album]] = select(Album).where(Album.title == clean)
        if artist is None:
            stmt = stmt.where(Album.artist_id.is_(None))
        else:
            stmt = stmt.where(Album.artist_id == artist.id)
        existing = self.session.execute(stmt).scalar_one_or_none()
        if existing:
            return existing
        album = Album(title=clean, artist=artist, year=year)
        self.session.add(album)
        self.session.flush()
        return album

    def add_track(
        self,
        *,
        title: str,
        file_path: Path,
        artist_name: str | None = None,
        album_title: str | None = None,
        album_artist: str | None = None,
        track_number: int | None = None,
        disc_number: int | None = None,
        year: int | None = None,
        genre: str | None = None,
        bpm: float | None = None,
        duration_seconds: float | None = None,
        source_url: str | None = None,
        source_provider: str | None = None,
        source_video_id: str | None = None,
        file_hash: str | None = None,
        artwork_path: str | None = None,
        codec: str | None = None,
        bitrate: int | None = None,
        sample_rate: int | None = None,
    ) -> Track:
        artist = self.get_or_create_artist(artist_name or "Unknown Artist")
        album = None
        if album_title:
            album = self.get_or_create_album(album_title, artist, year=year)

        track = Track(
            uuid=new_uuid(),
            title=title.strip() or "Unknown Title",
            artist=artist,
            album=album,
            album_artist=album_artist or artist.name,
            track_number=track_number,
            disc_number=disc_number,
            year=year,
            genre=genre,
            bpm=bpm,
            duration_seconds=duration_seconds,
            source_url=source_url,
            source_provider=source_provider,
            source_video_id=source_video_id,
            file_path=str(file_path),
            file_hash=file_hash,
            artwork_path=artwork_path,
            codec=codec,
            bitrate=bitrate,
            sample_rate=sample_rate,
            normalized_title=normalize_text(title),
            normalized_artist=normalize_text(artist.name),
        )
        self.session.add(track)
        self.session.flush()
        return track

    def find_by_source(self, provider: str, video_id: str) -> Track | None:
        return self.session.execute(
            select(Track).where(
                Track.source_provider == provider,
                Track.source_video_id == video_id,
            )
        ).scalar_one_or_none()

    def find_by_normalized(self, artist: str, title: str) -> Sequence[Track]:
        return (
            self.session.execute(
                select(Track).where(
                    Track.normalized_artist == normalize_text(artist),
                    Track.normalized_title == normalize_text(title),
                )
            )
            .scalars()
            .all()
        )

    def find_by_hash(self, file_hash: str) -> Track | None:
        return self.session.execute(
            select(Track).where(Track.file_hash == file_hash)
        ).scalar_one_or_none()

    def search_tracks(self, query: str, *, limit: int = 200) -> Sequence[Track]:
        q = f"%{query.strip()}%"
        if not query.strip():
            stmt = (
                select(Track)
                .options(joinedload(Track.artist), joinedload(Track.album))
                .order_by(Track.date_added.desc())
                .limit(limit)
            )
        else:
            stmt = (
                select(Track)
                .options(joinedload(Track.artist), joinedload(Track.album))
                .outerjoin(Artist)
                .outerjoin(Album)
                .where(
                    or_(
                        Track.title.ilike(q),
                        Artist.name.ilike(q),
                        Album.title.ilike(q),
                        Track.genre.ilike(q),
                    )
                )
                .order_by(Track.title)
                .limit(limit)
            )
        return self.session.execute(stmt).unique().scalars().all()

    def list_recent(self, *, limit: int = 50) -> Sequence[Track]:
        stmt = (
            select(Track)
            .options(joinedload(Track.artist), joinedload(Track.album))
            .order_by(Track.date_added.desc())
            .limit(limit)
        )
        return self.session.execute(stmt).unique().scalars().all()

    def list_artists(self) -> Sequence[Artist]:
        return self.session.execute(select(Artist).order_by(Artist.name)).scalars().all()

    def list_albums(self) -> Sequence[Album]:
        return (
            self.session.execute(
                select(Album).options(joinedload(Album.artist)).order_by(Album.title)
            )
            .unique()
            .scalars()
            .all()
        )

    def list_tracks_for_artist(self, artist_id: int) -> Sequence[Track]:
        stmt = (
            select(Track)
            .options(joinedload(Track.artist), joinedload(Track.album))
            .where(Track.artist_id == artist_id)
            .order_by(Track.title)
        )
        return self.session.execute(stmt).unique().scalars().all()

    def list_tracks_for_album(self, album_id: int) -> Sequence[Track]:
        stmt = (
            select(Track)
            .options(joinedload(Track.artist), joinedload(Track.album))
            .where(Track.album_id == album_id)
            .order_by(Track.disc_number, Track.track_number, Track.title)
        )
        return self.session.execute(stmt).unique().scalars().all()

    def artist_track_count(self, artist_id: int) -> int:
        return int(
            self.session.execute(
                select(func.count(Track.id)).where(Track.artist_id == artist_id)
            ).scalar_one()
            or 0
        )

    def album_track_count(self, album_id: int) -> int:
        return int(
            self.session.execute(
                select(func.count(Track.id)).where(Track.album_id == album_id)
            ).scalar_one()
            or 0
        )

    def get_track(self, track_id: int) -> Track | None:
        return (
            self.session.execute(
                select(Track)
                .options(joinedload(Track.artist), joinedload(Track.album))
                .where(Track.id == track_id)
            )
            .unique()
            .scalar_one_or_none()
        )

    def delete_track(self, track_id: int) -> Track | None:
        track = self.get_track(track_id)
        if track is None:
            return None
        self.session.delete(track)
        self.session.flush()
        return track

    def update_track_metadata(self, track_id: int, **fields: object) -> Track | None:
        track = self.get_track(track_id)
        if track is None:
            return None
        allowed = {
            "title",
            "album_artist",
            "track_number",
            "disc_number",
            "year",
            "genre",
            "bpm",
            "artwork_path",
            "codec",
            "bitrate",
            "sample_rate",
            "file_path",
            "duration_seconds",
            "file_hash",
        }
        for key, value in fields.items():
            if key in allowed:
                setattr(track, key, value)
        if "title" in fields:
            track.normalized_title = normalize_text(str(fields["title"]))
        if "artist_name" in fields and isinstance(fields["artist_name"], str):
            artist = self.get_or_create_artist(fields["artist_name"])
            track.artist = artist
            track.normalized_artist = normalize_text(artist.name)
        if "album_title" in fields and isinstance(fields["album_title"], str):
            album = self.get_or_create_album(fields["album_title"], track.artist, year=track.year)
            track.album = album
        self.session.flush()
        return track

    def mark_played(self, track_id: int) -> None:
        track = self.get_track(track_id)
        if track is None:
            return
        track.play_count = (track.play_count or 0) + 1
        track.last_played = datetime.now(UTC)
        self.session.flush()

    # --- Playlists ---

    def create_playlist(self, name: str, description: str | None = None) -> Playlist:
        playlist = Playlist(name=name.strip(), description=description)
        self.session.add(playlist)
        self.session.flush()
        return playlist

    def list_playlists(self) -> Sequence[Playlist]:
        return self.session.execute(select(Playlist).order_by(Playlist.name)).scalars().all()

    def rename_playlist(self, playlist_id: int, name: str) -> Playlist | None:
        playlist = self.session.get(Playlist, playlist_id)
        if playlist is None:
            return None
        playlist.name = name.strip()
        self.session.flush()
        return playlist

    def delete_playlist(self, playlist_id: int) -> bool:
        playlist = self.session.get(Playlist, playlist_id)
        if playlist is None:
            return False
        self.session.delete(playlist)
        self.session.flush()
        return True

    def add_to_playlist(self, playlist_id: int, track_id: int) -> PlaylistTrack:
        max_pos = self.session.execute(
            select(func.max(PlaylistTrack.position)).where(PlaylistTrack.playlist_id == playlist_id)
        ).scalar_one_or_none()
        entry = PlaylistTrack(
            playlist_id=playlist_id,
            track_id=track_id,
            position=(max_pos or 0) + 1,
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def remove_from_playlist(self, playlist_id: int, track_id: int) -> bool:
        entry = self.session.execute(
            select(PlaylistTrack).where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id,
            )
        ).scalar_one_or_none()
        if entry is None:
            return False
        self.session.delete(entry)
        self.session.flush()
        return True

    def playlist_tracks(self, playlist_id: int) -> Sequence[Track]:
        stmt = (
            select(Track)
            .join(PlaylistTrack)
            .options(joinedload(Track.artist), joinedload(Track.album))
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position)
        )
        return self.session.execute(stmt).unique().scalars().all()

    def reorder_playlist(self, playlist_id: int, track_ids: Sequence[int]) -> None:
        entries = (
            self.session.execute(
                select(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist_id)
            )
            .scalars()
            .all()
        )
        by_track = {e.track_id: e for e in entries}
        for position, track_id in enumerate(track_ids, start=1):
            if track_id in by_track:
                by_track[track_id].position = position
        self.session.flush()

    # --- Downloads ---

    def create_download_job(
        self,
        *,
        url: str,
        title: str | None = None,
        artist: str | None = None,
        source_provider: str | None = None,
        source_video_id: str | None = None,
        playlist_group: str | None = None,
        selected: bool = True,
    ) -> DownloadJob:
        job = DownloadJob(
            uuid=new_uuid(),
            url=url,
            title=title,
            artist=artist,
            source_provider=source_provider,
            source_video_id=source_video_id,
            playlist_group=playlist_group,
            selected=selected,
            status="queued",
        )
        self.session.add(job)
        self.session.flush()
        return job

    def list_downloads(self, *, include_completed: bool = True) -> Sequence[DownloadJob]:
        stmt = select(DownloadJob).order_by(DownloadJob.created_at.desc())
        if not include_completed:
            stmt = stmt.where(DownloadJob.status.notin_(("complete", "cancelled")))
        return self.session.execute(stmt).scalars().all()

    def update_download(self, job_id: int, **fields: object) -> DownloadJob | None:
        job = self.session.get(DownloadJob, job_id)
        if job is None:
            return None
        for key, value in fields.items():
            if hasattr(job, key):
                setattr(job, key, value)
        job.updated_at = datetime.now(UTC)
        self.session.flush()
        return job

    def clear_completed_downloads(self) -> int:
        jobs = (
            self.session.execute(
                select(DownloadJob).where(DownloadJob.status.in_(("complete", "cancelled")))
            )
            .scalars()
            .all()
        )
        count = len(jobs)
        for job in jobs:
            self.session.delete(job)
        self.session.flush()
        return count

    # --- Settings ---

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.session.get(Setting, key)
        return row.value if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.session.merge(Setting(key=key, value=value))
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
