"""Shared Qt widgets."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)
        if subtitle:
            body = QLabel(subtitle)
            body.setWordWrap(True)
            body.setObjectName("pageSubtitle")
            layout.addWidget(body)
        layout.addStretch(1)


class StatusPill(QLabel):
    def __init__(self, text: str = "Ready", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("statusPill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
