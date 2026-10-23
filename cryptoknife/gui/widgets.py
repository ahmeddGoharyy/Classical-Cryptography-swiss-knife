"""Reusable widgets: cards, segmented tabs, help buttons/dialogs, parameter forms and charts."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QLocale, QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QBoxLayout, QButtonGroup, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame,
                               QHBoxLayout, QLabel, QLayout, QScrollArea, QLineEdit, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox,
                               QStackedWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from ..core.cipher import Param
from .theme import theme


def mono_font(size: float = 11) -> QFont:
    f = QFont(theme().mono_font)
    f.setStyleHint(QFont.Monospace)
    f.setPointSizeF(size)
    return f


class StatusLabel(QLabel):
    """A label that hides itself while empty, so it never reserves blank space."""

    def setText(self, text: str) -> None:
        super().setText(text)
        self.setVisible(bool(text))

    def clear(self) -> None:
        super().clear()
        self.hide()


def status_label(name: str) -> StatusLabel:
    lbl = StatusLabel()
    lbl.setObjectName(name)
    lbl.setWordWrap(True)
    lbl.hide()
    return lbl


def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


class Card(QFrame):
    """Rounded panel with an optional header (title, help button, extra widgets on the right)."""

    def __init__(self, title: str = "", help_title: str = "", help_text: str = "", markdown: bool = True,
                 margins: int = 16, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins - 2, margins, margins)
        self.body.setSpacing(10)
        self.header = None
        if title:
            self.header = QHBoxLayout()
            self.header.setSpacing(8)
            self.header.addWidget(label(title, "h2"))
            if help_text:
                self.header.addWidget(HelpButton(help_title or title, help_text, markdown))
            self.header.addStretch(1)
            self.body.addLayout(self.header)

    def add(self, w, stretch: int = 0):
        (self.body.addLayout if not isinstance(w, QWidget) else self.body.addWidget)(w, stretch)
        return w


class SegmentedTabs(QWidget):
    """Pill-style segmented control driving a stacked widget."""
    currentChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bar = QFrame()
        self.bar.setObjectName("segmentBar")
        self._bar_lay = QHBoxLayout(self.bar)
        self._bar_lay.setContentsMargins(3, 3, 3, 3)
        self._bar_lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.stack = QStackedWidget()
        self.group.idClicked.connect(self.setCurrentIndex)

    def addTab(self, w: QWidget, title: str) -> int:
        i = self.stack.addWidget(w)
        b = QPushButton(title)
        b.setObjectName("segment")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        self.group.addButton(b, i)
        self._bar_lay.addWidget(b)
        if i == 0:
            b.setChecked(True)
        return i

    def setCurrentIndex(self, i: int) -> None:
        self.group.button(i).setChecked(True)
        self.stack.setCurrentIndex(i)
        self.currentChanged.emit(i)

    def currentIndex(self) -> int:
        return self.stack.currentIndex()


class HelpDialog(QDialog):
    def __init__(self, title: str, text: str, markdown: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        icon = label("?", "help")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(34, 34)
        ui = theme().ui
        icon.setStyleSheet(f"background:{ui['accent']}; color:white; border-radius:17px; font-weight:800; font-size:13pt;")
        head.addWidget(icon)
        head.addWidget(label(title, "h1"))
        head.addStretch(1)
        lay.addLayout(head)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.document().setDefaultStyleSheet(
            f"h1,h2,h3 {{ color: {ui['text']}; }} h2 {{ margin-top: 14px; }} "
            f"code, pre {{ font-family: '{theme().mono_font}'; background: {ui['alt']}; }} "
            f"td, th {{ padding: 4px 10px; }} th {{ color: {ui['muted']}; text-align: left; }}")
        view.setStyleSheet(f"QTextBrowser {{ background: {ui['card']}; border-radius: 12px; padding: 14px 18px; "
                           "font-size: 11pt; }")
        if markdown:
            view.setMarkdown(text)
        else:
            view.setHtml(text)
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("Got it")
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        lay.addLayout(row)


class HelpButton(QPushButton):
    """Small round “?” that opens an explanation window. ``text`` may be a string or a callable."""

    def __init__(self, title: str, text, markdown: bool = True, parent=None):
        super().__init__("?", parent)
        self.setObjectName("help")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"What is this? — {title}")
        self.clicked.connect(lambda: HelpDialog(title, text() if callable(text) else text, markdown,
                                                self.window()).exec())


class WrapCheckBox(QWidget):
    """A checkbox whose label wraps onto several lines instead of being clipped."""
    toggled = Signal(bool)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.box = QCheckBox()
        self.box.toggled.connect(self.toggled)
        lay.addWidget(self.box, 0, Qt.AlignTop)
        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.text_label.setContentsMargins(0, 1, 0, 0)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.text_label.setCursor(Qt.PointingHandCursor)
        self.text_label.mousePressEvent = lambda ev: self.box.isEnabled() and self.box.toggle()
        lay.addWidget(self.text_label, 1)

    def isChecked(self) -> bool:
        return self.box.isChecked()

    def setChecked(self, on: bool) -> None:
        self.box.setChecked(on)

    def setEnabled(self, on: bool) -> None:
        super().setEnabled(on)
        self.text_label.setObjectName("" if on else "muted")
        self.text_label.setStyleSheet("")

    def setToolTip(self, tip: str) -> None:
        super().setToolTip(tip)
        self.box.setToolTip(tip)
        self.text_label.setToolTip(tip)


class ParamForm(QWidget):
    """Builds input widgets from a cipher's Param list."""
    changed = Signal()

    def __init__(self, params: list[Param], length_provider: Callable[[], int] = lambda: 10, parent=None):
        super().__init__(parent)
        self.params = params
        self.length_provider = length_provider
        self.widgets: dict[str, QWidget] = {}
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for p in params:
            w = self._make(p)
            self.widgets[p.name] = w
            if p.random:
                row = QHBoxLayout()
                row.setSpacing(6)
                row.addWidget(w, 1)
                b = QToolButton()
                b.setObjectName("dice")
                b.setText("🎲")
                b.setCursor(Qt.PointingHandCursor)
                b.setToolTip("Generate a random key")
                b.clicked.connect(lambda _=False, p=p: self._set(p, p.random(self.length_provider())))
                row.addWidget(b)
                form.addRow(label(p.label, "muted"), row)
            elif p.kind == "bool":
                form.addRow(w)
            else:
                form.addRow(label(p.label, "muted"), w)
            if p.help:
                w.setToolTip(p.help)

    def _make(self, p: Param) -> QWidget:
        if p.kind == "int":
            w = QSpinBox()
            w.setLocale(QLocale(QLocale.English, QLocale.UnitedStates))  # Western digits and "-" sign always
            w.lineEdit().setTextMargins(6, 0, 0, 0)
            w.setRange(p.minimum, p.maximum)
            w.setValue(int(p.default))
            w.valueChanged.connect(self.changed)
        elif p.kind == "choice":
            w = QComboBox()
            w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(12)
            w.addItems(p.choices or [])
            w.setCurrentText(str(p.default))
            w.currentIndexChanged.connect(self.changed)
        elif p.kind == "bool":
            w = WrapCheckBox(p.label)
            w.setChecked(bool(p.default))
            w.toggled.connect(self.changed)
        else:
            w = StartLineEdit(str(p.default))
            w.setFont(mono_font(10.5))
            if p.help:
                w.setPlaceholderText(p.help)
            w.textChanged.connect(self.changed)
        return w

    def _set(self, p: Param, value) -> None:
        w = self.widgets[p.name]
        if isinstance(w, QSpinBox):
            w.setValue(int(value))
        elif isinstance(w, QComboBox):
            w.setCurrentText(str(value))
        elif isinstance(w, (QCheckBox, WrapCheckBox)):
            w.setChecked(bool(value))
        else:
            w.setText(str(value))

    def values(self) -> dict:
        out = {}
        for p in self.params:
            w = self.widgets[p.name]
            if isinstance(w, QSpinBox):
                out[p.name] = w.value()
            elif isinstance(w, QComboBox):
                out[p.name] = w.currentText()
            elif isinstance(w, (QCheckBox, WrapCheckBox)):
                out[p.name] = w.isChecked()
            else:
                out[p.name] = w.text()
        return out

    def set_values(self, values: dict) -> None:
        for p in self.params:
            if p.name in values:
                self._set(p, values[p.name])


def params_help(params: list[Param]) -> str:
    """Markdown describing each parameter (for the key card's help window)."""
    lines = []
    for p in params:
        extra = f" (range {p.minimum}–{p.maximum})" if p.kind == "int" else ""
        extra += f" — options: {', '.join(p.choices)}" if p.choices else ""
        lines.append(f"- **{p.label}**{extra}: {p.help or 'see the cipher help for details.'}")
        if p.random:
            lines[-1] += " Press 🎲 for a random value."
    return "\n".join(lines)


def ChartView(parent=None, height: float = 2.6):  # noqa: N802 — used like a class
    """A themed bar chart (see charts.py). matplotlib is imported on first use, keeping startup fast."""
    from .charts import ChartView as _ChartView
    return _ChartView(parent, height)


class StartLineEdit(QLineEdit):
    """A one-line field that shows the start of a long text whenever it is not being edited.

    Qt leaves the cursor (and so the view) at the end after setText, hiding the beginning of long keys.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursorPosition(0)

    def setText(self, text: str) -> None:  # noqa: N802 — Qt API name
        super().setText(text)
        if not self.hasFocus():
            self.setCursorPosition(0)

    def focusOutEvent(self, ev) -> None:  # noqa: N802
        super().focusOutEvent(ev)
        self.setCursorPosition(0)


class MonoText(QPlainTextEdit):
    def __init__(self, placeholder: str = "", read_only: bool = False, parent=None):
        super().__init__(parent)
        self.setFont(mono_font(11))
        self.setPlaceholderText(placeholder)
        self.setReadOnly(read_only)
        self.setTabChangesFocus(True)


class FlowLayout(QLayout):
    """Lays widgets out left to right and wraps onto new lines when space runs out."""

    def __init__(self, parent=None, spacing: int = 10):
        super().__init__(parent)
        self._items = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            if it.widget() is None or not it.widget().isHidden():
                size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        x, y, line_h = rect.x(), rect.y(), 0
        for it in self._items:
            if it.widget() is not None and it.widget().isHidden():
                continue  # hidden on purpose: takes no space
            hint = it.sizeHint()
            nx = x + hint.width() + self._spacing
            if nx - self._spacing > rect.right() + 1 and line_h > 0:
                x, y = rect.x(), y + line_h + self._spacing
                nx = x + hint.width() + self._spacing
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class Responsive(QObject):
    """Switches box layouts / splitters between horizontal and vertical at a width breakpoint."""

    def __init__(self, watched: QWidget, breakpoint: int, layouts=(), splitters=(), callback=None):
        super().__init__(watched)
        self.breakpoint = breakpoint
        self.layouts, self.splitters, self.callback = list(layouts), list(splitters), callback
        self.wide = None
        watched.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            wide = obj.width() >= self.breakpoint
            if wide != self.wide:
                self.wide = wide
                for lay in self.layouts:
                    lay.setDirection(QBoxLayout.LeftToRight if wide else QBoxLayout.TopToBottom)
                for sp in self.splitters:
                    sp.setOrientation(Qt.Horizontal if wide else Qt.Vertical)
                if self.callback:
                    self.callback(wide)
        return False


def vscroll(widget: QWidget, min_height: int = 0) -> QScrollArea:
    """Wrap a page body so it keeps its natural size and scrolls when the window is too short."""
    if min_height:
        widget.setMinimumHeight(min_height)
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setWidget(widget)
    return area
