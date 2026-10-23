"""Polyalphabetic substitution with the Vigenère tableau: a repeating keyword or an autokey."""
from __future__ import annotations

import random
from functools import lru_cache

from ..analysis.frequency import chi_squared_counts
from ..analysis import ENGLISH_IOC, RANDOM_IOC, best_caesar_shift, get_scorer, kasiski, periodic_ioc
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import ALPHABET, CipherError, require_letters, to_nums, to_text
from ..trace import Arrow, Cell, Chart, Grid, Row, Stack, Step, Trace, fan, letters_grid, limit, stream_grid


@lru_cache(maxsize=2048)  # the same highlighted tableau repeats across steps and runs; grids are never mutated
def tableau(row: int | None = None, col: int | None = None, forward: bool = True) -> Grid:
    """26×26 Vigenère tableau. Row = key letter, column = plaintext letter, cell = ciphertext.

    Cell ids: column headers f"tc{c}", row headers f"tr{r}", body f"t{r}_{c}".
    """
    cells = [[Cell("", "header")] + [Cell(ALPHABET[c], ("active" if forward else "current") if c == col else "header",
                                          "", f"tc{c}") for c in range(26)]]
    for r in range(26):
        line = [Cell(ALPHABET[r], "key" if r == row else "header", "", f"tr{r}")]
        for c in range(26):
            st = "normal"
            if r == row and c == col:
                st = "current" if forward else "active"
            elif row is not None and col is not None and (r == row and c < col or c == col and r < row):
                st = "hl"
            line.append(Cell(ALPHABET[(r + c) % 26], st, "", f"t{r}_{c}"))
        cells.append(line)
    return Grid(cells, "Vigenère tableau (row = key letter, column = plain letter)", compact=True)


REPEATING, AUTOKEY = "Repeating key", "Autokey"
BOTH = "Try both"


@register
class Vigenere(Cipher):
    id = "vigenere"
    name = "Polyalphabetic (Vigenère)"
    family = "Polyalphabetic substitution"
    order = 10
    key_label = "K-stream"
    summary = "Shift each letter by a key letter: the keyword repeats, or (autokey) continues with the plaintext."
    description = ("Polyalphabetic: each letter is shifted by its own key letter using the Vigenère tableau, so "
                   "the same plain letter encrypts differently at different positions.<br>"
                   "<b>Repeating key:</b> the keyword is repeated to the message length. "
                   "<b>Autokey:</b> the keyword is followed by the plaintext itself, so the key never repeats.<br>"
                   "<b>Encrypt:</b> C<sub>i</sub> = (P<sub>i</sub> + K<sub>i</sub>) mod 26 &nbsp; "
                   "<b>Decrypt:</b> P<sub>i</sub> = (C<sub>i</sub> − K<sub>i</sub>) mod 26")
    crack_hint = ("Repeating key: find the key length m (Kasiski examination + index of coincidence); each of the "
                  "m columns is then a Caesar cipher solved by frequency analysis. Autokey: for a guessed keyword "
                  "length m, the chain j, j+m, j+2m… depends only on key letter j, so each is solved by chi². "
                  "\"Try both\" runs both attacks and ranks all results.")
    help = """## Idea
A **polyalphabetic** cipher: every letter is shifted by its own key letter (A = 0 … Z = 25), so the same plain letter becomes different cipher letters. Two ways to make the key stream (**Key mode**):

- **Repeating key:** the keyword is repeated to the length of the message.
- **Autokey:** the keyword is followed by the **plaintext itself**, so the key never repeats.

## Formulas
- **Encrypt:** `Cᵢ = (Pᵢ + Kᵢ) mod 26`
- **Decrypt:** `Pᵢ = (Cᵢ − Kᵢ) mod 26`. With autokey, each recovered plaintext letter is appended to the key stream, so decryption runs left to right.

## The Vigenère tableau
A 26 × 26 table: **row = key letter**, **column = plain letter**, the cell is the cipher letter.

## Examples
```
P.T                 A T T A C K A T D A W N
K-stream (repeat)   L E M O N L E M O N L E
C.T                 L X F O P V E F R N H R

K-stream (autokey)  Q U E E N A T T A C K A
C.T                 Q N X E P K T M D C G N
```

## Security
Letter frequencies are flattened. But a repeating key splits the text into m Caesar ciphers once m is known, and an autokey stream is English text that a guessed keyword length unlocks.
"""
    key_help = """## Key shape
A **keyword** of m letters, each a Caesar shift (A = 0 … Z = 25), plus the **key mode**:
- **Repeating key:** keyword, keyword, keyword…
- **Autokey:** keyword, then the plaintext itself.

## Key space
**26ᵐ** for an m-letter keyword, e.g. 26⁵ ≈ 1.2 × 10⁷. Real words are far fewer.

## Weaknesses
- **Repeating key:** the key repeats, so Kasiski and the index of coincidence find m; every m-th letter is then a Caesar cipher.
- **Autokey:** Kasiski fails, but the key stream is English; once m is guessed, each keyword letter falls to chi², and a guessed word (crib) reveals the text around it.
- Short or dictionary keywords are easy. Only a random key as long as the message, never reused, would be unbreakable (a one-time pad).
"""
    params = [Param("key", "Keyword", "text", "LEMON", help="Letters only",
                    random=lambda n: "".join(random.choice(ALPHABET) for _ in range(random.randint(3, 8)))),
              Param("variant", "Key mode", "choice", REPEATING, [REPEATING, AUTOKEY],
                    help="Repeating key: the keyword repeats. Autokey: the keyword is followed by the plaintext")]
    crack_params = [Param("variant", "Key mode", "choice", BOTH, [BOTH, REPEATING, AUTOKEY]),
                    Param("max_len", "Max key length", "int", 16, minimum=1, maximum=40)]
    examples = [
        {"label": 'Encrypt: attack at dawn (key LEMON)', "mode": 'encrypt', "text": 'attack at dawn',
         "params": {'key': 'LEMON', 'variant': REPEATING}},
        {"label": 'Encrypt: we are discovered… (key DECEPTIVE)', "mode": 'encrypt',
         "text": 'we are discovered save yourself', "params": {'key': 'deceptive', 'variant': REPEATING}},
        {"label": 'Decrypt: key KEY', "mode": 'decrypt', "text": 'MVWZXMQVYZLWSWDER',
         "params": {'key': 'KEY', 'variant': REPEATING}},
        {"label": 'Encrypt: autokey, attack at dawn (key QUEEN)', "mode": 'encrypt', "text": 'attack at dawn',
         "params": {'key': 'QUEEN', 'variant': AUTOKEY}},
        {"label": 'Decrypt: autokey, key QUEEN', "mode": 'decrypt', "text": 'CYIXZQEXMTIBKBKKFRBQUSN',
         "params": {'key': 'QUEEN', 'variant': AUTOKEY}},
    ]

    @staticmethod
    def key_stream(letters: str, key: str, variant: str) -> str:
        if variant == AUTOKEY:
            return (key + letters)[:len(letters)]
        return (key * (len(letters) // len(key) + 1))[:len(letters)]

    def _process(self, letters: str, key: str, mode: str, variant: str = REPEATING) -> tuple[str, str]:
        """Return (output, key stream)."""
        k = require_letters(key)
        out: list[str] = []
        if variant == AUTOKEY and mode == "decrypt":  # key stream grows with the recovered plaintext
            ks = list(k)
            for i, c in enumerate(letters):
                p = ALPHABET[(ord(c) - ord(ks[i])) % 26]
                out.append(p)
                ks.append(p)
            return "".join(out), "".join(ks[:len(letters)])
        ks = self.key_stream(letters, k, variant)
        sign = 1 if mode == "encrypt" else -1
        return to_text(a + sign * b for a, b in zip(to_nums(letters), to_nums(ks))), ks

    def encrypt(self, letters, key="LEMON", variant=REPEATING, **_):
        return self._process(letters, key, "encrypt", variant)[0]

    def decrypt(self, letters, key="LEMON", variant=REPEATING, **_):
        return self._process(letters, key, "decrypt", variant)[0]

    def trace(self, letters, mode, key="LEMON", variant=REPEATING, **_):
        enc = mode == "encrypt"
        notes: list[str] = []
        src = limit(letters, notes)
        out, ks = self._process(src, key, mode, variant)
        k = require_letters(key)
        L = len(k)
        n = len(src)
        nums, knums, onums = to_nums(src), to_nums(ks), to_nums(out)
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        auto_dec = variant == AUTOKEY and not enc
        # Autokey decryption: key letter j (j >= keyword length) is the plaintext recovered at step j-L.
        key_reveal = [-1 if j < L else j - L for j in range(n)] if auto_dec else None
        LM = 92
        rows_in = [
            Row(a, list(src), "input", given=True, id="in"),
            Row(f"{a} index", [str(x) for x in nums], given=True, id="ix"),
            Row(self.key_label, list(ks), "key", reveal=key_reveal, given=key_reveal is None, id="ks"),
            Row("K index", [str(x) for x in knums], "key", reveal=key_reveal, given=key_reveal is None, id="kx"),
        ]
        rows_out = [Row(f"{b} index", [str(x) for x in onums], id="ox"), Row(b, list(out), "result", id="out")]

        def tables(i):
            return stream_grid(rows_in, i, label_min=LM), stream_grid(rows_out, i, label_min=LM)

        # ---- key stream generation
        t_in, t_out = tables(-1)
        intro_rows = [[letters_grid(k[:40], "kw", "Keyword", "key")], [t_in]]
        if variant == REPEATING:
            arrows = [Arrow(f"kw{j % L}", f"ks{j}", "repeat" if j == L else ("keyword" if j == 0 else ""),
                            j // L, reveal=True, kind="key") for j in range(min(n, 60))]
        else:  # autokey
            arrows = fan(((f"kw{j}", f"ks{j}") for j in range(min(L, n))), 0, "keyword", "key")
            if enc:
                arrows += fan(((f"in{j - L}", f"ks{j}") for j in range(L, n)), 1, "plaintext feeds the key")
        if key_reveal is None:  # key rows are given: animate them filling in
            arrows += fan(((f"ks{j}", f"kx{j}") for j in range(min(n, 60))), 9, "letter → number", "key",
                          curve="straight")
        steps = [Step("Generate the key stream", self.stream_explanation(k, ks, enc, variant), intro_rows, arrows),
                 Step("The Vigenère tableau",
                      "Row r of the tableau is the alphabet shifted by r. Each letter of the message is shifted by "
                      "its own key letter — so every letter uses a different Caesar alphabet (one tableau row).\n"
                      + ("Encrypt: in the key letter's row, take the letter under the plain letter." if enc else
                         "Decrypt: in the key letter's row, find the cipher letter and read its column header."),
                      [[Stack([t_in, t_out]), tableau()]])]
        for i in range(n):
            x, kk, y = nums[i], knums[i], onums[i]
            K = ks[i]
            t_in, t_out = tables(i)
            if enc:
                calc = f"C = (P + K) mod 26 = ({x} + {kk}) mod 26 = {y} → {out[i]}"
                look = (f"① plain {src[i]} picks column {src[i]}, key {K} picks row {K}\n"
                        f"② where they cross: {out[i]}")
                arrows = [Arrow(f"in{i}", f"tc{x}", f"column {src[i]}", 0),
                          Arrow(f"ks{i}", f"tr{kk}", f"row {K}", 0, kind="key"),
                          Arrow(f"tc{x}", f"t{kk}_{x}", "", 1, curve="straight"),
                          Arrow(f"tr{kk}", f"t{kk}_{x}", "", 1, kind="key", curve="straight"),
                          Arrow(f"t{kk}_{x}", f"out{i}", f"= {out[i]}", 2, reveal=True, kind="result"),
                          Arrow(f"ix{i}", f"ox{i}", f"({x}+{kk}) mod 26 = {y}", 3, reveal=True),
                          Arrow(f"kx{i}", f"ox{i}", "", 3, kind="key")]
            else:
                calc = f"P = (C − K) mod 26 = ({x} − {kk}) mod 26 = {y} → {out[i]}"
                look = (f"① key {K} picks row {K}; find cipher {src[i]} along that row\n"
                        f"② go up to the column header: {out[i].upper()}")
                arrows = [Arrow(f"ks{i}", f"tr{kk}", f"row {K}", 0, kind="key"),
                          Arrow(f"tr{kk}", f"t{kk}_{y}", f"find {src[i]}", 1, kind="key", curve="straight"),
                          Arrow(f"t{kk}_{y}", f"tc{y}", "column header", 2, curve="straight"),
                          Arrow(f"tc{y}", f"out{i}", f"= {out[i].upper()}", 3, reveal=True, kind="result"),
                          Arrow(f"ix{i}", f"ox{i}", f"({x}−{kk}) mod 26 = {y}", 4, reveal=True),
                          Arrow(f"kx{i}", f"ox{i}", "", 4, kind="key")]
            extra = ""
            if auto_dec and i + L < n:
                extra = f"\n④ autokey: plaintext {out[i].upper()} becomes key letter #{i + L + 1}."
                arrows += [Arrow(f"out{i}", f"ks{i + L}", "feeds the key", 5, reveal=True, kind="key"),
                           Arrow(f"ks{i + L}", f"kx{i + L}", "", 6, reveal=True, kind="key", curve="straight")]
            steps.append(Step(f"Letter {i + 1}/{n}: {src[i]} with key {K} → {out[i]}",
                              f"{look}\n③ check with numbers: {calc}{extra}",
                              [[Stack([t_in, t_out]), tableau(kk, x if enc else y, enc)]], arrows))
        t_in, t_out = tables(None)
        steps.append(Step("Done", f"Result: {out}", [[Stack([t_in, t_out]), tableau()]]))
        return Trace(steps, out, notes)

    @staticmethod
    def stream_explanation(k: str, ks: str, enc: bool, variant: str) -> str:
        if variant == REPEATING:
            return f"Repeat the keyword “{k}” until it is as long as the text:\n{ks}"
        if enc:
            return f"Autokey: key stream = keyword “{k}” followed by the plaintext:\n{ks}"
        return (f"Autokey: the key stream starts with the keyword “{k}”. The rest is unknown until we decrypt:\n"
                "each recovered plaintext letter is appended to the key stream.")

    def crack(self, letters, ctx, variant=BOTH, max_len=16, **_):
        if len(letters) < 20:
            raise CipherError("Need at least 20 letters of ciphertext (a few hundred is best).")
        res = CrackResult()
        found: list[Candidate] = []
        if variant in (BOTH, REPEATING):
            found += self._crack_repeating(letters, ctx, max_len, res)
        if variant in (BOTH, AUTOKEY):
            if variant == BOTH:
                res.log.append("")
            found += self._crack_autokey(letters, ctx, max_len, res)
        res.candidates = sorted(found, key=lambda c: -c.score)
        if res.candidates:
            best = res.candidates[0]
            res.log.append(f"\nBest: key = {best.key} ({best.params['variant'].lower()})")
        return res

    def _crack_repeating(self, letters, ctx, max_len, res: CrackResult) -> list[Candidate]:
        n = len(letters)
        sc = get_scorer()
        found: list[Candidate] = []
        max_len = max(1, min(int(max_len), n // 2))
        reps, factors = kasiski(letters, max_len)
        res.log.append("Step 1 — Kasiski examination: repeated sequences are often the same plaintext "
                       "encrypted with the same part of the key, so their distance is a multiple of the key length.")
        for seq, pos, d in reps[:12]:
            res.log.append(f"  {seq:<6} at {pos}  distances {d}")
        if not reps:
            res.log.append("  (no repeated sequences of length ≥ 3)")
        if factors:
            res.log.append("  most common factors: " + ", ".join(f"{f}×{c}" for f, c in factors.most_common(8)))
        iocs = periodic_ioc(letters, max_len)
        res.log.append(f"\nStep 2 — Index of coincidence per key length (English ≈ {ENGLISH_IOC:.3f}, "
                       f"random ≈ {RANDOM_IOC:.3f}). The right length makes every column look like English:")
        for L, v in enumerate(iocs, 1):
            res.log.append(f"  m = {L:>2}: IoC = {v:.4f} {'█' * int(max(0, v - 0.03) * 600)}")
        # candidate lengths: best IoC, preferring short lengths whose multiples also score well
        order = sorted(range(1, max_len + 1), key=lambda L: -iocs[L - 1])[:6]
        res.log.append("\nStep 3 — For each candidate length, solve every column as a Caesar cipher (min chi²):")
        for t, L in enumerate(order):
            ctx.progress(t / len(order), f"key length {L}")
            key = ""
            for j in range(L):
                k, _ = best_caesar_shift(letters[j::L])
                key += ALPHABET[k]
            pt = self.decrypt(letters, key, REPEATING)
            found.append(Candidate(key, {"key": key, "variant": REPEATING}, pt, sc.english_likeness(pt),
                                   f"repeating, m = {L}, IoC {iocs[L - 1]:.3f}"))
            res.log.append(f"  m = {L:>2}: key {key:<16} → {pt[:50]}")
        # Strip repeated keys like ABCABC → ABC
        for c in found:
            k = c.key
            for d in range(1, len(k)):
                if len(k) % d == 0 and k[:d] * (len(k) // d) == k:
                    c.key = k[:d]
                    c.params = {"key": k[:d], "variant": REPEATING}
                    break
        uniq: dict[str, Candidate] = {}
        for c in sorted(found, key=lambda c: -c.score):
            uniq.setdefault(c.key, c)
        found = list(uniq.values())
        best_len = len(found[0].key) if found else 0
        res.charts.append(Chart("Index of coincidence by key length", [str(L) for L in range(1, max_len + 1)],
                                {"IoC": iocs}, "IoC", {"English": ENGLISH_IOC, "random": RANDOM_IOC},
                                [best_len - 1] if 0 < best_len <= max_len else []))
        if factors:
            fs = list(range(2, max_len + 1))
            res.charts.append(Chart("Kasiski: how often each factor divides a repeat distance",
                                    [str(f) for f in fs], {"count": [factors.get(f, 0) for f in fs]}, "count"))
        return found

    def _crack_autokey(self, letters, ctx, max_len, res: CrackResult) -> list[Candidate]:
        n = len(letters)
        sc = get_scorer()
        found: list[Candidate] = []
        nums = to_nums(letters)
        res.log.append("Autokey — for each keyword length m: positions j, j+m, j+2m… form a chain that depends only on "
                       "key letter j, so pick the key letter whose chain looks most like English (chi²).\n")
        max_len = max(1, min(int(max_len), n // 3))
        for L in range(1, max_len + 1):
            ctx.progress(L / max_len, f"keyword length {L}")
            key = ""
            for j in range(L):
                chain = nums[j::L]
                best, best_chi = 0, float("inf")
                for k in range(26):
                    prev, col = k, []
                    for c in chain:
                        prev = (c - prev) % 26
                        col.append(prev)
                    cnt = [0] * 26
                    for x in col:
                        cnt[x] += 1
                    chi = chi_squared_counts(cnt)
                    if chi < best_chi:
                        best, best_chi = k, chi
                key += ALPHABET[best]
            pt = self.decrypt(letters, key, AUTOKEY)
            found.append(Candidate(key, {"key": key, "variant": AUTOKEY}, pt, sc.english_likeness(pt),
                                   f"autokey, m = {L}"))
            res.log.append(f"  m = {L:>2}: key {key:<14} English {found[-1].score:.2f} → {pt[:45]}")
        return found
