"""GUI-independent description of a visualization.

A cipher's ``trace()`` returns a :class:`Trace`: a list of :class:`Step`
objects. Each step is a small "scene" made of panels (grids of cells and
labels) plus an explanation. The GUI only knows how to draw these panels,
so ciphers never contain drawing code and stay unit-testable.

Cell styles (the renderer maps them to colors):
    normal  plain cell              header  table header
    input   given input letter      key     key material
    active  being processed now     current value just produced
    result  produced earlier        hl      highlighted lane/region
    filler  padding / filler letter dim     de-emphasized
    empty   not computed yet        warn    problem / attention

Arrows: cells (and whole grids) can have an ``id``. A step's ``arrows`` connect
ids to show *where each value comes from and where it goes*. The GUI animates
them phase by phase: the arrow draws itself, a token carrying the value flies
along it, and (``reveal=True``) the destination cell fills in when it lands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

MAX_VIZ = 120  # letters animated step by step; longer texts are still fully en/decrypted


@dataclass
class Cell:
    text: str = ""
    style: str = "normal"
    sub: str = ""  # small corner annotation (e.g. letter index)
    id: str = ""   # target for arrows


@dataclass
class Grid:
    cells: list[list[Cell]]
    title: str = ""
    row_labels: list[str] | None = None
    compact: bool = False
    id: str = ""   # the whole grid can be an arrow target
    label_min: float = 0  # minimum row-label column width (px at zoom 1), to align stacked grids


@dataclass
class Label:
    text: str
    big: bool = True
    id: str = ""


@dataclass
class Wheel:
    """Cipher wheel: outer ring = plain alphabet, inner ring = alphabet rotated by ``offset``.

    Outer slot i shows letter i; the inner ring shows letter (i + offset) mod 26 at slot i, so plain
    letter i lines up with cipher letter i + offset. ``offset_from`` animates the rotation.
    Ids: outer letters f"{id}o{i}", inner letters f"{id}i{j}" (j = the inner letter's index).
    """
    offset: int = 0
    offset_from: int | None = None
    outer_styles: dict = field(default_factory=dict)
    inner_styles: dict = field(default_factory=dict)
    title: str = ""
    id: str = "w"
    caption: str = ""


@dataclass
class Stack:
    """Panels stacked vertically inside one cell of a row."""
    panels: list
    id: str = ""


Panel = Grid | Label | Wheel | Stack


@dataclass
class Arrow:
    """An animated arrow from one cell/grid id to another.

    phase  arrows animate in increasing phase order; equal phases move together
    label  short text drawn on the arrow (e.g. "+3 mod 26", "row K")
    carry  text of the token that travels along the arrow (default: the source cell's text)
    reveal hide the destination cell's text until the token arrives
    kind   flow (blue) | key (amber) | result (green) | muted
    """
    src: str
    dst: str
    label: str = ""
    phase: int = 0
    carry: str | None = None
    reveal: bool = False
    kind: str = "flow"
    curve: str = "auto"  # auto | straight
    static: bool = False  # drawn fully at all times (paths, guides), not animated


@dataclass
class Step:
    title: str
    detail: str = ""
    rows: list[list[Panel]] = field(default_factory=list)
    arrows: list[Arrow] = field(default_factory=list)


@dataclass
class Trace:
    steps: list[Step]
    result: str
    notes: list[str] = field(default_factory=list)


@dataclass
class Chart:
    """Bar chart spec rendered by the GUI with matplotlib."""
    title: str
    labels: list[str]
    series: dict[str, list[float]]
    ylabel: str = ""
    refs: dict[str, float] = field(default_factory=dict)  # horizontal reference lines
    highlight: list[int] = field(default_factory=list)


def limit(letters: str, notes: list[str]) -> str:
    if len(letters) > MAX_VIZ:
        notes.append(f"Visualization animates the first {MAX_VIZ} of {len(letters)} letters; "
                     "the output box contains the full result.")
        return letters[:MAX_VIZ]
    return letters


@dataclass
class Row:
    """One row of a :func:`stream_grid`.

    reveal[j] is the step at which cell j gets computed; -1 means it is given
    up front. ``None`` means every cell is computed at its own index.
    """
    label: str
    values: Sequence[str]
    style: str = "normal"
    reveal: Sequence[int] | None = None
    given: bool = False
    id: str = ""  # cell ids become f"{id}{j}"


def stream_grid(rows: list[Row], active: int | None, title: str = "", filler: set[int] | None = None,
                label_min: float = 0) -> Grid:
    """A classic textbook-style table (P.T / index / key / C.T rows) revealed up to ``active``.

    active = None shows everything (overview); -1 shows only given rows.
    """
    filler = filler or set()
    cells = []
    for row in rows:
        out = []
        for j, v in enumerate(row.values):
            r = -1 if row.given else (row.reveal[j] if row.reveal is not None else j)
            style = "filler" if (j in filler and row.style in ("input", "result")) else row.style
            if active is None:
                c = Cell(v, style)
            elif r == active and not row.given and r >= 0:
                c = Cell(v, "current")
            elif r < active or r == -1:
                c = Cell(v, "active" if j == active else style)
            else:
                c = Cell("", "empty")
            c.id = f"{row.id}{j}" if row.id else ""
            out.append(c)
        cells.append(out)
    return Grid(cells, title, [r.label for r in rows], label_min=label_min)


def mapping_strip(top_label: str, top: str, bottom_label: str, bottom: str,
                  col: int | None, forward: bool, title: str = "", key_cols: set[int] | None = None,
                  id: str = "map", label_min: float = 0) -> Grid:
    """Two aligned alphabets (e.g. plain vs cipher) with one column highlighted.

    Cell ids: f"{id}t{j}" (top row) and f"{id}b{j}" (bottom row).
    """
    key_cols = key_cols or set()
    t, b = [], []
    for j in range(len(top)):
        ts, bs = "header", ("key" if j in key_cols else "normal")
        if j == col:
            ts, bs = ("active", "current") if forward else ("current", "active")
        t.append(Cell(top[j], ts, str(j), f"{id}t{j}"))
        b.append(Cell(bottom[j], bs, "", f"{id}b{j}"))
    return Grid([t, b], title, [top_label, bottom_label], id=id, label_min=label_min)


def letter_cells(s: str, style: str = "normal", id: str = "") -> list[Cell]:
    return [Cell(c, style, "", f"{id}{j}" if id else "") for j, c in enumerate(s)]


def fan(pairs, phase: int = 0, label: str = "", kind: str = "flow", reveal: bool = True,
        limit: int = 60, curve: str = "auto") -> list[Arrow]:
    """Arrows for many (src, dst) pairs moving together; only the first one carries the label."""
    return [Arrow(s, d, label if k == 0 else "", phase, None, reveal, kind, curve)
            for k, (s, d) in enumerate(list(pairs)[:limit])]


def letters_grid(s: str, id: str, title: str = "", style: str = "input", styles: dict[int, str] | None = None,
                 label: str | None = None, label_min: float = 0) -> Grid:
    """One-row grid of letters with ids f"{id}{j}"."""
    styles = styles or {}
    return Grid([[Cell(c, styles.get(j, style), "", f"{id}{j}") for j, c in enumerate(s)]], title,
                [label] if label else None, label_min=label_min)
