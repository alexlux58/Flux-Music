"""Metadata read/write via Mutagen, plus optional MusicBrainz enrichment."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger("metadata")


@dataclass(slots=True)
class TrackMetadata:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    album_artist: str | None = None
    track_number: int | None = None
    disc_number: int | None = None
    year: int | None = None
    genre: str | None = None
    bpm: float | None = None
    duration: float | None = None
    source_url: str | None = None
    source_id: str | None = None
    codec: str | None = None
    bitrate: int | None = None
    sample_rate: int | None = None
    artwork_path: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


class MetadataService:
    def read(self, path: Path) -> TrackMetadata:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=True)
        if audio is None:
            return TrackMetadata()

        def first(key: str) -> str | None:
            values = audio.get(key) if audio else None
            if not values:
                return None
            return str(values[0])

        track_no = _parse_int(first("tracknumber"))
        disc_no = _parse_int(first("discnumber"))
        year = _parse_year(first("date") or first("year"))
        info = getattr(audio, "info", None)
        return TrackMetadata(
            title=first("title"),
            artist=first("artist"),
            album=first("album"),
            album_artist=first("albumartist"),
            track_number=track_no,
            disc_number=disc_no,
            year=year,
            genre=first("genre"),
            bpm=_read_bpm(path),
            duration=float(info.length) if info and getattr(info, "length", None) else None,
            bitrate=int(info.bitrate) if info and getattr(info, "bitrate", None) else None,
            sample_rate=int(info.sample_rate)
            if info and getattr(info, "sample_rate", None)
            else None,
        )

    def write(self, path: Path, meta: TrackMetadata, *, artwork: Path | None = None) -> None:
        suffix = path.suffix.lower()
        if suffix in {".mp3"}:
            self._write_id3(path, meta, artwork=artwork)
        elif suffix in {".m4a", ".mp4", ".aac"}:
            self._write_mp4(path, meta, artwork=artwork)
        elif suffix in {".opus", ".ogg"}:
            self._write_ogg(path, meta, artwork=artwork)
        elif suffix in {".flac"}:
            self._write_flac(path, meta, artwork=artwork)
        elif suffix in {".wav", ".wave"}:
            self._write_wave(path, meta, artwork=artwork)
        elif suffix in {".aiff", ".aif"}:
            self._write_aiff(path, meta, artwork=artwork)
        else:
            # Easy tags fallback for unsupported write containers
            self._write_easy(path, meta)
        logger.info("Wrote metadata to %s", path)

    def enrich_from_ytdlp(self, base: TrackMetadata, raw: dict[str, Any]) -> TrackMetadata:
        return TrackMetadata(
            title=base.title or raw.get("track") or raw.get("title"),
            artist=base.artist or raw.get("artist") or raw.get("uploader") or raw.get("channel"),
            album=base.album or raw.get("album"),
            album_artist=base.album_artist or raw.get("album_artist") or raw.get("artist"),
            track_number=base.track_number or raw.get("track_number") or raw.get("playlist_index"),
            disc_number=base.disc_number,
            year=base.year or _year_from_upload(raw.get("upload_date") or raw.get("release_year")),
            genre=base.genre or raw.get("genre"),
            bpm=base.bpm,
            duration=base.duration or (float(raw["duration"]) if raw.get("duration") else None),
            source_url=base.source_url or raw.get("webpage_url"),
            source_id=base.source_id or raw.get("id"),
            artwork_path=base.artwork_path,
            codec=base.codec,
            bitrate=base.bitrate,
            sample_rate=base.sample_rate,
        )

    def lookup_musicbrainz(self, artist: str, title: str) -> TrackMetadata | None:
        try:
            import musicbrainzngs
        except ImportError:
            return None
        musicbrainzngs.set_useragent("MusicLibrary", "0.1.0", "https://localhost")
        try:
            result = musicbrainzngs.search_recordings(artist=artist, recording=title, limit=1)
        except Exception as exc:
            logger.warning("MusicBrainz lookup failed: %s", exc)
            return None
        recordings = result.get("recording-list") or []
        if not recordings:
            return None
        rec = recordings[0]
        album = None
        year = None
        releases = rec.get("release-list") or []
        if releases:
            album = releases[0].get("title")
            date = releases[0].get("date")
            if date and len(date) >= 4 and date[:4].isdigit():
                year = int(date[:4])
        credit = rec.get("artist-credit") or []
        artist_name = credit[0]["artist"]["name"] if credit else artist
        return TrackMetadata(
            title=rec.get("title") or title,
            artist=artist_name,
            album=album,
            year=year,
        )

    def _write_easy(self, path: Path, meta: TrackMetadata) -> None:
        from mutagen import File as MutagenFile

        audio = MutagenFile(path, easy=True)
        if audio is None:
            return
        mapping = {
            "title": meta.title,
            "artist": meta.artist,
            "album": meta.album,
            "albumartist": meta.album_artist,
            "genre": meta.genre,
        }
        for key, value in mapping.items():
            if value:
                audio[key] = value
        if meta.track_number is not None:
            audio["tracknumber"] = str(meta.track_number)
        if meta.disc_number is not None:
            audio["discnumber"] = str(meta.disc_number)
        if meta.bpm is not None:
            audio["bpm"] = str(meta.bpm)
        if meta.year is not None:
            audio["date"] = str(meta.year)
        audio.save()

    def _write_id3(self, path: Path, meta: TrackMetadata, *, artwork: Path | None) -> None:
        from mutagen.id3 import APIC, ID3, TALB, TBPM, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK
        from mutagen.mp3 import MP3

        audio = MP3(path)
        if audio.tags is None:
            audio.add_tags()
        assert audio.tags is not None
        tags: ID3 = audio.tags
        if meta.title:
            tags["TIT2"] = TIT2(encoding=3, text=meta.title)
        if meta.artist:
            tags["TPE1"] = TPE1(encoding=3, text=meta.artist)
        if meta.album:
            tags["TALB"] = TALB(encoding=3, text=meta.album)
        if meta.album_artist:
            tags["TPE2"] = TPE2(encoding=3, text=meta.album_artist)
        if meta.genre:
            tags["TCON"] = TCON(encoding=3, text=meta.genre)
        if meta.bpm is not None:
            tags["TBPM"] = TBPM(encoding=3, text=str(round(meta.bpm)))
        if meta.year is not None:
            tags["TDRC"] = TDRC(encoding=3, text=str(meta.year))
        if meta.track_number is not None:
            tags["TRCK"] = TRCK(encoding=3, text=str(meta.track_number))
        if meta.disc_number is not None:
            tags["TPOS"] = TPOS(encoding=3, text=str(meta.disc_number))
        if artwork and artwork.is_file():
            mime = "image/png" if artwork.suffix.lower() == ".png" else "image/jpeg"
            tags["APIC"] = APIC(
                encoding=3,
                mime=mime,
                type=3,
                desc="Cover",
                data=artwork.read_bytes(),
            )
        audio.save()

    def _write_mp4(self, path: Path, meta: TrackMetadata, *, artwork: Path | None) -> None:
        from mutagen.mp4 import MP4, MP4Cover

        audio = MP4(path)
        if audio.tags is None:
            audio.add_tags()
        assert audio.tags is not None
        if meta.title:
            audio.tags["\xa9nam"] = [meta.title]
        if meta.artist:
            audio.tags["\xa9ART"] = [meta.artist]
        if meta.album:
            audio.tags["\xa9alb"] = [meta.album]
        if meta.album_artist:
            audio.tags["aART"] = [meta.album_artist]
        if meta.genre:
            audio.tags["\xa9gen"] = [meta.genre]
        if meta.bpm is not None:
            audio.tags["tmpo"] = [round(meta.bpm)]
        if meta.year is not None:
            audio.tags["\xa9day"] = [str(meta.year)]
        if meta.track_number is not None:
            audio.tags["trkn"] = [(meta.track_number, 0)]
        if meta.disc_number is not None:
            audio.tags["disk"] = [(meta.disc_number, 0)]
        if artwork and artwork.is_file():
            fmt = MP4Cover.FORMAT_PNG if artwork.suffix.lower() == ".png" else MP4Cover.FORMAT_JPEG
            audio.tags["covr"] = [MP4Cover(artwork.read_bytes(), imageformat=fmt)]
        audio.save()

    def _write_ogg(self, path: Path, meta: TrackMetadata, *, artwork: Path | None) -> None:
        from mutagen.oggopus import OggOpus
        from mutagen.oggvorbis import OggVorbis

        audio = OggOpus(path) if path.suffix.lower() == ".opus" else OggVorbis(path)
        mapping = {
            "TITLE": meta.title,
            "ARTIST": meta.artist,
            "ALBUM": meta.album,
            "ALBUMARTIST": meta.album_artist,
            "GENRE": meta.genre,
        }
        for key, value in mapping.items():
            if value:
                audio[key] = [value]
        if meta.track_number is not None:
            audio["TRACKNUMBER"] = [str(meta.track_number)]
        if meta.disc_number is not None:
            audio["DISCNUMBER"] = [str(meta.disc_number)]
        if meta.bpm is not None:
            audio["BPM"] = [str(meta.bpm)]
        if meta.year is not None:
            audio["DATE"] = [str(meta.year)]
        audio.save()
        if artwork:
            logger.debug("Artwork embedding skipped for Ogg/Opus container at %s", path)

    def _write_flac(self, path: Path, meta: TrackMetadata, *, artwork: Path | None) -> None:
        from mutagen.flac import FLAC, Picture

        audio = FLAC(path)
        mapping = {
            "title": meta.title,
            "artist": meta.artist,
            "album": meta.album,
            "albumartist": meta.album_artist,
            "genre": meta.genre,
        }
        for key, value in mapping.items():
            if value:
                audio[key] = value
        if meta.track_number is not None:
            audio["tracknumber"] = str(meta.track_number)
        if meta.disc_number is not None:
            audio["discnumber"] = str(meta.disc_number)
        if meta.bpm is not None:
            audio["bpm"] = str(meta.bpm)
        if meta.year is not None:
            audio["date"] = str(meta.year)
        if artwork and artwork.is_file():
            picture = Picture()
            picture.type = 3
            picture.mime = "image/png" if artwork.suffix.lower() == ".png" else "image/jpeg"
            picture.data = artwork.read_bytes()
            audio.clear_pictures()
            audio.add_picture(picture)
        audio.save()

    def _write_wave(self, path: Path, meta: TrackMetadata, *, artwork: Path | None) -> None:
        from mutagen.id3 import APIC, ID3, TALB, TBPM, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK
        from mutagen.wave import WAVE

        audio = WAVE(path)
        if audio.tags is None:
            audio.add_tags()
        assert audio.tags is not None
        tags: ID3 = audio.tags
        if meta.title:
            tags["TIT2"] = TIT2(encoding=3, text=meta.title)
        if meta.artist:
            tags["TPE1"] = TPE1(encoding=3, text=meta.artist)
        if meta.album:
            tags["TALB"] = TALB(encoding=3, text=meta.album)
        if meta.album_artist:
            tags["TPE2"] = TPE2(encoding=3, text=meta.album_artist)
        if meta.genre:
            tags["TCON"] = TCON(encoding=3, text=meta.genre)
        if meta.bpm is not None:
            tags["TBPM"] = TBPM(encoding=3, text=str(round(meta.bpm)))
        if meta.year is not None:
            tags["TDRC"] = TDRC(encoding=3, text=str(meta.year))
        if meta.track_number is not None:
            tags["TRCK"] = TRCK(encoding=3, text=str(meta.track_number))
        if meta.disc_number is not None:
            tags["TPOS"] = TPOS(encoding=3, text=str(meta.disc_number))
        if artwork and artwork.is_file():
            mime = "image/png" if artwork.suffix.lower() == ".png" else "image/jpeg"
            tags["APIC"] = APIC(
                encoding=3,
                mime=mime,
                type=3,
                desc="Cover",
                data=artwork.read_bytes(),
            )
        audio.save()

    def _write_aiff(self, path: Path, meta: TrackMetadata, *, artwork: Path | None) -> None:
        from mutagen.aiff import AIFF
        from mutagen.id3 import APIC, ID3, TALB, TBPM, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK

        audio = AIFF(path)
        if audio.tags is None:
            audio.add_tags()
        assert audio.tags is not None
        tags: ID3 = audio.tags
        if meta.title:
            tags["TIT2"] = TIT2(encoding=3, text=meta.title)
        if meta.artist:
            tags["TPE1"] = TPE1(encoding=3, text=meta.artist)
        if meta.album:
            tags["TALB"] = TALB(encoding=3, text=meta.album)
        if meta.album_artist:
            tags["TPE2"] = TPE2(encoding=3, text=meta.album_artist)
        if meta.genre:
            tags["TCON"] = TCON(encoding=3, text=meta.genre)
        if meta.bpm is not None:
            tags["TBPM"] = TBPM(encoding=3, text=str(round(meta.bpm)))
        if meta.year is not None:
            tags["TDRC"] = TDRC(encoding=3, text=str(meta.year))
        if meta.track_number is not None:
            tags["TRCK"] = TRCK(encoding=3, text=str(meta.track_number))
        if meta.disc_number is not None:
            tags["TPOS"] = TPOS(encoding=3, text=str(meta.disc_number))
        if artwork and artwork.is_file():
            mime = "image/png" if artwork.suffix.lower() == ".png" else "image/jpeg"
            tags["APIC"] = APIC(
                encoding=3,
                mime=mime,
                type=3,
                desc="Cover",
                data=artwork.read_bytes(),
            )
        audio.save()


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    part = value.split("/")[0].strip()
    return int(part) if part.isdigit() else None


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    digits = "".join(ch for ch in value[:4] if ch.isdigit())
    return int(digits) if len(digits) == 4 else None


def _year_from_upload(value: object) -> int | None:
    if isinstance(value, int):
        return value if value > 1000 else None
    if isinstance(value, str) and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None


def _read_bpm(path: Path) -> float | None:
    from math import isfinite

    from mutagen import File as MutagenFile

    audio = MutagenFile(path, easy=False)
    if audio is None or audio.tags is None:
        return None
    for key in ("tmpo", "TBPM", "bpm", "BPM"):
        values = audio.tags.get(key)
        if values:
            try:
                bpm = float(str(values[0]))
                return bpm if isfinite(bpm) and 30 <= bpm <= 300 else None
            except (ValueError, TypeError, IndexError):
                return None
    return None
