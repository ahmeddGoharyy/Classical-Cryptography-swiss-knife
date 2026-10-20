"""App logo: a front-facing Spartan (Corinthian) helmet with a keyhole on the forehead.

Flat, single colour — no gradients.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

TILE_COLOR = "#3b82f6"

# 200 × 200 canvas, symmetric about x = 100.
CREST = "M 94 46 C 93 32, 88 18, 80 6 C 93 9, 107 9, 120 6 C 112 18, 107 32, 106 46 Z"
# helmet outline, then (even-odd holes) the face opening — almond eye slits, a nose guard hanging
# between them, the mouth gap between the cheek guards — and a keyhole on the forehead
HELMET = ("M 100 52 C 140 52, 164 80, 164 118 L 164 150 C 164 170, 170 184, 178 196 L 22 196 "
          "C 30 184, 36 170, 36 150 L 36 118 C 36 80, 60 52, 100 52 Z "
          "M 44 116 C 62 112, 80 113, 92 119 L 92 148 L 108 148 L 108 119 C 120 113, 138 112, 156 116 "
          "C 150 128, 136 136, 117 138 L 113 196 L 87 196 L 83 138 C 64 136, 50 128, 44 116 Z "
          "M 95 84 A 10 10 0 1 1 105 84 L 108 99 L 92 99 Z")


def logo_svg(color: str = "#e8eaed", tile: bool = False) -> str:
    """tile=True: white helmet on a flat rounded square (app icon); otherwise the helmet alone in `color`."""
    shapes = f"<path d='{CREST}'/><path d='{HELMET}' fill-rule='evenodd'/>"
    if tile:
        body = (f"<rect width='200' height='200' rx='44' fill='{TILE_COLOR}'/>"
                f"<g transform='translate(26 22) scale(0.74)' fill='white'>{shapes}</g>")
    else:
        body = f"<g fill='{color}'>{shapes}</g>"
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 200'>{body}</svg>"


def logo_pixmap(size: int, tile: bool = False, color: str = "#e8eaed", dpr: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(logo_svg(color, tile).encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    renderer.render(qp, QRectF(0, 0, pm.width(), pm.height()))
    qp.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s, tile=True, dpr=1.0))
    return icon
