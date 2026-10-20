"""App logo: the Crypto Swiss Knife emblem (Spartan helmet in a binary/circuit ring).

The artwork ships as transparent masks in ``cryptoknife/data``:
- ``logo.png``         the full emblem with the name, for the home page
- ``logo-helmet.png``  the helmet alone, for small icons
Both are tinted at runtime, so the logo follows the light/dark theme. Flat colours only.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPixmap

DATA = Path(__file__).resolve().parent.parent / "data"
TILE_COLOR = "#3b82f6"


@lru_cache(maxsize=None)
def _mask(name: str) -> QImage:
    return QImage(str(DATA / name)).convertToFormat(QImage.Format_ARGB32_Premultiplied)


def _tinted(name: str, color: str, w: int, h: int) -> QImage:
    """The mask scaled to fit w × h (aspect kept), filled with ``color``."""
    img = _mask(name).scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    qp = QPainter(img)
    qp.setCompositionMode(QPainter.CompositionMode_SourceIn)
    qp.fillRect(img.rect(), QColor(color))
    qp.end()
    return img


def emblem_pixmap(height: int, color: str, dpr: float = 2.0) -> QPixmap:
    """The full emblem (helmet, binary ring and name) in one flat colour."""
    src = _mask("logo.png")
    h = int(height * dpr)
    w = int(h * src.width() / src.height())
    pm = QPixmap.fromImage(_tinted("logo.png", color, w, h))
    pm.setDevicePixelRatio(dpr)
    return pm


def logo_pixmap(size: int, tile: bool = False, color: str = "#e8eaed", dpr: float = 2.0) -> QPixmap:
    """The helmet alone; tile=True puts a white helmet on a flat rounded square (icons)."""
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    qp.setRenderHint(QPainter.SmoothPixmapTransform)
    pad = 0.0
    if tile:
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, px, px), px * 0.22, px * 0.22)
        qp.fillPath(path, QColor(TILE_COLOR))
        pad = px * 0.14
    helmet = _tinted("logo-helmet.png", "#ffffff" if tile else color, int(px - 2 * pad), int(px - 2 * pad))
    qp.drawImage(int((px - helmet.width()) / 2), int((px - helmet.height()) / 2), helmet)
    qp.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(logo_pixmap(s, tile=True, dpr=1.0))
    return icon
