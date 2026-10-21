"""Digraph substitution: a higher-order (block) cipher that replaces each letter pair using a 26×26 table."""
from __future__ import annotations

import random
import re
from functools import lru_cache

from ..cipher import Cipher, Param, register
from ..text import ALPHABET, CipherError, chunks, clean
from ..trace import Arrow, Cell, Grid, Row, Step, Trace, fan, letters_grid, limit, stream_grid

PAIRS = [a + b for a in ALPHABET for b in ALPHABET]
DEFAULT_FIXED = "AA=DS AB=CG AC=HH"  # the lecture's table
DEFAULT_KEY = "LECTURE"


def parse_fixed(fixed: str) -> dict[str, str]:
    """'AA=DS AB=CG' → {'AA': 'DS', 'AB': 'CG'}."""
    out: dict[str, str] = {}
    for entry in (e for e in re.split(r"[\s,;]+", fixed) if e):
        p, eq, c = entry.partition("=")
        p, c = clean(p), clean(c)
        if not eq or len(p) != 2 or len(c) != 2:
            raise CipherError(f"Fixed pair “{entry}” should look like AA=DS (two letters = two letters).")
        if p in out:
            raise CipherError(f"Fixed pairs list the plain pair {p} twice.")
        if c in out.values():
            raise CipherError(f"Fixed pairs use the cipher pair {c} twice; each cipher pair may appear once.")
        out[p] = c
    return out


@lru_cache(maxsize=8)
def build_table(fixed: str, key: str) -> dict[str, str]:
    """All 676 plain pairs → cipher pairs: the fixed pairs, then the rest shuffled by the keyword."""
    table = parse_fixed(fixed)
    rest = [c for c in PAIRS if c not in set(table.values())]
    random.Random("digraph:" + clean(key)).shuffle(rest)  # a string seed gives the same order on every run
    for p, c in zip((p for p in PAIRS if p not in table), rest):
        table[p] = c
    return table


@lru_cache(maxsize=8)
def inverse_table(fixed: str, key: str) -> dict[str, str]:
    return {c: p for p, c in build_table(fixed, key).items()}


def _filler(filler: str) -> str:
    return (clean(filler) or "X")[0]


def table_grid(table: dict[str, str], fixed: set[str], r: int | None = None, c: int | None = None,
               forward: bool = True) -> Grid:
    """26×26 table: row = first plain letter, column = second, cell = cipher pair.

    Ids: column headers f"dc{c}", row headers f"dr{r}", body f"d{r}_{c}".
    """
    cells = [[Cell("", "header")] + [Cell(ALPHABET[j], ("active" if forward else "current") if j == c else "header",
                                          "", f"dc{j}") for j in range(26)]]
    for i in range(26):
        line = [Cell(ALPHABET[i], ("active" if forward else "current") if i == r else "header", "", f"dr{i}")]
        for j in range(26):
            p = ALPHABET[i] + ALPHABET[j]
            st = "key" if p in fixed else "normal"
            if i == r and j == c:
                st = "current" if forward else "active"
            elif r is not None and c is not None and (i == r and j < c or j == c and i < r):
                st = "hl"
            line.append(Cell(table[p], st, "", f"d{i}_{j}"))
        cells.append(line)
    return Grid(cells, "Key table (row = 1st letter, column = 2nd letter)", compact=True)


@register
class Digraph(Cipher):
    id = "digraph"
    name = "Digraph substitution (higher order)"
    family = "Polygraphic substitution"
    order = 5
    preserves_layout = False
    summary = "Replace each pair of letters with another pair from a 26×26 table: a block cipher on digrams."
    description = ("Higher-order substitution: the text is split into <b>blocks of two letters</b>, and every one "
                   "of the 26 × 26 = 676 possible pairs has its own cipher pair (AA→DS, AB→CG, AC→HH, …). A filler "
                   "(X) completes an odd last pair.<br>"
                   "<b>Key space:</b> 676! — and single-letter frequencies are hidden; only pair frequencies leak.")
    crack_hint = ("No automatic cracker: the key has 676 entries, so an attack needs digram frequency analysis "
                  "on a very long ciphertext (thousands of letters). Playfair and Hill are digraph ciphers with "
                  "much smaller keys, which is why they can be cracked here.")
    crackable = False
    help = """## Idea
**Higher-order substitution** replaces **blocks of letters** instead of single letters, so it is a simple *block cipher*. With blocks of two letters (digrams), the key is a table of all 26 × 26 = 676 pairs. From the lecture:

| plain | cipher |
|---|---|
| aa | DS |
| ab | CG |
| ac | HH |
| … | … |

## Key
Nobody types 676 pairs, so the key has two parts:
- **Fixed pairs:** entries you choose, e.g. `AA=DS AB=CG AC=HH` (the lecture's rows).
- **Keyword:** shuffles the remaining cipher pairs onto the remaining plain pairs. The same keyword always gives the same table.

The table is a permutation: every cipher pair is used exactly once, so decryption is unique.

## Steps
1. Split the text into pairs; add the **filler** (X) if the last pair has one letter.
2. **Encrypt:** for each pair, take row = 1st letter and column = 2nd letter; the cell is the cipher pair.
3. **Decrypt:** find the cipher pair in the table; its row and column headers are the plain pair.

## Security
Single-letter frequencies are hidden, but each pair is always encrypted the same way, so **pair frequencies** (TH, HE, IN…) still leak. That needs much more ciphertext than letter frequency analysis. Playfair and Hill are digraph ciphers too, with keys small enough to remember.
"""
    params = [
        Param("fixed", "Fixed pairs", "text", DEFAULT_FIXED,
              help="Plain pair = cipher pair entries, e.g. AA=DS AB=CG; every other pair comes from the keyword"),
        Param("key", "Keyword", "text", DEFAULT_KEY, help="Shuffles the pairs that are not fixed",
              random=lambda n: "".join(random.choices(ALPHABET, k=8))),
        Param("filler", "Filler letter", "text", "X", help="Completes an odd last pair"),
    ]
    examples = [
        {"label": "Encrypt: lecture pairs (aa ab ac)", "mode": "encrypt", "text": "aa ab ac", "params": {}},
        {"label": "Encrypt: odd length gets a filler", "mode": "encrypt", "text": "attack at dawn", "params": {}},
        {"label": "Encrypt: keyword SECRET", "mode": "encrypt", "text": "meet me at the usual place",
         "params": {"key": "SECRET"}},
        {"label": "Decrypt: lecture pairs", "mode": "decrypt", "text": "DSCGHH", "params": {}},
    ]

    def encrypt(self, letters, fixed=DEFAULT_FIXED, key=DEFAULT_KEY, filler="X", **_):
        table = build_table(fixed, key)
        if len(letters) % 2:
            letters += _filler(filler)
        return "".join(table[p] for p in chunks(letters, 2))

    def decrypt(self, letters, fixed=DEFAULT_FIXED, key=DEFAULT_KEY, **_):
        if len(letters) % 2:
            raise CipherError("Digraph ciphertext must have an even number of letters (it is made of pairs).")
        inv = inverse_table(fixed, key)
        return "".join(inv[c] for c in chunks(letters, 2))

    def trace(self, letters, mode, fixed=DEFAULT_FIXED, key=DEFAULT_KEY, filler="X", **_):
        enc = mode == "encrypt"
        table = build_table(fixed, key)
        fixed_pairs = set(parse_fixed(fixed))
        notes: list[str] = []
        src = limit(letters, notes)
        if not enc and len(src) % 2:
            if len(src) == len(letters):
                raise CipherError("Digraph ciphertext must have an even number of letters (it is made of pairs).")
            src = src[:-1]
        padded = enc and len(src) % 2 == 1
        text = src + _filler(filler) if padded else src
        pairs = chunks(text, 2)
        out_pairs = chunks(self.encrypt(text, fixed, key) if enc else self.decrypt(text, fixed, key), 2)
        out = "".join(out_pairs)
        a, b = ("P.T pairs", "C.T pairs") if enc else ("C.T pairs", "P.T pairs")
        LM = 84
        fill = {len(pairs) - 1} if padded else set()
        rows_in = [Row(a, pairs, "input", given=True, id="in")]
        rows_out = [Row(b, out_pairs, "result", id="out")]

        def scene(i, r=None, c=None):
            return [[stream_grid(rows_in, i, filler=fill, label_min=LM)],
                    [stream_grid(rows_out, i, label_min=LM)],
                    [table_grid(table, fixed_pairs, r, c, enc)]]

        f = _filler(filler)
        split = (f"Split the text into blocks of two letters: {' '.join(pairs)}"
                 + (f"\nThe last block had one letter, so the filler {f} was added." if padded else ""))
        steps = [Step("Split into pairs", split,
                      [[letters_grid(text, "lt", "Letters", "input", {len(text) - 1: "filler"} if padded else None)],
                       [stream_grid(rows_in, None, filler=fill, label_min=LM)]],
                      fan(((f"lt{j}", f"in{j // 2}") for j in range(len(text))), 0, "pair up"))]
        fx = ", ".join(f"{p}→{table[p]}" for p in sorted(fixed_pairs)) or "none"
        steps.append(Step("The key is a table of all 676 pairs",
                          f"Row = first letter, column = second letter, cell = cipher pair.\nFixed pairs (amber): {fx}. "
                          f"Every other pair was assigned by shuffling with the keyword “{clean(key)}”.\n"
                          + ("Encrypt: row of the 1st letter, column of the 2nd → the cell." if enc else
                             "Decrypt: find the cipher pair in the table → its row and column headers."),
                          scene(-1)))
        for i, (p, o) in enumerate(zip(pairs, out_pairs)):
            plain = p if enc else o
            r, c = ALPHABET.index(plain[0]), ALPHABET.index(plain[1])
            cell = f"d{r}_{c}"
            if enc:
                how = (f"① row {p[0]}, column {p[1]}\n② the cell where they cross holds {o}\n③ write {o}")
                arrows = [Arrow(f"in{i}", f"dr{r}", f"row {p[0]}", 0), Arrow(f"in{i}", f"dc{c}", f"column {p[1]}", 0),
                          Arrow(f"dr{r}", cell, "", 1, kind="key", curve="straight"),
                          Arrow(f"dc{c}", cell, "", 1, kind="key", curve="straight"),
                          Arrow(cell, f"out{i}", f"= {o}", 2, reveal=True, kind="result")]
            else:
                how = (f"① find the cipher pair {p} in the table\n② its row header is {plain[0]} and its column "
                       f"header is {plain[1]}\n③ write {o}")
                arrows = [Arrow(f"in{i}", cell, f"find {p}", 0),
                          Arrow(cell, f"dr{r}", f"row {plain[0]}", 1, kind="key", curve="straight"),
                          Arrow(cell, f"dc{c}", f"column {plain[1]}", 1, kind="key", curve="straight"),
                          Arrow(f"dr{r}", f"out{i}", f"= {o}", 2, carry=o, reveal=True, kind="result")]
            steps.append(Step(f"Pair {i + 1}/{len(pairs)}: {p} → {o}", how, scene(i, r, c), arrows))
        steps.append(Step("Done", f"Result: {out}" + ("\nThe last letter is the filler; drop it after decrypting."
                                                      if padded else ""), scene(None)))
        return Trace(steps, out, notes)
