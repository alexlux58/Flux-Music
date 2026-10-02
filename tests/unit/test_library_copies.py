"""Two destinations, verified bytes, offline retry, and existing-song safety."""

from pathlib import Path

import pytest

from src.config import AppConfig
from src.services.library_copies import copy_to_libraries, sync_library_copies


def song(tmp_path):
    primary, extra = tmp_path / "local", tmp_path / "nas"
    source = primary / "Artist/Album/01 - Song.m4a"
    source.parent.mkdir(parents=True)
    extra.mkdir()
    source.write_bytes(bytes(range(256)) * 100)
    return source, primary, extra


def test_exact_tagged_bytes_and_names_in_both_destinations(tmp_path):
    source, primary, extra = song(tmp_path)
    copied = copy_to_libraries(source, primary, [extra])
    assert copied == [extra / "Artist/Album/01 - Song.m4a"]
    assert copied[0].read_bytes() == source.read_bytes()
    before = copied[0].stat().st_mtime_ns
    assert copy_to_libraries(source, primary, [extra]) == copied
    assert copied[0].stat().st_mtime_ns == before
    assert not list(extra.rglob("*.partial"))


def test_unavailable_nas_retains_local_song_and_retry_copies_it(tmp_path):
    source, primary, extra = song(tmp_path)
    offline = extra / "missing-share"
    with pytest.raises(OSError, match="Local song retained"):
        copy_to_libraries(source, primary, [offline])
    assert source.exists() and not offline.exists()
    offline.mkdir()
    assert copy_to_libraries(source, primary, [offline])[0].read_bytes() == source.read_bytes()


def test_existing_different_song_is_never_overwritten(tmp_path):
    source, primary, extra = song(tmp_path)
    target = extra / source.relative_to(primary)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"another song")
    with pytest.raises(FileExistsError, match="nothing overwritten"):
        copy_to_libraries(source, primary, [extra])
    assert target.read_bytes() == b"another song" and source.exists()


def test_retry_of_old_nas_song_creates_local_copy(tmp_path):
    source, nas, local = song(tmp_path)
    assert sync_library_copies(source, local, [nas])[0].read_bytes() == source.read_bytes()


def test_same_folder_and_unconfigured_source(tmp_path):
    source, primary, extra = song(tmp_path)
    assert copy_to_libraries(source, primary, [primary]) == []
    with pytest.raises(ValueError, match="outside"):
        sync_library_copies(source, extra, [])


def test_destination_symlink_escape_is_rejected(tmp_path):
    source, primary, extra = song(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (extra / "Artist").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        copy_to_libraries(source, primary, [extra])
    assert not list(outside.iterdir()) and source.exists()


def test_relative_copy_folders_are_resolved(tmp_path):
    config = AppConfig.model_validate({"paths": {"copy_roots": ["nas"]}}).resolve_paths(tmp_path)
    assert config.paths.copy_roots == [tmp_path / "nas"]
    assert isinstance(config.paths.copy_roots[0], Path)
