"""URL validation tests."""

import pytest

from src.utils.validation import (
    extract_video_id,
    is_radio_or_mix_list,
    is_supported_url,
    looks_like_playlist,
    normalize_download_url,
    parse_url_list,
    validate_url,
)


def test_supported_youtube_urls() -> None:
    assert is_supported_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_supported_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
    assert is_supported_url("https://youtu.be/dQw4w9WgXcQ")


def test_rejects_non_youtube() -> None:
    assert not is_supported_url("https://example.com/watch?v=x")
    with pytest.raises(ValueError):
        validate_url("ftp://youtube.com/watch?v=dQw4w9WgXcQ")


def test_playlist_detection() -> None:
    assert looks_like_playlist("https://www.youtube.com/playlist?list=PLxxxxxxxx")
    assert not looks_like_playlist("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not looks_like_playlist(
        "https://music.youtube.com/watch?v=oKOtzIo-uYw&list=RDAMVMoKOtzIo-uYw"
    )


def test_radio_mix_normalized_to_single_video() -> None:
    raw = "https://music.youtube.com/watch?v=oKOtzIo-uYw&list=RDAMVMoKOtzIo-uYw"
    assert extract_video_id(raw) == "oKOtzIo-uYw"
    assert is_radio_or_mix_list("RDAMVMoKOtzIo-uYw")
    assert normalize_download_url(raw) == "https://www.youtube.com/watch?v=oKOtzIo-uYw"
    assert validate_url(raw) == "https://www.youtube.com/watch?v=oKOtzIo-uYw"


def test_parse_url_list_bulk() -> None:
    text = """
    # house set
    https://www.youtube.com/watch?v=dQw4w9WgXcQ
    https://www.youtube.com/watch?v=dQw4w9WgXcQ
    https://example.com/nope
    https://youtu.be/abcdefghijk
    """
    valid, invalid = parse_url_list(text)
    assert valid == [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=abcdefghijk",
    ]
    assert "https://example.com/nope" in invalid
