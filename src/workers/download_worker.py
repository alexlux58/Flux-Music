"""Background workers using QRunnable / QThreadPool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from src.config import AppConfig
from src.database.migrations import make_engine, make_session_factory
from src.database.repository import LibraryRepository
from src.services.library_scanner import LibraryScanner
from src.services.metadata import MetadataService
from src.services.pipeline import DownloadPipeline
from src.utils.logging import get_logger

logger = get_logger("workers")


class WorkerSignals(QObject):
    progress = Signal(str, float, dict)  # stage, progress 0-1, extras
    finished = Signal(object)
    error = Signal(str)
    status = Signal(str)


class DownloadWorker(QRunnable):
    def __init__(
        self,
        config: AppConfig,
        job_id: int,
        url: str,
        *,
        allow_duplicate_copy: bool = False,
    ) -> None:
        super().__init__()
        self.config = config
        self.job_id = job_id
        self.url = url
        self.allow_duplicate_copy = allow_duplicate_copy
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        engine = make_engine(self.config.paths.database)
        session = make_session_factory(engine)()
        repo = LibraryRepository(session)
        try:
            repo.update_download(
                self.job_id, status="retrieving_metadata", stage="Retrieving metadata"
            )
            repo.commit()

            def on_stage(stage: str, progress: float, extra: dict[str, Any]) -> None:
                status_map = {
                    "Retrieving metadata": "retrieving_metadata",
                    "Downloading": "downloading",
                    "Processing": "processing",
                    "Embedding metadata": "embedding_metadata",
                    "Organizing library": "processing",
                    "Updating database": "processing",
                    "Complete": "complete",
                }
                repo.update_download(
                    self.job_id,
                    status=status_map.get(stage, "processing"),
                    stage=stage,
                    progress=progress * 100,
                    speed=str(extra.get("speed") or ""),
                    eta=str(extra.get("eta") or ""),
                )
                repo.commit()
                self.signals.progress.emit(stage, progress, extra)

            pipeline = DownloadPipeline(self.config, repo)
            result = pipeline.run(
                self.url,
                on_stage=on_stage,
                allow_duplicate_copy=self.allow_duplicate_copy,
            )
            if result.skipped:
                repo.update_download(
                    self.job_id,
                    status="complete",
                    stage="Skipped",
                    progress=100,
                    error_message=result.skip_reason,
                )
            else:
                repo.update_download(
                    self.job_id,
                    status="complete",
                    stage="Complete",
                    progress=100,
                )
            repo.commit()
            self.signals.finished.emit({"job_id": self.job_id, "result": result})
        except Exception as exc:
            logger.exception("Download job %s failed", self.job_id)
            try:
                repo.update_download(
                    self.job_id,
                    status="failed",
                    stage="Failed",
                    error_message=str(exc),
                )
                repo.commit()
            except Exception:
                logger.exception("Failed to persist download error state")
            self.signals.error.emit(str(exc))
        finally:
            session.close()


class ScanWorker(QRunnable):
    def __init__(self, config: AppConfig, root: Path) -> None:
        super().__init__()
        self.config = config
        self.root = root
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        engine = make_engine(self.config.paths.database)
        session = make_session_factory(engine)()
        repo = LibraryRepository(session)
        try:
            scanner = LibraryScanner(repo, MetadataService())

            def progress(index: int, total: int, path: Path) -> None:
                pct = index / total if total else 1.0
                self.signals.progress.emit(
                    "Scanning",
                    pct,
                    {"path": str(path), "index": index, "total": total},
                )

            count = scanner.scan(self.root, progress=progress)
            self.signals.finished.emit({"imported": count})
        except Exception as exc:
            logger.exception("Scan failed")
            self.signals.error.emit(str(exc))
        finally:
            session.close()


class MetadataWorker(QRunnable):
    def __init__(
        self,
        config: AppConfig,
        track_id: int,
        updates: dict[str, Any],
        artwork_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.track_id = track_id
        self.updates = updates
        self.artwork_path = artwork_path
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        engine = make_engine(self.config.paths.database)
        session = make_session_factory(engine)()
        repo = LibraryRepository(session)
        try:
            track = repo.get_track(self.track_id)
            if track is None:
                msg = f"Track {self.track_id} not found"
                raise ValueError(msg)
            path = Path(track.file_path)
            meta = MetadataService().read(path)
            for key, value in self.updates.items():
                if hasattr(meta, key):
                    setattr(meta, key, value)
            MetadataService().write(path, meta, artwork=self.artwork_path)
            repo.update_track_metadata(self.track_id, **self.updates)
            if self.artwork_path:
                repo.update_track_metadata(self.track_id, artwork_path=str(self.artwork_path))
            repo.commit()
            self.signals.finished.emit({"track_id": self.track_id})
        except Exception as exc:
            logger.exception("Metadata update failed")
            self.signals.error.emit(str(exc))
        finally:
            session.close()


class PreviewWorker(QRunnable):
    def __init__(self, url: str) -> None:
        super().__init__()
        self.url = url
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            from src.services.downloader import YtDlpDownloader

            preview = YtDlpDownloader().preview(self.url)
            self.signals.finished.emit(preview)
        except Exception as exc:
            self.signals.error.emit(str(exc))
