"""Media-player style controls for stepping through a trace."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSlider, QToolButton, QWidget

from .theme import theme

SPEEDS = [("0.5×", 3400), ("1×", 1800), ("2×", 950), ("4×", 480), ("8×", 240)]


class StepPlayer(QWidget):
    stepChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.count = 0
        self.index = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self._buttons: list[tuple[QToolButton, str]] = []
        self._keys: list[tuple[str, object]] = []

        def btn(icon, tip, fn, key=None, main=False):
            b = QToolButton()
            b.setObjectName("playerMain" if main else "player")
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(18, 18) if main else QSize(14, 14))
            b.setToolTip(tip)
            b.clicked.connect(fn)
            if key:
                self._keys.append((key, fn))
            lay.addWidget(b)
            self._buttons.append((b, icon))
            return b

        btn("first", "First step (Home)", lambda: self.go(0), "Home")
        btn("prev", "Previous step (←)", lambda: self.go(self.index - 1), "Left")
        self.play_btn = btn("play", "Play / pause (Space)", self.toggle, "Space", main=True)
        btn("next", "Next step (→)", lambda: self.go(self.index + 1), "Right")
        btn("last", "Last step (End)", lambda: self.go(self.count - 1), "End")
        lay.addSpacing(6)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self.go)
        lay.addWidget(self.slider, 1)
        self.label = QLabel("–")
        self.label.setObjectName("muted")
        self.label.setMinimumWidth(84)
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)
        self.speed = QComboBox()
        for name, _ in SPEEDS:
            self.speed.addItem(name)
        self.speed.setCurrentIndex(1)
        self.speed.setToolTip("Animation speed")
        self.speed.currentIndexChanged.connect(lambda _: self.timer.setInterval(SPEEDS[self.speed.currentIndex()][1]))
        lay.addWidget(self.speed)
        self._refresh_icons()
        theme().changed.connect(self._refresh_icons)

    def bind_keys(self, scope: QWidget) -> None:
        """Keyboard control (Space, ←/→, Home/End) only while focus is inside ``scope``, so typing in
        text boxes or toggling checkboxes elsewhere never moves the animation."""
        for key, fn in self._keys:
            sc = QShortcut(QKeySequence(key), scope, fn)
            sc.setContext(Qt.WidgetWithChildrenShortcut)

    def _refresh_icons(self) -> None:
        playing = self.timer.isActive()
        for b, name in self._buttons:
            if b is self.play_btn:
                b.setIcon(theme().icon("pause" if playing else "play", "#ffffff"))
            else:
                b.setIcon(theme().icon(name))

    def set_count(self, n: int, start: int | None = None) -> None:
        self.stop()
        self.count = n
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(0, n - 1))
        self.slider.blockSignals(False)
        self.go(n - 1 if start is None else start, force=True)

    def go(self, i: int, force: bool = False) -> None:
        if self.count == 0:
            self.label.setText("–")
            return
        i = max(0, min(self.count - 1, i))
        if i == self.index and not force:
            return
        self.index = i
        self.slider.blockSignals(True)
        self.slider.setValue(i)
        self.slider.blockSignals(False)
        self.label.setText(f"{i + 1} / {self.count}")
        self.stepChanged.emit(i)

    @property
    def interval(self) -> int:
        return SPEEDS[self.speed.currentIndex()][1]

    def toggle(self) -> None:
        if self.timer.isActive():
            self.stop()
        else:
            self.play()

    def play(self) -> None:
        if self.count <= 1:
            return
        if self.index >= self.count - 1:
            self.go(0)
        self.timer.start(SPEEDS[self.speed.currentIndex()][1])
        self._refresh_icons()

    def stop(self) -> None:
        self.timer.stop()
        self._refresh_icons()

    def _tick(self) -> None:
        if self.index >= self.count - 1:
            self.stop()
        else:
            self.go(self.index + 1)
            if self.index >= self.count - 1:
                self.stop()
