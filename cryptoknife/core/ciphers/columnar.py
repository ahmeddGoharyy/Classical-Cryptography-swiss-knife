"""Columnar transposition: write in rows under the key, read columns in key order."""
from __future__ import annotations

import itertools
import math
import random
import re
import time

import numpy as np

from ..analysis import get_scorer
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import CipherError, clean
from ..trace import Arrow, Cell, Grid, Row, Step, Trace, fan, letters_grid, limit, stream_grid


def parse_key(key: str) -> tuple[list[int], str]:
    """Return (rank of each column, 1-based; display labels). Accepts '4 3 1 2 5 6 7', '4312567' or a keyword."""
    k = key.strip()
    if re.fullmatch(r"[\d\s,;-]+", k):
        nums = [int(x) for x in re.findall(r"\d+", k)] if re.search(r"[\s,;-]", k) else [int(c) for c in k]
        if sorted(nums) == list(range(len(nums))):
            nums = [x + 1 for x in nums]
        if sorted(nums) != list(range(1, len(nums) + 1)):
            raise CipherError("A numeric key must be a permutation of 1..n (e.g. 4 3 1 2 5 6 7).")
        return nums, " ".join(map(str, nums))
    word = clean(k)
    if not word:
        raise CipherError("Enter a keyword or a numeric order like 4 3 1 2 5 6 7.")
    order = sorted(range(len(word)), key=lambda i: (word[i], i))
    ranks = [0] * len(word)
    for r, i in enumerate(order, 1):
        ranks[i] = r
    return ranks, word


def col_lengths(n: int, L: int) -> list[int]:
    rows, rem = divmod(n, L)
    return [rows + (1 if j < rem else 0) for j in range(L)]


def encrypt_once(t: str, ranks: list[int]) -> str:
    L = len(ranks)
    return "".join(t[ranks.index(r)::L] for r in range(1, L + 1))


def decrypt_once(t: str, ranks: list[int]) -> str:
    L = len(ranks)
    lens = col_lengths(len(t), L)
    cols, pos = [""] * L, 0
    for r in range(1, L + 1):
        j = ranks.index(r)
        cols[j] = t[pos:pos + lens[j]]
        pos += lens[j]
    return "".join(cols[j][i] for i in range(max(lens)) for j in range(L) if i < len(cols[j]))


def decrypt_index(n: int, ranks: list[int]) -> list[int]:
    """Index map so that plaintext = [ct[i] for i in map]."""
    L = len(ranks)
    lens = col_lengths(n, L)
    start, pos = [0] * L, 0
    for r in range(1, L + 1):
        j = ranks.index(r)
        start[j] = pos
        pos += lens[j]
    return [start[j] + i for i in range(max(lens)) for j in range(L) if i < lens[j]]


@register
class Columnar(Cipher):
    id = "columnar"
    name = "Columnar transposition"
    family = "Transposition"
    order = 10
    preserves_layout = False
    summary = "Write the message in rows under a key; read the columns in key order."
    description = ("Write the plaintext row by row in a table whose width is the key length, then read the "
                   "columns top-to-bottom in the order given by the key (a numeric order like 4 3 1 2 5 6 7, or "
                   "a keyword whose letters are ranked alphabetically). Letters are only rearranged, so letter "
                   "frequencies stay exactly English. Two rounds = double transposition.")
    crack_hint = ("Try every column order for short keys (≤ 8) and hill-climb longer ones, scoring each "
                  "candidate with English quadgrams.")
    help = """## Idea
A **transposition**: letters are rearranged, not replaced. Write the message in rows under the key, then read the **columns** in key order.

## Key
- Numbers: `4 3 1 2 5 6 7` (the column labelled 1 is read first)
- or a keyword: letters ranked alphabetically, ties left to right. `ZEBRAS` → 6 3 2 4 1 5

## Steps
- **Encrypt:** fill the table row by row (optionally pad the last row with X), read columns in key order.
- **Decrypt:** work out each column's length, fill columns in key order, read rows.
- **Double transposition:** apply it twice (Rounds = 2).

## Tell-tale sign
Letter frequencies stay **exactly** like English.
"""
    key_help = """## Key shape
A **column order**: numbers (`4 3 1 2 5 6 7`), or a **keyword** whose alphabetical order gives the numbers (`ZEBRAS` → 6 3 2 4 1 5).

## Key space
**L!** orders for L columns, e.g. 40,320 for 8 columns.

## Weaknesses
- Letters move but never change: **frequencies match English exactly**, which gives away that it is a transposition.
- Short keys are brute-forced; matching adjacent columns (anagramming) finds longer ones.
"""
    params = [
        Param("key", "Key", "text", "4 3 1 2 5 6 7",
              help="e.g. 4 3 1 2 5 6 7 or ZEBRAS",
              random=lambda n: " ".join(map(str, random.sample(range(1, 7), 6)))),
        Param("pad", "Pad the last row", "bool", True),
        Param("filler", "Padding letter", "text", "X"),
        Param("rounds", "Rounds", "int", 1, minimum=1, maximum=3, help="2 = double transposition"),
    ]
    crack_params = [Param("max_len", "Max key length", "int", 8, minimum=2, maximum=12),
                    Param("seconds", "Time limit (s)", "int", 30, minimum=5, maximum=300)]
    examples = [
        {"label": 'Encrypt: key 4 3 1 2 5 6 7', "mode": 'encrypt', "text": 'attack postponed until two am xyz', "params": {'key': '4 3 1 2 5 6 7', 'pad': True, 'rounds': 1}},
        {"label": 'Encrypt: keyword ZEBRAS, no padding', "mode": 'encrypt', "text": 'we are discovered flee at once', "params": {'key': 'ZEBRAS', 'pad': False, 'rounds': 1}},
        {"label": 'Encrypt: double transposition', "mode": 'encrypt', "text": 'attack postponed until two am', "params": {'key': '4 3 1 2 5 6 7', 'rounds': 2}},
        {"label": 'Decrypt: keyword CIPHER', "mode": 'decrypt', "text": 'TMAAINLCDXEIAITHYTTGEWTMHELKNX', "params": {'key': 'CIPHER', 'pad': True, 'rounds': 1}},
    ]

    @staticmethod
    def _pad(t: str, L: int, pad: bool, filler: str) -> str:
        return t + (clean(filler) or "X")[0] * (-len(t) % L) if pad else t

    def encrypt(self, letters, key="", pad=True, filler="X", rounds=1, **_):
        ranks, _ = parse_key(key)
        t = letters
        for _r in range(int(rounds)):
            t = encrypt_once(self._pad(t, len(ranks), pad, filler), ranks)
        return t

    def decrypt(self, letters, key="", pad=True, filler="X", rounds=1, **_):
        ranks, _ = parse_key(key)
        t = letters
        for _r in range(int(rounds)):
            t = decrypt_once(t, ranks)
        return t

    @staticmethod
    def _table(text: str, ranks: list[int], labels: list[str], filled: set[int], hl_col: int | None = None,
               hl_row: int | None = None, fill: set[int] | None = None) -> Grid:
        """Transposition table; body cell for text index k has id f"c{k}", rank headers f"rk{j}"."""
        L = len(ranks)
        lens = col_lengths(len(text), L)
        rows = max(lens)
        cells = [[Cell(lb, "key" if j == hl_col else "header") for j, lb in enumerate(labels)]] if any(labels) else []
        cells.append([Cell(str(r), "active" if j == hl_col else "header", "", f"rk{j}") for j, r in enumerate(ranks)])
        for i in range(rows):
            line = []
            for j in range(L):
                k = i * L + j
                if i >= lens[j]:
                    line.append(Cell("", "dim"))
                elif k not in filled:
                    line.append(Cell("", "empty", "", f"c{k}"))
                else:
                    st = "filler" if fill and k in fill else "normal"
                    if j == hl_col or i == hl_row:
                        st = "current"
                    line.append(Cell(text[k], st, "", f"c{k}"))
            cells.append(line)
        return Grid(cells, "Transposition table")

    def trace(self, letters, mode, key="", pad=True, filler="X", rounds=1, **_):
        enc = mode == "encrypt"
        ranks, label = parse_key(key)
        L = len(ranks)
        labels = list(label.replace(" ", "")) if not label[0].isdigit() else [""] * L
        notes: list[str] = []
        t = limit(letters, notes)
        steps = []
        order_txt = ", ".join(f"col {ranks.index(r) + 1}" for r in range(1, L + 1))
        key_grid = Grid([[Cell(lb, "key", "", f"kl{j}") for j, lb in enumerate(labels)]] if any(labels) else []
                        + [[Cell(str(r), "header", "", f"kr{j}") for j, r in enumerate(ranks)]], "Key")
        if any(labels):
            key_grid = Grid([[Cell(lb, "key", "", f"kl{j}") for j, lb in enumerate(labels)],
                             [Cell(str(r), "header", "", f"kr{j}") for j, r in enumerate(ranks)]], "Key → read order")
            steps.append(Step("Key order", f"Keyword {label}: rank its letters alphabetically (ties left to right) "
                              f"→ {ranks}.\nRead order: {order_txt}.", [[key_grid]],
                              [Arrow(f"kl{ranks.index(r)}", f"kr{ranks.index(r)}", "1st" if r == 1 else "", r - 1,
                                     carry=str(r), reveal=True, kind="key") for r in range(1, L + 1)]))
        else:
            steps.append(Step("Key order", f"Key {label}: the number above each column is its reading rank.\n"
                              f"Read order: {order_txt}.", [[key_grid]]))
        for rnd in range(int(rounds)):
            tag = f"Round {rnd + 1}: " if int(rounds) > 1 else ""
            if enc:
                src = self._pad(t, L, pad, filler)
                fill = set(range(len(t), len(src)))
                out = encrypt_once(src, ranks)
                n_rows = math.ceil(len(src) / L)
                in_grid = letters_grid(src, "in", "P.T" + (" (padded)" if fill else ""), "input",
                                       {k: "filler" for k in fill})
                rows_out = [Row("C.T", list(out), "result", id="out")]
                for i in range(n_rows):
                    seg = range(i * L, min(len(src), (i + 1) * L))
                    filled = set(range(min(len(src), (i + 1) * L)))
                    steps.append(Step(f"{tag}Write row {i + 1}/{n_rows}",
                                      f"The next {len(seg)} letters “{src[i * L:(i + 1) * L]}” go left to right "
                                      f"into row {i + 1}" + (" (padding highlighted)." if fill & set(seg) else "."),
                                      [[in_grid], [self._table(src, ranks, labels, filled, hl_row=i, fill=fill)],
                                       [stream_grid(rows_out, -1)]],
                                      fan(((f"in{k}", f"c{k}") for k in seg), 0, f"row {i + 1}")))
                pos = 0
                lens = col_lengths(len(src), L)
                for r in range(1, L + 1):
                    j = ranks.index(r)
                    seg = src[j::L]
                    ks = [i * L + j for i in range(lens[j])]
                    steps.append(Step(f"{tag}Read column ranked {r}",
                                      f"Column {j + 1} has rank {r}: read it top to bottom → “{seg}” and append it "
                                      "to the ciphertext.",
                                      [[in_grid], [self._table(src, ranks, labels, set(range(len(src))), hl_col=j,
                                                               fill=fill)],
                                       [stream_grid(rows_out, pos + lens[j] - 1)]],
                                      [Arrow(f"rk{j}", f"c{ks[0]}", f"rank {r}", 0, kind="key") for _ in ks[:1]]
                                      + fan(((f"c{k}", f"out{pos + q}") for q, k in enumerate(ks)), 1,
                                            "top → bottom", "result")))
                    pos += lens[j]
                t = out
            else:
                lens = col_lengths(len(t), L)
                out = decrypt_once(t, ranks)
                in_grid = letters_grid(t, "in", "C.T", "input")
                steps.append(Step(f"{tag}Column lengths",
                                  f"{len(t)} letters / {L} columns → {math.ceil(len(t) / L)} rows; column lengths "
                                  f"{lens} (the first {len(t) % L or L} columns are full).",
                                  [[in_grid], [self._table(out, ranks, labels, set())]]))
                filled: set[int] = set()
                pos = 0
                for r in range(1, L + 1):
                    j = ranks.index(r)
                    ks = [i * L + j for i in range(lens[j])]
                    seg = t[pos:pos + lens[j]]
                    filled |= set(ks)
                    steps.append(Step(f"{tag}Fill column ranked {r}",
                                      f"The next {lens[j]} ciphertext letters “{seg}” go down column {j + 1} "
                                      f"(rank {r}).",
                                      [[in_grid], [self._table(out, ranks, labels, set(filled), hl_col=j)]],
                                      [Arrow(f"rk{j}", f"c{ks[0]}", f"rank {r}", 0, kind="key") for _ in ks[:1]]
                                      + fan(((f"in{pos + q}", f"c{k}") for q, k in enumerate(ks)), 1, "top → bottom")))
                    pos += lens[j]
                rows_out = [Row("P.T", list(out), "result", id="out")]
                for i in range(math.ceil(len(t) / L)):
                    seg = range(i * L, min(len(out), (i + 1) * L))
                    steps.append(Step(f"{tag}Read row {i + 1}", f"Row {i + 1} left to right: "
                                      f"{out[i * L:(i + 1) * L]}",
                                      [[in_grid], [self._table(out, ranks, labels, set(range(len(out))), hl_row=i)],
                                       [stream_grid(rows_out, min(len(out), (i + 1) * L) - 1)]],
                                      fan(((f"c{k}", f"out{k}") for k in seg), 0, f"row {i + 1}", "result")))
                t = out
        steps.append(Step("Done", f"Result: {t}", [[letters_grid(t, "res", "Result", "result")]]))
        return Trace(steps, t, notes)

    # ----- cracking ---------------------------------------------------------------------------
    def crack(self, letters, ctx, max_len=8, seconds=30, **_):
        n = len(letters)
        if n < 10:
            raise CipherError("Need at least 10 letters.")
        sc = get_scorer()
        res = CrackResult()
        ct = np.frombuffer(letters.encode(), dtype=np.uint8).astype(np.int64) - 65
        deadline = time.monotonic() + int(seconds)
        best: dict[int, tuple[float, list[int]]] = {}
        max_len = min(int(max_len), n - 1)
        res.log.append("Transposition keeps letter frequencies — check: the ciphertext letters should look like "
                       "English already. Now search column orders, scoring each candidate with quadgrams.\n")

        def score(ranks):
            return sc.score_nums(ct[decrypt_index(n, ranks)])

        for L in range(2, max_len + 1):
            if ctx.cancelled or time.monotonic() > deadline:
                break
            ctx.progress((L - 2) / max(1, max_len - 1), f"key length {L}")
            if L <= 8 and math.factorial(L) <= 40320:
                top = (-1e18, None)
                for i, perm in enumerate(itertools.permutations(range(1, L + 1))):
                    if i % 2000 == 0 and (ctx.cancelled or time.monotonic() > deadline):
                        break
                    s = score(list(perm))
                    if s > top[0]:
                        top = (s, list(perm))
                method = f"all {math.factorial(L)} orders"
            else:
                rng = random.Random(L)
                top = (-1e18, None)
                for _rs in range(20):
                    cur = rng.sample(range(1, L + 1), L)
                    cs = score(cur)
                    improved = True
                    while improved and time.monotonic() < deadline:
                        improved = False
                        for a, b in itertools.combinations(range(L), 2):
                            cur[a], cur[b] = cur[b], cur[a]
                            s = score(cur)
                            if s > cs:
                                cs, improved = s, True
                            else:
                                cur[a], cur[b] = cur[b], cur[a]
                    if cs > top[0]:
                        top = (cs, cur[:])
                method = "hill climbing"
            if top[1]:
                best[L] = top
                pt = decrypt_once(letters, top[1])
                res.log.append(f"  L = {L:>2} ({method}): best order {' '.join(map(str, top[1]))} → {pt[:45]}")
        for L, (s, ranks) in sorted(best.items(), key=lambda kv: -kv[1][0] / max(1, n - 3)):
            pt = decrypt_once(letters, ranks)
            key = " ".join(map(str, ranks))
            res.candidates.append(Candidate(key, {"key": key, "rounds": 1}, pt, sc.english_likeness(pt), f"L = {L}"))
        if res.candidates:
            res.log.append(f"\nBest: key {res.candidates[0].key}")
        return res
