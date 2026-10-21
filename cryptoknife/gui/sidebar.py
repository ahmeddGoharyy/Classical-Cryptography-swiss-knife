"""Left navigation: brand, search, collapsible colour-coded categories with icon items, theme toggle."""
from __future__ import annotations

import re

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from ..core.cipher import all_ciphers
from .logo import logo_pixmap
from .nav_icons import ICONS, icon_pixmap
from .theme import theme

AUTHOR = "Ahmed El Gohary"

# Menu categories: (title, icon glyph, colour, one-line description)
CLASSICAL = ("Classical ciphers", "classical", "#4f8cff", "Pen-and-paper ciphers")
MODERN = [("Modern symmetric", "symmetric", "#2dd4bf", "One shared secret key"),
          ("Modern asymmetric", "asymmetric", "#a78bfa", "Public / private key pair")]
TOOLS = ("Tools", "tools", "#22c55e", "Text statistics")
# cipher family -> badge colour of its items (keeps related ciphers visually close without sub-groups)
FAMILY_COLORS = {
    "Monoalphabetic substitution": "#4f8cff",
    "Polyalphabetic substitution": "#a78bfa",
    "Polygraphic substitution": "#f5b84b",
    "Transposition": "#2dd4bf",
}
# id -> (title, subtitle) shown in the menu
DISPLAY = {"caesar": ("Caesar", "shift cipher"), "monoalphabetic": ("Monoalphabetic", "substitution table"),
           "homophonic": ("Homophonic", "several symbols per letter"),
           "polyalphabetic": ("Polyalphabetic", "several alphabets in turn"),
           "digraph": ("Digraph", "higher-order pair table"),
           "vigenere": ("Vigenère", "repeating key"), "autokey": ("Autokey", "Vigenère variant"),
           "otp": ("One-time pad", "perfect secrecy"), "playfair": ("Playfair", "5×5 key square"),
           "hill": ("Hill", "matrix cipher"), "columnar": ("Columnar", "transposition table"),
           "railfence": ("Rail fence", "zigzag"), "freq": ("Frequency analysis", "letter statistics")}


def rgba(hex_color: str, alpha: float) -> str:
    """'#4f8cff', 0.16 -> 'rgba(79, 140, 255, 0.16)' (Qt reads 8-digit hex as #AARRGGBB, so avoid it)."""
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


def split_name(name: str) -> tuple[str, str]:
    """'Vigenère (repeating key)' -> ('Vigenère', 'repeating key')."""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", name)
    return (m.group(1), m.group(2)) if m else (name, "")


class NavItem(QPushButton):
    def __init__(self, key: str, title: str, subtitle: str, icon: str, color: str):
        super().__init__()
        self.key = key
        self.search_text = f"{title} {subtitle}".lower()
        self.setObjectName("navItem")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(40 if not subtitle else 46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(10)
        badge = QLabel()
        badge.setPixmap(icon_pixmap(icon, color, 18))
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(30, 30)
        badge.setStyleSheet(f"background: {rgba(color, 0.16)}; border-radius: 8px;")
        badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(badge)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("navTitle")
        t.setAttribute(Qt.WA_TransparentForMouseEvents)
        texts.addWidget(t)
        if subtitle:
            st = QLabel(subtitle)
            st.setObjectName("navSub")
            st.setAttribute(Qt.WA_TransparentForMouseEvents)
            texts.addWidget(st)
        lay.addLayout(texts, 1)


class Group(QWidget):
    def __init__(self, title: str, icon: str, color: str, desc: str, items: list[NavItem]):
        super().__init__()
        self.items = items
        self.title = title
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.header = QPushButton()
        self.header.setObjectName("groupHeader")
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setCheckable(True)
        self.header.setChecked(QSettings().value(f"nav/open/{title}", True, type=bool))
        h = QHBoxLayout(self.header)
        h.setContentsMargins(8, 6, 10, 6)
        h.setSpacing(10)
        tile = QLabel()
        tile.setPixmap(icon_pixmap(icon, "#ffffff", 18))
        tile.setAlignment(Qt.AlignCenter)
        tile.setFixedSize(30, 30)
        tile.setStyleSheet(f"background: {color}; border-radius: 9px;")
        tile.setAttribute(Qt.WA_TransparentForMouseEvents)
        h.addWidget(tile)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("groupTitle")
        t.setWordWrap(True)
        t.setAttribute(Qt.WA_TransparentForMouseEvents)
        d = QLabel(desc)
        d.setObjectName("navSub")
        d.setAttribute(Qt.WA_TransparentForMouseEvents)
        texts.addWidget(t)
        texts.addWidget(d)
        h.addLayout(texts, 1)
        self.count = QLabel(str(len(items)))
        self.count.setObjectName("countPill")
        self.count.setAlignment(Qt.AlignCenter)
        self.count.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.count.setVisible(bool(items))  # empty categories: no "0" pill, more room for the title
        h.addWidget(self.count)
        self.chev = QLabel()
        self.chev.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.chev.setObjectName("navSub")
        h.addWidget(self.chev)
        lay.addWidget(self.header)
        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(14, 2, 0, 6)
        bl.setSpacing(2)
        for it in items:
            bl.addWidget(it)
        if not items:
            soon = QLabel("Coming soon")
            soon.setObjectName("navSub")
            soon.setContentsMargins(12, 4, 0, 4)
            bl.addWidget(soon)
        lay.addWidget(self.body)
        self.header.toggled.connect(self._toggle)
        self._toggle(self.header.isChecked())

    def _toggle(self, open_: bool) -> None:
        QSettings().setValue(f"nav/open/{self.title}", open_)
        self.body.setVisible(open_)
        self.chev.setText("▾" if open_ else "▸")

    def filter(self, words: list[str]) -> bool:
        visible = 0
        for it in self.items:
            ok = all(w in it.search_text for w in words)
            it.setVisible(ok)
            visible += ok
        self.setVisible(visible > 0 or not words)
        if words:
            self.body.setVisible(True)
            self.chev.setText("▾")
        else:
            self._toggle(self.header.isChecked())
        return visible > 0


class Sidebar(QFrame):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(272)
        self.items: dict[str, NavItem] = {}
        self.buttons = QButtonGroup(self)
        self.buttons.setExclusive(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 16, 14, 12)
        lay.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(logo_pixmap(40, tile=True))
        logo.setFixedSize(40, 40)
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        b1 = QLabel("Crypto Swiss Knife")
        b1.setObjectName("brand")
        b2 = QLabel("Classical cryptography")
        b2.setObjectName("brandSub")
        names.addWidget(b1)
        names.addWidget(b2)
        brand.addLayout(names, 1)
        lay.addLayout(brand)

        self.search = QLineEdit()
        self.search.setObjectName("navSearch")
        self.search.setPlaceholderText("🔍  Search ciphers…   Ctrl+K")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._open_first)
        lay.addWidget(self.search)

        nav = QWidget()
        nav.setObjectName("navArea")
        self.nav_lay = QVBoxLayout(nav)
        self.nav_lay.setContentsMargins(0, 0, 4, 0)
        self.nav_lay.setSpacing(6)
        self.home = self._item("home", "Home", "about the app", "home", "#9aa0a8")
        self.nav_lay.addWidget(self.home)
        self.groups: list[Group] = []
        title, icon, color, desc = CLASSICAL
        items = []
        for c in all_ciphers():
            t, sub = DISPLAY.get(c.id) or split_name(c.name)
            badge = FAMILY_COLORS.get(c.family, color)
            items.append(self._item(f"cipher:{c.id}", t, sub, c.id if c.id in ICONS else "classical", badge, c.summary))
        for title, icon, color, desc in [CLASSICAL, *MODERN]:
            g = Group(title, icon, color, desc, items if title == CLASSICAL[0] else [])
            self.groups.append(g)
            self.nav_lay.addWidget(g)
        t_title, t_icon, t_color, t_desc = TOOLS
        tool = Group(t_title, t_icon, t_color, t_desc,
                     [self._item("freq", *DISPLAY["freq"], "freq", t_color,
                                 "Letter statistics of any text")])
        self.groups.append(tool)
        self.nav_lay.addWidget(tool)
        self.nav_lay.addStretch(1)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sc.setWidget(nav)
        lay.addWidget(sc, 1)

        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        lay.addWidget(line)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("themeToggle")
        self.theme_btn.setCursor(Qt.PointingHandCursor)
        self.theme_btn.clicked.connect(theme().toggle)
        theme().changed.connect(self._theme_text)
        self._theme_text()
        lay.addWidget(self.theme_btn)
        credit = QLabel(f"Vibe coded by <b>{AUTHOR}</b>")
        credit.setObjectName("brandSub")
        credit.setAlignment(Qt.AlignCenter)
        lay.addWidget(credit)

    def _item(self, key, title, sub, icon, color, tip="") -> NavItem:
        it = NavItem(key, title, sub, icon, color)
        if tip:
            it.setToolTip(tip)
        it.clicked.connect(lambda: self.selected.emit(key))
        self.buttons.addButton(it)
        self.items[key] = it
        return it

    def select(self, key: str) -> None:
        if key in self.items:
            self.items[key].setChecked(True)

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _filter(self, text: str) -> None:
        words = text.lower().split()
        self.home.setVisible(not words or all(w in "home" for w in words))
        for g in self.groups:
            g.filter(words)

    def _open_first(self) -> None:
        if not self.home.isHidden():
            self.selected.emit("home")
            return
        for g in self.groups:
            for it in g.items:
                if it.isVisible() and g.isVisible():
                    self.selected.emit(it.key)
                    return

    def _theme_text(self) -> None:
        self.theme_btn.setText("☀️   Switch to light mode" if theme().name == "gray" else "🌙   Switch to dark mode")
