"""Landing page: a small logo, the app name and one line on how to start, centred."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .logo import logo_pixmap
from .widgets import label


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 30, 32, 30)
        lay.setSpacing(0)
        lay.addStretch(1)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(72, tile=True))
        logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(logo)
        lay.addSpacing(18)
        title = QLabel("Crypto Swiss Knife")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22pt; font-weight: 700;")
        lay.addWidget(title)
        lay.addSpacing(8)
        desc = label("Encrypt, visualize and crack classical ciphers.", "muted", wrap=True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("font-size: 12pt;")
        lay.addWidget(desc)
        lay.addSpacing(20)
        hint = label("Pick a cipher from the menu, or press Ctrl+K to search.", "muted", wrap=True)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("font-size: 10pt;")
        lay.addWidget(hint)
        lay.addStretch(1)
