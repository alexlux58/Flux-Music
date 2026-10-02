"""Startup dependency diagnostics."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from src.services.audio_processor import AudioProcessor


@dataclass(slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_diagnostics(
    *,
    database_path: Path,
    music_root: Path,
    temp_dir: Path,
) -> list[CheckResult]:
    results: list[CheckResult] = []

    results.append(
        CheckResult(
            name="Python",
            ok=sys.version_info >= (3, 12),
            detail=f"{sys.version.split()[0]} ({sys.executable})",
        )
    )

    processor = AudioProcessor()
    ffmpeg_ok, ffprobe_ok = processor.available()
    results.append(
        CheckResult(
            name="FFmpeg",
            ok=ffmpeg_ok,
            detail=processor.ffmpeg or "not found on PATH",
        )
    )
    results.append(
        CheckResult(
            name="ffprobe",
            ok=ffprobe_ok,
            detail=processor.ffprobe or "not found on PATH",
        )
    )

    ytdlp_ok = importlib.util.find_spec("yt_dlp") is not None
    results.append(
        CheckResult(
            name="yt-dlp",
            ok=ytdlp_ok,
            detail="Python package available" if ytdlp_ok else "package missing",
        )
    )

    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        db_ok = database_path.parent.is_dir()
        detail = str(database_path)
    except OSError as exc:
        db_ok = False
        detail = str(exc)
    results.append(CheckResult(name="Database", ok=db_ok, detail=detail))

    try:
        music_root.mkdir(parents=True, exist_ok=True)
        probe = music_root / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        music_ok = True
        music_detail = str(music_root)
    except OSError as exc:
        music_ok = False
        music_detail = str(exc)
    results.append(CheckResult(name="Music directory", ok=music_ok, detail=music_detail))

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_ok = True
        temp_detail = str(temp_dir)
    except OSError as exc:
        temp_ok = False
        temp_detail = str(exc)
    results.append(CheckResult(name="Temp directory", ok=temp_ok, detail=temp_detail))

    which_ffmpeg = shutil.which("ffmpeg")
    if not which_ffmpeg and not ffmpeg_ok:
        results.append(
            CheckResult(
                name="Hint",
                ok=False,
                detail="Install FFmpeg and ensure ffmpeg/ffprobe are on PATH",
            )
        )

    return results
