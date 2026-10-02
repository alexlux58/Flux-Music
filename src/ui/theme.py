"""Alex Flux inspired desktop theme (navy + electric cyan)."""

from __future__ import annotations

FLUX_QSS = """
QWidget {
  background-color: #070B14;
  color: #E8EEF7;
  font-size: 13px;
  font-family: "Segoe UI", "Inter", sans-serif;
}
QMainWindow, QDialog {
  background-color: #070B14;
}
QListWidget#navList {
  background: #0B1220;
  border: none;
  border-right: 1px solid #1B2A44;
  padding: 12px 8px;
  outline: none;
}
QListWidget#navList::item {
  padding: 11px 14px;
  border-radius: 8px;
  margin: 2px 4px;
  color: #A8B8D0;
}
QListWidget#navList::item:hover {
  background: #132033;
  color: #E8EEF7;
}
QListWidget#navList::item:selected {
  background: #12324A;
  color: #7DF0FF;
  font-weight: 600;
}
QLineEdit, QTextEdit, QSpinBox, QComboBox, QTableWidget, QListWidget {
  background: #0F172A;
  border: 1px solid #24324A;
  border-radius: 8px;
  padding: 7px 10px;
  color: #E8EEF7;
  selection-background-color: #155E75;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {
  border: 1px solid #22D3EE;
}
QHeaderView::section {
  background: #0B1220;
  color: #8BA3C7;
  border: none;
  border-bottom: 1px solid #1B2A44;
  padding: 8px;
  font-weight: 600;
}
QTableWidget {
  gridline-color: #1B2A44;
  alternate-background-color: #0C1424;
}
QTableWidget::item:selected {
  background: #155E75;
  color: #F0FDFF;
}
QPushButton {
  background: #22D3EE;
  color: #04202A;
  border: none;
  border-radius: 10px;
  padding: 8px 16px;
  font-weight: 700;
}
QPushButton:hover { background: #67E8F9; }
QPushButton:pressed { background: #06B6D4; }
QPushButton:disabled { background: #1E293B; color: #64748B; }
QPushButton#btnSecondary {
  background: transparent;
  color: #7DF0FF;
  border: 1px solid #155E75;
}
QPushButton#btnSecondary:hover { background: #12324A; }
QPushButton#btnGhost {
  background: #132033;
  color: #E8EEF7;
  border: 1px solid #24324A;
  font-weight: 600;
}
QPushButton#btnGhost:hover { background: #1B2A44; }
QPushButton#btnDanger {
  background: transparent;
  color: #FCA5A5;
  border: 1px solid #7F1D1D;
}
QPushButton#btnPlay {
  background: #22D3EE;
  color: #04202A;
  min-width: 48px;
}
#pageTitle { font-size: 24px; font-weight: 700; color: #F8FAFC; letter-spacing: -0.3px; }
#pageSubtitle { color: #8BA3C7; }
#brandMark { color: #22D3EE; font-weight: 800; font-size: 15px; letter-spacing: 0.4px; }
#emptyState { color: #8BA3C7; font-size: 14px; padding: 32px; }
#playerBar {
  background: #0B1220;
  border-top: 1px solid #1B2A44;
}
#nowTitle { font-weight: 700; }
#nowArtist { color: #8BA3C7; }
QSlider::groove:horizontal {
  height: 5px;
  background: #1E3A5F;
  border-radius: 3px;
}
QSlider::sub-page:horizontal {
  background: #22D3EE;
  border-radius: 3px;
}
QSlider::handle:horizontal {
  width: 14px;
  height: 14px;
  margin: -5px 0;
  background: #F0FDFF;
  border: 2px solid #22D3EE;
  border-radius: 8px;
}
QStatusBar {
  background: #070B14;
  color: #8BA3C7;
  border-top: 1px solid #1B2A44;
}
QMenu {
  background: #0F172A;
  border: 1px solid #24324A;
  color: #E8EEF7;
}
QMenu::item:selected { background: #155E75; }
QScrollBar:vertical {
  background: #070B14;
  width: 10px;
  margin: 0;
}
QScrollBar::handle:vertical {
  background: #24324A;
  min-height: 24px;
  border-radius: 5px;
}
QToolTip {
  background: #0F172A;
  color: #E8EEF7;
  border: 1px solid #22D3EE;
}
"""
