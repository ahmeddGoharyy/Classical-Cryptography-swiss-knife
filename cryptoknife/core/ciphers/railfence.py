"""Rail fence: write the message over k rails (in a zigzag, or down the columns), read rail by rail."""
from __future__ import annotations

import math
import random

from ..analysis import get_scorer
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import CipherError
from ..trace import Arrow, Cell, Grid, Row, Step, Trace, fan, letters_grid, limit, stream_grid


def zigzag(n: int, rails: int) -> list[int]:
    if rails < 2:
        return [0] * n
    cycle = 2 * (rails - 1)
    return [i % cycle if i % cycle < rails else cycle - i % cycle for i in range(n)]


ZIGZAG, COLUMNS = "Zigzag", "Columns (top to bottom)"


def rails_of(n: int, rails: int, pattern: str = ZIGZAG) -> list[int]:
    """The rail (row) each text position is written on."""
    if pattern == COLUMNS:  # down each column of `rails` rows, then on to the next column
        return [i % rails for i in range(n)]
    return zigzag(n, rails)


def rail_order(n: int, rails: int, pattern: str = ZIGZAG) -> list[int]:
    """Text positions in the order they are read (rail by rail)."""
    z = rails_of(n, rails, pattern)
    return sorted(range(n), key=lambda i: (z[i], i))


@register
class RailFence(Cipher):
    id = "railfence"
    name = "Rail fence"
    family = "Transposition"
    order = 20
    preserves_layout = False
    summary = "Write the message over k rails (zigzag or column by column), then read each rail."
    description = ("Write the plaintext over <b>k rails</b> (rows), then read the rails one after another to get "
                   "the ciphertext. <b>Zigzag:</b> diagonally down and up. <b>Columns:</b> straight down each "
                   "column of k rows, like the lecture. Decryption rebuilds the pattern, fills each rail with "
                   "the right number of letters, then reads it back in writing order.")
    crack_hint = ("Brute force: there are only a few possible rail counts (for both patterns); rank them by "
                  "English score.")
    help = """## Idea
Write the message over *k* rails (the **depth**), then read rail by rail. Two ways to write it:

**Zigzag:** diagonally down to the bottom rail and back up.
```
m . e . m . a . t . r . h . t . g . p . r . y
. e . t . e . f . e . t . e . o . a . a . t .
```
→ `MEMATRHTGPRYETEFETEOAAT`

**Columns** (lecture): straight down each column of k rows, then the next column.
```
c m u e s i n e
o p t r c e c
```
`Computer Science`, depth 2 → `CMUESINEOPTRCEC`; depth 3 → `CPECNOURICMTSEE`

## Decrypt
Rebuild the pattern and count the letters on each rail: for columns, the text fills ⌈length ÷ depth⌉ columns (15 ÷ 2 = 7.5 → 8), and only the first rails reach the last column. Fill each rail with that many ciphertext letters, then read in writing order.

## Security
The only key is the number of rails, so brute force is trivial.
"""
    key_help = """## Key shape
**One number:** how many rails (rows, the depth), plus the writing pattern (zigzag or columns).

## Key space
At most **n − 1** useful values for an n-letter message, which is tiny.

## Weaknesses
- Brute force over the rail count takes a fraction of a second.
- Letters keep their identity, so frequencies match English.
"""
    params = [Param("rails", "Rails (depth)", "int", 2, minimum=2, maximum=50,
                    random=lambda n: random.randint(2, 6)),
              Param("pattern", "Pattern", "choice", ZIGZAG, [ZIGZAG, COLUMNS],
                    help="Zigzag: down and up diagonally. Columns: straight down each column (lecture)")]
    crack_params = [Param("max_rails", "Max rails", "int", 20, minimum=2, maximum=100)]
    examples = [
        {"label": 'Encrypt: 2 rails', "mode": 'encrypt', "text": 'meet me after the toga party', "params": {'rails': 2}},
        {"label": 'Encrypt: 3 rails', "mode": 'encrypt', "text": 'we are discovered flee at once', "params": {'rails': 3}},
        {"label": 'Decrypt: 3 rails', "mode": 'decrypt', "text": 'DNETLHSEEDHESWLOTEATEFTAAFCL', "params": {'rails': 3}},
        {"label": 'Encrypt: columns, depth 2 (lecture)', "mode": 'encrypt', "text": 'Computer Science',
         "params": {'rails': 2, 'pattern': COLUMNS}},
        {"label": 'Encrypt: columns, depth 3 (lecture)', "mode": 'encrypt', "text": 'Computer Science',
         "params": {'rails': 3, 'pattern': COLUMNS}},
        {"label": 'Decrypt: columns, depth 2 (lecture)', "mode": 'decrypt', "text": 'CMUESINEOPTRCEC',
         "params": {'rails': 2, 'pattern': COLUMNS}},
    ]

    def encrypt(self, letters, rails=2, pattern=ZIGZAG, **_):
        return "".join(letters[i] for i in rail_order(len(letters), int(rails), pattern))

    def decrypt(self, letters, rails=2, pattern=ZIGZAG, **_):
        out = [""] * len(letters)
        for c, i in zip(letters, rail_order(len(letters), int(rails), pattern)):
            out[i] = c
        return "".join(out)

    @staticmethod
    def _grid(text: str, rails: int, shown: set[int], active: int | None = None, hl_rail: int | None = None,
              path: bool = False, pattern: str = ZIGZAG) -> Grid:
        """Rail grid; the cell holding text position i has id f"g{i}".

        Zigzag: one column per letter. Columns: ⌈n / rails⌉ columns, letter i at (i mod rails, i div rails).
        """
        n = len(text)
        if pattern == COLUMNS:
            ncols = math.ceil(n / rails)
            where = {(i % rails, i // rails): i for i in range(n)}
        else:
            ncols, z = n, zigzag(n, rails)
            where = {(z[i], i): i for i in range(n)}
        cells = []
        for r in range(rails):
            line = []
            for c in range(ncols):
                i = where.get((r, c))
                if i is None:
                    line.append(Cell("·" if pattern == ZIGZAG else "", "dim"))
                elif i in shown:
                    st = "current" if i == active else ("hl" if r == hl_rail else "normal")
                    line.append(Cell(text[i], st, "", f"g{i}"))
                else:
                    line.append(Cell("?" if path else "", "empty", "", f"g{i}"))
            cells.append(line)
        title = f"{rails} rails" + (f", {ncols} columns" if pattern == COLUMNS else "")
        return Grid(cells, title, [f"rail {r + 1}" for r in range(rails)], label_min=70)

    def trace(self, letters, mode, rails=2, pattern=ZIGZAG, **_):
        enc = mode == "encrypt"
        k = int(rails)
        cols = pattern == COLUMNS
        notes: list[str] = []
        t = limit(letters, notes)
        n = len(t)
        z = rails_of(n, k, pattern)
        steps = []
        grid = lambda *a, **kw: self._grid(*a, pattern=pattern, **kw)  # noqa: E731

        def path(upto: int) -> list:
            """The zigzag drawn as a guide line through positions 0..upto."""
            return [Arrow(f"g{j}", f"g{j + 1}", "", 0, kind="muted", curve="center", static=True)
                    for j in range(min(upto, n - 1))]

        if enc:
            out = self.encrypt(t, k, pattern)
            order = rail_order(n, k, pattern)
            in_grid = letters_grid(t, "in", "", "input", label="P.T", label_min=70)
            rows_out = [Row("C.T", list(out), "result", id="out")]
            how = (f"Write the {n} letters down the columns: {k} letters per column, top to bottom, then the "
                   f"next column ({n} ÷ {k} → {math.ceil(n / k)} columns)." if cols else
                   f"Write the {n} letters diagonally over {k} rails: down to the bottom rail, then back up, "
                   "repeating.")
            steps.append(Step("Columns pattern" if cols else "Zigzag pattern", how,
                              [[in_grid], [grid(t, k, set(), path=True)], [stream_grid(rows_out, -1)]],
                              path(n)))
            for i in range(n):
                if cols:
                    where = f"column {i // k + 1}, rail {z[i] + 1}"
                else:
                    where = f"rail {z[i] + 1} (the zigzag is moving {'down' if i % (2 * (k - 1)) < k - 1 else 'up'})"
                steps.append(Step(f"Place letter {i + 1}/{n}: {t[i]}", f"{t[i]} goes in {where}.",
                                  [[in_grid], [grid(t, k, set(range(i + 1)), i)], [stream_grid(rows_out, -1)]],
                                  path(i) + [Arrow(f"in{i}", f"g{i}", f"rail {z[i] + 1}", 0, reveal=True,
                                                   curve="straight")]))
            pos = 0
            for r in range(k):
                idx = [i for i in range(n) if z[i] == r]
                seg = "".join(t[i] for i in idx)
                steps.append(Step(f"Read rail {r + 1}", f"Rail {r + 1} left to right: {seg}",
                                  [[in_grid], [grid(t, k, set(range(n)), hl_rail=r)],
                                   [stream_grid(rows_out, pos + len(idx) - 1)]],
                                  path(n) + fan(((f"g{i}", f"out{order.index(i)}") for i in idx), 0,
                                                f"rail {r + 1}", "result")))
                pos += len(idx)
            final = grid(t, k, set(range(n)))
        else:
            out = self.decrypt(t, k, pattern)
            counts = [z.count(r) for r in range(k)]
            in_grid = letters_grid(t, "in", "C.T", "input")
            shape = (f"{math.ceil(n / k)} columns of {k} rails ({n} ÷ {k} rounded up; the last column may be "
                     "short)" if cols else f"the zigzag for {n} letters on {k} rails")
            steps.append(Step("Mark the pattern", f"Draw {shape}, marked ?. Rail lengths: {counts}.",
                              [[in_grid], [grid(out, k, set(), path=True)]], path(n)))
            shown: set[int] = set()
            pos = 0
            for r in range(k):
                idxs = [i for i in range(n) if z[i] == r]
                shown |= set(idxs)
                seg = t[pos:pos + len(idxs)]
                steps.append(Step(f"Fill rail {r + 1}", f"The next {len(idxs)} ciphertext letters “{seg}” fill the "
                                  f"marked places on rail {r + 1}, left to right.",
                                  [[in_grid], [grid(out, k, set(shown), hl_rail=r, path=True)]],
                                  path(n) + fan(((f"in{pos + q}", f"g{i}") for q, i in enumerate(idxs)), 0,
                                                f"rail {r + 1}")))
                pos += len(idxs)
            rows_out = [Row("P.T", list(out), "result", id="out")]
            for i in range(n):
                out_grid = stream_grid(rows_out, i, label_min=70)
                route = f"column {i // k + 1}, rail {z[i] + 1}" if cols else f"rail {z[i] + 1}"
                steps.append(Step(f"Read in writing order {i + 1}/{n}: {out[i]}",
                                  f"Position {i + 1} is in {route} → {out[i]}",
                                  [[in_grid], [grid(out, k, set(range(n)), i)], [out_grid]],
                                  path(i) + [Arrow(f"g{i}", f"out{i}", f"rail {z[i] + 1}", 0, reveal=True,
                                                   kind="result", curve="straight")]))
            final = grid(out, k, set(range(n)))
        steps.append(Step("Done", f"Result: {out}", [[final], [letters_grid(out, "res", "Result", "result")]]))
        return Trace(steps, out, notes)

    def crack(self, letters, ctx, max_rails=20, **_):
        n = len(letters)
        if n < 4:
            raise CipherError("Need at least 4 letters.")
        sc = get_scorer()
        res = CrackResult()
        res.log.append("Brute force over the number of rails, for both writing patterns:\n")
        top = min(int(max_rails), n - 1)
        for pattern in (ZIGZAG, COLUMNS):
            for k in range(2, top + 1):
                pt = self.decrypt(letters, k, pattern)
                key = f"{k} rails, {pattern.split()[0].lower()}"
                res.candidates.append(Candidate(key, {"rails": k, "pattern": pattern}, pt, sc.english_likeness(pt)))
                res.log.append(f"  {key:<18} English {res.candidates[-1].score:.2f} → {pt[:50]}")
        res.candidates.sort(key=lambda c: -c.score)
        res.log.append(f"\nBest: {res.candidates[0].key}")
        return res
