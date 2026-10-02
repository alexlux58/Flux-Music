"""End-to-end download → organize → database pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import AppConfig
from src.database.repository import LibraryRepository
from src.services.artwork import ArtworkService
from src.services.audio_processor import AudioProcessor
from src.services.downloader import YtDlpDownloader
from src.services.duplicate_detector import DuplicateDetector
from src.services.library_copies import sync_library_copies
from src.services.library_scanner import file_sha256
from src.services.metadata import MetadataService, TrackMetadata
from src.services.organizer import LibraryOrganizer
from src.services.tempo import TempoAnalyzer
from src.utils.filesystem import ensure_dir
from src.utils.logging import get_logger

logger = get_logger("pipeline")

StageCallback = Callable[[str, float, dict[str, Any]], None]


@dataclass(slots=True)
class PipelineResult:
    track_id: int
    file_path: Path
    skipped: bool = False
    skip_reason: str | None = None


class DownloadPipeline:
    def __init__(
        self,
        config: AppConfig,
        repo: LibraryRepository,
        *,
        downloader: YtDlpDownloader | None = None,
        audio: AudioProcessor | None = None,
        metadata: MetadataService | None = None,
        artwork: ArtworkService | None = None,
        organizer: LibraryOrganizer | None = None,
        tempo: TempoAnalyzer | None = None,
    ) -> None:
        self.config = config
        self.repo = repo
        self.downloader = downloader or YtDlpDownloader()
        self.audio = audio or AudioProcessor()
        self.metadata = metadata or MetadataService()
        self.artwork = artwork or ArtworkService(config.paths.temp_dir / "artwork")
        self.organizer = organizer or LibraryOrganizer(config.paths.music_root, config.organization)
        self.duplicates = DuplicateDetector(repo)
        self.tempo = tempo or TempoAnalyzer()

    def run(
        self,
        url: str,
        *,
        on_stage: StageCallback | None = None,
        allow_duplicate_copy: bool = False,
    ) -> PipelineResult:
        def stage(name: str, progress: float, **extra: Any) -> None:
            if on_stage:
                on_stage(name, progress, extra)

        stage("Retrieving metadata", 0.05)
        preview = self.downloader.preview(url)
        if hasattr(preview, "entries"):
            msg = "Playlist URLs must be expanded into individual jobs first"
            raise ValueError(msg)

        entry = preview
        provider = "youtube"
        video_id = entry.id

        stage("Checking duplicates", 0.1)
        source_hit = self.duplicates.check_source(provider, video_id) if video_id else None
        if (
            source_hit
            and self.config.duplicates.on_source_id_match == "skip"
            and not allow_duplicate_copy
        ):
            existing = self.repo.get_track(source_hit.track_id)
            if existing is None:
                raise RuntimeError("Duplicate song disappeared; refresh the library")
            stage("Verifying library copies", 0.9)
            sync_library_copies(
                Path(existing.file_path),
                self.config.paths.music_root,
                self.config.paths.copy_roots,
                source_roots=self.config.paths.read_roots,
            )
            return PipelineResult(
                track_id=source_hit.track_id,
                file_path=Path(),
                skipped=True,
                skip_reason=f"Already in library (source id match: {source_hit.title})",
            )

        temp = ensure_dir(self.config.paths.temp_dir / "downloads")

        def progress_hook(status: dict[str, Any]) -> None:
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
                downloaded = status.get("downloaded_bytes") or 0
                pct = (downloaded / total) if total else 0.0
                stage(
                    "Downloading",
                    0.15 + min(pct, 1.0) * 0.45,
                    speed=str(status.get("_speed_str") or status.get("speed") or ""),
                    eta=str(status.get("_eta_str") or status.get("eta") or ""),
                )
            elif status.get("status") == "finished":
                stage("Processing", 0.65)

        stage("Downloading", 0.15)
        downloaded = self.downloader.download_audio(
            entry.url or url,
            temp,
            format_preference=self.config.audio.default_format,
            mp3_bitrate=self.config.audio.mp3_bitrate,
            progress_callback=progress_hook,
        )

        stage("Processing", 0.7)
        probe = None
        try:
            probe = self.audio.probe(downloaded)
        except Exception as exc:
            logger.warning("ffprobe failed: %s", exc)

        meta = TrackMetadata(
            title=entry.title,
            artist=entry.uploader,
            album=entry.album,
            album_artist=entry.uploader,
            track_number=entry.track_number,
            year=entry.release_year,
            duration=entry.duration or (probe.duration if probe else None),
            source_url=entry.url or url,
            source_id=video_id,
            codec=probe.codec if probe else downloaded.suffix.lstrip("."),
            bitrate=probe.bitrate if probe else None,
            sample_rate=probe.sample_rate if probe else None,
        )
        meta = self.metadata.enrich_from_ytdlp(meta, entry.raw)

        if self.config.metadata.provider == "musicbrainz" and meta.artist and meta.title:
            stage("Enriching metadata", 0.75)
            enriched = self.metadata.lookup_musicbrainz(meta.artist, meta.title)
            if enriched:
                meta.title = enriched.title or meta.title
                meta.artist = enriched.artist or meta.artist
                meta.album = meta.album or enriched.album
                meta.year = meta.year or enriched.year

        if self.config.organization.categorize_by_bpm:
            stage("Detecting BPM", 0.78)
            try:
                meta.bpm = self.tempo.estimate(downloaded)
            except Exception as exc:
                logger.warning("BPM unavailable; saving under Unknown BPM: %s", exc)

        stage("Embedding metadata", 0.8)
        art_path = None
        if entry.thumbnail:
            art_path = self.artwork.download(
                entry.thumbnail, stem=video_id or meta.title or "cover"
            )
            meta.artwork_path = str(art_path) if art_path else None

        self.metadata.write(
            downloaded, meta, artwork=art_path if self.config.audio.embed_artwork else None
        )

        stage("Organizing library", 0.9)
        final_path = self.organizer.place(downloaded, meta)
        digest = file_sha256(final_path)

        hash_hit = self.duplicates.check_hash(digest)
        if hash_hit and not allow_duplicate_copy:
            logger.info("File hash already in library: %s", hash_hit.title)

        stage("Updating database", 0.95)
        track = self.repo.add_track(
            title=meta.title or "Unknown Title",
            file_path=final_path,
            artist_name=meta.artist,
            album_title=meta.album,
            album_artist=meta.album_artist,
            track_number=meta.track_number,
            disc_number=meta.disc_number,
            year=meta.year,
            genre=meta.genre,
            bpm=meta.bpm,
            duration_seconds=meta.duration,
            source_url=meta.source_url,
            source_provider=provider,
            source_video_id=video_id,
            file_hash=digest,
            artwork_path=meta.artwork_path,
            codec=meta.codec,
            bitrate=meta.bitrate,
            sample_rate=meta.sample_rate,
        )
        self.repo.commit()
        stage("Saving library copies", 0.98)
        sync_library_copies(final_path, self.config.paths.music_root, self.config.paths.copy_roots)
        stage("Complete", 1.0)
        return PipelineResult(track_id=track.id, file_path=final_path)
