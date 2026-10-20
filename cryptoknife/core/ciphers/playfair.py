"""Playfair: digraph substitution with a 5×5 key square (I and J share a cell)."""
from __future__ import annotations

import math
import random
import time

import numpy as np

from ..analysis import get_scorer, nums_array
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import CipherError, clean, keyed_alphabet, unique_letters
from ..trace import Arrow, Cell, Grid, Row, Step, Trace, fan, letters_grid, limit, stream_grid

SQUARE_ALPHABET = "ABCDEFGHIKLMNOPQRSTUVWXYZ"  # no J


def build_square(keyword: str) -> str:
    return keyed_alphabet(clean(keyword).replace("J", "I"), SQUARE_ALPHABET)


def prepare(letters: str, filler: str = "X") -> tuple[list[str], set[int]]:
    """Split into digrams: J→I, a filler between doubled letters in a pair, and at the end if odd.

    Returns (pairs, indices of filler letters in the joined digram string).
    """
    f = (clean(filler) or "X")[0].replace("J", "I")
    alt = "Q" if f != "Q" else "Z"
    t = letters.replace("J", "I")
    pairs, fill, i = [], set(), 0
    while i < len(t):
        a = t[i]
        b = t[i + 1] if i + 1 < len(t) else None
        if b is None or a == b:
            pad = f if a != f else alt
            fill.add(2 * len(pairs) + 1)
            pairs.append(a + pad)
            i += 1
        else:
            pairs.append(a + b)
            i += 2
    return pairs, fill


def _rule(sq: str, a: str, b: str, enc: bool) -> tuple[str, str, str]:
    ra, ca = divmod(sq.index(a), 5)
    rb, cb = divmod(sq.index(b), 5)
    d = 1 if enc else -1
    if ra == rb:
        return sq[ra * 5 + (ca + d) % 5] + sq[rb * 5 + (cb + d) % 5], "row", \
            f"same row → take the letter to the {'right' if enc else 'left'} of each (wrapping around)"
    if ca == cb:
        return sq[((ra + d) % 5) * 5 + ca] + sq[((rb + d) % 5) * 5 + cb], "col", \
            f"same column → take the letter {'below' if enc else 'above'} each (wrapping around)"
    return sq[ra * 5 + cb] + sq[rb * 5 + ca], "rect", \
        "rectangle → each letter is replaced by the one in its own row and the other letter's column"


def square_grid(sq: str, inp: str = "", out: str = "", kind: str = "", kw_len: int = 0, title="Key square",
                hidden: set[str] | None = None) -> Grid:
    pos = {c: divmod(i, 5) for i, c in enumerate(sq)}
    lane: set[tuple[int, int]] = set()
    if inp:
        (ra, ca), (rb, cb) = pos[inp[0]], pos[inp[1]]
        if kind == "row":
            lane = {(ra, c) for c in range(5)}
        elif kind == "col":
            lane = {(r, ca) for r in range(5)}
        elif kind == "rect":
            lane = {(r, c) for r in range(min(ra, rb), max(ra, rb) + 1) for c in range(min(ca, cb), max(ca, cb) + 1)}
    cells = []
    for r in range(5):
        row = []
        for c in range(5):
            ch = sq[r * 5 + c]
            st = "key" if r * 5 + c < kw_len else "normal"
            if hidden and ch in hidden:
                row.append(Cell("", "empty", "", f"sq{ch}"))
                continue
            if (r, c) in lane:
                st = "hl"
            if ch in out:
                st = "current"
            if ch in inp:
                st = "active"
            row.append(Cell("I/J" if ch == "I" else ch, st, "", f"sq{ch}"))
        cells.append(row)
    return Grid(cells, title)


@register
class Playfair(Cipher):
    id = "playfair"
    name = "Playfair"
    family = "Polygraphic substitution"
    order = 10
    preserves_layout = False
    summary = "Encrypt letter pairs using a 5×5 keyword square."
    description = ("Build a 5×5 square from the keyword (duplicates removed, I and J share a cell), then fill "
                   "with the rest of the alphabet. Split the plaintext into pairs, inserting a filler (X) between "
                   "repeated letters and at the end if needed. For each pair: <b>same row</b> → letters to the "
                   "right; <b>same column</b> → letters below; otherwise <b>rectangle</b> → swap columns. "
                   "Decryption goes left / up.")
    crack_hint = ("Simulated annealing over key squares scored with English quadgrams. Needs a long "
                  "ciphertext (≈200+ letters) and some time; results are stochastic.")
    help = """## Idea
Encrypt **pairs of letters** (digrams) with a 5 × 5 key square.

## Key square
Write the keyword's letters (no duplicates, **J = I**) row by row, then the rest of the alphabet. Keyword `MONARCHY`:
```
M O N A R
C H Y B D
E F G I K
L P Q S T
U V W X Z
```

## Preparing the text
1. Replace J with I.
2. Split into pairs; if a pair would be two identical letters, insert the filler **X** between them.
3. Pad a final single letter with X.

## Rules for each pair
| Case | Encrypt | Decrypt |
|---|---|---|
| Same row | letter to the **right** | letter to the **left** |
| Same column | letter **below** | letter **above** |
| Rectangle | same row, **other letter's column** | same |

All moves wrap around the square.

## Example
`balloon` → BA LX LO ON → `IBSUPMNA`
"""
    params = [
        Param("key", "Keyword", "text", "MONARCHY", help="Keyword for the 5×5 square",
              random=lambda n: "".join(random.sample(SQUARE_ALPHABET, 25))),
        Param("filler", "Filler letter", "text", "X", help="Inserted between doubled letters and at the end"),
        Param("strip", "Remove fillers when decrypting", "bool", False,
              help="Drop X between identical letters and a trailing X"),
    ]
    crack_params = [Param("seconds", "Time limit (s)", "int", 120, minimum=5, maximum=600)]
    examples = [
        {"label": 'Encrypt: instruments (key MONARCHY)', "mode": 'encrypt', "text": 'instruments', "params": {'key': 'MONARCHY'}},
        {"label": 'Encrypt: balloon — doubled letters', "mode": 'encrypt', "text": 'balloon', "params": {'key': 'MONARCHY'}},
        {"label": 'Encrypt: hide the gold… (key PLAYFAIR EXAMPLE)', "mode": 'encrypt', "text": 'hide the gold in the tree stump', "params": {'key': 'playfair example'}},
        {"label": 'Decrypt: key KEYWORD', "mode": 'decrypt', "text": 'NKKUNKRVVFWDBFGNWU', "params": {'key': 'KEYWORD', 'strip': True}},
    ]

    def encrypt(self, letters, key="MONARCHY", filler="X", **_):
        sq = build_square(key)
        pairs, _ = prepare(letters, filler)
        return "".join(_rule(sq, p[0], p[1], True)[0] for p in pairs)

    def decrypt(self, letters, key="MONARCHY", filler="X", strip=False, **_):
        sq = build_square(key)
        t = letters.replace("J", "I")
        if len(t) % 2:
            raise CipherError("Playfair ciphertext must have an even number of letters.")
        pairs = [t[i:i + 2] for i in range(0, len(t), 2)]
        for p in pairs:
            if p[0] == p[1]:
                raise CipherError(f"Invalid ciphertext pair “{p}”: Playfair never produces a doubled pair.")
        out = "".join(_rule(sq, p[0], p[1], False)[0] for p in pairs)
        return self.strip_fillers(out, filler) if strip else out

    @staticmethod
    def strip_fillers(text: str, filler: str = "X") -> str:
        f = (clean(filler) or "X")[0]
        out = [c for i, c in enumerate(text)
               if not (c == f and i % 2 == 1 and 0 < i < len(text) - 1 and text[i - 1] == text[i + 1])]
        if out and out[-1] == f:
            out.pop()
        return "".join(out)

    def trace(self, letters, mode, key="MONARCHY", filler="X", strip=False, **_):
        enc = mode == "encrypt"
        notes: list[str] = []
        src = limit(letters, notes)
        if not enc and len(src) % 2:
            src = src[:-1]
        sq = build_square(key)
        raw_kw = clean(key).replace("J", "I")
        kw = unique_letters(raw_kw)
        rest = [c for c in SQUARE_ALPHABET if c not in kw]
        steps = []
        # ---- 1. keyword into the square
        dup = {j for j, c in enumerate(raw_kw) if c in raw_kw[:j]}
        kw_grid = letters_grid(raw_kw[:30], "kw", "Keyword (duplicates skipped)", "key", {j: "dim" for j in dup})
        first = {}
        for j, c in enumerate(raw_kw):
            first.setdefault(c, j)
        steps.append(Step("Write the keyword into the square",
                          f"Keyword “{clean(key)}” → unique letters {kw} (J counts as I, repeated letters are "
                          "skipped). They fill the square row by row.",
                          [[kw_grid], [square_grid(sq, kw_len=len(kw), hidden=set(rest))]],
                          [Arrow(f"kw{first[c]}", f"sq{c}", "", k // 3, reveal=True, kind="key")
                           for k, c in enumerate(kw) if first[c] < 30]))
        # ---- 2. rest of the alphabet
        alpha_grid = letters_grid(SQUARE_ALPHABET, "ab", "Alphabet without J", "normal",
                                  {j: "dim" for j, c in enumerate(SQUARE_ALPHABET) if c in kw})
        steps.append(Step("Fill in the rest of the alphabet",
                          f"The remaining letters {''.join(rest)} fill the empty cells in alphabetical order.",
                          [[alpha_grid], [square_grid(sq, kw_len=len(kw))]],
                          fan(((f"ab{SQUARE_ALPHABET.index(c)}", f"sq{c}") for c in rest), 0, "in order")))
        # ---- 3. digrams
        if enc:
            pairs, fill = prepare(src, filler)
        else:
            t = src.replace("J", "I")
            pairs, fill = [t[i:i + 2] for i in range(0, len(t), 2)], set()
        joined = "".join(pairs)
        if enc:
            mapping, i_src = [], 0  # prepared index -> source index (None for fillers)
            for j, c in enumerate(joined):
                if j in fill:
                    mapping.append(None)
                else:
                    mapping.append(i_src)
                    i_src += 1
            prep = letters_grid(joined, "pr", "Digrams (fillers highlighted)", "input",
                                {j: "filler" for j in fill})
            steps.append(Step("Split the text into pairs",
                              f"J → I. Split into pairs; a doubled letter inside a pair gets the filler "
                              f"{filler or 'X'} between them, and an odd last letter is padded.\n{' '.join(pairs)}",
                              [[letters_grid(src.replace('J', 'I'), "raw", "Plaintext", "input")], [prep]],
                              fan(((f"raw{m}", f"pr{j}") for j, m in enumerate(mapping) if m is not None), 0,
                                  "keep order")))
        outs, kinds, whys = [], [], []
        for p in pairs:
            o, kind, why = _rule(sq, p[0], p[1], enc)
            outs.append(o)
            kinds.append(kind)
            whys.append(why)
        a, b = ("P.T pairs", "C.T pairs") if enc else ("C.T pairs", "P.T pairs")
        rows_in = [Row(a, pairs, "input", given=True, id="pin")]
        rows_out = [Row(b, outs, "result", id="pout")]
        short = {"row": ("→ right" if enc else "← left"), "col": ("↓ below" if enc else "↑ above"),
                 "rect": "swap columns"}
        for i, (p, o) in enumerate(zip(pairs, outs)):
            arrows = [Arrow(f"pin{i}", f"sq{p[0]}", "locate", 0, carry=p[0]),
                      Arrow(f"pin{i}", f"sq{p[1]}", "", 0, carry=p[1]),
                      Arrow(f"sq{p[0]}", f"sq{o[0]}", short[kinds[i]], 1, kind="key",
                            curve="auto" if kinds[i] == "rect" else "straight"),
                      Arrow(f"sq{p[1]}", f"sq{o[1]}", "", 1, kind="key",
                            curve="auto" if kinds[i] == "rect" else "straight"),
                      Arrow(f"sq{o[0]}", f"pout{i}", "write", 2, reveal=True, kind="result"),
                      Arrow(f"sq{o[1]}", f"pout{i}", "", 2, reveal=True, kind="result")]
            steps.append(Step(f"Pair {i + 1}/{len(pairs)}: {p} → {o}",
                              f"① locate {p[0]} and {p[1]} in the square\n② {whys[i]}\n③ write {o}",
                              [[stream_grid(rows_in, i, label_min=90)], [square_grid(sq, p, o, kinds[i], len(kw))],
                               [stream_grid(rows_out, i, label_min=90)]], arrows))
        result = "".join(outs)
        if not enc and strip:
            result = self.strip_fillers(result, filler)
        steps.append(Step("Done", f"Result: {result}" + ("" if enc else
                          "\n(Fillers stay in the decrypted text unless “Remove fillers” is on.)"),
                          [[stream_grid(rows_in, None, label_min=90)], [square_grid(sq, kw_len=len(kw))],
                           [stream_grid(rows_out, None, label_min=90)]]))
        return Trace(steps, result, notes)

    # ----- cracking ---------------------------------------------------------------------------
    def crack(self, letters, ctx, seconds=120, **_):
        t = letters.replace("J", "I")
        if len(t) % 2:
            t = t[:-1]
        if len(t) < 40:
            raise CipherError("Need at least 40 letters (≈200+ for reliable results).")
        sc = get_scorer()
        res = CrackResult()
        ct = nums_array(t)
        a, b = ct[0::2], ct[1::2]
        n = len(t)
        sq_letters = np.array([ord(c) - 65 for c in SQUARE_ALPHABET])

        def decrypt_np(sq: np.ndarray) -> np.ndarray:
            pos = np.empty(26, dtype=np.int64)
            pos[sq] = np.arange(25)
            pos[9] = pos[8]  # J → I
            ra, ca = np.divmod(pos[a], 5)
            rb, cb = np.divmod(pos[b], 5)
            same_r, same_c = ra == rb, ca == cb
            ar = np.where(same_c & ~same_r, (ra - 1) % 5, ra)
            br = np.where(same_c & ~same_r, (rb - 1) % 5, rb)
            ac = np.where(same_r, (ca - 1) % 5, np.where(same_c, ca, cb))
            bc = np.where(same_r, (cb - 1) % 5, np.where(same_c, cb, ca))
            out = np.empty(n, dtype=np.int64)
            out[0::2] = sq[ar * 5 + ac]
            out[1::2] = sq[br * 5 + bc]
            return out

        def mutate(sq: np.ndarray, rng: random.Random) -> np.ndarray:
            k = sq.copy()
            r = rng.random()
            if r < 0.9:
                i, j = rng.sample(range(25), 2)
                k[i], k[j] = k[j], k[i]
            elif r < 0.93:
                i, j = rng.sample(range(5), 2)
                g = k.reshape(5, 5)
                g[[i, j]] = g[[j, i]]
            elif r < 0.96:
                i, j = rng.sample(range(5), 2)
                g = k.reshape(5, 5)
                g[:, [i, j]] = g[:, [j, i]]
            elif r < 0.98:
                k = k.reshape(5, 5)[::-1].ravel().copy()
            else:
                k = k.reshape(5, 5)[:, ::-1].ravel().copy()
            return k

        res.log.append("Simulated annealing: start with a random square, make small changes (swap two letters, "
                       "swap rows/columns, flip). Always accept improvements; accept worse squares with "
                       "probability e^(Δ/T) so the search can escape local maxima. T slowly decreases.\n")
        rng = random.Random()
        deadline = time.monotonic() + int(seconds)
        best_key, best_score = None, -1e18
        restart = 0
        start = time.monotonic()
        while time.monotonic() < deadline and not ctx.cancelled:
            restart += 1
            parent = np.array(rng.sample(list(sq_letters), 25))
            pscore = sc.score_nums(decrypt_np(parent))
            T = 10 + 0.087 * (n - 84) if n > 84 else 10.0
            while T > 0 and time.monotonic() < deadline and not ctx.cancelled:
                for _ in range(2000):
                    child = mutate(parent, rng)
                    s = sc.score_nums(decrypt_np(child))
                    d = s - pscore
                    if d > 0 or rng.random() < math.exp(d / T):
                        parent, pscore = child, s
                        if s > best_score:
                            best_key, best_score = child.copy(), s
                T -= 0.4
                pt = "".join(chr(65 + x) for x in decrypt_np(best_key))
                ctx.progress((time.monotonic() - start) / int(seconds),
                             f"restart {restart}, T={T:.1f}, best {best_score / (n - 3):.2f}: {pt[:40]}")
            pt = "".join(chr(65 + x) for x in decrypt_np(best_key))
            res.log.append(f"  restart {restart}: best so far {best_score / (n - 3):.3f}/quadgram → {pt[:50]}")
            if sc.english_likeness(pt) > 0.9:
                break
        if best_key is None:
            return res
        key = "".join(chr(65 + x) for x in best_key)
        pt = "".join(chr(65 + x) for x in decrypt_np(best_key))
        res.candidates.append(Candidate(key, {"key": key}, pt, sc.english_likeness(pt), "best square found"))
        res.log.append(f"\nBest square: {key}\nPlaintext (fillers remain): {pt}")
        return res
