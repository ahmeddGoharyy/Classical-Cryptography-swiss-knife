"""Searchable command palette (Ctrl+K) for jumping to any cipher or tool."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtWidgets import (QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget)

from ..core.cipher import all_ciphers
from .widgets import StartLineEdit


def entries() -> list[tuple[str, str, str]]:
    """(page key, title, subtitle) for everything the palette can open — a flat list, no groups."""
    items = [("home", "Home", "About the app")]
    items += [(f"cipher:{c.id}", c.name, c.summary) for c in all_ciphers()]
    items.append(("freq", "Frequency analysis", "Letter statistics of any text compared with English"))
    return items


class _Row(QWidget):
    def __init__(self, title: str, subtitle: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(1)
        t = QLabel(title)
        t.setStyleSheet("font-weight: 600; background: transparent;")
        s = QLabel(subtitle)
        s.setObjectName("muted")
        s.setStyleSheet("font-size: 9pt; background: transparent;")
        lay.addWidget(t)
        lay.addWidget(s)


class CommandPalette(QFrame):
    """Popup with a search box and a filtered list; emits the chosen page key."""
    chosen = Signal(str)

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setObjectName("palette")
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        self.search = StartLineEdit()
        self.search.setPlaceholderText("Search ciphers and tools…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.installEventFilter(self)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("paletteList")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.itemActivated.connect(self._activate)
        self.list.itemClicked.connect(self._activate)
        lay.addWidget(self.list)
        for key, title, sub in entries():
            it = QListWidgetItem()
            it.setData(Qt.UserRole, key)
            it.setData(Qt.UserRole + 1, f"{title} {sub}".lower())
            it.setSizeHint(QSize(0, 52))
            self.list.addItem(it)
            self.list.setItemWidget(it, _Row(title, sub))
        self.empty = QLabel("No matches")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        lay.addWidget(self.empty)

    def open_below(self, anchor: QWidget, current: str = "") -> None:
        w = max(460, anchor.width())
        h = min(560, 64 + 52 * self.list.count())
        top_left = anchor.mapToGlobal(QPoint((anchor.width() - w) // 2, anchor.height() + 6))
        self.setGeometry(top_left.x(), top_left.y(), w, h)
        self.search.clear()
        self._filter("")
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == current:
                self.list.setCurrentRow(i)
                break
        self.show()
        self.search.setFocus()

    def _filter(self, text: str) -> None:
        words = text.lower().split()
        first = None
        for i in range(self.list.count()):
            it = self.list.item(i)
            hidden = not all(w in it.data(Qt.UserRole + 1) for w in words)
            it.setHidden(hidden)
            if not hidden and first is None:
                first = i
        self.empty.setVisible(first is None)
        if first is not None and (self.list.currentItem() is None or self.list.currentItem().isHidden() or words):
            self.list.setCurrentRow(first)

    def _move(self, step: int) -> None:
        rows = [i for i in range(self.list.count()) if not self.list.item(i).isHidden()]
        if not rows:
            return
        cur = self.list.currentRow()
        pos = rows.index(cur) if cur in rows else -1
        self.list.setCurrentRow(rows[(pos + step) % len(rows)])

    def eventFilter(self, obj, ev):
        if obj is self.search and ev.type() == QEvent.KeyPress:
            if ev.key() == Qt.Key_Down:
                self._move(1)
                return True
            if ev.key() == Qt.Key_Up:
                self._move(-1)
                return True
            if ev.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.list.currentItem() and not self.list.currentItem().isHidden():
                    self._activate(self.list.currentItem())
                return True
            if ev.key() == Qt.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, ev)

    def _activate(self, item: QListWidgetItem) -> None:
        self.hide()
        self.chosen.emit(item.data(Qt.UserRole))
