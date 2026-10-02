"""Offline tempo estimation, portable configuration and retained catalog migrations."""

from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import text

from src.config import AppConfig, OrganizationConfig, load_config, project_root
from src.database.migrations import make_engine, make_session_factory, run_migrations
from src.database.repository import LibraryRepository
from src.services.library_copies import sync_library_copies
from src.services.library_repair import organize_existing
from src.services.metadata import MetadataService, TrackMetadata
from src.services.organizer import LibraryOrganizer
from src.services.tempo import TempoAnalyzer, bpm_category


@pytest.mark.parametrize("bpm", [75, 90, 120, 150, 180])
def test_regular_beats_detected_with_half_double_tempo_tolerance(bpm):
    rate = 22050
    samples = np.zeros(rate * 16, dtype=np.float32)
    for start in np.arange(0.5, 15.5, 60 / bpm):
        index = int(start * rate)
        length = 512
        pulse = np.sin(np.arange(length) * 2 * np.pi * 1000 / rate)
        samples[index : index + length] = pulse * np.exp(-np.arange(length) / 60)
    detected = TempoAnalyzer.estimate_samples(samples, rate)
    assert detected is not None
    assert min(abs(detected / bpm - factor) for factor in (0.5, 1, 2)) < 0.03
    if bpm == 120:
        assert abs(detected - 120) < 2


def test_silent_short_invalid_audio_is_unknown():
    assert TempoAnalyzer.estimate_samples(np.zeros(22050 * 10), 22050) is None
    assert TempoAnalyzer.estimate_samples(np.ones(22050), 22050) is None
    assert TempoAnalyzer.estimate_samples(np.full(22050 * 10, np.nan), 22050) is None


@pytest.mark.parametrize(
    ("bpm", "expected"),
    [
        (None, "Unknown BPM"),
        (float("nan"), "Unknown BPM"),
        (0, "Unknown BPM"),
        (119.9, "110-119 BPM"),
        (120, "120-129 BPM"),
    ],
)
def test_ten_bpm_categories(bpm, expected):
    assert bpm_category(bpm) == expected


def test_existing_catalog_and_playlist_survive_additive_migration(tmp_path):
    engine = make_engine(tmp_path / "fixture.db")
    run_migrations(engine)
    session = make_session_factory(engine)()
    repo = LibraryRepository(session)
    track = repo.add_track(title="Retained", file_path=tmp_path / "song.m4a")
    playlist = repo.create_playlist("Retained playlist")
    repo.add_to_playlist(playlist.id, track.id)
    track_id, playlist_id = track.id, playlist.id
    repo.commit()
    session.close()
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE tracks DROP COLUMN bpm"))
        connection.execute(text("DELETE FROM schema_version WHERE version=2"))
    assert run_migrations(engine) == 2
    assert run_migrations(engine) == 2
    session = make_session_factory(engine)()
    repo = LibraryRepository(session)
    retained = repo.get_track(track_id)
    assert retained.title == "Retained" and retained.bpm is None
    assert [t.id for t in repo.playlist_tracks(playlist_id)] == [track_id]
    repo.update_track_metadata(track_id, bpm=123.4)
    repo.commit()
    assert repo.get_track(track_id).bpm == 123.4
    session.close()
    engine.dispose()


def test_frozen_app_uses_external_component_config(tmp_path, monkeypatch):
    import sys

    (tmp_path / "src").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    exe = tmp_path / "dist/MusicLibrary/MusicLibrary.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert project_root() == tmp_path


def test_portable_frozen_defaults_use_music_folder_not_internal(tmp_path, monkeypatch):
    import sys

    bundle = tmp_path / "bundle"
    (bundle / "config").mkdir(parents=True)
    (bundle / "config/default.yaml").write_text("audio:\n  concurrent_downloads: 4\n")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    cfg = load_config(root=tmp_path / "portable")
    assert cfg.paths.music_root == Path.home() / "Music"
    assert cfg.audio.concurrent_downloads == 4


def test_repair_copies_legacy_library_without_new_writes_to_legacy_root(tmp_path):
    legacy, local, nas = [tmp_path / name for name in ("legacy", "local", "nas")]
    for root in (legacy, local, nas):
        root.mkdir()
    source = legacy / "Artist/Album/01 - Song.m4a"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"retained audio fixture")
    assert len(sync_library_copies(source, local, [nas], source_roots=[legacy])) == 2
    assert source.read_bytes() == b"retained audio fixture"
    assert len(list(legacy.rglob("*.m4a"))) == 1


def test_organize_existing_preserves_originals_ids_playlists_and_conflicts(tmp_path):
    cfg = AppConfig().resolve_paths(tmp_path)
    cfg.paths.copy_roots = [tmp_path / "nas"]
    cfg.paths.copy_roots[0].mkdir()
    source = cfg.paths.music_root / "Artist/Album/01 - Song.m4a"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original audio")
    engine = make_engine(cfg.paths.database)
    run_migrations(engine)
    session = make_session_factory(engine)()
    repo = LibraryRepository(session)
    track = repo.add_track(
        title="Song", file_path=source, artist_name="Artist", album_title="Album", track_number=1
    )
    playlist = repo.create_playlist("Favorites")
    repo.add_to_playlist(playlist.id, track.id)
    repo.commit()

    class FakeTempo:
        def estimate(self, path):
            assert path.exists()
            return 124.0

    class FakeMetadata(MetadataService):
        def read(self, path):
            assert path.exists()
            return TrackMetadata()

    kwargs = {"tempo": FakeTempo(), "metadata": FakeMetadata()}
    result = organize_existing(cfg, repo, **kwargs)
    assert result == {"organized": 1, "errors": []}
    target = Path(repo.get_track(track.id).file_path)
    assert target != source and "120-129 BPM" in str(target)
    assert target.read_bytes() == source.read_bytes() == b"original audio"
    copy = cfg.paths.copy_roots[0] / target.relative_to(cfg.paths.music_root)
    assert copy.read_bytes() == target.read_bytes()
    assert repo.playlist_tracks(playlist.id)[0].id == track.id
    assert organize_existing(cfg, repo, **kwargs) == result  # idempotent
    assert len(list(cfg.paths.music_root.rglob("*.m4a"))) == 2
    copy.write_bytes(b"conflicting file")  # disposable test fixture only
    assert organize_existing(cfg, repo, **kwargs)["errors"]
    assert copy.read_bytes() == b"conflicting file" and source.exists()
    session.close()
    engine.dispose()


def test_bpm_folder_setting_and_unknown_fallback(tmp_path):
    metadata = TrackMetadata(title="Song", artist="Artist", bpm=None)
    organizer = LibraryOrganizer(tmp_path, OrganizationConfig())
    assert "Unknown BPM" in str(organizer.destination_for(metadata, extension=".mp3"))
    organizer.config.categorize_by_bpm = False
    assert (
        organizer.destination_for(metadata, extension=".mp3").relative_to(tmp_path).parts[0]
        == "Artist"
    )


def test_packaged_audio_check_never_opens_catalog(tmp_path, monkeypatch):
    from src import main

    def forbidden_catalog(*args, **kwargs):
        raise AssertionError("Read-only audio check must not open the catalog")

    monkeypatch.setattr(main, "create_app", forbidden_catalog)
    monkeypatch.setattr(TempoAnalyzer, "estimate", lambda _self, _path: 120.0)
    monkeypatch.setattr(
        MetadataService, "read", lambda _self, _path: TrackMetadata(title="Fixture")
    )
    report = tmp_path / "report.json"
    assert main.main(["--verify-audio", str(tmp_path / "song.m4a"), "--report", str(report)]) == 0
    assert '"bpm": 120.0' in report.read_text()
