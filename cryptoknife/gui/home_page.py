"""Landing page: the logo and a short description of the app, centred."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .logo import logo_pixmap
from .theme import theme
from .widgets import label


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 30, 32, 30)
        lay.setSpacing(0)
        lay.addStretch(1)
        self.logo = QLabel()
        self.logo.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.logo)
        lay.addSpacing(18)
        name = label("Crypto Swiss Knife")
        name.setStyleSheet("font-size: 30pt; font-weight: 800;")
        name.setAlignment(Qt.AlignCenter)
        lay.addWidget(name)
        lay.addSpacing(10)
        desc = label("Learn, visualize and break ciphers — watch every encryption step unfold, "
                     "or let the app find the key.", "muted", wrap=True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("font-size: 12.5pt;")
        lay.addWidget(desc)
        lay.addStretch(1)
        theme().changed.connect(self._paint_logo)
        self._paint_logo()

    def _paint_logo(self) -> None:
        self.logo.setPixmap(logo_pixmap(210, color=theme().ui["text"]))
