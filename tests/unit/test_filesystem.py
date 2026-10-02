"""Unit tests for filename sanitization."""

from pathlib import Path

from src.utils.filesystem import ensure_within, sanitize_filename, unique_path


def test_sanitize_removes_invalid_chars() -> None:
    assert "<bad>|name?.mp3" not in sanitize_filename("a<b>|c?.mp3")
    assert sanitize_filename("hello/world") == "helloworld"


def test_sanitize_reserved_windows_names() -> None:
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("nul") == "_nul"


def test_sanitize_unicode_and_emoji() -> None:
    name = sanitize_filename("アーティスト 🎵 song")
    assert "アーティスト" in name
    assert "song" in name


def test_sanitize_fallback() -> None:
    assert sanitize_filename("   ") == "untitled"


def test_unique_path(tmp_path: Path) -> None:
    path = tmp_path / "track.m4a"
    path.write_text("a", encoding="utf-8")
    alt = unique_path(path)
    assert alt != path
    assert alt.name == "track (2).m4a"


def test_ensure_within_blocks_traversal(tmp_path: Path) -> None:
    base = tmp_path / "music"
    base.mkdir()
    try:
        ensure_within(base, tmp_path / "other" / "x.m4a")
        raised = False
    except ValueError:
        raised = True
    assert raised
