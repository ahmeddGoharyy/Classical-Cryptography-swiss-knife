"""Modern gray themes (blue accent, green buttons): palette, stylesheet, SVG icons and visualization colors."""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QSize, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette
from PySide6.QtWidgets import QApplication

UI_FONT_CANDIDATES = ["Inter", "Noto Sans", "Ubuntu", "Cantarell", "Segoe UI", "Helvetica Neue", "Arial"]
MONO_FONT_CANDIDATES = ["JetBrains Mono", "Fira Code", "Cascadia Code", "DejaVu Sans Mono", "Consolas", "Menlo"]

UI = {
    "gray": {
        "window": "#26282c", "sidebar": "#1e1f22", "card": "#2e3035", "input": "#25272b", "alt": "#383b41",
        "border": "#3b3e45", "text": "#e8eaed", "muted": "#9aa0a8", "accent": "#4f8cff", "accent_soft": "#2c3b57",
        "accent_text": "#ffffff", "button": "#16a34a", "button_hover": "#22c55e", "button_text": "#ffffff",
        "good": "#4ade80", "bad": "#f87171", "scene": "#2e3035",
        "series": ["#4f8cff", "#f5b84b", "#22c55e", "#f87171"],
    },
    "light": {
        "window": "#eef0f3", "sidebar": "#e2e5e9", "card": "#ffffff", "input": "#f5f6f8", "alt": "#e7e9ed",
        "border": "#d7dadf", "text": "#1b1d21", "muted": "#5f6670", "accent": "#2563eb", "accent_soft": "#dbe6ff",
        "accent_text": "#ffffff", "button": "#16a34a", "button_hover": "#15803d", "button_text": "#ffffff",
        "good": "#15803d", "bad": "#dc2626", "scene": "#ffffff",
        "series": ["#2563eb", "#d98b0b", "#16a34a", "#dc2626"],
    },
}

# visualization cell style -> (background, foreground, border); None = transparent
CELL = {
    "gray": {
        "normal": ("#3a3d43", "#eef0f2", "#484c53"),
        "header": ("#33363b", "#a9afb8", "#3f4248"),
        "input": ("#41454c", "#ffffff", "#545961"),
        "key": ("#4d4123", "#ffd27a", "#6f5c2b"),
        "active": ("#4f8cff", "#ffffff", "#7aa8ff"),
        "current": ("#16a34a", "#ffffff", "#34d27a"),
        "result": ("#24402f", "#a7f0c3", "#2f5a40"),
        "hl": ("#2c3b57", "#cfe0ff", "#3d5580"),
        "filler": ("#4a3555", "#efc2ff", "#664a75"),
        "dim": (None, "#6f757e", None),
        "empty": (None, "#6f757e", "#484c53"),
        "warn": ("#5a2a2e", "#ffb8bd", "#83404a"),
    },
    "light": {
        "normal": ("#f3f4f6", "#1b1d21", "#d7dadf"),
        "header": ("#e7e9ed", "#4f5660", "#d7dadf"),
        "input": ("#ffffff", "#11141a", "#bfc4cc"),
        "key": ("#fff3cf", "#7a5300", "#ecd18a"),
        "active": ("#2563eb", "#ffffff", "#1d4fc4"),
        "current": ("#16a34a", "#ffffff", "#15803d"),
        "result": ("#dcf5e6", "#125a33", "#a6dcbb"),
        "hl": ("#dbe6ff", "#1e3a8a", "#a9c1f5"),
        "filler": ("#f3ddf8", "#7a1f8f", "#ddb0e8"),
        "dim": (None, "#9aa0a8", None),
        "empty": (None, "#9aa0a8", "#d0d4da"),
        "warn": ("#fde2e2", "#991b1b", "#f1a9a9"),
    },
}

ICONS = {
    "chevron-down": '<path d="M6 9l6 6 6-6" fill="none" stroke="{c}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "chevron-up": '<path d="M6 15l6-6 6 6" fill="none" stroke="{c}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5" fill="none" stroke="{c}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
    "first": '<path d="M6 5v14" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/><path d="M18 5.5v13L9 12z" fill="{c}" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>',
    "prev": '<path d="M16 5.5v13L7 12z" fill="{c}" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>',
    "play": '<path d="M8 5.5v13L18 12z" fill="{c}" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>',
    "pause": '<rect x="7" y="5.5" width="3.6" height="13" rx="1" fill="{c}"/><rect x="13.4" y="5.5" width="3.6" height="13" rx="1" fill="{c}"/>',
    "next": '<path d="M8 5.5v13L17 12z" fill="{c}" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>',
    "last": '<path d="M18 5v14" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/><path d="M6 5.5v13L15 12z" fill="{c}" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>',
}


def _rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, {alpha})"


def _pick(candidates: list[str]) -> str:
    families = set(QFontDatabase.families())
    return next((f for f in candidates if f in families), candidates[-1])


class ThemeManager(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        name = QSettings().value("theme", "gray")
        self.name = name if name in UI else "gray"
        self._icon_dir = Path(tempfile.mkdtemp(prefix="cryptoknife-icons-"))
        self.ui_font = "Sans Serif"
        self.mono_font = "Monospace"

    @property
    def ui(self) -> dict:
        return UI[self.name]

    def cell(self, style: str):
        table = CELL[self.name]
        return table.get(style, table["normal"])

    def icon(self, name: str, color: str | None = None) -> QIcon:
        return QIcon(str(self._svg(name, color or self.ui["text"])))

    def _svg(self, name: str, color: str) -> Path:
        path = self._icon_dir / f"{name}-{color.lstrip('#')}.svg"
        if not path.exists():
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
                            + ICONS[name].format(c=color) + "</svg>")
        return path

    def set(self, name: str) -> None:
        self.name = name
        QSettings().setValue("theme", name)
        self.apply(QApplication.instance())
        self.changed.emit()

    def toggle(self) -> None:
        self.set("light" if self.name == "gray" else "gray")

    def apply(self, app: QApplication) -> None:
        c = self.ui
        self.ui_font = _pick(UI_FONT_CANDIDATES)
        self.mono_font = _pick(MONO_FONT_CANDIDATES)
        app.setStyle("Fusion")
        f = QFont(self.ui_font)
        f.setPointSizeF(10.5)
        app.setFont(f)
        p = QPalette()
        for role, key in [(QPalette.Window, "window"), (QPalette.Base, "input"), (QPalette.AlternateBase, "alt"),
                          (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "alt"),
                          (QPalette.ButtonText, "text"), (QPalette.ToolTipBase, "card"),
                          (QPalette.ToolTipText, "text"), (QPalette.Highlight, "accent"),
                          (QPalette.HighlightedText, "accent_text"), (QPalette.PlaceholderText, "muted"),
                          (QPalette.Link, "accent")]:
            p.setColor(role, QColor(c[key]))
        for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText):
            p.setColor(QPalette.Disabled, role, QColor(c["muted"]))
        app.setPalette(p)
        down = self._svg("chevron-down", c["muted"]).as_posix()
        up = self._svg("chevron-up", c["muted"]).as_posix()
        check = self._svg("check", "#ffffff").as_posix()
        app.setStyleSheet(f"""
            * {{ outline: none; }}
            QWidget {{ color: {c['text']}; font-family: "{self.ui_font}"; font-size: 10.5pt; }}
            QMainWindow, QWidget#content {{ background: {c['window']}; }}
            QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']};
                border-radius: 8px; padding: 6px 8px; }}

            /* ---------- top bar & palette ---------- */
            QFrame#topbar {{ background: {c['sidebar']}; border: none; border-bottom: 1px solid {c['border']}; }}
            QPushButton#brandButton {{ background: transparent; color: {c['text']}; font-size: 12.5pt; font-weight: 700;
                padding: 6px 8px; border-radius: 9px; text-align: left; }}
            QPushButton#brandButton:hover {{ background: {c['alt']}; }}
            QPushButton#switcher {{ background: {c['input']}; color: {c['muted']}; border: 1px solid {c['border']};
                border-radius: 11px; padding: 8px 14px; text-align: left; font-weight: 500; }}
            QPushButton#switcher:hover {{ border-color: {c['accent']}; color: {c['text']}; background: {c['input']}; }}
            QPushButton#topAction {{ background: transparent; color: {c['text']}; border: 1px solid transparent;
                border-radius: 10px; padding: 7px 12px; font-weight: 500; }}
            QPushButton#topAction:hover {{ background: {c['alt']}; }}
            QPushButton#topAction:checked {{ background: {c['accent_soft']}; border-color: {c['accent']}; }}
            QFrame#palette {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; }}
            QListWidget#paletteList {{ background: transparent; border: none; outline: none; }}
            QListWidget#paletteList::item {{ border-radius: 9px; margin: 1px 0; }}
            QListWidget#paletteList::item:hover {{ background: {c['alt']}; }}
            QListWidget#paletteList::item:selected {{ background: {c['accent_soft']}; }}

            /* ---------- grouped sidebar ---------- */
            QLabel#brandTile {{ background: {c['accent']};
                border-radius: 12px; font-size: 17pt; }}
            QLineEdit#navSearch {{ background: {c['input']}; border-radius: 10px; padding: 7px 10px; }}
            QWidget#navArea {{ background: transparent; }}
            QPushButton#groupHeader {{ background: transparent; border: none; border-radius: 11px; padding: 0;
                text-align: left; min-height: 46px; }}
            QPushButton#groupHeader:hover {{ background: {c['alt']}; }}
            QLabel#groupTitle {{ font-weight: 700; font-size: 10.5pt; background: transparent; }}
            QLabel#navTitle {{ font-weight: 500; background: transparent; }}
            QLabel#navSub {{ color: {c['muted']}; font-size: 8.5pt; background: transparent; }}
            QLabel#countPill {{ background: {c['alt']}; color: {c['muted']}; border-radius: 9px; padding: 1px 7px;
                font-size: 8.5pt; font-weight: 700; min-width: 10px; }}
            QPushButton#navItem {{ background: transparent; border: none; border-radius: 10px; padding: 0;
                text-align: left; border-left: 3px solid transparent; }}
            QPushButton#navItem:hover {{ background: {c['alt']}; }}
            QPushButton#navItem:checked {{ background: {c['accent_soft']}; border-left: 3px solid {c['accent']}; }}
            QPushButton#navItem:checked QLabel#navTitle {{ font-weight: 700; }}

            /* ---------- sidebar ---------- */
            QFrame#sidebar {{ background: {c['sidebar']}; border: none; border-right: 1px solid {c['border']}; }}
            QFrame#sidebar QScrollArea, QFrame#sidebar QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
            QLabel#brand {{ font-size: 13pt; font-weight: 700; }}
            QLabel#brandSub {{ color: {c['muted']}; font-size: 9pt; }}
            QLabel#navSection {{ color: {c['muted']}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1px;
                padding: 14px 12px 4px 12px; }}
            QPushButton#nav {{ background: transparent; color: {c['muted']}; border: none; border-radius: 9px;
                text-align: left; padding: 8px 12px; font-weight: 500; }}
            QPushButton#nav:hover {{ background: {c['alt']}; color: {c['text']}; }}
            QPushButton#nav:checked {{ background: {c['accent_soft']}; color: {c['text']}; font-weight: 600;
                border-left: 3px solid {c['accent']}; padding-left: 9px; }}

            /* ---------- typography ---------- */
            QLabel#h1 {{ font-size: 20pt; font-weight: 700; }}
            QLabel#h2 {{ font-size: 12pt; font-weight: 650; }}
            QLabel#hero {{ font-size: 28pt; font-weight: 800; }}
            QLabel#muted {{ color: {c['muted']}; }}
            QLabel#error {{ color: {c['bad']}; font-weight: 600; background: {_rgba(c['bad'], 0.12)};
                border: 1px solid {_rgba(c['bad'], 0.45)}; border-radius: 8px; padding: 8px 10px; }}
            QLabel#ok {{ color: {c['good']}; font-weight: 500; }}
            QLabel#chip, QFrame#card QLabel#chip {{ color: {c['accent']}; background: {c['accent_soft']}; border-radius: 10px;
                padding: 3px 10px; font-size: 9pt; font-weight: 600; }}
            QLabel#pill, QFrame#card QLabel#pill {{ color: {c['text']}; background: {c['alt']}; border-radius: 12px; padding: 5px 12px;
                font-size: 9.5pt; }}

            /* ---------- cards ---------- */
            QFrame#card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px; }}
            QFrame#card QLabel {{ background: transparent; }}
            QFrame#hero {{ background: {c['accent']};
                border-radius: 20px; }}
            QFrame#hero QLabel {{ color: white; background: transparent; }}
            QPushButton#heroButton {{ background: rgba(255,255,255,0.18); color: white; border: 1px solid rgba(255,255,255,0.55);
                border-radius: 12px; padding: 10px 18px; font-size: 11pt; font-weight: 600; }}
            QPushButton#heroButton:hover {{ background: rgba(255,255,255,0.30); }}
            QFrame#divider {{ background: {c['border']}; max-height: 1px; border: none; }}

            /* ---------- inputs ---------- */
            QPlainTextEdit, QTextBrowser, QLineEdit, QSpinBox, QComboBox {{ background: {c['input']};
                border: 1px solid {c['border']}; border-radius: 10px; padding: 6px 9px;
                selection-background-color: {c['accent']}; selection-color: white; }}
            QPlainTextEdit, QTextBrowser {{ padding: 8px 10px; }}
            QPlainTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
            QPlainTextEdit[invalid="true"], QLineEdit[invalid="true"], QSpinBox[invalid="true"],
            QComboBox[invalid="true"] {{ border: 1.5px solid {c['bad']}; }}
            QComboBox {{ padding-right: 28px; min-height: 20px; }}
            QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{ border-color: {c['muted']}; }}
            QComboBox::drop-down {{ border: none; width: 26px; subcontrol-position: center right; }}
            QComboBox::down-arrow {{ image: url("{down}"); width: 14px; height: 14px; }}
            QComboBox QAbstractItemView {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px;
                padding: 4px; selection-background-color: {c['accent']}; selection-color: white; outline: none; }}
            QSpinBox {{ padding: 6px 24px 6px 9px; }}
            QSpinBox QLineEdit {{ border: none; background: transparent; padding: 0 0 0 6px; margin: 0; }}
            QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 20px; border: none;
                background: transparent; }}
            QSpinBox::up-button {{ subcontrol-position: top right; margin: 3px 3px 0 0; }}
            QSpinBox::down-button {{ subcontrol-position: bottom right; margin: 0 3px 3px 0; }}
            QSpinBox::up-arrow {{ image: url("{up}"); width: 11px; height: 11px; }}
            QSpinBox::down-arrow {{ image: url("{down}"); width: 11px; height: 11px; }}
            QCheckBox {{ spacing: 8px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border: 1.5px solid {c['muted']}; border-radius: 6px;
                background: {c['input']}; }}
            QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
            QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; image: url("{check}"); }}
            QCheckBox::indicator:disabled {{ background: {c['alt']}; border-color: {c['border']}; }}
            QCheckBox:disabled {{ color: {c['muted']}; }}

            /* ---------- buttons ---------- */
            QPushButton {{ background: {c['button']}; color: {c['button_text']}; border: none; border-radius: 10px;
                padding: 8px 16px; font-weight: 600; }}
            QPushButton:hover {{ background: {c['button_hover']}; }}
            QPushButton:pressed {{ padding-top: 9px; padding-bottom: 7px; }}
            QPushButton:disabled {{ background: {c['alt']}; color: {c['muted']}; }}
            QPushButton#big {{ font-size: 11pt; padding: 10px 22px; border-radius: 11px; }}
            QPushButton#ghost {{ background: transparent; color: {c['button']}; border: 1.5px solid {c['button']}; }}
            QPushButton#ghost:hover {{ background: {c['button']}; color: white; }}
            QPushButton#ghost:disabled {{ color: {c['muted']}; border-color: {c['border']}; background: transparent; }}
            QPushButton#help {{ background: {c['alt']}; color: {c['text']}; border-radius: 13px; padding: 0;
                min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; font-weight: 700; font-size: 10.5pt; }}
            QPushButton#help:hover {{ background: {c['accent']}; color: white; }}
            QPushButton#segment {{ background: transparent; color: {c['muted']}; border-radius: 9px; padding: 7px 16px;
                font-weight: 600; }}
            QPushButton#segment:hover {{ color: {c['text']}; }}
            QPushButton#segment:checked {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; }}
            QFrame#segmentBar {{ background: {c['input']}; border: 1px solid {c['border']}; border-radius: 12px; }}
            QPushButton#themeToggle {{ background: {c['alt']}; color: {c['text']}; border-radius: 10px; text-align: left;
                padding: 8px 12px; font-weight: 500; }}
            QPushButton#themeToggle:hover {{ background: {c['accent_soft']}; }}
            QToolButton#player {{ background: {c['alt']}; border: none; border-radius: 17px; min-width: 34px;
                min-height: 34px; max-width: 34px; max-height: 34px; }}
            QToolButton#player:hover {{ background: {c['accent_soft']}; }}
            QToolButton#playerMain {{ background: {c['accent']}; border: none; border-radius: 21px; min-width: 42px;
                min-height: 42px; max-width: 42px; max-height: 42px; }}
            QToolButton#playerMain:hover {{ background: {c['button']}; }}
            QToolButton#dice {{ background: {c['alt']}; border: none; border-radius: 9px; padding: 5px; }}
            QToolButton#dice:hover {{ background: {c['accent_soft']}; }}

            /* ---------- tables, progress, sliders, scrollbars ---------- */
            QTableWidget {{ background: {c['card']}; border: none; gridline-color: {c['border']};
                selection-background-color: {c['accent_soft']}; selection-color: {c['text']}; }}
            QTableWidget::item {{ padding: 4px 6px; border-bottom: 1px solid {c['border']}; }}
            QHeaderView::section {{ background: transparent; color: {c['muted']}; border: none;
                border-bottom: 1px solid {c['border']}; padding: 6px; font-weight: 600; }}
            QTableCornerButton::section {{ background: transparent; border: none; }}
            QProgressBar {{ background: {c['input']}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
            QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
            QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: white; border: 3px solid {c['accent']}; width: 10px; height: 10px;
                margin: -6px 0; border-radius: 8px; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
            QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 3px; min-width: 30px; }}
            QScrollBar::handle:hover {{ background: {c['muted']}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
            QSplitter::handle {{ background: transparent; }}
            QSplitter::handle:vertical {{ height: 10px; }}
            QSplitter::handle:horizontal {{ width: 10px; }}
            QDialog {{ background: {c['window']}; }}
        """)


_theme: ThemeManager | None = None


def theme() -> ThemeManager:
    global _theme
    if _theme is None:
        _theme = ThemeManager()
    return _theme
