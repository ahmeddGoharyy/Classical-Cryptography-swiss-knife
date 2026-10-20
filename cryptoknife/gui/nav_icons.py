"""Flat line icons for the menu (24 × 24, single colour stroke)."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_S = 'fill="none" stroke="{c}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"'

ICONS = {
    "home": f'<path d="M4 11l8-7 8 7"  {_S}/><path d="M6 10v10h12V10" {_S}/><path d="M10 20v-6h4v6" {_S}/>',
    # cipher wheel: ring + rotation arrow
    "caesar": f'<circle cx="12" cy="12" r="8" {_S}/><circle cx="12" cy="12" r="3.5" {_S}/>'
              f'<path d="M12 4v4.5M20 12h-4.5M12 20v-4.5M4 12h4.5" {_S}/>',
    # substitution table: two rows linked by arrows
    "monoalphabetic": f'<path d="M4 6h16M4 18h16" {_S}/><path d="M7 9v6M12 9v6M17 9v6" {_S}/>'
                      f'<path d="M5.5 13.5L7 15l1.5-1.5M10.5 13.5L12 15l1.5-1.5M15.5 13.5L17 15l1.5-1.5" {_S}/>',
    # tableau: grid
    "vigenere": f'<rect x="4" y="4" width="16" height="16" rx="2" {_S}/><path d="M4 9.3h16M4 14.6h16M9.3 4v16M14.6 4v16" {_S}/>',
    # key feeding itself: key + loop
    "autokey": f'<circle cx="8" cy="12" r="3.5" {_S}/><path d="M11.5 12H20M17 12v3M20 12v2" {_S}/>'
               f'<path d="M5 6.5A8 8 0 0 1 19 7" {_S}/><path d="M19 3.8V7h-3.2" {_S}/>',
    # pad of paper with random lines
    "otp": f'<rect x="5" y="3.5" width="14" height="17" rx="2" {_S}/><path d="M8.5 8h7M8.5 11.5h4.5M8.5 15h6" {_S}/>',
    # 5×5 key square (shown as a 3×3 grid with a highlighted rectangle)
    "playfair": f'<rect x="4" y="4" width="16" height="16" rx="2" {_S}/><path d="M4 12h16M12 4v16" {_S}/>'
                f'<rect x="7" y="7" width="10" height="10" rx="1" fill="{{c}}" fill-opacity="0.35" stroke="none"/>',
    # matrix in brackets
    "hill": f'<path d="M7 4H5v16h2M17 4h2v16h-2" {_S}/>'
            f'<circle cx="9.5" cy="9" r="1.2" fill="{{c}}"/><circle cx="14.5" cy="9" r="1.2" fill="{{c}}"/>'
            f'<circle cx="9.5" cy="15" r="1.2" fill="{{c}}"/><circle cx="14.5" cy="15" r="1.2" fill="{{c}}"/>',
    # columns being rearranged
    "columnar": f'<rect x="4" y="5" width="4" height="14" rx="1" {_S}/><rect x="10" y="5" width="4" height="14" rx="1" {_S}/>'
                f'<rect x="16" y="5" width="4" height="14" rx="1" {_S}/>',
    "railfence": f'<path d="M3 7l4.5 10L12 7l4.5 10L21 7" {_S}/>',
    "freq": f'<path d="M4 20h16" {_S}/><path d="M7 20v-9M11 20V6M15 20v-6M19 20v-3" {_S}/>',
    # categories
    "classical": f'<path d="M6 4h10a2 2 0 0 1 2 2v12a2 2 0 0 0 2 2H8a2 2 0 0 1-2-2V4z" {_S}/>'
                 f'<path d="M6 4a2 2 0 0 0-2 2v1h2M9.5 9h5M9.5 12.5h5M9.5 16h3" {_S}/>',
    "symmetric": f'<circle cx="7.5" cy="12" r="3.5" {_S}/><path d="M11 12h9.5M17.5 12v3M20.5 12v2.5" {_S}/>',
    "asymmetric": f'<rect x="5" y="10.5" width="14" height="10" rx="2" {_S}/><path d="M8 10.5V7.5a4 4 0 0 1 8 0" {_S}/>'
                  f'<path d="M12 14.5v2.5" {_S}/>',
    "tools": f'<path d="M14.5 5.5a4 4 0 0 0 4.9 4.9L20 11l-9 9-3-3 9-9 .6.6a4 4 0 0 1-3.1-3.1z" {_S}/>',
}


def icon_pixmap(name: str, color: str, size: int = 18, dpr: float = 2.0) -> QPixmap:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{ICONS[name].format(c=color)}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.Antialiasing)
    renderer.render(qp, QRectF(0, 0, pm.width(), pm.height()))
    qp.end()
    pm.setDevicePixelRatio(dpr)
    return pm
