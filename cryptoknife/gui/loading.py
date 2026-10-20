"""Animated loading overlay shown over the output box while the visualization runs."""
from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QConicalGradient, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .theme import theme


class LoadingOverlay(QWidget):
    """Covers its parent with a spinning gradient ring, an animated label and a progress bar."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.text = "Working"
        self.progress = 0.0
        self.detail = ""
        self._angle = 0.0
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, ev):
        if obj is self.parent() and ev.type() == QEvent.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def start(self, text: str) -> None:
        self.text = text
        self.progress = 0.0
        self.detail = ""
        self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self._timer.start()

    def set_progress(self, i: int, n: int, detail: str = "") -> None:
        self.progress = (i + 1) / max(1, n)
        self.detail = detail
        self.update()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 6) % 360
        self._frame += 1
        self.update()

    def paintEvent(self, _ev) -> None:
        ui = theme().ui
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        bg = QColor(ui["input"])
        bg.setAlpha(238)
        qp.setPen(Qt.NoPen)
        qp.setBrush(bg)
        qp.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 10, 10)

        compact = self.height() < 190
        r = 18 if compact else 26
        if compact:  # spinner on the left, text and bar on the right
            block_w = min(self.width() - 20, 360)
            left = (self.width() - block_w) / 2
            cx, cy = left + r + 14, self.height() / 2
        else:
            cx, cy = self.width() / 2, self.height() / 2 - 18
        # faint track
        qp.setPen(QPen(QColor(ui["border"]), 6))
        qp.setBrush(Qt.NoBrush)
        qp.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        # spinning gradient arc (blue → green)
        grad = QConicalGradient(cx, cy, -self._angle)
        grad.setColorAt(0.0, QColor(ui["accent"]))
        grad.setColorAt(0.5, QColor(ui["button"]))
        transparent = QColor(ui["button"])
        transparent.setAlpha(0)
        grad.setColorAt(0.75, transparent)
        grad.setColorAt(1.0, QColor(ui["accent"]))
        pen = QPen(grad, 6)
        pen.setCapStyle(Qt.RoundCap)
        qp.setPen(pen)
        qp.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), int(-self._angle * 16), int(270 * 16))
        # orbiting dots
        for k in range(3):
            a = math.radians(self._angle * 1.6 + k * 120)
            pulse = 0.6 + 0.4 * math.sin(self._frame / 8 + k)
            c = QColor(ui["accent"] if k % 2 == 0 else ui["button"])
            qp.setPen(Qt.NoPen)
            qp.setBrush(c)
            rr = 3.2 * pulse
            qp.drawEllipse(QRectF(cx + (r + 12) * math.cos(a) - rr, cy + (r + 12) * math.sin(a) - rr, 2 * rr, 2 * rr))
        # label with animated dots
        dots = "." * (1 + (self._frame // 20) % 3)
        f = QFont(theme().ui_font)
        f.setPointSizeF(12)
        f.setWeight(QFont.DemiBold)
        qp.setFont(f)
        qp.setPen(QColor(ui["text"]))
        if compact:
            tx = cx + r + 26
            bw = max(80, min(240, self.width() - tx - 16))
            qp.drawText(QRectF(tx, cy - 26, bw + 40, 24), Qt.AlignLeft | Qt.AlignVCenter, self.text + dots)
            bar = QRectF(tx, cy + 2, bw, 6)
        else:
            qp.drawText(QRectF(0, cy + r + 18, self.width(), 24), Qt.AlignHCenter | Qt.AlignTop, self.text + dots)
            bw = min(260, self.width() - 60)
            bar = QRectF(cx - bw / 2, cy + r + 48, bw, 6)
        qp.setBrush(QColor(ui["border"]))
        qp.drawRoundedRect(bar, 3, 3)
        if self.progress > 0:
            fill = QRectF(bar.x(), bar.y(), bw * self.progress, 6)
            qp.setBrush(QColor(ui["accent"]))
            qp.drawRoundedRect(fill, 3, 3)
        if self.detail:
            f.setPointSizeF(9)
            f.setWeight(QFont.Normal)
            qp.setFont(f)
            qp.setPen(QColor(ui["muted"]))
            if compact:
                qp.drawText(QRectF(bar.x(), bar.bottom() + 6, self.width() - bar.x() - 8, 20),
                            Qt.AlignLeft | Qt.AlignTop, self.detail)
            else:
                qp.drawText(QRectF(10, bar.bottom() + 8, self.width() - 20, 20), Qt.AlignHCenter | Qt.AlignTop,
                            self.detail)
