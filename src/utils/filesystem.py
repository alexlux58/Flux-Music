"""Filesystem helpers: sanitization, safe paths, unique names."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")


def sanitize_filename(name: str, *, max_length: int = 120, fallback: str = "untitled") -> str:
    """Sanitize a single path segment for Windows, Linux, and macOS."""
    text = unicodedata.normalize("NFKC", name or "")
    text = INVALID_CHARS.sub("", text)
    text = text.replace("\u202a", "").replace("\u202c", "")
    text = WHITESPACE.sub(" ", text).strip(" .")
    if not text:
        text = fallback
    if text.upper() in WINDOWS_RESERVED:
        text = f"_{text}"
    if len(text) > max_length:
        text = text[:max_length].rstrip(" .")
    return text or fallback


def ensure_within(base: Path, candidate: Path) -> Path:
    """Resolve candidate and ensure it stays under base (no traversal)."""
    base_resolved = base.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base_resolved)
    except ValueError as exc:
        msg = f"Path escapes allowed directory: {candidate}"
        raise ValueError(msg) from exc
    return resolved


def unique_path(path: Path) -> Path:
    """Return path, or path with a numeric suffix if it already exists."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    index = 2
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def disk_free_bytes(path: Path) -> int | None:
    try:
        usage = path.resolve().anchor
        import shutil

        return shutil.disk_usage(usage).free
    except OSError:
        return None
