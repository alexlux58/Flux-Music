"""Scan existing local music collections into the database."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from pathlib import Path

from src.database.repository import LibraryRepository
from src.services.metadata import MetadataService
from src.utils.logging import get_logger

logger = get_logger("library_scanner")

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".ogg", ".opus", ".wav", ".aiff", ".aif"}

ProgressFn = Callable[[int, int, Path], None]


class LibraryScanner:
    def __init__(self, repo: LibraryRepository, metadata: MetadataService) -> None:
        self.repo = repo
        self.metadata = metadata

    def iter_audio_files(self, root: Path) -> Iterator[Path]:
        root = root.resolve()
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
                yield path

    def scan(
        self,
        root: Path,
        *,
        compute_hash: bool = True,
        progress: ProgressFn | None = None,
    ) -> int:
        files = list(self.iter_audio_files(root))
        total = len(files)
        imported = 0
        for index, path in enumerate(files, start=1):
            if progress:
                progress(index, total, path)
            digest = file_sha256(path) if compute_hash else None
            if digest and self.repo.find_by_hash(digest):
                continue
            # Also skip if exact path already known
            existing = [
                t
                for t in self.repo.search_tracks(path.stem, limit=20)
                if Path(t.file_path).resolve() == path.resolve()
            ]
            if existing:
                continue
            meta = self.metadata.read(path)
            self.repo.add_track(
                title=meta.title or path.stem,
                file_path=path,
                artist_name=meta.artist or "Unknown Artist",
                album_title=meta.album,
                album_artist=meta.album_artist,
                track_number=meta.track_number,
                disc_number=meta.disc_number,
                year=meta.year,
                genre=meta.genre,
                bpm=meta.bpm,
                duration_seconds=meta.duration,
                file_hash=digest,
                codec=path.suffix.lstrip(".").lower(),
                bitrate=meta.bitrate,
                sample_rate=meta.sample_rate,
            )
            imported += 1
        self.repo.commit()
        logger.info("Imported %s tracks from %s", imported, root)
        return imported


def file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
