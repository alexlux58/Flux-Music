"""Application context: wires config, database, and services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import AppConfig, load_config, project_root
from src.database.migrations import make_engine, make_session_factory, run_migrations
from src.database.repository import LibraryRepository
from src.services.artwork import ArtworkService
from src.services.audio_processor import AudioProcessor
from src.services.diagnostics import CheckResult, run_diagnostics
from src.services.downloader import YtDlpDownloader
from src.services.duplicate_detector import DuplicateDetector
from src.services.library_scanner import LibraryScanner
from src.services.metadata import MetadataService
from src.services.organizer import LibraryOrganizer
from src.services.pipeline import DownloadPipeline
from src.services.player import PlayerService
from src.utils.filesystem import ensure_dir
from src.utils.logging import get_logger, setup_logging


@dataclass
class AppContext:
    config: AppConfig
    engine: Engine
    session_factory: sessionmaker[Session]
    root: Path

    def session(self) -> Session:
        return self.session_factory()

    def repository(self, session: Session | None = None) -> tuple[LibraryRepository, Session]:
        sess = session or self.session()
        return LibraryRepository(sess), sess

    def diagnostics(self) -> list[CheckResult]:
        return run_diagnostics(
            database_path=self.config.paths.database,
            music_root=self.config.paths.music_root,
            temp_dir=self.config.paths.temp_dir,
        )

    def pipeline(self, repo: LibraryRepository) -> DownloadPipeline:
        return DownloadPipeline(self.config, repo)

    def scanner(self, repo: LibraryRepository) -> LibraryScanner:
        return LibraryScanner(repo, MetadataService())

    def duplicates(self, repo: LibraryRepository) -> DuplicateDetector:
        return DuplicateDetector(repo)

    def build_services(self) -> dict[str, object]:
        return {
            "downloader": YtDlpDownloader(),
            "audio": AudioProcessor(),
            "metadata": MetadataService(),
            "artwork": ArtworkService(self.config.paths.temp_dir / "artwork"),
            "organizer": LibraryOrganizer(self.config.paths.music_root, self.config.organization),
            "player": PlayerService(),
        }


def create_app(root: Path | None = None) -> AppContext:
    base = root or project_root()
    config = load_config(root=base)
    ensure_dir(config.paths.music_root)
    ensure_dir(config.paths.temp_dir)
    ensure_dir(config.paths.logs_dir)
    ensure_dir(config.paths.database.parent)

    setup_logging(config.logging, config.paths.log_file, component="app")
    logger = get_logger("app")
    logger.info("Starting %s v%s", config.app.name, config.app.version)

    engine = make_engine(config.paths.database)
    version = run_migrations(engine)
    logger.info("Database ready (schema v%s) at %s", version, config.paths.database)

    return AppContext(
        config=config,
        engine=engine,
        session_factory=make_session_factory(engine),
        root=base,
    )
