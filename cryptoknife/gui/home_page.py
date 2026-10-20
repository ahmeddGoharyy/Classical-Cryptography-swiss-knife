"""Landing page: what the app is, and who made it."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .. import __version__
from ..core.cipher import all_ciphers
from .widgets import Card, label

AUTHOR = "Ahmed El Gohary"

FEATURES = [
    ("🎬", "Step-by-step animation", "Watch every encryption and decryption unfold — tables, tableaus, key "
                                     "squares, matrices and zigzags, one step at a time."),
    ("⚡", "Automatic cracking", "Break ciphertexts without the key: brute force, frequency analysis, Kasiski, "
                                "hill climbing and simulated annealing."),
    ("📊", "Frequency analysis", "Compare any text with English: letter frequencies, index of coincidence, "
                                "chi-squared and n-grams."),
    ("🧩", "Extensible", "Every cipher is a self-contained plugin — new algorithms appear in the app "
                        "automatically."),
]


class HomePage(QScrollArea):
    def __init__(self, open_palette=None, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        outer = QWidget()
        h = QHBoxLayout(outer)
        h.setContentsMargins(32, 30, 32, 30)
        col = QWidget()
        col.setMaximumWidth(980)
        h.addWidget(col)
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(20)

        hero = QFrame()
        hero.setObjectName("hero")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(40, 38, 40, 38)
        hl.setSpacing(8)
        logo = label("🔐")
        logo.setStyleSheet("font-size: 44pt;")
        hl.addWidget(logo)
        hl.addWidget(label("Classical Cryptography Swiss Knife", "hero", wrap=True))
        tag = label("Learn, visualize and break the classic ciphers.", wrap=True)
        tag.setStyleSheet("font-size: 14pt; font-weight: 500;")
        hl.addWidget(tag)
        if open_palette:
            hl.addSpacing(10)
            go = QPushButton("🔍   Search ciphers   ·   Ctrl+K")
            go.setObjectName("heroButton")
            go.setCursor(Qt.PointingHandCursor)
            go.clicked.connect(open_palette)
            row = QHBoxLayout()
            row.addWidget(go)
            row.addStretch(1)
            hl.addLayout(row)
        lay.addWidget(hero)

        about = Card("What is it?")
        about.add(label(
            "An interactive toolkit for classical cryptography. Type any message and key, press Encrypt or "
            "Decrypt, and watch the algorithm work step by step — or hand it a ciphertext and let it find the "
            "key for you. It is built for studying how these ciphers work and why they fail.", wrap=True))
        wrap = QWidget()
        wl = QGridLayout(wrap)
        wl.setContentsMargins(0, 4, 0, 0)
        wl.setHorizontalSpacing(8)
        wl.setVerticalSpacing(8)
        for i, c in enumerate(all_ciphers()):
            wl.addWidget(label(c.name, "pill"), i // 5, i % 5, Qt.AlignLeft)
        wl.setColumnStretch(5, 1)
        about.add(wrap)
        lay.addWidget(about)

        grid = QGridLayout()
        grid.setSpacing(16)
        for i, (icon, title, text) in enumerate(FEATURES):
            card = Card()
            row = QHBoxLayout()
            ic = label(icon)
            ic.setStyleSheet("font-size: 22pt;")
            ic.setAlignment(Qt.AlignTop)
            row.addWidget(ic)
            txt = QVBoxLayout()
            txt.setSpacing(4)
            txt.addWidget(label(title, "h2"))
            txt.addWidget(label(text, "muted", wrap=True))
            row.addLayout(txt, 1)
            card.add(row)
            grid.addWidget(card, i // 2, i % 2)
        lay.addLayout(grid)

        footer = Card()
        fr = QHBoxLayout()
        avatar = label("AG")
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(52, 52)
        avatar.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #4f8cff, stop:1 #16a34a);"
                             "color: white; border-radius: 26px; font-size: 15pt; font-weight: 800;")
        fr.addWidget(avatar)
        who = QVBoxLayout()
        who.setSpacing(2)
        who.addWidget(label("Made by", "muted"))
        name = label(AUTHOR, "h1")
        who.addWidget(name)
        fr.addLayout(who, 1)
        fr.addWidget(label(f"Version {__version__}", "pill"), 0, Qt.AlignVCenter)
        footer.add(fr)
        lay.addWidget(footer)
        lay.addStretch(1)
        self.setWidget(outer)
