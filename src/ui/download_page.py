"""Download page — bulk URLs, playlist preview, parallel queue."""

from __future__ import annotations

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.app import AppContext
from src.database.repository import LibraryRepository
from src.services.downloader import MediaEntry, PlaylistPreview
from src.utils.validation import parse_url_list, validate_url
from src.workers.download_worker import DownloadWorker, PreviewWorker

ACTIVE_STATUSES = frozenset(
    {
        "retrieving_metadata",
        "downloading",
        "processing",
        "embedding_metadata",
    }
)


class DownloadPage(QWidget):
    library_changed = Signal()

    def __init__(self, ctx: AppContext, pool: QThreadPool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.pool = pool
        self._preview: MediaEntry | PlaylistPreview | None = None
        self._paused = False
        self._started_job_ids: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        title = QLabel("Downloads")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        notice = QLabel(
            "Only download content you have the legal right and permission to obtain. "
            "This app does not bypass DRM, paywalls, or account restrictions. "
            "Paste one URL per line for bulk parallel downloads."
        )
        notice.setWordWrap(True)
        notice.setObjectName("pageSubtitle")
        layout.addWidget(notice)

        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText(
            "Paste one or more YouTube / YouTube Music URLs (one per line)…\n"
            "https://music.youtube.com/watch?v=...\n"
            "https://www.youtube.com/watch?v=...\n"
            "# comments and blank lines are ignored"
        )
        self.url_input.setMaximumHeight(110)
        layout.addWidget(self.url_input)

        row = QHBoxLayout()
        self.analyze_btn = QPushButton("Analyze first URL")
        self.analyze_btn.setObjectName("btnSecondary")
        self.analyze_btn.clicked.connect(self.analyze_url)
        row.addWidget(self.analyze_btn)
        self.enqueue_btn = QPushButton("Queue selected preview")
        self.enqueue_btn.setObjectName("btnGhost")
        self.enqueue_btn.clicked.connect(self.enqueue)
        row.addWidget(self.enqueue_btn)
        self.bulk_btn = QPushButton("Queue all URLs (parallel)")
        self.bulk_btn.clicked.connect(self.enqueue_bulk)
        row.addWidget(self.bulk_btn)
        row.addWidget(QLabel("Parallel:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 8)
        self.parallel_spin.setValue(ctx.config.audio.concurrent_downloads)
        self.parallel_spin.valueChanged.connect(self._on_parallel_changed)
        row.addWidget(self.parallel_spin)
        row.addStretch(1)
        layout.addLayout(row)

        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        self.preview_box.setMaximumHeight(120)
        layout.addWidget(self.preview_box)

        self.track_table = QTableWidget(0, 3)
        self.track_table.setHorizontalHeaderLabels(["Include", "Title", "Duration"])
        self.track_table.horizontalHeader().setStretchLastSection(True)
        self.track_table.setMaximumHeight(160)
        layout.addWidget(self.track_table)

        controls = QHBoxLayout()
        self.pause_btn = QPushButton("Pause queue")
        self.pause_btn.setObjectName("btnGhost")
        self.pause_btn.clicked.connect(self.toggle_pause)
        controls.addWidget(self.pause_btn)
        self.clear_btn = QPushButton("Clear completed")
        self.clear_btn.setObjectName("btnGhost")
        self.clear_btn.clicked.connect(self.clear_completed)
        controls.addWidget(self.clear_btn)
        self.retry_btn = QPushButton("Retry failed")
        self.retry_btn.setObjectName("btnSecondary")
        self.retry_btn.clicked.connect(self.retry_failed)
        controls.addWidget(self.retry_btn)
        controls.addStretch(1)
        self.active_label = QLabel("")
        self.active_label.setObjectName("pageSubtitle")
        controls.addWidget(self.active_label)
        layout.addLayout(controls)

        self.queue_table = QTableWidget(0, 7)
        self.queue_table.setHorizontalHeaderLabels(
            ["Title", "Artist", "Status", "Progress", "Speed", "ETA", "Stage"]
        )
        self.queue_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.queue_table, stretch=1)

        self._on_parallel_changed(self.parallel_spin.value())
        self.refresh_queue()

    def _on_parallel_changed(self, value: int) -> None:
        self.ctx.config.audio.concurrent_downloads = value
        self.pool.setMaxThreadCount(max(value, 2))
        if not self._paused:
            self._drain_queued()

    def _first_url(self) -> str:
        valid, _invalid = parse_url_list(self.url_input.toPlainText())
        if valid:
            return valid[0]
        return validate_url(self.url_input.toPlainText().strip().splitlines()[0])

    def analyze_url(self) -> None:
        try:
            url = self._first_url()
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Invalid URL", str(exc) if str(exc) else "Paste a URL first.")
            return
        self.analyze_btn.setEnabled(False)
        self.preview_box.setPlainText("Retrieving metadata…")
        worker = PreviewWorker(url)
        worker.signals.finished.connect(self._on_preview)
        worker.signals.error.connect(self._on_preview_error)
        self.pool.start(worker)

    def _on_preview(self, preview: object) -> None:
        self.analyze_btn.setEnabled(True)
        self._preview = preview  # type: ignore[assignment]
        self.track_table.setRowCount(0)
        if isinstance(preview, PlaylistPreview):
            duration = preview.total_duration
            dur_txt = f"{int(duration // 60)}m" if duration else "unknown"
            self.preview_box.setPlainText(
                f"Playlist: {preview.title}\nTracks: {preview.track_count}\n"
                f"Estimated duration: {dur_txt}"
            )
            for entry in preview.entries:
                row = self.track_table.rowCount()
                self.track_table.insertRow(row)
                check = QCheckBox()
                check.setChecked(True)
                self.track_table.setCellWidget(row, 0, check)
                self.track_table.setItem(row, 1, QTableWidgetItem(entry.title))
                dur = f"{int(entry.duration)}s" if entry.duration else "—"
                self.track_table.setItem(row, 2, QTableWidgetItem(dur))
        elif isinstance(preview, MediaEntry):
            self.preview_box.setPlainText(
                f"Title: {preview.title}\nArtist: {preview.uploader or '—'}\n"
                f"Duration: {int(preview.duration) if preview.duration else '—'}s"
            )
            row = self.track_table.rowCount()
            self.track_table.insertRow(row)
            check = QCheckBox()
            check.setChecked(True)
            self.track_table.setCellWidget(row, 0, check)
            self.track_table.setItem(row, 1, QTableWidgetItem(preview.title))
            dur = f"{int(preview.duration)}s" if preview.duration else "—"
            self.track_table.setItem(row, 2, QTableWidgetItem(dur))

    def _on_preview_error(self, message: str) -> None:
        self.analyze_btn.setEnabled(True)
        self.preview_box.setPlainText("")
        QMessageBox.critical(self, "Analyze failed", message)

    def enqueue_bulk(self) -> None:
        valid, invalid = parse_url_list(self.url_input.toPlainText())
        if not valid:
            QMessageBox.warning(
                self,
                "No valid URLs",
                "Paste one supported YouTube / YouTube Music URL per line.",
            )
            return
        if invalid:
            sample = "\n".join(invalid[:5])
            more = "" if len(invalid) <= 5 else f"\n…and {len(invalid) - 5} more"
            answer = QMessageBox.question(
                self,
                "Some lines invalid",
                f"Queue {len(valid)} valid URL(s) and skip {len(invalid)} invalid line(s)?\n\n"
                f"{sample}{more}",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        jobs = [(url, None, None, None) for url in valid]
        self._enqueue_urls(jobs)
        self.preview_box.setPlainText(
            f"Queued {len(jobs)} URL(s) for parallel download "
            f"(up to {self.parallel_spin.value()} at once)."
        )

    def enqueue(self) -> None:
        if self._preview is None:
            self.enqueue_bulk()
            return

        jobs: list[tuple[str, str | None, str | None, str | None]] = []
        if isinstance(self._preview, PlaylistPreview):
            for row, entry in enumerate(self._preview.entries):
                widget = self.track_table.cellWidget(row, 0)
                if isinstance(widget, QCheckBox) and not widget.isChecked():
                    continue
                jobs.append((entry.url, entry.title, entry.uploader, entry.id))
        elif isinstance(self._preview, MediaEntry):
            entry = self._preview
            first = ""
            try:
                first = self._first_url()
            except (ValueError, IndexError):
                first = entry.url
            jobs.append((entry.url or first, entry.title, entry.uploader, entry.id))
        if not jobs:
            QMessageBox.information(self, "Nothing selected", "Select at least one track.")
            return
        self._enqueue_urls(jobs)

    def _enqueue_urls(self, jobs: list[tuple[str, str | None, str | None, str | None]]) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        try:
            for url, title, artist, video_id in jobs:
                repo.create_download_job(
                    url=url,
                    title=title,
                    artist=artist,
                    source_provider="youtube" if video_id else None,
                    source_video_id=video_id,
                )
            repo.commit()
        finally:
            session.close()
        self.refresh_queue()
        if not self._paused:
            self._drain_queued()

    def _start_job(self, job_id: int) -> None:
        if job_id in self._started_job_ids:
            return
        session = self.ctx.session()
        repo = LibraryRepository(session)
        job = next((j for j in repo.list_downloads() if j.id == job_id), None)
        session.close()
        if job is None or job.status != "queued":
            return
        self._started_job_ids.add(job_id)
        worker = DownloadWorker(self.ctx.config, job.id, job.url)
        worker.signals.progress.connect(lambda *_: self.refresh_queue())
        worker.signals.finished.connect(self._on_job_finished)
        worker.signals.error.connect(self._on_job_error)
        self.pool.start(worker)

    def _on_job_finished(self, payload: object) -> None:
        if isinstance(payload, dict) and "job_id" in payload:
            self._started_job_ids.discard(int(payload["job_id"]))
        self.refresh_queue()
        self.library_changed.emit()
        if not self._paused:
            self._drain_queued()

    def _on_job_error(self, _message: str) -> None:
        # Workers may fail before finished signal; resync from DB statuses.
        session = self.ctx.session()
        repo = LibraryRepository(session)
        active_or_done = {
            j.id
            for j in repo.list_downloads()
            if j.status in ACTIVE_STATUSES or j.status in {"complete", "failed", "cancelled"}
        }
        session.close()
        self._started_job_ids &= active_or_done
        self.refresh_queue()
        if not self._paused:
            self._drain_queued()

    def toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_btn.setText("Resume queue" if self._paused else "Pause queue")
        if not self._paused:
            self._drain_queued()

    def _drain_queued(self) -> None:
        """Start queued jobs until the parallel slot limit is filled."""
        if self._paused:
            return
        limit = self.parallel_spin.value()
        session = self.ctx.session()
        repo = LibraryRepository(session)
        jobs = list(repo.list_downloads())
        session.close()

        active = sum(
            1 for j in jobs if j.status in ACTIVE_STATUSES or j.id in self._started_job_ids
        )
        slots = max(0, limit - active)
        if slots == 0:
            return
        queued = [
            j
            for j in jobs
            if j.status == "queued" and j.selected and j.id not in self._started_job_ids
        ]
        # Oldest first
        queued.sort(key=lambda j: j.created_at or j.id)
        for job in queued[:slots]:
            self._start_job(job.id)

    def clear_completed(self) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        repo.clear_completed_downloads()
        repo.commit()
        session.close()
        self._started_job_ids.clear()
        self.refresh_queue()

    def retry_failed(self) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        failed = [j for j in repo.list_downloads() if j.status == "failed"]
        for job in failed:
            repo.update_download(job.id, status="queued", error_message=None, progress=0)
            self._started_job_ids.discard(job.id)
        repo.commit()
        session.close()
        self.refresh_queue()
        if not self._paused:
            self._drain_queued()

    def refresh_queue(self) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        jobs = list(repo.list_downloads())
        session.close()
        active = sum(1 for j in jobs if j.status in ACTIVE_STATUSES)
        queued = sum(1 for j in jobs if j.status == "queued")
        parallel = self.parallel_spin.value()
        pool_n = self.pool.activeThreadCount()
        self.active_label.setText(f"Active {active}/{parallel} · Queued {queued} · Pool {pool_n}")
        self.queue_table.setRowCount(0)
        for job in jobs:
            row = self.queue_table.rowCount()
            self.queue_table.insertRow(row)
            values = [
                job.title or job.url,
                job.artist or "—",
                job.status,
                f"{job.progress:.0f}%",
                job.speed or "—",
                job.eta or "—",
                job.stage or "—",
            ]
            for col, value in enumerate(values):
                self.queue_table.setItem(row, col, QTableWidgetItem(str(value)))
