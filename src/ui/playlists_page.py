"""Local playlist management."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.app import AppContext
from src.database.repository import LibraryRepository


class PlaylistsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        title = QLabel("Playlists")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Create local playlists from tracks already in your library.")
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        body = QHBoxLayout()
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load_tracks)
        left.addWidget(self.list)
        buttons = QHBoxLayout()
        create = QPushButton("New")
        create.clicked.connect(self.create_playlist)
        buttons.addWidget(create)
        rename = QPushButton("Rename")
        rename.setObjectName("btnGhost")
        rename.clicked.connect(self.rename_playlist)
        buttons.addWidget(rename)
        delete = QPushButton("Delete")
        delete.setObjectName("btnDanger")
        delete.clicked.connect(self.delete_playlist)
        buttons.addWidget(delete)
        left.addLayout(buttons)
        body.addLayout(left, stretch=1)

        self.tracks = QTableWidget(0, 3)
        self.tracks.setHorizontalHeaderLabels(["ID", "Title", "Artist"])
        self.tracks.setColumnHidden(0, True)
        self.tracks.horizontalHeader().setStretchLastSection(True)
        body.addWidget(self.tracks, stretch=3)
        layout.addLayout(body)
        self.refresh()

    def refresh(self) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        playlists = list(repo.list_playlists())
        session.close()
        self.list.clear()
        for playlist in playlists:
            self.list.addItem(f"{playlist.id}: {playlist.name}")
        self.tracks.setRowCount(0)

    def _current_playlist_id(self) -> int | None:
        item = self.list.currentItem()
        if item is None:
            return None
        return int(item.text().split(":", 1)[0])

    def _load_tracks(self, _row: int) -> None:
        playlist_id = self._current_playlist_id()
        self.tracks.setRowCount(0)
        if playlist_id is None:
            return
        session = self.ctx.session()
        repo = LibraryRepository(session)
        tracks = list(repo.playlist_tracks(playlist_id))
        session.close()
        for track in tracks:
            row = self.tracks.rowCount()
            self.tracks.insertRow(row)
            self.tracks.setItem(row, 0, QTableWidgetItem(str(track.id)))
            self.tracks.setItem(row, 1, QTableWidgetItem(track.title))
            self.tracks.setItem(
                row, 2, QTableWidgetItem(track.artist.name if track.artist else "—")
            )

    def create_playlist(self) -> None:
        name, ok = QInputDialog.getText(self, "New playlist", "Name:")
        if not ok or not name.strip():
            return
        session = self.ctx.session()
        repo = LibraryRepository(session)
        repo.create_playlist(name.strip())
        repo.commit()
        session.close()
        self.refresh()

    def rename_playlist(self) -> None:
        playlist_id = self._current_playlist_id()
        if playlist_id is None:
            return
        name, ok = QInputDialog.getText(self, "Rename playlist", "New name:")
        if not ok or not name.strip():
            return
        session = self.ctx.session()
        repo = LibraryRepository(session)
        repo.rename_playlist(playlist_id, name.strip())
        repo.commit()
        session.close()
        self.refresh()

    def delete_playlist(self) -> None:
        playlist_id = self._current_playlist_id()
        if playlist_id is None:
            return
        if (
            QMessageBox.question(self, "Delete playlist", "Delete this playlist?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        session = self.ctx.session()
        repo = LibraryRepository(session)
        repo.delete_playlist(playlist_id)
        repo.commit()
        session.close()
        self.refresh()
