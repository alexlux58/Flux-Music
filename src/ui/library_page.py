"""Library browsing, search, context actions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.app import AppContext
from src.database.repository import LibraryRepository
from src.services.tempo import bpm_category


class _TempoItem(QTableWidgetItem):
    """Keep tempo sorting numeric even when some rows have unknown tempo."""

    def __init__(self, bpm: float | None) -> None:
        super().__init__(f"{bpm:.1f}" if bpm is not None else "—")
        self.bpm = bpm

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _TempoItem):
            return (self.bpm if self.bpm is not None else float("inf")) < (
                other.bpm if other.bpm is not None else float("inf")
            )
        return super().__lt__(other)


class LibraryPage(QWidget):
    play_requested = Signal(int)
    selection_changed = Signal()

    def __init__(
        self,
        ctx: AppContext,
        *,
        mode: str = "library",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self._mode = mode
        self._artist_id: int | None = None
        self._album_id: int | None = None
        self._detail_title: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.setObjectName("btnGhost")
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self._go_back)
        header.addWidget(self.back_btn)
        self.title = QLabel(self._title_for_mode())
        self.title.setObjectName("pageTitle")
        header.addWidget(self.title)
        header.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, artist, album, genre…")
        self.search.textChanged.connect(lambda _: self.refresh())
        header.addWidget(self.search, stretch=2)
        self.import_btn = QPushButton("Import folder")
        self.import_btn.setObjectName("btnSecondary")
        self.import_btn.clicked.connect(self.import_folder)
        header.addWidget(self.import_btn)
        self.organize_btn = QPushButton("Organize by BPM")
        self.organize_btn.setToolTip("Create BPM copies locally and on Synology; keep originals.")
        self.organize_btn.clicked.connect(self.organize_by_bpm)
        header.addWidget(self.organize_btn)
        layout.addLayout(header)

        self.hint = QLabel("")
        self.hint.setObjectName("pageSubtitle")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.table = QTableWidget(0, 10)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setColumnHidden(0, True)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.table)

        self.empty = QLabel("")
        self.empty.setObjectName("emptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setVisible(False)
        layout.addWidget(self.empty)

        self._apply_mode_chrome()
        self.refresh()

    def _title_for_mode(self) -> str:
        if self._detail_title:
            return self._detail_title
        return {
            "library": "Library",
            "recent": "Recently Added",
            "artists": "Artists",
            "albums": "Albums",
        }.get(self._mode, "Library")

    def _apply_mode_chrome(self) -> None:
        showing_tracks = self._showing_tracks()
        show_import = self._mode == "library" and showing_tracks and not self._artist_id
        self.import_btn.setVisible(show_import)
        self.search.setVisible(showing_tracks)
        self.back_btn.setVisible(bool(self._artist_id or self._album_id))
        if self._mode == "recent":
            self.hint.setText("Newest imports first. Double-click a row to play.")
        elif self._mode == "artists" and not self._artist_id:
            self.hint.setText("Double-click an artist to see their tracks.")
        elif self._mode == "albums" and not self._album_id:
            self.hint.setText("Double-click an album to open it.")
        elif self._mode == "library":
            self.hint.setText("Your local catalog. Right-click a track for play, edit, or delete.")
        else:
            self.hint.setText("Double-click a track to play.")
        self.title.setText(self._title_for_mode())

    def _showing_tracks(self) -> bool:
        if self._mode in {"library", "recent"}:
            return True
        return bool(self._artist_id or self._album_id)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        self._artist_id = None
        self._album_id = None
        self._detail_title = None
        self._apply_mode_chrome()
        self.refresh()

    def refresh(self) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        try:
            if self._mode == "artists" and self._artist_id is None:
                self._show_artists(repo)
                return
            if self._mode == "albums" and self._album_id is None:
                self._show_albums(repo)
                return
            if self._artist_id is not None:
                tracks = list(repo.list_tracks_for_artist(self._artist_id))
            elif self._album_id is not None:
                tracks = list(repo.list_tracks_for_album(self._album_id))
            elif self._mode == "recent":
                tracks = list(repo.list_recent(limit=100))
            else:
                tracks = list(repo.search_tracks(self.search.text().strip()))
        finally:
            session.close()

        self._render_tracks(tracks)

    def _set_empty(self, message: str | None) -> None:
        has_rows = self.table.rowCount() > 0
        self.empty.setVisible(not has_rows)
        self.table.setVisible(has_rows)
        if not has_rows:
            self.empty.setText(message or "Nothing here yet.")

    def _render_tracks(self, tracks: list) -> None:
        query = self.search.text().strip().casefold()
        if query and self._mode != "library":
            tracks = [
                t
                for t in tracks
                if query in (t.title or "").casefold()
                or query in (t.artist.name if t.artist else "").casefold()
                or query in (t.album.title if t.album else "").casefold()
            ]
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Title",
                "Artist",
                "Album",
                "Duration",
                "Format",
                "Bitrate",
                "BPM",
                "Tempo",
                "Date Added",
            ]
        )
        self.table.setColumnHidden(0, True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for track in tracks:
            row = self.table.rowCount()
            self.table.insertRow(row)
            duration = (
                f"{int(track.duration_seconds // 60)}:{int(track.duration_seconds % 60):02d}"
                if track.duration_seconds
                else "—"
            )
            bitrate = "—"
            if track.bitrate:
                kbps = track.bitrate // 1000 if track.bitrate >= 1000 else track.bitrate
                bitrate = f"{kbps} kbps"
            values = [
                str(track.id),
                track.title,
                track.artist.name if track.artist else "—",
                track.album.title if track.album else "—",
                duration,
                track.codec or Path(track.file_path).suffix.lstrip(".") or "—",
                bitrate,
                f"{track.bpm:.1f}" if track.bpm else "—",
                bpm_category(track.bpm),
                track.date_added.strftime("%Y-%m-%d") if track.date_added else "—",
            ]
            for col, value in enumerate(values):
                item = _TempoItem(track.bpm) if col == 7 else QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, track.id)
                self.table.setItem(row, col, item)
        self.table.setSortingEnabled(True)
        self.table.resizeColumnsToContents()
        empty_msg = {
            "recent": "No recent tracks. Download or import music to populate this list.",
            "library": "Your library is empty. Use Downloads or Import folder to add music.",
        }.get(self._mode, "No tracks in this view.")
        self._set_empty(empty_msg)
        self._apply_mode_chrome()

    def _show_artists(self, repo: LibraryRepository) -> None:
        artists = list(repo.list_artists())
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "Artist", "Tracks"])
        self.table.setColumnHidden(0, True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for artist in artists:
            row = self.table.rowCount()
            self.table.insertRow(row)
            count = repo.artist_track_count(artist.id)
            self.table.setItem(row, 0, QTableWidgetItem(str(artist.id)))
            self.table.setItem(row, 1, QTableWidgetItem(artist.name))
            self.table.setItem(row, 2, QTableWidgetItem(str(count)))
        self.table.setSortingEnabled(True)
        self._set_empty("No artists yet. Add music first.")
        self._apply_mode_chrome()

    def _show_albums(self, repo: LibraryRepository) -> None:
        albums = list(repo.list_albums())
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["ID", "Album", "Artist", "Year", "Tracks"])
        self.table.setColumnHidden(0, True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for album in albums:
            row = self.table.rowCount()
            self.table.insertRow(row)
            count = repo.album_track_count(album.id)
            self.table.setItem(row, 0, QTableWidgetItem(str(album.id)))
            self.table.setItem(row, 1, QTableWidgetItem(album.title))
            self.table.setItem(row, 2, QTableWidgetItem(album.artist.name if album.artist else "—"))
            self.table.setItem(row, 3, QTableWidgetItem(str(album.year) if album.year else "—"))
            self.table.setItem(row, 4, QTableWidgetItem(str(count)))
        self.table.setSortingEnabled(True)
        self._set_empty("No albums yet. Add music first.")
        self._apply_mode_chrome()

    def selected_ids(self) -> list[int]:
        ids: list[int] = []
        for index in self.table.selectionModel().selectedRows():
            item = self.table.item(index.row(), 0)
            if item:
                ids.append(int(item.text()))
        return ids

    def _on_double_click(self) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        if self._mode == "artists" and self._artist_id is None:
            self._open_artist(ids[0])
            return
        if self._mode == "albums" and self._album_id is None:
            self._open_album(ids[0])
            return
        self.play_requested.emit(ids[0])

    def _open_artist(self, artist_id: int) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        artists = {a.id: a.name for a in repo.list_artists()}
        session.close()
        self._artist_id = artist_id
        self._detail_title = artists.get(artist_id, "Artist")
        self._apply_mode_chrome()
        self.refresh()

    def _open_album(self, album_id: int) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        albums = {a.id: a.title for a in repo.list_albums()}
        session.close()
        self._album_id = album_id
        self._detail_title = albums.get(album_id, "Album")
        self._apply_mode_chrome()
        self.refresh()

    def _go_back(self) -> None:
        self._artist_id = None
        self._album_id = None
        self._detail_title = None
        self._apply_mode_chrome()
        self.refresh()

    def _context_menu(self, pos) -> None:
        if not self._showing_tracks():
            return
        ids = self.selected_ids()
        if not ids:
            return
        menu = QMenu(self)
        play = QAction("Play", self)
        play.triggered.connect(lambda: self.play_requested.emit(ids[0]))
        menu.addAction(play)
        open_loc = QAction("Open file location", self)
        open_loc.triggered.connect(lambda: self._open_location(ids[0]))
        menu.addAction(open_loc)
        edit = QAction("Edit metadata", self)
        edit.triggered.connect(lambda: self._edit_metadata(ids[0]))
        menu.addAction(edit)
        add_pl = QAction("Add to playlist…", self)
        add_pl.triggered.connect(lambda: self._add_to_playlist(ids))
        menu.addAction(add_pl)
        menu.addSeparator()
        del_lib = QAction("Delete from library", self)
        del_lib.triggered.connect(lambda: self._delete(ids, delete_files=False))
        menu.addAction(del_lib)
        del_disk = QAction("Delete file from disk", self)
        del_disk.triggered.connect(lambda: self._delete(ids, delete_files=True))
        menu.addAction(del_disk)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_location(self, track_id: int) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        track = repo.get_track(track_id)
        session.close()
        if track is None:
            return
        path = Path(track.file_path)
        if sys.platform.startswith("win"):
            subprocess.run(["explorer", "/select,", str(path)], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path.parent)], check=False)

    def _edit_metadata(self, track_id: int) -> None:
        from src.ui.metadata_dialog import MetadataDialog

        dialog = MetadataDialog(self.ctx, track_id, parent=self)
        if dialog.exec():
            self.refresh()

    def _add_to_playlist(self, track_ids: list[int]) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        playlists = list(repo.list_playlists())
        if not playlists:
            name, ok = QInputDialog.getText(self, "New playlist", "Playlist name:")
            if not ok or not name.strip():
                session.close()
                return
            playlist = repo.create_playlist(name.strip())
            repo.commit()
            playlist_id = playlist.id
        else:
            names = [p.name for p in playlists]
            name, ok = QInputDialog.getItem(self, "Add to playlist", "Playlist:", names, 0, False)
            if not ok:
                session.close()
                return
            playlist_id = next(p.id for p in playlists if p.name == name)
        for track_id in track_ids:
            repo.add_to_playlist(playlist_id, track_id)
        repo.commit()
        session.close()

    def _delete(self, track_ids: list[int], *, delete_files: bool) -> None:
        label = "library records and files on disk" if delete_files else "library records only"
        confirm = QMessageBox.question(
            self,
            "Confirm delete",
            f"Delete {len(track_ids)} track(s) from {label}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        session = self.ctx.session()
        repo = LibraryRepository(session)
        for track_id in track_ids:
            track = repo.get_track(track_id)
            if track is None:
                continue
            path = Path(track.file_path)
            repo.delete_track(track_id)
            if delete_files and path.is_file():
                path.unlink()
        repo.commit()
        session.close()
        self.refresh()

    def import_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Select music folder")
        if not directory:
            return
        from PySide6.QtCore import QThreadPool

        from src.workers.download_worker import ScanWorker

        pool = QThreadPool.globalInstance()
        worker = ScanWorker(self.ctx.config, Path(directory))
        worker.signals.finished.connect(lambda payload: self._import_done(payload))
        worker.signals.error.connect(lambda msg: QMessageBox.critical(self, "Import failed", msg))
        pool.start(worker)
        QMessageBox.information(self, "Import started", "Scanning in the background…")

    def _import_done(self, payload: object) -> None:
        imported = 0
        if isinstance(payload, dict):
            imported = int(payload.get("imported") or 0)
        QMessageBox.information(self, "Import complete", f"Imported {imported} new track(s).")
        self.refresh()

    def organize_by_bpm(self) -> None:
        from PySide6.QtCore import QThreadPool

        from src.workers.organize_worker import OrganizeWorker

        self.organize_btn.setEnabled(False)
        worker = OrganizeWorker(self.ctx.config)
        self._organize_worker = worker
        worker.signals.finished.connect(self._organize_done)
        worker.signals.error.connect(self._organize_error)
        QThreadPool.globalInstance().start(worker)

    def _organize_done(self, payload: object) -> None:
        self.organize_btn.setEnabled(True)
        if isinstance(payload, dict):
            errors = payload.get("errors") or []
            message = f"Organized {payload.get('organized', 0)} songs. Originals retained."
            if errors:
                QMessageBox.warning(
                    self, "Some songs need attention", message + "\n" + "\n".join(errors)
                )
            else:
                QMessageBox.information(self, "BPM organization complete", message)
        self.refresh()

    def _organize_error(self, message: str) -> None:
        self.organize_btn.setEnabled(True)
        QMessageBox.critical(self, "Organization failed", message)
