"""URL and input validation."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

SUPPORTED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}

YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def is_supported_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host in SUPPORTED_HOSTS


def extract_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.lstrip("/").split("/")[0]
        return candidate if YOUTUBE_ID.match(candidate) else None
    qs = parse_qs(parsed.query)
    for key in ("v",):
        values = qs.get(key) or []
        if values and YOUTUBE_ID.match(values[0]):
            return values[0]
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"} and YOUTUBE_ID.match(parts[1]):
        return parts[1]
    return None


def playlist_id(url: str) -> str | None:
    qs = parse_qs(urlparse(url.strip()).query)
    values = qs.get("list") or []
    return values[0] if values else None


def is_radio_or_mix_list(list_id: str | None) -> bool:
    """YouTube Music radio / mix ids typically start with RD (e.g. RDAMVM…)."""
    if not list_id:
        return False
    return list_id.upper().startswith("RD")


def normalize_download_url(url: str) -> str:
    """Return a stable URL suitable for single-track or real-playlist fetch.

    Watch URLs that include a radio/mix ``list=RD…`` parameter hang yt-dlp if
    treated as playlists. Collapse those (and any watch+list pair) to the
    single video. Keep dedicated playlist/channel URLs unchanged.
    """
    cleaned = validate_url(url, normalize=False)
    parsed = urlparse(cleaned)
    path = parsed.path.lower()
    vid = extract_video_id(cleaned)
    list_id = playlist_id(cleaned)

    if "/playlist" in path or "/channel/" in path or "/browse/" in path:
        return cleaned

    if vid:
        # Always prefer the concrete video when a watch id is present.
        return f"https://www.youtube.com/watch?v={vid}"

    if list_id and not is_radio_or_mix_list(list_id):
        return cleaned

    return cleaned


def validate_url(url: str, *, normalize: bool = True) -> str:
    cleaned = url.strip()
    if not cleaned:
        msg = "URL is empty"
        raise ValueError(msg)
    if not is_supported_url(cleaned):
        msg = (
            "Unsupported URL. Use a YouTube or YouTube Music watch, "
            "playlist, or share link you are authorized to download."
        )
        raise ValueError(msg)
    if normalize:
        return normalize_download_url(cleaned)
    return cleaned


def looks_like_playlist(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if "/playlist" in path or "/channel/" in path or "/browse/" in path:
        return True
    list_id = playlist_id(url)
    if not list_id or is_radio_or_mix_list(list_id):
        return False
    # watch?v=…&list=PL… → treat as single video for download queue safety
    return not extract_video_id(url)


def parse_url_list(text: str) -> tuple[list[str], list[str]]:
    """Split pasted text into validated URLs and invalid lines.

    Accepts one URL per line, or whitespace-separated URLs on a line.
    Blank lines and ``#`` comments are ignored.
    """
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        candidates = [part.strip() for part in line.split() if part.strip()]
        for candidate in candidates:
            try:
                url = validate_url(candidate)
            except ValueError:
                invalid.append(candidate)
                continue
            if url not in seen:
                seen.add(url)
                valid.append(url)
    return valid, invalid
