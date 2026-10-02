"""Lossless convert format helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.services.audio_processor import AudioProcessor


def test_is_lossless_format() -> None:
    assert AudioProcessor.is_lossless_format("wav")
    assert AudioProcessor.is_lossless_format("AIFF")
    assert AudioProcessor.is_lossless_format(".aif")
    assert AudioProcessor.is_lossless_format("flac")
    assert not AudioProcessor.is_lossless_format("mp3")
    assert not AudioProcessor.is_lossless_format("m4a")


def test_convert_to_format_rejects_unknown(tmp_path: Path) -> None:
    source = tmp_path / "track.m4a"
    source.write_bytes(b"not-audio")
    processor = AudioProcessor()
    with pytest.raises(ValueError, match="Unsupported target format"):
        processor.convert_to_format(source, target_format="wma")


def test_convert_to_format_maps_aif_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "track.m4a"
    source.write_bytes(b"not-audio")
    captured: dict[str, object] = {}

    def fake_convert(self, src, destination, *, codec="copy", bitrate=None):
        captured["codec"] = codec
        captured["destination"] = destination
        destination.write_bytes(b"ok")
        return destination

    monkeypatch.setattr(AudioProcessor, "convert", fake_convert)
    out = AudioProcessor().convert_to_format(source, target_format="aif")
    assert captured["codec"] == "pcm_s16be"
    assert out.suffix == ".aiff"


def test_convert_to_format_wav_skips_bitrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "track.mp3"
    source.write_bytes(b"not-audio")

    def fake_convert(self, src, destination, *, codec="copy", bitrate=None):
        assert codec == "pcm_s16le"
        assert bitrate is None
        destination.write_bytes(b"ok")
        return destination

    monkeypatch.setattr(AudioProcessor, "convert", fake_convert)
    out = AudioProcessor().convert_to_format(source, target_format="wav", bitrate_kbps=320)
    assert out.suffix == ".wav"
