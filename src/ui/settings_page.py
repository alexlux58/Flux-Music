"""Settings and diagnostics."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.app import AppContext
from src.config import _deep_merge, load_yaml_config


class SettingsPage(QWidget):
    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Local paths, format defaults, and diagnostics. Nothing here is sent to a cloud."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.music_root = QLabel(str(ctx.config.paths.music_root))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_music)
        music_row = QHBoxLayout()
        music_row.addWidget(self.music_root, stretch=1)
        music_row.addWidget(browse)
        form.addRow("Music library", music_row)
        self.copy_roots = QLineEdit(";".join(str(p) for p in ctx.config.paths.copy_roots))
        self.copy_roots.setPlaceholderText("Extra copy folders, separated by semicolons")
        form.addRow("Also save songs to", self.copy_roots)

        self.bpm_folders = QCheckBox("Automatically group downloads into 10 BPM folders")
        self.bpm_folders.setChecked(ctx.config.organization.categorize_by_bpm)
        form.addRow("Tempo", self.bpm_folders)

        self.format = QComboBox()
        self.format.addItems(["original", "m4a", "opus", "mp3", "flac", "wav", "aiff"])
        self.format.setCurrentText(ctx.config.audio.default_format)
        form.addRow("Default format", self.format)

        self.bitrate = QComboBox()
        self.bitrate.addItems(["320", "256", "192"])
        self.bitrate.setCurrentText(str(ctx.config.audio.mp3_bitrate))
        form.addRow("MP3 bitrate", self.bitrate)

        self.concurrent = QSpinBox()
        self.concurrent.setRange(1, 8)
        self.concurrent.setValue(ctx.config.audio.concurrent_downloads)
        form.addRow("Concurrent downloads", self.concurrent)

        self.embed_art = QCheckBox("Embed artwork when possible")
        self.embed_art.setChecked(ctx.config.audio.embed_artwork)
        form.addRow("", self.embed_art)

        self.dup_source = QComboBox()
        self.dup_source.addItems(["skip", "ask", "download_copy"])
        self.dup_source.setCurrentText(ctx.config.duplicates.on_source_id_match)
        form.addRow("On source-ID duplicate", self.dup_source)

        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(ctx.config.ui.theme)
        form.addRow("Theme", self.theme)

        self.web_host = QLabel(f"{ctx.config.ui.web_host}:{ctx.config.ui.web_port}")
        form.addRow("Web UI bind", self.web_host)

        layout.addLayout(form)

        actions = QHBoxLayout()
        save = QPushButton("Save settings")
        save.clicked.connect(self.save)
        actions.addWidget(save)
        diag = QPushButton("Run diagnostics")
        diag.setObjectName("btnGhost")
        diag.clicked.connect(self.show_diagnostics)
        actions.addWidget(diag)
        logs = QPushButton("Open log viewer")
        logs.setObjectName("btnSecondary")
        logs.clicked.connect(self.show_logs)
        actions.addWidget(logs)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, stretch=1)

    def _browse_music(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Music library location")
        if path:
            self.music_root.setText(path)

    def save(self) -> None:
        # Persist overrides into config/local.yaml via simple write
        import yaml

        local_path = self.ctx.root / "config" / "local.yaml"
        data = {
            "paths": {
                "music_root": self.music_root.text(),
                "copy_roots": [p.strip() for p in self.copy_roots.text().split(";") if p.strip()],
            },
            "audio": {
                "default_format": self.format.currentText(),
                "mp3_bitrate": int(self.bitrate.currentText()),
                "concurrent_downloads": self.concurrent.value(),
                "embed_artwork": self.embed_art.isChecked(),
            },
            "organization": {"categorize_by_bpm": self.bpm_folders.isChecked()},
            "duplicates": {"on_source_id_match": self.dup_source.currentText()},
            "ui": {"theme": self.theme.currentText()},
        }
        local_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep persistent database, legacy read roots and other unedited overrides.
        data = _deep_merge(load_yaml_config(local_path), data)
        local_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        # Apply to running config where safe
        self.ctx.config.paths.music_root = Path(self.music_root.text())
        self.ctx.config.paths.copy_roots = [Path(p) for p in data["paths"]["copy_roots"]]
        self.ctx.config.audio.default_format = self.format.currentText()  # type: ignore[assignment]
        self.ctx.config.audio.mp3_bitrate = int(self.bitrate.currentText())  # type: ignore[assignment]
        self.ctx.config.audio.concurrent_downloads = self.concurrent.value()
        self.ctx.config.audio.embed_artwork = self.embed_art.isChecked()
        self.ctx.config.duplicates.on_source_id_match = self.dup_source.currentText()  # type: ignore[assignment]
        self.ctx.config.organization.categorize_by_bpm = self.bpm_folders.isChecked()
        self.ctx.config.ui.theme = self.theme.currentText()  # type: ignore[assignment]
        QMessageBox.information(
            self,
            "Saved",
            "Settings saved to config/local.yaml. Restart if theme does not refresh.",
        )

    def show_diagnostics(self) -> None:
        lines = []
        for check in self.ctx.diagnostics():
            mark = "OK" if check.ok else "FAIL"
            lines.append(f"{check.name}: {mark} — {check.detail}")
        self.output.setPlainText("\n".join(lines))

    def show_logs(self) -> None:
        log_file = self.ctx.config.paths.log_file
        if not log_file.is_file():
            self.output.setPlainText("No log file yet.")
            return
        text = log_file.read_text(encoding="utf-8", errors="replace")
        self.output.setPlainText(text[-20000:])
