"""Application entry point."""
from __future__ import annotations

import sys

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import theme


def main() -> None:
    # Western digits everywhere, even if the system number locale is e.g. ar_EG.
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
    app = QApplication(sys.argv)
    app.setOrganizationName("cryptoknife")
    app.setApplicationName("Classical Cryptography Swiss Knife")
    theme().apply(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
