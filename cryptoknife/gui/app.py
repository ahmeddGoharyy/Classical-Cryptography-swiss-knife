"""Application entry point."""
from __future__ import annotations

import signal
import sys
import time
import traceback

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication, QMessageBox

from .logo import app_icon
from .main_window import MainWindow
from .theme import theme


_last_report = 0.0


def _report_error(exc_type, exc, tb) -> None:
    """Unexpected errors never close the app: log the traceback and tell the user (at most every 5 s)."""
    global _last_report
    traceback.print_exception(exc_type, exc, tb)
    if issubclass(exc_type, KeyboardInterrupt) or QApplication.instance() is None:
        return
    now = time.monotonic()
    if now - _last_report < 5:
        return
    _last_report = now
    box = QMessageBox(QApplication.activeWindow())
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Something went wrong")
    box.setText("An unexpected error happened, but the app is still running.")
    box.setInformativeText("You can keep working. If it happens again, try different input, "
                           "or restart the app.")
    box.setDetailedText("".join(traceback.format_exception(exc_type, exc, tb)))
    box.setStandardButtons(QMessageBox.Ok)
    box.open()  # non-blocking


def main() -> None:
    # Ctrl+C in the terminal quits the app at once instead of printing a KeyboardInterrupt traceback.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.excepthook = _report_error
    # Western digits everywhere, even if the system number locale is e.g. ar_EG.
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
    app = QApplication(sys.argv)
    app.setOrganizationName("cryptoknife")
    app.setApplicationName("Classical Cryptography Swiss Knife")
    app.setWindowIcon(app_icon())
    theme().apply(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
