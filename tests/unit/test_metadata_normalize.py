"""Metadata normalization helpers."""

from src.database.repository import normalize_text
from src.services.duplicate_detector import DuplicateDetector


def test_normalize_text() -> None:
    assert normalize_text("  Hello, World! ") == "hello world"
    assert normalize_text("Ańdré") == "ańdré".casefold()


def test_same_normalized() -> None:
    assert DuplicateDetector.same_normalized("The Band", "Song!", "the band", "song")
    assert not DuplicateDetector.same_normalized("A", "One", "B", "Two")
