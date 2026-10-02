"""Duplicate detection by source ID, normalized title/artist, and file hash."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.database.repository import LibraryRepository, normalize_text


class DuplicateKind(StrEnum):
    SOURCE_ID = "source_id"
    TITLE_ARTIST = "title_artist"
    FILE_HASH = "file_hash"


@dataclass(slots=True)
class DuplicateMatch:
    kind: DuplicateKind
    track_id: int
    title: str
    artist: str | None


class DuplicateDetector:
    def __init__(self, repo: LibraryRepository) -> None:
        self.repo = repo

    def check_source(self, provider: str, video_id: str) -> DuplicateMatch | None:
        track = self.repo.find_by_source(provider, video_id)
        if track is None:
            return None
        return DuplicateMatch(
            kind=DuplicateKind.SOURCE_ID,
            track_id=track.id,
            title=track.title,
            artist=track.artist.name if track.artist else None,
        )

    def check_title_artist(self, artist: str, title: str) -> list[DuplicateMatch]:
        matches = self.repo.find_by_normalized(artist, title)
        return [
            DuplicateMatch(
                kind=DuplicateKind.TITLE_ARTIST,
                track_id=t.id,
                title=t.title,
                artist=t.artist.name if t.artist else None,
            )
            for t in matches
        ]

    def check_hash(self, file_hash: str) -> DuplicateMatch | None:
        track = self.repo.find_by_hash(file_hash)
        if track is None:
            return None
        return DuplicateMatch(
            kind=DuplicateKind.FILE_HASH,
            track_id=track.id,
            title=track.title,
            artist=track.artist.name if track.artist else None,
        )

    @staticmethod
    def same_normalized(a_artist: str, a_title: str, b_artist: str, b_title: str) -> bool:
        return normalize_text(a_artist) == normalize_text(b_artist) and normalize_text(
            a_title
        ) == normalize_text(b_title)
