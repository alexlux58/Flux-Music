"""Real UI fixture: numeric tempo sorting and preservation of persistent paths."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from src.app import create_app
from src.config import load_yaml_config
from src.database.repository import LibraryRepository
from src.ui.library_page import LibraryPage
from src.ui.settings_page import SettingsPage


def test_bpm_column_sorts_numerically(qtbot, tmp_path):
    ctx = create_app(root=tmp_path)
    session = ctx.session()
    repo = LibraryRepository(session)
    for title, bpm in (("Slow", 90), ("Fast", 120), ("Unknown", None)):
        repo.add_track(title=title, file_path=tmp_path / (title + ".m4a"), bpm=bpm)
    repo.commit()
    session.close()
    page = LibraryPage(ctx)
    qtbot.addWidget(page)
    assert page.table.horizontalHeaderItem(7).text() == "BPM"
    page.table.sortItems(7, Qt.SortOrder.AscendingOrder)
    values = [page.table.item(row, 7).text() for row in range(page.table.rowCount())]
    known = [float(value) for value in values if value != "—"]
    assert known == [90, 120]
    assert "Unknown BPM" in [page.table.item(row, 8).text() for row in range(3)]
    ctx.engine.dispose()


def test_settings_retains_catalog_and_read_roots(qtbot, tmp_path, monkeypatch):
    ctx = create_app(root=tmp_path)
    local = tmp_path / "config/local.yaml"
    local.parent.mkdir()
    local.write_text("paths:\n  database: legacy/catalog.db\n  read_roots: [legacy/music]\n")
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    page = SettingsPage(ctx)
    qtbot.addWidget(page)
    page.bpm_folders.setChecked(False)
    page.save()
    data = load_yaml_config(local)
    assert data["paths"]["database"] == "legacy/catalog.db"
    assert data["paths"]["read_roots"] == ["legacy/music"]
    assert data["organization"]["categorize_by_bpm"] is False
    ctx.engine.dispose()
