"""Local tempo estimation and human-readable BPM folder categories."""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path


def bpm_category(bpm: float | None) -> str:
    if bpm is None or not math.isfinite(bpm) or bpm <= 0:
        return "Unknown BPM"
    lower = int(bpm) // 10 * 10
    return f"{lower:03d}-{lower + 9:03d} BPM"


class TempoAnalyzer:
    """Decode up to three minutes with FFmpeg; analyze offline, without changing audio."""

    def __init__(self, ffmpeg: str | None = None) -> None:
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg")

    def estimate(self, path: Path) -> float | None:
        import numpy as np

        if not self.ffmpeg:
            raise RuntimeError("FFmpeg is required for BPM detection")
        result = subprocess.run(
            [
                self.ffmpeg,
                "-v",
                "error",
                "-i",
                str(path),
                "-t",
                "180",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-f",
                "f32le",
                "-acodec",
                "pcm_f32le",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
            timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        samples = np.frombuffer(result.stdout, dtype="<f4")
        return self.estimate_samples(samples, 22050)

    @staticmethod
    def estimate_samples(samples, rate: int) -> float | None:
        import librosa
        import numpy as np

        if len(samples) < rate * 8 or not np.all(np.isfinite(samples)):
            return None
        if float(np.max(np.abs(samples))) < 1e-5:
            return None
        tempo, beats = librosa.beat.beat_track(y=samples, sr=rate, hop_length=256)
        bpm = float(np.asarray(tempo).reshape(-1)[0])
        if len(beats) < 4 or not math.isfinite(bpm) or not 30 <= bpm <= 300:
            return None
        return round(bpm, 1)
