"""Artwork download and local caching."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

from src.utils.filesystem import ensure_dir, sanitize_filename
from src.utils.logging import get_logger

logger = get_logger("artwork")


class ArtworkService:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = ensure_dir(cache_dir)

    def download(self, url: str | None, *, stem: str) -> Path | None:
        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            logger.warning("Refusing non-http artwork URL")
            return None
        suffix = Path(parsed.path).suffix.lower() or ".jpg"
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        target = self.cache_dir / f"{sanitize_filename(stem)}{suffix}"
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if not content_type.startswith("image/"):
                    logger.warning("Artwork URL did not return an image")
                    return None
                target.write_bytes(response.content)
            return target
        except Exception as exc:
            logger.warning("Artwork download failed: %s", exc)
            return None
