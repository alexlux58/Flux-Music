"""yt-dlp download service (Python API, not shell)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from src.utils.logging import get_logger
from src.utils.validation import validate_url

logger = get_logger("downloader")

ProgressCallback = Callable[[dict[str, Any]], None]


class DownloaderProtocol(Protocol):
    def extract_info(self, url: str, *, download: bool = False) -> dict[str, Any]: ...

    def download_audio(
        self,
        url: str,
        output_dir: Path,
        *,
        format_preference: str = "m4a",
        mp3_bitrate: int = 320,
        progress_callback: ProgressCallback | None = None,
    ) -> Path: ...


@dataclass(slots=True)
class MediaEntry:
    id: str
    title: str
    url: str
    uploader: str | None = None
    duration: float | None = None
    thumbnail: str | None = None
    album: str | None = None
    track_number: int | None = None
    release_year: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass(slots=True)
class PlaylistPreview:
    title: str
    entries: list[MediaEntry]
    webpage_url: str | None = None

    @property
    def track_count(self) -> int:
        return len(self.entries)

    @property
    def total_duration(self) -> float | None:
        durations = [e.duration for e in self.entries if e.duration]
        return float(sum(durations)) if durations else None


class YtDlpDownloader:
    """Application-facing wrapper around the yt-dlp Python API."""

    def __init__(self, *, ffmpeg_location: str | None = None) -> None:
        self.ffmpeg_location = ffmpeg_location

    def _base_opts(self, *, allow_playlist: bool = False) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "ignoreerrors": False,
            "noplaylist": not allow_playlist,
            "socket_timeout": 30,
            "retries": 3,
            "extractor_retries": 3,
        }
        if self.ffmpeg_location:
            opts["ffmpeg_location"] = self.ffmpeg_location
        return opts

    def extract_info(
        self,
        url: str,
        *,
        download: bool = False,
        allow_playlist: bool | None = None,
    ) -> dict[str, Any]:
        import yt_dlp

        from src.utils.validation import looks_like_playlist

        cleaned = validate_url(url)
        playlist = looks_like_playlist(cleaned) if allow_playlist is None else allow_playlist
        opts = self._base_opts(allow_playlist=playlist)
        opts["skip_download"] = not download
        if playlist:
            # Avoid resolving every playlist entry deeply during preview.
            opts["extract_flat"] = "in_playlist"
        logger.info("yt-dlp extract url=%s playlist=%s", cleaned, playlist)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(cleaned, download=download)
        if not isinstance(info, dict):
            msg = "yt-dlp returned no metadata for this URL"
            raise RuntimeError(msg)
        return info

    def preview(self, url: str) -> MediaEntry | PlaylistPreview:
        from src.utils.validation import looks_like_playlist

        cleaned = validate_url(url)
        info = self.extract_info(
            cleaned, download=False, allow_playlist=looks_like_playlist(cleaned)
        )
        if "entries" in info:
            entries: list[MediaEntry] = []
            for item in info.get("entries") or []:
                if not item:
                    continue
                entries.append(self._to_entry(item))
            return PlaylistPreview(
                title=str(info.get("title") or "Playlist"),
                entries=entries,
                webpage_url=info.get("webpage_url") or cleaned,
            )
        return self._to_entry(info)

    def download_audio(
        self,
        url: str,
        output_dir: Path,
        *,
        format_preference: str = "m4a",
        mp3_bitrate: int = 320,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        import yt_dlp

        cleaned = validate_url(url)
        output_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(output_dir / "%(id)s.%(ext)s")

        postprocessors: list[dict[str, Any]] = []
        format_selector = "bestaudio/best"

        if format_preference == "m4a":
            format_selector = "bestaudio[ext=m4a]/bestaudio/best"
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "0",
                }
            )
        elif format_preference == "opus":
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "opus",
                    "preferredquality": "0",
                }
            )
        elif format_preference == "mp3":
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(mp3_bitrate),
                }
            )
        elif format_preference == "flac":
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "flac",
                }
            )
        elif format_preference == "wav":
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }
            )
        elif format_preference == "aiff":
            # yt-dlp FFmpegExtractAudio does not support aiff; extract wav then convert.
            postprocessors.append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }
            )
        # original: leave as bestaudio container from yt-dlp

        opts = self._base_opts(allow_playlist=False)
        opts.update(
            {
                "format": format_selector,
                "outtmpl": outtmpl,
                "noplaylist": True,
                "postprocessors": postprocessors,
            }
        )
        if progress_callback:

            def _hook(status: dict[str, Any]) -> None:
                progress_callback(status)

            opts["progress_hooks"] = [_hook]

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(cleaned, download=True)
            if not isinstance(info, dict):
                msg = "Download produced no metadata"
                raise RuntimeError(msg)
            requested = info.get("requested_downloads") or []
            if requested and requested[0].get("filepath"):
                path = Path(requested[0]["filepath"])
            else:
                path = Path(ydl.prepare_filename(info))
                # After extract audio, extension may change
                for ext in (
                    ".m4a",
                    ".opus",
                    ".mp3",
                    ".flac",
                    ".wav",
                    ".aiff",
                    ".aif",
                    ".webm",
                    ".ogg",
                    path.suffix,
                ):
                    candidate = path.with_suffix(ext)
                    if candidate.exists():
                        path = candidate
                        break

        if not path.exists():
            # Search output dir by id
            vid = str(info.get("id") or "")
            matches = list(output_dir.glob(f"{vid}.*")) if vid else []
            if not matches:
                msg = "Downloaded file not found on disk"
                raise FileNotFoundError(msg)
            path = matches[0]

        if format_preference == "aiff" and path.suffix.lower() != ".aiff":
            from src.services.audio_processor import AudioProcessor

            path = AudioProcessor().convert_to_format(path, target_format="aiff")

        logger.info("Downloaded %s -> %s", cleaned, path)
        return path

    @staticmethod
    def _to_entry(item: dict[str, Any]) -> MediaEntry:
        year = None
        release = item.get("release_year") or item.get("upload_date")
        if isinstance(release, int):
            year = release
        elif isinstance(release, str) and len(release) >= 4 and release[:4].isdigit():
            year = int(release[:4])
        return MediaEntry(
            id=str(item.get("id") or ""),
            title=str(item.get("track") or item.get("title") or "Unknown Title"),
            url=str(item.get("webpage_url") or item.get("url") or ""),
            uploader=item.get("artist") or item.get("uploader") or item.get("channel"),
            duration=float(item["duration"]) if item.get("duration") is not None else None,
            thumbnail=item.get("thumbnail"),
            album=item.get("album"),
            track_number=item.get("track_number") or item.get("playlist_index"),
            release_year=year,
            raw=item,
        )
