"""Rail fence: write the message in a zigzag over k rails, read rail by rail."""
from __future__ import annotations

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


def rail_order(n: int, rails: int) -> list[int]:
    """Text positions in the order they are read (rail by rail)."""
    z = zigzag(n, rails)
    return sorted(range(n), key=lambda i: (z[i], i))


@register
class RailFence(Cipher):
    id = "railfence"
    name = "Rail fence"
    family = "Transposition"
    order = 20
    preserves_layout = False
    summary = "Write the message in a zigzag over k rails, then read each rail."
    description = ("Write the plaintext diagonally down and up across <b>k rails</b> (rows), then read the rails "
                   "one after another to get the ciphertext. Decryption rebuilds the zigzag pattern, fills each "
                   "rail with the right number of letters, then reads along the zigzag.")
    crack_hint = "Brute force: there are only a few possible rail counts; rank them by English score."
    help = """## Idea
Write the message in a **zigzag** over *k* rails, then read rail by rail.

## Example — 2 rails
```
m . e . m . a . t . r . h . t . g . p . r . y
. e . t . e . f . e . t . e . o . a . a . t .
```
→ `MEMATRHTGPRYETEFETEOAAT`

## Decrypt
Draw the zigzag, count how many letters land on each rail, fill each rail with that many ciphertext letters, then read along the zigzag.

## Security
The only key is the number of rails, so brute force is trivial.
"""
    params = [Param("rails", "Rails (depth)", "int", 2, minimum=2, maximum=50,
                    random=lambda n: random.randint(2, 6))]
    crack_params = [Param("max_rails", "Max rails", "int", 20, minimum=2, maximum=100)]
    examples = [
        {"label": 'Encrypt: 2 rails', "mode": 'encrypt', "text": 'meet me after the toga party', "params": {'rails': 2}},
        {"label": 'Encrypt: 3 rails', "mode": 'encrypt', "text": 'we are discovered flee at once', "params": {'rails': 3}},
        {"label": 'Decrypt: 3 rails', "mode": 'decrypt', "text": 'DNETLHSEEDHESWLOTEATEFTAAFCL', "params": {'rails': 3}},
    ]

    def encrypt(self, letters, rails=2, **_):
        return "".join(letters[i] for i in rail_order(len(letters), int(rails)))

    def decrypt(self, letters, rails=2, **_):
        out = [""] * len(letters)
        for c, i in zip(letters, rail_order(len(letters), int(rails))):
            out[i] = c
        return "".join(out)

    @staticmethod
    def _grid(text: str, rails: int, shown: set[int], active: int | None = None, hl_rail: int | None = None,
              path: bool = False) -> Grid:
        """Rail grid; the cell holding text position i has id f"g{i}"."""
        z = zigzag(len(text), rails)
        cells = []
        for r in range(rails):
            line = []
            for i, ch in enumerate(text):
                if z[i] != r:
                    line.append(Cell("·", "dim"))
                elif i in shown:
                    st = "current" if i == active else ("hl" if r == hl_rail else "normal")
                    line.append(Cell(ch, st, "", f"g{i}"))
                else:
                    line.append(Cell("?" if path else "", "empty", "", f"g{i}"))
            cells.append(line)
        return Grid(cells, f"{rails} rails", [f"rail {r + 1}" for r in range(rails)], label_min=70)

    def trace(self, letters, mode, rails=2, **_):
        enc = mode == "encrypt"
        k = int(rails)
        notes: list[str] = []
        t = limit(letters, notes)
        n = len(t)
        z = zigzag(n, k)
        steps = []

        def path(upto: int) -> list:
            """The zigzag drawn as a guide line through positions 0..upto."""
            return [Arrow(f"g{j}", f"g{j + 1}", "", 0, kind="muted", curve="center", static=True)
                    for j in range(min(upto, n - 1))]

        if enc:
            out = self.encrypt(t, k)
            order = rail_order(n, k)
            in_grid = letters_grid(t, "in", "", "input", label="P.T", label_min=70)
            rows_out = [Row("C.T", list(out), "result", id="out")]
            steps.append(Step("Zigzag pattern", f"Write the {n} letters diagonally over {k} rails: down to the "
                              "bottom rail, then back up, repeating.",
                              [[in_grid], [self._grid(t, k, set(), path=True)], [stream_grid(rows_out, -1)]],
                              path(n)))
            for i in range(n):
                direction = "down" if (i % (2 * (k - 1))) < k - 1 else "up"
                steps.append(Step(f"Place letter {i + 1}/{n}: {t[i]}",
                                  f"{t[i]} goes on rail {z[i] + 1} (the zigzag is moving {direction}).",
                                  [[in_grid], [self._grid(t, k, set(range(i + 1)), i)], [stream_grid(rows_out, -1)]],
                                  path(i) + [Arrow(f"in{i}", f"g{i}", f"rail {z[i] + 1}", 0, reveal=True,
                                                   curve="straight")]))
            pos = 0
            for r in range(k):
                idx = [i for i in range(n) if z[i] == r]
                seg = "".join(t[i] for i in idx)
                steps.append(Step(f"Read rail {r + 1}", f"Rail {r + 1} left to right: {seg}",
                                  [[in_grid], [self._grid(t, k, set(range(n)), hl_rail=r)],
                                   [stream_grid(rows_out, pos + len(idx) - 1)]],
                                  path(n) + fan(((f"g{i}", f"out{order.index(i)}") for i in idx), 0,
                                                f"rail {r + 1}", "result")))
                pos += len(idx)
            final = self._grid(t, k, set(range(n)))
        else:
            out = self.decrypt(t, k)
            counts = [z.count(r) for r in range(k)]
            in_grid = letters_grid(t, "in", "C.T", "input")
            steps.append(Step("Mark the zigzag", f"Draw the zigzag for {n} letters on {k} rails (marked ?). "
                              f"Rail lengths: {counts}.", [[in_grid], [self._grid(out, k, set(), path=True)]], path(n)))
            shown: set[int] = set()
            pos = 0
            for r in range(k):
                idxs = [i for i in range(n) if z[i] == r]
                shown |= set(idxs)
                seg = t[pos:pos + len(idxs)]
                steps.append(Step(f"Fill rail {r + 1}", f"The next {len(idxs)} ciphertext letters “{seg}” fill the "
                                  f"marked places on rail {r + 1}, left to right.",
                                  [[in_grid], [self._grid(out, k, set(shown), hl_rail=r, path=True)]],
                                  path(n) + fan(((f"in{pos + q}", f"g{i}") for q, i in enumerate(idxs)), 0,
                                                f"rail {r + 1}")))
                pos += len(idxs)
            rows_out = [Row("P.T", list(out), "result", id="out")]
            for i in range(n):
                out_grid = stream_grid(rows_out, i, label_min=70)
                steps.append(Step(f"Read along the zigzag {i + 1}/{n}: {out[i]}",
                                  f"Follow the zigzag: position {i + 1} is on rail {z[i] + 1} → {out[i]}",
                                  [[in_grid], [self._grid(out, k, set(range(n)), i)], [out_grid]],
                                  path(i) + [Arrow(f"g{i}", f"out{i}", f"rail {z[i] + 1}", 0, reveal=True,
                                                   kind="result", curve="straight")]))
            final = self._grid(out, k, set(range(n)))
        steps.append(Step("Done", f"Result: {out}", [[final], [letters_grid(out, "res", "Result", "result")]]))
        return Trace(steps, out, notes)

    def crack(self, letters, ctx, max_rails=20, **_):
        n = len(letters)
        if n < 4:
            raise CipherError("Need at least 4 letters.")
        sc = get_scorer()
        res = CrackResult()
        res.log.append("Brute force over the number of rails (the only key):\n")
        top = min(int(max_rails), n - 1)
        for k in range(2, top + 1):
            pt = self.decrypt(letters, k)
            res.candidates.append(Candidate(str(k), {"rails": k}, pt, sc.english_likeness(pt)))
            res.log.append(f"  {k:>3} rails: English {res.candidates[-1].score:.2f} → {pt[:55]}")
        res.candidates.sort(key=lambda c: -c.score)
        res.log.append(f"\nBest: {res.candidates[0].key} rails")
        return res
