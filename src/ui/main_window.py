"""Main window with sidebar navigation and player bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.app import AppContext
from src.database.repository import LibraryRepository
from src.services.player import NowPlaying, PlayerService
from src.ui.download_page import DownloadPage
from src.ui.library_page import LibraryPage
from src.ui.playlists_page import PlaylistsPage
from src.ui.settings_page import SettingsPage
from src.ui.theme import FLUX_QSS

NAV_ITEMS = (
    "Library",
    "Downloads",
    "Playlists",
    "Recently Added",
    "Artists",
    "Albums",
    "Settings",
)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(ctx.config.audio.concurrent_downloads)
        self.player_service = PlayerService()
        self.media = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.media.setAudioOutput(self.audio)
        self.audio.setVolume(0.8)
        self._seeking = False
        self.media.positionChanged.connect(self._on_position)
        self.media.durationChanged.connect(self._on_duration)

        self.setWindowTitle(ctx.config.app.name)
        self.resize(1280, 800)
        icon = ctx.root / "assets" / "icons" / "app-icon.ico"
        if icon.is_file():
            self.setWindowIcon(QIcon(str(icon)))

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        sidebar = QVBoxLayout()
        sidebar.setContentsMargins(0, 16, 0, 12)
        brand = QLabel("FLUX  MUSIC")
        brand.setObjectName("brandMark")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sidebar.addWidget(brand)

        self.nav = QListWidget()
        self.nav.setObjectName("navList")
        self.nav.setFixedWidth(208)
        self.nav.setSpacing(2)
        for label in NAV_ITEMS:
            QListWidgetItem(label, self.nav)
        self.nav.currentRowChanged.connect(self._navigate)
        sidebar.addWidget(self.nav, stretch=1)
        body.addLayout(sidebar)

        self.stack = QStackedWidget()
        self.library_page = LibraryPage(ctx, mode="library")
        self.download_page = DownloadPage(ctx, self.pool)
        self.playlists_page = PlaylistsPage(ctx)
        self.recent_page = LibraryPage(ctx, mode="recent")
        self.artists_page = LibraryPage(ctx, mode="artists")
        self.albums_page = LibraryPage(ctx, mode="albums")
        self.settings_page = SettingsPage(ctx)
        for page in (
            self.library_page,
            self.download_page,
            self.playlists_page,
            self.recent_page,
            self.artists_page,
            self.albums_page,
            self.settings_page,
        ):
            self.stack.addWidget(page)
        self._catalog_pages = (
            self.library_page,
            self.recent_page,
            self.artists_page,
            self.albums_page,
        )
        body.addWidget(self.stack, stretch=1)
        outer.addLayout(body, stretch=1)
        outer.addWidget(self._build_player_bar())

        for page in self._catalog_pages:
            page.play_requested.connect(self.play_track)
        self.download_page.library_changed.connect(self._refresh_catalog)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")
        self.setStyleSheet(FLUX_QSS)
        self.nav.setCurrentRow(0)

        self._queue_timer = QTimer(self)
        self._queue_timer.setInterval(3000)
        self._queue_timer.timeout.connect(self.download_page._drain_queued)
        self._queue_timer.start()

        failing = [c for c in ctx.diagnostics() if not c.ok and c.name != "Hint"]
        if failing:
            details = "\n".join(f"{c.name}: {c.detail}" for c in failing)
            QMessageBox.warning(
                self,
                "Diagnostics",
                "Some dependencies need attention:\n\n" + details,
            )

    def _refresh_catalog(self) -> None:
        for page in self._catalog_pages:
            page.refresh()
        self.playlists_page.refresh()

    def _build_player_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("playerBar")
        bar.setFixedHeight(88)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 10, 16, 10)

        self.art = QLabel()
        self.art.setFixedSize(56, 56)
        self.art.setStyleSheet("background:#132033; border-radius:6px; border:1px solid #24324A;")
        layout.addWidget(self.art)

        meta = QVBoxLayout()
        self.now_title = QLabel("Nothing playing")
        self.now_title.setObjectName("nowTitle")
        self.now_artist = QLabel("Queue a track from the library")
        self.now_artist.setObjectName("nowArtist")
        meta.addWidget(self.now_title)
        meta.addWidget(self.now_artist)
        layout.addLayout(meta, stretch=1)

        controls = QVBoxLayout()
        buttons = QHBoxLayout()
        prev_btn = QPushButton("⏮")
        prev_btn.setObjectName("btnGhost")
        prev_btn.setToolTip("Previous track")
        prev_btn.clicked.connect(self.play_previous)
        back_btn = QPushButton("-10s")
        back_btn.setObjectName("btnGhost")
        back_btn.setToolTip("Skip back 10 seconds")
        back_btn.clicked.connect(lambda: self._nudge(-10_000))
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("btnPlay")
        self.play_btn.setToolTip("Play / Pause")
        self.play_btn.clicked.connect(self.toggle_play)
        fwd_btn = QPushButton("+10s")
        fwd_btn.setObjectName("btnGhost")
        fwd_btn.setToolTip("Skip forward 10 seconds")
        fwd_btn.clicked.connect(lambda: self._nudge(10_000))
        next_btn = QPushButton("⏭")
        next_btn.setObjectName("btnGhost")
        next_btn.setToolTip("Next track")
        next_btn.clicked.connect(self.play_next)
        for btn in (prev_btn, back_btn, self.play_btn, fwd_btn, next_btn):
            btn.setFixedHeight(36)
            buttons.addWidget(btn)
        controls.addLayout(buttons)
        seek_row = QHBoxLayout()
        self.pos_label = QLabel("0:00")
        self.pos_label.setObjectName("nowArtist")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setTracking(True)
        self.seek.setToolTip("Drag or click to seek")
        self.seek.sliderPressed.connect(self._seek_pressed)
        self.seek.sliderMoved.connect(self._seek_moved)
        self.seek.sliderReleased.connect(self._seek_released)
        self.dur_label = QLabel("0:00")
        self.dur_label.setObjectName("nowArtist")
        seek_row.addWidget(self.pos_label)
        seek_row.addWidget(self.seek, stretch=1)
        seek_row.addWidget(self.dur_label)
        controls.addLayout(seek_row)
        layout.addLayout(controls, stretch=2)

        vol_box = QVBoxLayout()
        vol_label = QLabel("Volume")
        vol_label.setObjectName("nowArtist")
        vol_box.addWidget(vol_label)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(120)
        self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        vol_box.addWidget(self.volume)
        layout.addLayout(vol_box)
        return bar

    def _navigate(self, row: int) -> None:
        if 0 <= row < self.stack.count():
            self.stack.setCurrentIndex(row)
        if row == 2:
            self.playlists_page.refresh()
        elif row == 3:
            self.recent_page.refresh()
        elif row == 4:
            self.artists_page.refresh()
        elif row == 5:
            self.albums_page.refresh()
        elif row == 0:
            self.library_page.refresh()

    def play_track(self, track_id: int) -> None:
        session = self.ctx.session()
        repo = LibraryRepository(session)
        track = repo.get_track(track_id)
        if track is None:
            session.close()
            return
        item = NowPlaying(
            track_id=track.id,
            title=track.title,
            artist=track.artist.name if track.artist else "Unknown",
            album=track.album.title if track.album else "",
            path=Path(track.file_path),
            artwork_path=track.artwork_path,
        )
        others = [
            NowPlaying(
                track_id=t.id,
                title=t.title,
                artist=t.artist.name if t.artist else "Unknown",
                album=t.album.title if t.album else "",
                path=Path(t.file_path),
                artwork_path=t.artwork_path,
            )
            for t in repo.search_tracks("")
        ]
        repo.mark_played(track_id)
        repo.commit()
        session.close()
        start = next((i for i, x in enumerate(others) if x.track_id == track_id), 0)
        self.player_service.set_queue(others or [item], start_at=start)
        self._load_current()

    def _load_current(self) -> None:
        current = self.player_service.current()
        if current is None:
            return
        self.now_title.setText(current.title)
        self.now_artist.setText(
            f"{current.artist} — {current.album}" if current.album else current.artist
        )
        if current.artwork_path and Path(current.artwork_path).is_file():
            self.art.setPixmap(
                QPixmap(current.artwork_path).scaled(
                    56,
                    56,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self.media.setSource(QUrl.fromLocalFile(str(current.path)))
        self.media.play()
        self.play_btn.setText("❚❚")
        self.statusBar().showMessage(f"Playing {current.title}")

    def toggle_play(self) -> None:
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media.pause()
            self.play_btn.setText("▶")
        else:
            self.media.play()
            self.play_btn.setText("❚❚")

    def play_next(self) -> None:
        if self.player_service.next():
            self._load_current()

    def play_previous(self) -> None:
        if self.player_service.previous():
            self._load_current()

    def _on_position(self, pos: int) -> None:
        if self._seeking:
            return
        self.seek.blockSignals(True)
        self.seek.setValue(pos)
        self.seek.blockSignals(False)
        self.pos_label.setText(_fmt_ms(pos))

    def _on_duration(self, dur: int) -> None:
        self.seek.setRange(0, max(dur, 0))
        self.dur_label.setText(_fmt_ms(dur))

    def _seek_pressed(self) -> None:
        self._seeking = True

    def _seek_moved(self, pos: int) -> None:
        self.pos_label.setText(_fmt_ms(pos))

    def _seek_released(self) -> None:
        self.media.setPosition(self.seek.value())
        self._seeking = False
        self.pos_label.setText(_fmt_ms(self.seek.value()))

    def _nudge(self, delta_ms: int) -> None:
        duration = max(self.media.duration(), 0)
        target = max(0, min(duration, self.media.position() + delta_ms))
        self.media.setPosition(target)
        self.seek.blockSignals(True)
        self.seek.setValue(target)
        self.seek.blockSignals(False)
        self.pos_label.setText(_fmt_ms(target))


def _fmt_ms(ms: int) -> str:
    seconds = max(ms, 0) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"
