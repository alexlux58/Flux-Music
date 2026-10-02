"""Metadata editor dialog (tags + optional format/bitrate re-encode)."""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from src.app import AppContext
from src.database.repository import LibraryRepository
from src.services.audio_processor import AudioProcessor
from src.services.library_scanner import file_sha256
from src.services.metadata import MetadataService, TrackMetadata
from src.utils.logging import get_logger

logger = get_logger("metadata_dialog")

FORMAT_CHOICES = ("keep", "m4a", "mp3", "opus", "flac", "wav", "aiff")
BITRATE_CHOICES = ("keep", "320", "256", "192", "160", "128")
LOSSLESS_FORMATS = frozenset({"flac", "wav", "aiff"})


class MetadataDialog(QDialog):
    def __init__(self, ctx: AppContext, track_id: int, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.track_id = track_id
        self.artwork_path: Path | None = None
        self.setWindowTitle("Edit track")
        self.resize(520, 560)

        session = ctx.session()
        repo = LibraryRepository(session)
        track = repo.get_track(track_id)
        session.close()
        if track is None:
            QMessageBox.critical(self, "Missing", "Track not found")
            self.reject()
            return

        self.file_path = Path(track.file_path)
        self._original_codec = (track.codec or self.file_path.suffix.lstrip(".")).lower()
        self._original_bitrate = track.bitrate

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title = QLineEdit(track.title)
        self.artist = QLineEdit(track.artist.name if track.artist else "")
        self.album = QLineEdit(track.album.title if track.album else "")
        self.album_artist = QLineEdit(track.album_artist or "")
        self.track_no = QSpinBox()
        self.track_no.setRange(0, 999)
        self.track_no.setValue(track.track_number or 0)
        self.disc_no = QSpinBox()
        self.disc_no.setRange(0, 99)
        self.disc_no.setValue(track.disc_number or 0)
        self.year = QSpinBox()
        self.year.setRange(0, 2100)
        self.year.setValue(track.year or 0)
        self.genre = QLineEdit(track.genre or "")
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(0, 300)
        self.bpm.setDecimals(1)
        self.bpm.setSpecialValueText("Unknown")
        self.bpm.setValue(track.bpm or 0)
        self.bpm.setToolTip("Estimated tempo; correct half/double-tempo readings here.")

        self.format_box = QComboBox()
        self.format_box.addItems(list(FORMAT_CHOICES))
        current_fmt = self._normalize_format(self._original_codec)
        idx = self.format_box.findText(current_fmt)
        self.format_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.format_box.currentTextChanged.connect(self._on_format_changed)

        self.bitrate_box = QComboBox()
        self.bitrate_box.addItems(list(BITRATE_CHOICES))
        kbps = self._bitrate_kbps(self._original_bitrate)
        if kbps is not None:
            closest = min((320, 256, 192, 160, 128), key=lambda x: abs(x - kbps))
            bi = self.bitrate_box.findText(str(closest))
            if bi >= 0:
                self.bitrate_box.setCurrentIndex(bi)

        self.reencode = QCheckBox("Re-encode audio when format/bitrate changes")
        self.reencode.setChecked(True)
        self.reencode.setToolTip(
            "Uses FFmpeg to rewrite the file. Leave unchecked to only update database fields."
        )
        self._on_format_changed(self.format_box.currentText())

        current = QLabel(
            f"Current file: {self.file_path.name} · "
            f"format={self._original_codec or '—'} · "
            f"bitrate={self._format_bitrate(self._original_bitrate)}"
        )
        current.setWordWrap(True)
        current.setObjectName("pageSubtitle")

        form.addRow("Title", self.title)
        form.addRow("Artist", self.artist)
        form.addRow("Album", self.album)
        form.addRow("Album artist", self.album_artist)
        form.addRow("Track", self.track_no)
        form.addRow("Disc", self.disc_no)
        form.addRow("Year", self.year)
        form.addRow("Genre", self.genre)
        form.addRow("BPM", self.bpm)
        form.addRow("Format", self.format_box)
        form.addRow("Bitrate (kbps)", self.bitrate_box)
        form.addRow("", self.reencode)
        layout.addWidget(current)
        layout.addLayout(form)

        art_row = QHBoxLayout()
        self.art_label = QLabel()
        self.art_label.setFixedSize(128, 128)
        if track.artwork_path and Path(track.artwork_path).is_file():
            self.artwork_path = Path(track.artwork_path)
            self.art_label.setPixmap(QPixmap(str(self.artwork_path)).scaled(128, 128))
        art_row.addWidget(self.art_label)
        pick = QPushButton("Replace artwork…")
        pick.clicked.connect(self._pick_art)
        art_row.addWidget(pick)
        art_row.addStretch(1)
        layout.addLayout(art_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _normalize_format(codec: str | None) -> str:
        value = (codec or "").lower()
        if value in {"m4a", "aac", "mp4"}:
            return "m4a"
        if value in {"mp3"}:
            return "mp3"
        if value in {"opus", "ogg"}:
            return "opus"
        if value in {"flac"}:
            return "flac"
        if value in {"wav", "wave", "pcm_s16le"}:
            return "wav"
        if value in {"aiff", "aif", "pcm_s16be"}:
            return "aiff"
        return "keep"

    def _on_format_changed(self, fmt: str) -> None:
        lossless = fmt in LOSSLESS_FORMATS
        self.bitrate_box.setEnabled(not lossless)
        if lossless:
            self.bitrate_box.setCurrentText("keep")
            self.bitrate_box.setToolTip("Bitrate does not apply to lossless PCM/FLAC.")
        else:
            self.bitrate_box.setToolTip("")

    @staticmethod
    def _bitrate_kbps(bitrate: int | None) -> int | None:
        if not bitrate:
            return None
        return bitrate // 1000 if bitrate >= 1000 else bitrate

    @staticmethod
    def _format_bitrate(bitrate: int | None) -> str:
        kbps = MetadataDialog._bitrate_kbps(bitrate)
        return f"{kbps} kbps" if kbps else "—"

    def _pick_art(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Artwork", "", "Images (*.jpg *.jpeg *.png *.webp)"
        )
        if path:
            self.artwork_path = Path(path)
            self.art_label.setPixmap(QPixmap(path).scaled(128, 128))

    def _target_format(self) -> str | None:
        choice = self.format_box.currentText()
        if choice == "keep":
            return None
        return choice

    def _target_bitrate_kbps(self) -> int | None:
        choice = self.bitrate_box.currentText()
        if choice == "keep":
            return None
        return int(choice)

    def _needs_reencode(self) -> bool:
        target_fmt = self._target_format()
        target_br = self._target_bitrate_kbps()
        current_fmt = self._normalize_format(self._original_codec)
        if target_fmt and target_fmt != current_fmt and target_fmt != "keep":
            return True
        if target_br is not None:
            current_br = self._bitrate_kbps(self._original_bitrate)
            if current_br is None or abs(current_br - target_br) > 8:
                return True
        return False

    def _save(self) -> None:
        meta = TrackMetadata(
            title=self.title.text().strip(),
            artist=self.artist.text().strip(),
            album=self.album.text().strip() or None,
            album_artist=self.album_artist.text().strip() or None,
            track_number=self.track_no.value() or None,
            disc_number=self.disc_no.value() or None,
            year=self.year.value() or None,
            genre=self.genre.text().strip() or None,
            bpm=self.bpm.value() or None,
        )
        try:
            working_path = self.file_path
            codec = self._original_codec
            bitrate = self._original_bitrate
            sample_rate = None
            digest = None

            if self.reencode.isChecked() and self._needs_reencode():
                target_fmt = self._target_format() or self._normalize_format(self._original_codec)
                if target_fmt == "keep":
                    target_fmt = "m4a"
                target_br = self._target_bitrate_kbps()
                if target_fmt in LOSSLESS_FORMATS:
                    target_br = None
                elif target_br is None:
                    target_br = self._bitrate_kbps(self._original_bitrate) or 256

                processor = AudioProcessor()
                if not processor.ffmpeg:
                    QMessageBox.critical(self, "FFmpeg missing", "Install FFmpeg to re-encode.")
                    return

                answer = QMessageBox.question(
                    self,
                    "Re-encode file",
                    f"Convert to {target_fmt}"
                    + (f" @ {target_br} kbps" if target_br else "")
                    + "?\nThe original file will be replaced after a successful convert.",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

                tmp_out = working_path.with_name(f".{working_path.stem}.tmp.{target_fmt}")
                converted = processor.convert_to_format(
                    working_path,
                    target_format=target_fmt,
                    bitrate_kbps=target_br,
                    destination=tmp_out,
                )
                final_path = working_path.with_suffix(converted.suffix)
                if final_path.exists() and final_path.resolve() != working_path.resolve():
                    final_path.unlink()
                if working_path.resolve() != converted.resolve():
                    if final_path.resolve() == working_path.resolve():
                        working_path.unlink(missing_ok=True)
                    shutil.move(str(converted), str(final_path))
                else:
                    final_path = converted

                working_path = final_path
                probe = processor.probe(working_path)
                codec = probe.codec or target_fmt
                bitrate = probe.bitrate
                sample_rate = probe.sample_rate
                digest = file_sha256(working_path)
                meta.duration = probe.duration
                meta.codec = codec
                meta.bitrate = bitrate
                meta.sample_rate = sample_rate

            MetadataService().write(working_path, meta, artwork=self.artwork_path)
            session = self.ctx.session()
            repo = LibraryRepository(session)
            updates: dict[str, object] = {
                "title": meta.title,
                "artist_name": meta.artist,
                "album_title": meta.album,
                "album_artist": meta.album_artist,
                "track_number": meta.track_number,
                "disc_number": meta.disc_number,
                "year": meta.year,
                "genre": meta.genre,
                "bpm": meta.bpm,
                "artwork_path": str(self.artwork_path) if self.artwork_path else None,
            }
            if working_path != self.file_path or digest:
                updates["file_path"] = str(working_path)
                updates["codec"] = codec
                if bitrate is not None:
                    updates["bitrate"] = bitrate
                if sample_rate is not None:
                    updates["sample_rate"] = sample_rate
                if meta.duration is not None:
                    updates["duration_seconds"] = meta.duration
                if digest:
                    updates["file_hash"] = digest
            elif not self.reencode.isChecked():
                # DB-only format/bitrate labels when user unchecked re-encode
                target_fmt = self._target_format()
                target_br = self._target_bitrate_kbps()
                if target_fmt:
                    updates["codec"] = target_fmt
                if target_br is not None:
                    updates["bitrate"] = target_br * 1000

            repo.update_track_metadata(self.track_id, **updates)
            repo.commit()
            session.close()
            self.file_path = working_path
            self.accept()
        except Exception as exc:
            logger.exception("Track edit failed")
            QMessageBox.critical(self, "Save failed", str(exc))
