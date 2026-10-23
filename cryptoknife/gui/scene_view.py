"""Draws a core.trace.Step (rows of grids and labels) and animates its arrows with QPainter.

Animation model: every arrow belongs to a *phase*. During a step's animation the
phases play one after another; in each phase the arrow draws itself from source
to destination while a token carrying the value travels along it. Destination
cells of ``reveal`` arrows stay empty until their token lands.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core.text import ALPHABET
from ..core.trace import Arrow, Grid, Label, Stack, Step, Wheel
from .theme import theme

MARGIN, ROW_GAP, PANEL_GAP, BEND_ROOM, STACK_GAP = 22, 46, 46, 70, 40
WHEEL_R, WHEEL_CELL, WHEEL_GAP = 124, 21, 34
KIND_COLOR = {"flow": "accent", "result": "result", "key": "#f5b84b", "muted": "muted"}


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


class SceneView(QWidget):
    focusChanged = Signal(QRectF)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.ClickFocus)
        self.step: Step | None = None
        self.zoom = 1.0
        self._items: list[tuple] = []
        self._rects: dict[str, QRectF] = {}
        self._texts: dict[str, str] = {}
        self._t = 1.0
        self._emit_focus = False
        # Grids and labels only change at a few moments of an animation (a new step, or a revealed cell), so they
        # are painted once into this pixmap; each animation frame just draws it and the moving arrows on top.
        self._version = 0
        self._layer: QPixmap | None = None
        self._layer_key: tuple | None = None
        self._layer_focus = None
        self._advance: dict[tuple, dict[str, float]] = {}  # text widths per font: cells repeat the same letters
        self._natural: dict[int, tuple[Step, tuple[float, float]]] = {}  # step sizes at zoom 1, by step identity
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Linear)
        self._anim.valueChanged.connect(self._tick)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        theme().changed.connect(self._invalidate)

    # ---- public API ---------------------------------------------------------------------------
    def set_step(self, step: Step | None, animate: bool = False, duration: int = 1200) -> None:
        self._anim.stop()
        self.step = step
        self._relayout()
        self._emit_focus = True
        if animate and step and self._has_animation(step):
            self._t = 0.0
            self._anim.setDuration(max(250, duration))
            self._anim.start()
        else:
            self._t = 1.0
        self.update()

    def natural_size(self, step: Step) -> tuple[float, float]:
        """Size of ``step`` at zoom 1 (does not change the current view)."""
        return self.natural_sizes([step])[0]

    def natural_sizes(self, steps: list[Step]) -> list[tuple[float, float]]:
        """Sizes of several steps at zoom 1, restoring the current view only once at the end."""
        saved = (self.step, self.zoom, self._items, self._rects, self._texts)
        if len(self._natural) > 5000:
            self._natural.clear()
        todo = [st for st in steps if self._natural.get(id(st), (None,))[0] is not st]
        if todo:
            self.zoom = 1.0
            for step in todo:
                self.step = step
                self._relayout()
                self._natural[id(step)] = (step, (self.minimumWidth(), self.minimumHeight()))
            self.step, self.zoom, self._items, self._rects, self._texts = saved
            self._relayout()
        return [self._natural[id(st)][1] for st in steps]

    @staticmethod
    def _has_animation(step: Step) -> bool:
        def wheels(panels):
            for p in panels:
                if isinstance(p, Stack):
                    yield from wheels(p.panels)
                elif isinstance(p, Wheel):
                    yield p
        moving = any(w.offset_from is not None for row in step.rows for w in wheels(row))
        return moving or any(not a.static for a in step.arrows)

    def set_zoom(self, z: float) -> None:
        self.zoom = z
        self._relayout()
        self.update()

    def _tick(self, v) -> None:
        self._t = float(v)
        self.update()

    # ---- fonts & measuring --------------------------------------------------------------------
    def _font(self, size: float, bold=False, mono=True) -> QFont:
        f = QFont(theme().ui_font)
        f.setPointSizeF(max(5.0, size * self.zoom))
        f.setWeight(QFont.Bold if (bold and not mono) else (QFont.DemiBold if (bold or mono) else QFont.Normal))
        return f

    def _grid_metrics(self, g: Grid):
        z = self.zoom
        font = self._font(8.5 if g.compact else 12, bold=True)
        fm = QFontMetrics(font)
        ncols = max((len(r) for r in g.cells), default=0)
        cmin, ch = (20 * z, 20 * z) if g.compact else (36 * z, 36 * z)
        gap = 2 * z if g.compact else 5 * z
        colw = [cmin] * ncols
        adv = self._advance.setdefault((g.compact, z), {})
        pad = (6 if g.compact else 14) * z
        for r in g.cells:
            for j, c in enumerate(r):
                t = c.text
                a = adv.get(t)
                if a is None:
                    a = adv[t] = fm.horizontalAdvance(t)
                if a + pad > colw[j]:
                    colw[j] = a + pad
        lab_font = self._font(9.5, mono=False)
        label_w = 0.0
        if g.row_labels:
            lfm = QFontMetrics(lab_font)
            label_w = max(max(lfm.horizontalAdvance(lbl) for lbl in g.row_labels) + 14 * z, g.label_min * z)
        title_h = 22 * z if g.title else 0
        w = label_w + sum(colw) + gap * max(0, ncols - 1)
        h = title_h + len(g.cells) * ch + gap * max(0, len(g.cells) - 1)
        return dict(font=font, lab_font=lab_font, colw=colw, ch=ch, gap=gap, label_w=label_w,
                    title_h=title_h, w=w, h=h)

    def _measure(self, p):
        if isinstance(p, Grid):
            m = self._grid_metrics(p)
            return m["w"], m["h"], m
        if isinstance(p, Stack):
            kids = [(c, *self._measure(c)) for c in p.panels]
            w = max((k[1] for k in kids), default=0)
            h = sum(k[2] for k in kids) + STACK_GAP * self.zoom * max(0, len(kids) - 1)
            return w, h, {"kids": kids}
        if isinstance(p, Wheel):
            z = self.zoom
            title_h = 22 * z if p.title else 0
            d = 2 * (WHEEL_R + WHEEL_CELL / 2 + 4) * z
            return d, d + title_h, {"title_h": title_h, "d": d}
        font = self._font(20 if p.big else 11, bold=p.big, mono=False)
        fm = QFontMetrics(font)
        return fm.horizontalAdvance(p.text) + 8, fm.height() + 4, {"font": font}

    def _invalidate(self) -> None:
        self._version += 1
        self._advance.clear()
        self._natural.clear()
        self.update()

    def _relayout(self) -> None:
        self._version += 1
        self._items, self._rects, self._texts = [], {}, {}
        if not self.step:
            self.setMinimumSize(0, 0)
            return
        z = self.zoom
        y, width = (MARGIN + (40 if self.step.arrows else 0)) * z, 0.0
        for row in self.step.rows:
            measured = [(p, *self._measure(p)) for p in row]
            if not measured:
                continue
            rh = max(h for _, _, h, _ in measured)
            centre = any(isinstance(p, Label) for p, *_ in measured)
            x = MARGIN * z
            for p, w, h, m in measured:
                self._place(p, x, y + ((rh - h) / 2 if centre else 0), w, h, m)
                x += w + PANEL_GAP * z
            width = max(width, x - PANEL_GAP * z + MARGIN * z)
            y += rh + ROW_GAP * z
        extra = BEND_ROOM * z if self.step.arrows else 0
        self.setMinimumSize(int(width + extra), int(y - ROW_GAP * z + MARGIN * z))
        self.updateGeometry()

    def _place(self, p, px: float, py: float, w: float, h: float, m: dict) -> None:
        z = self.zoom
        if isinstance(p, Stack):
            cy = py
            for c, cw, ch, cm in m["kids"]:
                self._place(c, px, cy, cw, ch, cm)
                cy += ch + STACK_GAP * z
            return
        self._items.append((p, px, py, w, h, m))
        th = m.get("title_h", 0) if isinstance(p, (Grid, Wheel)) else 0
        if isinstance(p, Grid):
            self._register_cells(p, px, py, m)
        if isinstance(p, Wheel):
            self._register_wheel(p, px, py, m)
        if p.id and not isinstance(p, Wheel):
            lw = m.get("label_w", 0) if isinstance(p, Grid) else 0
            self._rects[p.id] = QRectF(px + lw, py + th, w - lw, h - th)
            self._texts[p.id] = p.text if isinstance(p, Label) else ""

    def _wheel_geometry(self, wh: Wheel, px: float, py: float, m: dict):
        z = self.zoom
        cx, cy = px + m["d"] / 2, py + m["title_h"] + m["d"] / 2
        return cx, cy, WHEEL_R * z, (WHEEL_R - WHEEL_GAP) * z, WHEEL_CELL * z

    @staticmethod
    def _slot_point(cx, cy, r, slot: float) -> QPointF:
        ang = -math.pi / 2 + 2 * math.pi * slot / 26
        return QPointF(cx + r * math.cos(ang), cy + r * math.sin(ang))

    def _register_wheel(self, wh: Wheel, px: float, py: float, m: dict) -> None:
        cx, cy, ro, ri, cell = self._wheel_geometry(wh, px, py, m)
        for i in range(26):
            c = self._slot_point(cx, cy, ro, i)
            self._rects[f"{wh.id}o{i}"] = QRectF(c.x() - cell / 2, c.y() - cell / 2, cell, cell)
            self._texts[f"{wh.id}o{i}"] = ALPHABET[i]
            j = (i + wh.offset) % 26
            c = self._slot_point(cx, cy, ri, i)
            self._rects[f"{wh.id}i{j}"] = QRectF(c.x() - cell / 2, c.y() - cell / 2, cell, cell)
            self._texts[f"{wh.id}i{j}"] = ALPHABET[j]

    def _draw_wheel(self, qp: QPainter, wh: Wheel, px: float, py: float, m: dict, ui: dict, pending: set) -> None:
        z = self.zoom
        cx, cy, ro, ri, cell = self._wheel_geometry(wh, px, py, m)
        if wh.title:
            qp.setPen(QColor(ui["muted"]))
            qp.setFont(self._font(9.5, bold=True, mono=False))
            qp.drawText(QRectF(px, py, m["d"] + 100, m["title_h"]), Qt.AlignLeft | Qt.AlignVCenter, wh.title)
        # rings
        for r, col in ((ro, ui["border"]), (ri, ui["border"])):
            pen = QPen(QColor(col), 1.2 * z)
            qp.setPen(pen)
            qp.setBrush(Qt.NoBrush)
            qp.drawEllipse(QPointF(cx, cy), r + cell * 0.62, r + cell * 0.62)
        inner_disc = QColor(ui["alt"])
        qp.setPen(Qt.NoPen)
        qp.setBrush(inner_disc)
        qp.drawEllipse(QPointF(cx, cy), ri + cell * 0.62, ri + cell * 0.62)
        qp.setBrush(QColor(ui["card"]))
        qp.drawEllipse(QPointF(cx, cy), ri - cell * 0.62, ri - cell * 0.62)
        # rotation (animated)
        off = wh.offset
        if wh.offset_from is not None:
            off = wh.offset_from + (wh.offset - wh.offset_from) * _smooth(self._t)
        font = self._font(8.2, bold=True)

        def disc(center: QPointF, letter: str, style: str):
            bg, fg, border = theme().cell(style)
            r = QRectF(center.x() - cell / 2, center.y() - cell / 2, cell, cell)
            qp.setPen(QPen(QColor(border)) if border else Qt.NoPen)
            qp.setBrush(QColor(bg) if bg else Qt.NoBrush)
            qp.drawEllipse(r)
            qp.setPen(QColor(fg))
            qp.setFont(font)
            qp.drawText(r, Qt.AlignCenter, letter)

        for i in range(26):
            disc(self._slot_point(cx, cy, ro, i), ALPHABET[i], wh.outer_styles.get(i, "header"))
        for j in range(26):
            disc(self._slot_point(cx, cy, ri, j - off), ALPHABET[j], wh.inner_styles.get(j, "normal"))
        # centre caption
        qp.setPen(QColor(ui["text"]))
        qp.setFont(self._font(13, bold=True, mono=False))
        k = round(off)
        cap = wh.caption or (f"−{-k}" if -26 < k < 0 else f"+{k % 26}")  # negative keys keep their sign
        qp.drawText(QRectF(cx - 60 * z, cy - 18 * z, 120 * z, 24 * z), Qt.AlignCenter, cap)
        qp.setPen(QColor(ui["muted"]))
        qp.setFont(self._font(7.5, mono=False))
        qp.drawText(QRectF(cx - 60 * z, cy + 4 * z, 120 * z, 16 * z), Qt.AlignCenter, "outer: plain · inner: cipher")

    def _register_cells(self, g: Grid, x: float, y: float, m: dict) -> None:
        top = y + m["title_h"]
        for i, row in enumerate(g.cells):
            cy = top + i * (m["ch"] + m["gap"])
            if g.id and g.row_labels and i < len(g.row_labels):
                rid = f"{g.id}:row{i}"
                self._rects[rid] = QRectF(x, cy, m["label_w"] - 8 * self.zoom, m["ch"])
                self._texts[rid] = g.row_labels[i]
            cx = x + m["label_w"]
            for j, cell in enumerate(row):
                w = m["colw"][j]
                if cell.id:
                    self._rects[cell.id] = QRectF(cx, cy, w, m["ch"])
                    self._texts[cell.id] = cell.text
                cx += w + m["gap"]

    # ---- animation state ------------------------------------------------------------------------
    def _arrow_progress(self) -> list[tuple[Arrow, float]]:
        arrows = [a for a in (self.step.arrows if self.step else []) if a.src in self._rects and a.dst in self._rects]
        moving = [a for a in arrows if not a.static]
        phases = sorted({a.phase for a in moving})
        n = max(1, len(phases))
        index = {p: i for i, p in enumerate(phases)}
        return [(a, 1.0) for a in arrows if a.static] + [(a, _smooth(self._t * n - index[a.phase])) for a in moving]

    # ---- painting -----------------------------------------------------------------------------
    def paintEvent(self, _ev) -> None:
        qp = QPainter(self)
        qp.setRenderHint(QPainter.Antialiasing)
        ui = theme().ui
        qp.fillRect(self.rect(), QColor(ui["scene"]))
        if not self.step:
            qp.setPen(QColor(ui["muted"]))
            qp.setFont(self._font(11, mono=False))
            qp.drawText(self.rect(), Qt.AlignCenter,
                        "Enter a text and a key, then press Encrypt or Decrypt to watch the process step by step.")
            return
        progress = self._arrow_progress()
        pending = frozenset(a.dst for a, p in progress if a.reveal and p < 1.0)
        dpr = self.devicePixelRatioF()
        key = (self._version, pending, self.width(), self.height(), dpr)
        if key != self._layer_key or self._layer is None:
            self._layer_key = key
            self._layer, self._layer_focus = self._paint_layer(ui, pending, dpr)
        qp.drawPixmap(0, 0, self._layer)
        focus = self._layer_focus
        for p, x, y, w, h, m in self._items:
            if isinstance(p, Wheel):  # wheels rotate during the animation: always drawn live
                self._draw_wheel(qp, p, x, y, m, ui, pending)
        for a, prog in progress:
            if prog > 0:
                self._draw_arrow(qp, a, prog, ui)
        qp.end()
        if focus and self._emit_focus:
            self._emit_focus = False
            self.focusChanged.emit(focus[0])

    def _paint_layer(self, ui: dict, pending: frozenset, dpr: float):
        """Paint the static grids and labels into a pixmap; return it and the cell to focus."""
        pm = QPixmap(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor(ui["scene"]))
        qp = QPainter(pm)
        qp.setRenderHint(QPainter.Antialiasing)
        focus = None
        for p, x, y, w, h, m in self._items:
            if isinstance(p, Wheel):
                continue
            if isinstance(p, Label):
                if p.id and p.id in pending:
                    continue
                qp.setPen(QColor(ui["muted"] if not p.big else ui["text"]))
                qp.setFont(m["font"])
                qp.drawText(QRectF(x, y, w, h), Qt.AlignCenter, p.text)
            else:
                f = self._draw_grid(qp, p, x, y, m, ui, pending)
                if f is not None and (focus is None or not p.compact and focus[1]):
                    focus = (f, p.compact)
        qp.end()
        return pm, focus

    def _color(self, kind: str, ui: dict) -> QColor:
        key = KIND_COLOR.get(kind, "accent")
        return QColor(ui[key] if key in ui else key)

    def _path(self, S: QRectF, D: QRectF, curve: str = "auto") -> tuple[QPainterPath, bool]:
        """Cubic path between two rects; returns (path, bends_sideways)."""
        z = self.zoom
        sc, dc = S.center(), D.center()
        dx, dy = dc.x() - sc.x(), dc.y() - sc.y()
        path = QPainterPath()
        side = False
        if curve == "center":  # centre to centre, trimmed at both ends (zigzag guides)
            v = dc - sc
            length = math.hypot(v.x(), v.y()) or 1.0
            trim = min(S.width(), S.height()) * 0.42
            ux, uy = v.x() / length, v.y() / length
            path.moveTo(QPointF(sc.x() + ux * trim, sc.y() + uy * trim))
            path.lineTo(QPointF(dc.x() - ux * trim, dc.y() - uy * trim))
            return path, False
        if curve == "straight":
            if abs(dy) >= abs(dx):
                p0 = QPointF(sc.x(), S.bottom() + 2 if dy > 0 else S.top() - 2)
                p1 = QPointF(dc.x(), D.top() - 3 if dy > 0 else D.bottom() + 3)
            else:
                p0 = QPointF(S.right() + 2 if dx > 0 else S.left() - 2, sc.y())
                p1 = QPointF(D.left() - 3 if dx > 0 else D.right() + 3, dc.y())
            path.moveTo(p0)
            path.lineTo(p1)
            return path, False
        if curve == "side":  # leave and enter horizontally: wiring between columns placed side by side
            right = dx > 0
            p0 = QPointF(S.right() + 2 if right else S.left() - 2, sc.y())
            p1 = QPointF(D.left() - 3 if right else D.right() + 3, dc.y())
            span = p1.x() - p0.x()
            path.moveTo(p0)
            path.cubicTo(QPointF(p0.x() + span * 0.5, p0.y()), QPointF(p1.x() - span * 0.5, p1.y()), p1)
            return path, False
        if abs(dy) >= max(S.height(), D.height()) * 0.75:
            down = dy > 0
            p0 = QPointF(sc.x(), S.bottom() + 2 if down else S.top() - 2)
            p1 = QPointF(dc.x(), D.top() - 3 if down else D.bottom() + 3)
            span = p1.y() - p0.y()
            if abs(dx) < 6:  # same column: bulge to the right so intermediate cells stay visible
                b = min(70 * z, 24 * z + 0.15 * abs(span))
                c1, c2 = QPointF(p0.x() + b, p0.y() + span * 0.2), QPointF(p1.x() + b, p1.y() - span * 0.2)
                side = True
            else:
                c1, c2 = QPointF(p0.x(), p0.y() + span * 0.55), QPointF(p1.x(), p1.y() - span * 0.55)
        elif abs(dy) < 4:  # same row: arc above
            span = dc.x() - sc.x()
            lift = -min(58 * z, 22 * z + 0.12 * abs(span))
            p0, p1 = QPointF(sc.x(), S.top() - 2), QPointF(dc.x(), D.top() - 3)
            c1, c2 = QPointF(p0.x() + span * 0.15, p0.y() + lift), QPointF(p1.x() - span * 0.15, p1.y() + lift)
        else:
            right = dx > 0
            p0 = QPointF(S.right() + 2 if right else S.left() - 2, sc.y())
            p1 = QPointF(D.left() - 3 if right else D.right() + 3, dc.y())
            span = p1.x() - p0.x()
            c1, c2 = QPointF(p0.x() + span * 0.5, p0.y()), QPointF(p1.x() - span * 0.5, p1.y())
        path.moveTo(p0)
        path.cubicTo(c1, c2, p1)
        return path, side

    def _draw_arrow(self, qp: QPainter, a: Arrow, prog: float, ui: dict) -> None:
        z = self.zoom
        S, D = self._rects[a.src], self._rects[a.dst]
        path, side = self._path(S, D, a.curve)
        color = self._color(a.kind, ui)
        n = 40
        pts = [path.pointAtPercent(min(1.0, prog * k / n)) for k in range(n + 1)]
        partial = QPainterPath(pts[0])
        for pt in pts[1:]:
            partial.lineTo(pt)
        pen = QPen(color, 2.2 * z)
        pen.setCapStyle(Qt.RoundCap)
        if a.kind == "muted":
            pen.setStyle(Qt.DashLine)
        qp.setPen(pen)
        qp.setBrush(Qt.NoBrush)
        qp.drawPath(partial)
        tip, before = pts[-1], path.pointAtPercent(max(0.0, min(1.0, prog) - 0.04))
        ang = math.atan2(tip.y() - before.y(), tip.x() - before.x())
        size = 8 * z
        head = QPolygonF([tip,
                          QPointF(tip.x() - size * math.cos(ang - 0.45), tip.y() - size * math.sin(ang - 0.45)),
                          QPointF(tip.x() - size * math.cos(ang + 0.45), tip.y() - size * math.sin(ang + 0.45))])
        qp.setPen(Qt.NoPen)
        qp.setBrush(color)
        qp.drawPolygon(head)
        # travelling token
        if 0.0 < prog < 1.0:
            text = a.carry if a.carry is not None else self._texts.get(a.src, "")
            if text:
                f = self._font(10.5, bold=True)
                fm = QFontMetrics(f)
                w, h = fm.horizontalAdvance(text) + 14 * z, 24 * z
                r = QRectF(tip.x() - w / 2, tip.y() - h / 2, w, h)
                qp.setBrush(color)
                qp.drawRoundedRect(r, h / 2, h / 2)
                qp.setPen(QColor("#ffffff"))
                qp.setFont(f)
                qp.drawText(r, Qt.AlignCenter, text)
        # label pill
        if a.label and prog > 0.3:
            alpha = int(255 * min(1.0, (prog - 0.3) / 0.4))
            f = self._font(8.8, bold=True, mono=False)
            fm = QFontMetrics(f)
            mid = path.pointAtPercent(0.5)
            w, h = fm.horizontalAdvance(a.label) + 14 * z, 20 * z
            x = mid.x() + 6 * z if side else mid.x() - w / 2
            r = QRectF(x, mid.y() - h / 2, w, h)
            bg = QColor(ui["card"])
            bg.setAlpha(alpha)
            border = QColor(color)
            border.setAlpha(alpha)
            qp.setPen(QPen(border, 1.4 * z))
            qp.setBrush(bg)
            qp.drawRoundedRect(r, h / 2, h / 2)
            tc = QColor(ui["text"])
            tc.setAlpha(alpha)
            qp.setPen(tc)
            qp.setFont(f)
            qp.drawText(r, Qt.AlignCenter, a.label)

    def _draw_grid(self, qp: QPainter, g: Grid, x: float, y: float, m: dict, ui: dict, pending: set[str]):
        z = self.zoom
        focus = None
        if g.title:
            qp.setPen(QColor(ui["muted"]))
            qp.setFont(self._font(9.5, bold=True, mono=False))
            qp.drawText(QRectF(x, y, m["w"] + 200, m["title_h"]), Qt.AlignLeft | Qt.AlignVCenter, g.title)
        top = y + m["title_h"]
        sub_font = self._font(6.5 if not g.compact else 5, mono=False)
        radius = 4 * z if g.compact else 8 * z
        grid_waiting = bool(g.id) and g.id in pending
        for i, row in enumerate(g.cells):
            cy = top + i * (m["ch"] + m["gap"])
            if g.row_labels and i < len(g.row_labels):
                qp.setPen(QColor(ui["muted"]))
                qp.setFont(m["lab_font"])
                qp.drawText(QRectF(x, cy, m["label_w"] - 10 * z, m["ch"]), Qt.AlignRight | Qt.AlignVCenter,
                            g.row_labels[i])
            cx = x + m["label_w"]
            for j, cell in enumerate(row):
                w = m["colw"][j]
                rect = QRectF(cx, cy, w, m["ch"])
                waiting = grid_waiting or (cell.id and cell.id in pending)
                style = "empty" if waiting else cell.style
                bg, fg, border = theme().cell(style)
                if style == "empty":
                    pen = QPen(QColor(border))
                    pen.setStyle(Qt.DashLine)
                    qp.setPen(pen)
                    qp.setBrush(Qt.NoBrush)
                else:
                    qp.setPen(QPen(QColor(border)) if border else Qt.NoPen)
                    qp.setBrush(QColor(bg) if bg else Qt.NoBrush)
                if bg or border:
                    qp.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
                if cell.text and not waiting:
                    qp.setPen(QColor(fg))
                    qp.setFont(m["font"])
                    qp.drawText(rect, Qt.AlignCenter, cell.text)
                if cell.sub and not waiting:
                    qp.setPen(QColor(fg if cell.style in ("active", "current") else ui["muted"]))
                    qp.setFont(sub_font)
                    qp.drawText(rect.adjusted(0, 0, -3 * z, -1 * z), Qt.AlignRight | Qt.AlignBottom, cell.sub)
                if focus is None and cell.style in ("current", "active"):
                    focus = rect
                cx += w + m["gap"]
        return focus
