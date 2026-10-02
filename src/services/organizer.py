"""Organize downloaded files into Artist/Album folders."""

from __future__ import annotations

import shutil
from pathlib import Path

from src.config import OrganizationConfig
from src.services.metadata import TrackMetadata
from src.services.tempo import bpm_category
from src.utils.filesystem import ensure_dir, ensure_within, sanitize_filename, unique_path
from src.utils.logging import get_logger

logger = get_logger("organizer")


class LibraryOrganizer:
    def __init__(self, music_root: Path, config: OrganizationConfig) -> None:
        self.music_root = ensure_dir(music_root)
        self.config = config

    def destination_for(self, meta: TrackMetadata, *, extension: str, unique: bool = True) -> Path:
        artist = sanitize_filename(meta.artist or "Unknown Artist")
        is_single = not meta.album
        album = sanitize_filename(meta.album or self.config.singles_album)
        if is_single or album == self.config.singles_album:
            filename = sanitize_filename(
                self.config.singles_filename_template.format(title=meta.title or "Unknown Title")
            )
        else:
            track = meta.track_number or 0
            filename = sanitize_filename(
                self.config.filename_template.format(
                    track=track,
                    title=meta.title or "Unknown Title",
                )
            )
        folder = self.music_root / artist / album
        if self.config.categorize_by_bpm:
            folder = self.music_root / "BPM" / bpm_category(meta.bpm) / artist / album
        ensure_dir(folder)
        target = folder / f"{filename}{extension}"
        ensure_within(self.music_root, target)
        if unique and self.config.never_overwrite:
            target = unique_path(target)
        return target

    def place(self, source: Path, meta: TrackMetadata) -> Path:
        target = self.destination_for(meta, extension=source.suffix.lower())
        if source.resolve() == target.resolve():
            return target
        ensure_dir(target.parent)
        shutil.move(str(source), str(target))
        logger.info("Organized %s -> %s", source.name, target)
        return target
