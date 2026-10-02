"""Database repository tests."""

from pathlib import Path

from src.database.migrations import make_engine, make_session_factory, run_migrations
from src.database.repository import LibraryRepository
from src.services.duplicate_detector import DuplicateDetector


def test_add_search_and_duplicates(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    engine = make_engine(db)
    assert run_migrations(engine) == 2
    session = make_session_factory(engine)()
    repo = LibraryRepository(session)

    track = repo.add_track(
        title="Test Song",
        file_path=tmp_path / "a.m4a",
        artist_name="Tester",
        album_title="Demo",
        source_provider="youtube",
        source_video_id="abc123XYZ01",
        file_hash="deadbeef",
    )
    repo.commit()

    assert repo.find_by_source("youtube", "abc123XYZ01") is not None
    assert repo.search_tracks("Test")
    assert repo.search_tracks("Tester")

    detector = DuplicateDetector(repo)
    assert detector.check_source("youtube", "abc123XYZ01") is not None
    assert detector.check_title_artist("Tester", "Test Song")
    assert detector.check_hash("deadbeef") is not None

    playlist = repo.create_playlist("Favs")
    repo.add_to_playlist(playlist.id, track.id)
    repo.commit()
    assert len(repo.playlist_tracks(playlist.id)) == 1
    assert repo.artist_track_count(track.artist_id) == 1
    assert len(repo.list_tracks_for_artist(track.artist_id)) == 1
    assert len(repo.list_tracks_for_album(track.album_id)) == 1
    session.close()
