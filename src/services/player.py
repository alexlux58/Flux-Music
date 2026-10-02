"""Qt Multimedia based audio player service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger("player")


@dataclass(slots=True)
class NowPlaying:
    track_id: int | None
    title: str
    artist: str
    album: str
    path: Path
    artwork_path: str | None = None


class PlayerService:
    """Thin wrapper; UI constructs QMediaPlayer and calls into this for state."""

    def __init__(self) -> None:
        self.queue: list[NowPlaying] = []
        self.index: int = -1
        self.volume: float = 0.8

    def set_queue(self, items: list[NowPlaying], *, start_at: int = 0) -> NowPlaying | None:
        self.queue = items
        self.index = start_at if items else -1
        return self.current()

    def current(self) -> NowPlaying | None:
        if 0 <= self.index < len(self.queue):
            return self.queue[self.index]
        return None

    def next(self) -> NowPlaying | None:
        if self.index + 1 < len(self.queue):
            self.index += 1
            return self.current()
        return None

    def previous(self) -> NowPlaying | None:
        if self.index > 0:
            self.index -= 1
            return self.current()
        return None
