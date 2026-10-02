"""Explicit, non-destructive BPM organization of the existing catalog."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.config import AppConfig
from src.database.repository import LibraryRepository
from src.services.library_copies import sync_library_copies, verified_copy
from src.services.library_scanner import file_sha256
from src.services.metadata import MetadataService
from src.services.organizer import LibraryOrganizer
from src.services.tempo import TempoAnalyzer
from src.utils.logging import get_logger

logger = get_logger("library_repair")


def organize_existing(
    config: AppConfig,
    repo: LibraryRepository,
    *,
    tempo: TempoAnalyzer | None = None,
    metadata: MetadataService | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, object]:
    """Copies first; redirects catalog entries only after every destination verifies."""
    analyzer = tempo or TempoAnalyzer()
    reader = metadata or MetadataService()
    organizer = LibraryOrganizer(config.paths.music_root, config.organization)
    tracks = list(repo.search_tracks("", limit=1_000_000))
    changed, errors = 0, []
    for index, track in enumerate(tracks, 1):
        try:
            source = Path(track.file_path)
            roots = [config.paths.music_root, *config.paths.copy_roots, *config.paths.read_roots]
            if not any(source.resolve().is_relative_to(root.resolve()) for root in roots):
                raise ValueError(f"Song outside configured library folders: {source}")
            meta = reader.read(source)
            meta.title = track.title
            meta.artist = track.artist.name if track.artist else meta.artist
            meta.album = track.album.title if track.album else meta.album
            meta.track_number = track.track_number
            meta.bpm = track.bpm or meta.bpm
            if meta.bpm is None:
                try:
                    meta.bpm = analyzer.estimate(source)
                except Exception as exc:
                    logger.warning("Tempo unavailable for %s: %s", source, exc)
            target = organizer.destination_for(meta, extension=source.suffix.lower(), unique=False)
            verified_copy(source, target)
            sync_library_copies(target, config.paths.music_root, config.paths.copy_roots)
            repo.update_track_metadata(
                track.id, file_path=str(target), file_hash=file_sha256(target), bpm=meta.bpm
            )
            repo.commit()
            changed += 1
        except Exception as exc:
            repo.rollback()
            errors.append(f"{track.title}: {exc}")
        if progress:
            progress(index, len(tracks))
    return {"organized": changed, "errors": errors}
