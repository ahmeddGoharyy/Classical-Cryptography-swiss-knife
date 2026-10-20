"""Landing page: the emblem (with the app name) and a short description, centred."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .logo import emblem_pixmap
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
        lay.addSpacing(22)
        desc = label("Learn, visualize and break ciphers — watch every encryption step unfold, "
                     "or let the app find the key.", "muted", wrap=True)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("font-size: 12.5pt;")
        lay.addWidget(desc)
        lay.addStretch(1)
        theme().changed.connect(self._paint_logo)
        self._paint_logo()

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._paint_logo()

    def _paint_logo(self) -> None:
        # the emblem already carries the name; scale it with the window (but keep room for the tagline)
        h = max(200, min(420, self.height() - 170, self.width() - 80))
        if getattr(self, "_logo_key", None) != (h, theme().name):
            self._logo_key = (h, theme().name)
            self.logo.setPixmap(emblem_pixmap(h, theme().ui["text"]))
