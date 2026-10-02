"""Configuration loading and typed settings."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AudioFormat = Literal["original", "m4a", "opus", "mp3", "wav", "aiff", "flac"]
DuplicateAction = Literal["skip", "ask", "download_copy"]
DuplicateWarn = Literal["skip", "warn", "ask", "download_copy"]
MetadataProvider = Literal["none", "musicbrainz"]
ThemeName = Literal["dark", "light"]


def project_root() -> Path:
    """Return the music-library component root (parent of ``src``)."""
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        # A build inside the component shares its external config and persistent data.
        for candidate in executable_dir.parents:
            if (candidate / "pyproject.toml").is_file() and (candidate / "src").is_dir():
                return candidate
        return executable_dir
    return Path(__file__).resolve().parent.parent


class PathsConfig(BaseModel):
    music_root: Path = Path("music")
    copy_roots: list[Path] = Field(default_factory=list)
    read_roots: list[Path] = Field(default_factory=list)
    temp_dir: Path = Path(".tmp")
    database: Path = Path("data/music_library.db")
    logs_dir: Path = Path("logs")
    log_file: Path = Path("logs/music-library.log")


class AudioConfig(BaseModel):
    default_format: AudioFormat = "m4a"
    mp3_bitrate: Literal[320, 256, 192] = 320
    embed_artwork: bool = True
    concurrent_downloads: int = Field(default=2, ge=1, le=8)


class OrganizationConfig(BaseModel):
    categorize_by_bpm: bool = True
    folder_template: str = "{artist}/{album}"
    singles_album: str = "Singles"
    filename_template: str = "{track:02d} - {title}"
    singles_filename_template: str = "{title}"
    never_overwrite: bool = True


class DuplicatesConfig(BaseModel):
    on_source_id_match: DuplicateAction = "skip"
    on_title_artist_match: DuplicateWarn = "warn"


class MetadataConfig(BaseModel):
    provider: MetadataProvider = "musicbrainz"
    write_replaygain: bool = False


class UiConfig(BaseModel):
    theme: ThemeName = "dark"
    web_host: str = "127.0.0.1"
    web_port: int = Field(default=8787, ge=1, le=65535)
    open_web_on_start: bool = False


class LoggingConfig(BaseModel):
    level: str = "INFO"
    max_bytes: int = 5_242_880
    backup_count: int = 5


class AppMeta(BaseModel):
    name: str = "Music Library"
    version: str = "0.1.0"


class AppConfig(BaseModel):
    app: AppMeta = Field(default_factory=AppMeta)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    organization: OrganizationConfig = Field(default_factory=OrganizationConfig)
    duplicates: DuplicatesConfig = Field(default_factory=DuplicatesConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def resolve_paths(self, root: Path | None = None) -> AppConfig:
        """Return a copy with paths resolved against the project root."""
        base = root or project_root()
        data = self.model_dump()
        for key in ("music_root", "temp_dir", "database", "logs_dir", "log_file"):
            value = Path(data["paths"][key])
            data["paths"][key] = str(value if value.is_absolute() else (base / value))
        for key in ("copy_roots", "read_roots"):
            data["paths"][key] = [
                str(value if value.is_absolute() else base / value)
                for value in map(Path, data["paths"][key])
            ]
        return AppConfig.model_validate(data)


class EnvOverrides(BaseSettings):
    """Optional environment overrides. Never stores secrets."""

    model_config = SettingsConfigDict(
        env_prefix="MUSIC_LIBRARY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    root: Path | None = None
    temp: Path | None = None
    db: Path | None = None
    log_level: str | None = None
    web_host: str | None = None
    web_port: int | None = None


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        msg = f"Config root must be a mapping: {path}"
        raise ValueError(msg)
    return data


def load_config(
    config_path: Path | None = None,
    *,
    root: Path | None = None,
) -> AppConfig:
    """Load default.yaml, optional local overlay, and environment overrides."""
    base = root or project_root()
    default_path = config_path or (base / "config" / "default.yaml")
    if not default_path.is_file() and getattr(sys, "frozen", False):
        default_path = Path(sys._MEIPASS) / "config" / "default.yaml"
    local_path = base / "config" / "local.yaml"

    data = load_yaml_config(default_path)
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        data.setdefault("paths", {})["music_root"] = str(Path.home() / "Music")
    data = _deep_merge(data, load_yaml_config(local_path))
    cfg = AppConfig.model_validate(data).resolve_paths(base)

    env = EnvOverrides()
    updates: dict[str, Any] = {}
    if env.root is not None:
        updates.setdefault("paths", {})["music_root"] = env.root
    if env.temp is not None:
        updates.setdefault("paths", {})["temp_dir"] = env.temp
    if env.db is not None:
        updates.setdefault("paths", {})["database"] = env.db
    if env.log_level is not None:
        updates.setdefault("logging", {})["level"] = env.log_level
    if env.web_host is not None:
        updates.setdefault("ui", {})["web_host"] = env.web_host
    if env.web_port is not None:
        updates.setdefault("ui", {})["web_port"] = env.web_port

    if updates:
        merged = _deep_merge(cfg.model_dump(mode="json"), updates)
        cfg = AppConfig.model_validate(merged)

    return cfg
