"""FFmpeg / ffprobe audio processing via subprocess argument arrays."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.utils.logging import get_logger

logger = get_logger("audio_processor")


@dataclass(slots=True)
class ProbeResult:
    codec: str | None
    bitrate: int | None
    sample_rate: int | None
    duration: float | None
    format_name: str | None
    raw: dict


class AudioProcessor:
    def __init__(self, *, ffmpeg: str | None = None, ffprobe: str | None = None) -> None:
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg")
        self.ffprobe = ffprobe or shutil.which("ffprobe")

    def available(self) -> tuple[bool, bool]:
        return bool(self.ffmpeg), bool(self.ffprobe)

    def probe(self, path: Path) -> ProbeResult:
        if not self.ffprobe:
            msg = "ffprobe is not available"
            raise RuntimeError(msg)
        cmd = [
            self.ffprobe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(completed.stdout or "{}")
        audio = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
            {},
        )
        fmt = data.get("format", {})
        bitrate = audio.get("bit_rate") or fmt.get("bit_rate")
        sample_rate = audio.get("sample_rate")
        duration = fmt.get("duration") or audio.get("duration")
        return ProbeResult(
            codec=audio.get("codec_name"),
            bitrate=int(bitrate) if bitrate else None,
            sample_rate=int(sample_rate) if sample_rate else None,
            duration=float(duration) if duration else None,
            format_name=fmt.get("format_name"),
            raw=data,
        )

    def convert(
        self,
        source: Path,
        destination: Path,
        *,
        codec: str,
        bitrate: str | None = None,
    ) -> Path:
        if not self.ffmpeg:
            msg = "ffmpeg is not available"
            raise RuntimeError(msg)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cmd = [self.ffmpeg, "-y", "-i", str(source), "-vn"]
        if codec == "aac":
            cmd += ["-c:a", "aac"]
            if bitrate:
                cmd += ["-b:a", bitrate]
        elif codec == "libopus":
            cmd += ["-c:a", "libopus"]
            if bitrate:
                cmd += ["-b:a", bitrate]
        elif codec == "libmp3lame":
            cmd += ["-c:a", "libmp3lame"]
            if bitrate:
                cmd += ["-b:a", bitrate]
        elif codec == "flac":
            cmd += ["-c:a", "flac"]
        elif codec == "pcm_s16le":
            cmd += ["-c:a", "pcm_s16le"]
        elif codec == "pcm_s16be":
            cmd += ["-c:a", "pcm_s16be"]
        else:
            cmd += ["-c:a", "copy"]
        cmd.append(str(destination))
        logger.info("FFmpeg convert %s -> %s", source, destination)
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-500:]
            msg = f"FFmpeg convert failed: {detail or completed.returncode}"
            raise RuntimeError(msg)
        return destination

    def convert_to_format(
        self,
        source: Path,
        *,
        target_format: str,
        bitrate_kbps: int | None = None,
        destination: Path | None = None,
    ) -> Path:
        """Re-encode to m4a / mp3 / opus / flac / wav / aiff. Returns the output path."""
        fmt = target_format.lower().lstrip(".")
        if fmt == "aif":
            fmt = "aiff"
        mapping = {
            "m4a": ("aac", ".m4a"),
            "aac": ("aac", ".m4a"),
            "mp3": ("libmp3lame", ".mp3"),
            "opus": ("libopus", ".opus"),
            "flac": ("flac", ".flac"),
            "wav": ("pcm_s16le", ".wav"),
            "aiff": ("pcm_s16be", ".aiff"),
        }
        if fmt not in mapping:
            msg = f"Unsupported target format: {target_format}"
            raise ValueError(msg)
        codec, ext = mapping[fmt]
        out = destination or source.with_suffix(ext)
        if out.resolve() == source.resolve():
            out = source.with_name(f"{source.stem}.reencode{ext}")
        bitrate = None
        if bitrate_kbps and fmt not in {"flac", "wav", "aiff"}:
            bitrate = f"{int(bitrate_kbps)}k"
        self.convert(source, out, codec=codec, bitrate=bitrate)
        return out

    @staticmethod
    def is_lossless_format(fmt: str) -> bool:
        return fmt.lower().lstrip(".") in {"flac", "wav", "aiff", "aif"}

    def measure_loudness(self, path: Path) -> dict[str, float] | None:
        """Optional EBU R128 analysis. Does not rewrite audio."""
        if not self.ffmpeg:
            return None
        cmd = [
            self.ffmpeg,
            "-i",
            str(path),
            "-af",
            "loudnorm=print_format=json",
            "-f",
            "null",
            "-",
        ]
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        stderr = completed.stderr or ""
        start = stderr.rfind("{")
        end = stderr.rfind("}")
        if start < 0 or end < 0:
            return None
        try:
            payload = json.loads(stderr[start : end + 1])
            return {
                "input_i": float(payload.get("input_i", 0)),
                "input_tp": float(payload.get("input_tp", 0)),
                "input_lra": float(payload.get("input_lra", 0)),
                "input_thresh": float(payload.get("input_thresh", 0)),
            }
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
