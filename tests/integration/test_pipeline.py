"""Integration: mock download → organize → database."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.config import load_config
from src.database.migrations import make_engine, make_session_factory, run_migrations
from src.database.repository import LibraryRepository
from src.services.downloader import MediaEntry
from src.services.metadata import MetadataService, TrackMetadata
from src.services.organizer import LibraryOrganizer
from src.services.pipeline import DownloadPipeline


class FakeDownloader:
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path

    def preview(self, url: str) -> MediaEntry:
        return MediaEntry(
            id="videoid12345",
            title="Integration Track",
            url=url,
            uploader="Integration Artist",
            duration=12.0,
            album="Integration Album",
            track_number=1,
            raw={"id": "videoid12345", "title": "Integration Track", "webpage_url": url},
        )

    def download_audio(self, url: str, output_dir: Path, **kwargs: Any) -> Path:
        _ = url, kwargs
        target = output_dir / "videoid12345.m4a"
        target.write_bytes(self.file_path.read_bytes())
        return target

    def extract_info(self, url: str, *, download: bool = False) -> dict[str, Any]:
        _ = url, download
        return {"id": "videoid12345", "title": "Integration Track"}


class FakeAudio:
    def probe(self, path: Path) -> Any:
        _ = path
        from src.services.audio_processor import ProbeResult

        return ProbeResult(
            codec="aac",
            bitrate=256000,
            sample_rate=44100,
            duration=12.0,
            format_name="ipod",
            raw={},
        )


class FakeTempo:
    def __init__(self, mode: str) -> None:
        self.mode = mode

    def estimate(self, path: Path) -> float | None:
        assert path.is_file()
        if self.mode == "failed":
            raise RuntimeError("Cannot decode tempo")
        if self.mode == "unknown":
            return None
        return 123.4


class FakeArtwork:
    def download(self, url: str | None, *, stem: str) -> Path | None:
        _ = url, stem
        return None


@pytest.mark.integration
@pytest.mark.parametrize("tempo_mode", ["detected", "unknown", "failed"])
def test_pipeline_mock_download(tmp_path: Path, tempo_mode: str) -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = load_config(root=root)
    cfg.paths.music_root = tmp_path / "music"
    cfg.paths.temp_dir = tmp_path / "tmp"
    cfg.paths.copy_roots = [tmp_path / "nas"]
    cfg.paths.copy_roots[0].mkdir()
    cfg.paths.database = tmp_path / "lib.db"
    cfg.metadata.provider = "none"
    cfg.paths.music_root.mkdir()
    cfg.paths.temp_dir.mkdir()

    sample = tmp_path / "sample.m4a"
    # Minimal non-empty placeholder file (metadata write may no-op / soft-fail)
    sample.write_bytes(b"\x00" * 128)

    engine = make_engine(cfg.paths.database)
    run_migrations(engine)
    session = make_session_factory(engine)()
    repo = LibraryRepository(session)

    class SoftMetadata(MetadataService):
        def write(self, path: Path, meta: TrackMetadata, *, artwork: Path | None = None) -> None:
            _ = path, meta, artwork
            return

    pipeline = DownloadPipeline(
        cfg,
        repo,
        downloader=FakeDownloader(sample),  # type: ignore[arg-type]
        audio=FakeAudio(),  # type: ignore[arg-type]
        metadata=SoftMetadata(),
        tempo=FakeTempo(tempo_mode),  # type: ignore[arg-type]
        artwork=FakeArtwork(),  # type: ignore[arg-type]
        organizer=LibraryOrganizer(cfg.paths.music_root, cfg.organization),
    )

    result = pipeline.run("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert not result.skipped
    assert result.file_path.exists()
    assert "Integration Artist" in str(result.file_path)
    category = "120-129 BPM" if tempo_mode == "detected" else "Unknown BPM"
    assert category in str(result.file_path)
    assert repo.get_track(result.track_id).bpm == (123.4 if tempo_mode == "detected" else None)
    assert repo.find_by_source("youtube", "videoid12345") is not None
    nas_copy = cfg.paths.copy_roots[0] / result.file_path.relative_to(cfg.paths.music_root)
    assert nas_copy.read_bytes() == result.file_path.read_bytes()
    nas_copy.unlink()  # only this test fixture: retry must repair a missing copy
    retry = pipeline.run("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert retry.skipped and nas_copy.read_bytes() == result.file_path.read_bytes()
    session.close()
