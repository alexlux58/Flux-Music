"""Background organization, through services and the repository."""

from PySide6.QtCore import QRunnable, Slot

from src.config import AppConfig
from src.database.migrations import make_engine, make_session_factory
from src.database.repository import LibraryRepository
from src.services.library_repair import organize_existing
from src.workers.download_worker import WorkerSignals


class OrganizeWorker(QRunnable):
    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config.model_copy(deep=True)
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        engine = make_engine(self.config.paths.database)
        session = make_session_factory(engine)()
        try:
            result = organize_existing(self.config, LibraryRepository(session))
            self.signals.finished.emit(result)
        except Exception as exc:
            self.signals.error.emit(str(exc))
        finally:
            session.close()
            engine.dispose()
