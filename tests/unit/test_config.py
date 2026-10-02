"""Configuration loading tests."""

from pathlib import Path

from src.config import load_config


def test_load_default_config() -> None:
    root = Path(__file__).resolve().parents[2]
    cfg = load_config(root=root)
    assert cfg.app.name == "Music Library"
    assert cfg.audio.default_format == "m4a"
    assert cfg.paths.database.name == "music_library.db"
    assert cfg.ui.web_port == 8787
