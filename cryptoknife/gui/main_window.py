"""Main window: grouped left sidebar + lazily created pages."""
from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from ..core.cipher import get_cipher
from .cipher_page import CipherPage
from .frequency_page import FrequencyPage
from .home_page import HomePage
from .logo import app_icon
from .sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Classical Cryptography Swiss Knife")
        self.setWindowIcon(app_icon())
        self.setMinimumSize(980, 600)
        self.resize(1480, 920)
        self.pages: dict[str, QWidget] = {}
        central = QWidget()
        central.setObjectName("content")
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = Sidebar()
        self.sidebar.selected.connect(self.open_page)
        h.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        for seq in ("Ctrl+K", "Ctrl+F"):
            QShortcut(QKeySequence(seq), self, self.sidebar.focus_search)
        self.open_page("home")

    def open_page(self, key: str) -> None:
        if key not in self.pages:
            if key == "home":
                page = HomePage()
            elif key == "freq":
                page = FrequencyPage()
            else:
                page = CipherPage(get_cipher(key.split(":", 1)[1]))
            self.pages[key] = page
            self.stack.addWidget(page)
        self.sidebar.select(key)
        self.stack.setCurrentWidget(self.pages[key])

    def closeEvent(self, ev) -> None:
        for page in self.pages.values():
            crack = getattr(page, "crack", None)
            if crack is not None:
                crack.shutdown()
        super().closeEvent(ev)
