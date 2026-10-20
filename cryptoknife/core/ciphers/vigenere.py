"""Polyalphabetic ciphers built on the Vigenère tableau: repeating key, autokey, one-time pad."""
from __future__ import annotations

import random

from ..analysis.frequency import chi_squared_counts
from ..analysis import (ENGLISH_IOC, RANDOM_IOC, best_caesar_shift, get_scorer, index_of_coincidence,
                        kasiski, periodic_ioc)
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import ALPHABET, CipherError, clean, require_letters, to_nums, to_text
from ..trace import (Arrow, Cell, Chart, Grid, Row, Stack, Step, Trace, fan, letters_grid, limit, mapping_strip,
                     stream_grid)


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


class _Vigenere(Cipher):
    family = "Polyalphabetic substitution"
    key_label = "K-stream"

    def key_stream(self, letters: str, key: str, mode: str, result: str) -> str:
        raise NotImplementedError

    def _process(self, letters: str, key: str, mode: str) -> tuple[str, str]:
        """Return (output, key stream)."""
        k = require_letters(key)
        out: list[str] = []
        if self.id == "autokey" and mode == "decrypt":  # key stream grows with the recovered plaintext
            ks = list(k)
            for i, c in enumerate(letters):
                p = ALPHABET[(ord(c) - ord(ks[i])) % 26]
                out.append(p)
                ks.append(p)
            return "".join(out), "".join(ks[:len(letters)])
        ks = self.key_stream(letters, k, mode, "")
        sign = 1 if mode == "encrypt" else -1
        return to_text(a + sign * b for a, b in zip(to_nums(letters), to_nums(ks))), ks

    def encrypt(self, letters, key="", **_):
        return self._process(letters, key, "encrypt")[0]

    def decrypt(self, letters, key="", **_):
        return self._process(letters, key, "decrypt")[0]

    def trace(self, letters, mode, key="", **_):
        enc = mode == "encrypt"
        notes: list[str] = []
        src = limit(letters, notes)
        out, ks = self._process(src, key, mode)
        k = require_letters(key)
        L = len(k)
        n = len(src)
        nums, knums, onums = to_nums(src), to_nums(ks), to_nums(out)
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        auto_dec = self.id == "autokey" and not enc
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
        kw = k if self.id != "otp" else ks
        t_in, t_out = tables(-1)
        intro_rows = [[letters_grid(kw[:40], "kw", "Keyword" if self.id != "otp" else "Pad", "key")], [t_in]]
        if self.id == "vigenere":
            arrows = [Arrow(f"kw{j % L}", f"ks{j}", "repeat" if j == L else ("keyword" if j == 0 else ""),
                            j // L, reveal=True, kind="key") for j in range(min(n, 60))]
        elif self.id == "autokey":
            arrows = fan(((f"kw{j}", f"ks{j}") for j in range(min(L, n))), 0, "keyword", "key")
            if enc:
                arrows += fan(((f"in{j - L}", f"ks{j}") for j in range(L, n)), 1, "plaintext feeds the key")
        else:
            arrows = fan(((f"kw{j}", f"ks{j}") for j in range(min(n, 40))), 0, "one pad letter each", "key")
        if key_reveal is None:  # key rows are given: animate them filling in
            arrows += fan(((f"ks{j}", f"kx{j}") for j in range(min(n, 60))), 9, "letter → number", "key",
                          curve="straight")
        steps = [Step("Generate the key stream", self.stream_explanation(k, ks, enc), intro_rows, arrows),
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

    def stream_explanation(self, k: str, ks: str, enc: bool) -> str:
        return f"Key stream: {ks}"


@register
class VigenereRepeating(_Vigenere):
    id = "vigenere"
    name = "Vigenère (repeating key)"
    order = 10
    summary = "Repeat the keyword to the message length; shift each letter by its key letter."
    description = ("Polyalphabetic: the keyword is repeated until it is as long as the plaintext; each letter "
                   "is shifted by the corresponding key letter using the Vigenère tableau.<br>"
                   "<b>Encrypt:</b> C<sub>i</sub> = (P<sub>i</sub> + K<sub>i mod m</sub>) mod 26 &nbsp; "
                   "<b>Decrypt:</b> P<sub>i</sub> = (C<sub>i</sub> − K<sub>i mod m</sub>) mod 26")
    crack_hint = ("Find the key length m (Kasiski examination + index of coincidence), then each of the m "
                  "columns is a Caesar cipher solved with frequency analysis.")
    help = """## Idea
A **polyalphabetic** cipher: the keyword is repeated to the length of the message, and each letter is shifted by its key letter.

## Formulas
- **Encrypt:** `Cᵢ = (Pᵢ + Kᵢ mod m) mod 26`
- **Decrypt:** `Pᵢ = (Cᵢ − Kᵢ mod m) mod 26`

## The Vigenère tableau
A 26 × 26 table: **row = key letter**, **column = plain letter**, the cell is the cipher letter.

## Example
```
P.T       A T T A C K A T D A W N
K-stream  L E M O N L E M O N L E
C.T       L X F O P V E F R N H R
```

## Security
The same letter encrypts differently depending on its position, which flattens letter frequencies. But the key **repeats**: once the key length m is known, the text splits into m Caesar ciphers.
"""
    params = [Param("key", "Keyword", "text", "LEMON", help="Letters only; repeated to the message length",
                    random=lambda n: "".join(random.choice(ALPHABET) for _ in range(random.randint(3, 8))))]
    crack_params = [Param("max_len", "Max key length", "int", 16, minimum=1, maximum=40)]
    examples = [
        {"label": 'Encrypt: attack at dawn (key LEMON)', "mode": 'encrypt', "text": 'attack at dawn', "params": {'key': 'LEMON'}},
        {"label": 'Encrypt: we are discovered… (key DECEPTIVE)', "mode": 'encrypt', "text": 'we are discovered save yourself', "params": {'key': 'deceptive'}},
        {"label": 'Decrypt: key KEY', "mode": 'decrypt', "text": 'MVWZXMQVYZLWSWDER', "params": {'key': 'KEY'}},
    ]

    def key_stream(self, letters, key, mode, result):
        return (key * (len(letters) // len(key) + 1))[:len(letters)]

    def stream_explanation(self, k, ks, enc):
        return f"Repeat the keyword “{k}” until it is as long as the text:\n{ks}"

    def crack(self, letters, ctx, max_len=16, **_):
        n = len(letters)
        if n < 20:
            raise CipherError("Need at least 20 letters of ciphertext (a few hundred is best).")
        sc = get_scorer()
        res = CrackResult()
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
            pt = self.decrypt(letters, key)
            res.candidates.append(Candidate(key, {"key": key}, pt, sc.english_likeness(pt),
                                            f"m = {L}, IoC {iocs[L - 1]:.3f}"))
            res.log.append(f"  m = {L:>2}: key {key:<16} → {pt[:50]}")
        # Strip repeated keys like ABCABC → ABC
        for c in res.candidates:
            k = c.key
            for d in range(1, len(k)):
                if len(k) % d == 0 and k[:d] * (len(k) // d) == k:
                    c.key = k[:d]
                    c.params = {"key": k[:d]}
                    break
        uniq = {}
        for c in sorted(res.candidates, key=lambda c: -c.score):
            uniq.setdefault(c.key, c)
        res.candidates = list(uniq.values())
        res.log.append(f"\nBest: key = {res.candidates[0].key}")
        res.charts.append(Chart("Index of coincidence by key length", [str(L) for L in range(1, max_len + 1)],
                                {"IoC": iocs}, "IoC", {"English": ENGLISH_IOC, "random": RANDOM_IOC},
                                [len(res.candidates[0].key) - 1] if len(res.candidates[0].key) <= max_len else []))
        if factors:
            fs = list(range(2, max_len + 1))
            res.charts.append(Chart("Kasiski: how often each factor divides a repeat distance",
                                    [str(f) for f in fs], {"count": [factors.get(f, 0) for f in fs]}, "count"))
        return res


@register
class VigenereAutokey(_Vigenere):
    id = "autokey"
    name = "Vigenère (autokey)"
    order = 20
    summary = "Key stream = keyword followed by the plaintext itself."
    description = ("The keyword is followed by the plaintext to form the key stream, so the key never repeats."
                   "<br><b>K</b> = keyword ‖ plaintext, &nbsp; C<sub>i</sub> = (P<sub>i</sub> + K<sub>i</sub>) mod 26."
                   "<br>Decryption recovers the plaintext letter by letter and feeds it back into the key stream.")
    crack_hint = ("For a guessed keyword length m, column j depends only on key letter j "
                  "(P[j] = C[j] − k, P[j+m] = C[j+m] − P[j], …), so each column is solved with "
                  "frequency analysis just like Vigenère.")
    help = """## Idea
Like Vigenère, but the key stream is the **keyword followed by the plaintext itself**, so the key never repeats.

## Formulas
- Key stream: `K = keyword ‖ plaintext`
- **Encrypt:** `Cᵢ = (Pᵢ + Kᵢ) mod 26`
- **Decrypt:** `Pᵢ = (Cᵢ − Kᵢ) mod 26`. Each recovered plaintext letter is appended to the key stream, so decryption works left to right.

## Example
```
P.T       A T T A C K A T D A W N
K-stream  Q U E E N A T T A C K A
C.T       Q N X E P K T M D C G N
```
"""
    params = [Param("key", "Keyword", "text", "QUEEN", help="Letters only; followed by the plaintext",
                    random=lambda n: "".join(random.choice(ALPHABET) for _ in range(random.randint(3, 8))))]
    crack_params = [Param("max_len", "Max key length", "int", 12, minimum=1, maximum=30)]
    examples = [
        {"label": 'Encrypt: attack at dawn (key QUEEN)', "mode": 'encrypt', "text": 'attack at dawn', "params": {'key': 'QUEEN'}},
        {"label": 'Decrypt: key QUEEN', "mode": 'decrypt', "text": 'CYIXZQEXMTIBKBKKFRBQUSN', "params": {'key': 'QUEEN'}},
    ]

    def key_stream(self, letters, key, mode, result):
        return (key + letters)[:len(letters)]

    def stream_explanation(self, k, ks, enc):
        if enc:
            return f"Key stream = keyword “{k}” followed by the plaintext:\n{ks}"
        return (f"Key stream starts with the keyword “{k}”. The rest is unknown until we decrypt:\n"
                "each recovered plaintext letter is appended to the key stream.")

    def crack(self, letters, ctx, max_len=12, **_):
        n = len(letters)
        if n < 20:
            raise CipherError("Need at least 20 letters of ciphertext.")
        sc = get_scorer()
        res = CrackResult()
        nums = to_nums(letters)
        res.log.append("For each keyword length m: positions j, j+m, j+2m… form a chain that depends only on "
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
            pt = self.decrypt(letters, key)
            res.candidates.append(Candidate(key, {"key": key}, pt, sc.english_likeness(pt), f"m = {L}"))
            res.log.append(f"  m = {L:>2}: key {key:<14} English {res.candidates[-1].score:.2f} → {pt[:45]}")
        res.candidates.sort(key=lambda c: -c.score)
        res.log.append(f"\nBest: key = {res.candidates[0].key}")
        return res


@register
class OneTimePad(_Vigenere):
    id = "otp"
    name = "One-time pad"
    order = 30
    key_label = "Pad"
    summary = "Random key as long as the message, used once: perfect secrecy."
    description = ("Vigenère with a truly random key that is <b>as long as the message</b> and never reused. "
                   "The key stream is the key itself.<br>Every plaintext of the same length is equally likely, "
                   "so the ciphertext reveals nothing (unconditionally secure). Problems: key generation and "
                   "key distribution.")
    crack_hint = ("Unbreakable when the pad is random and used once. Enter a guessed plaintext to see that "
                  "a key exists for ANY guess of the same length.")
    help = """## Idea
Vigenère with a **truly random key as long as the message**, used **only once**. The key stream is the pad itself.

## Formulas
- **Encrypt:** `Cᵢ = (Pᵢ + padᵢ) mod 26`
- **Decrypt:** `Pᵢ = (Cᵢ − padᵢ) mod 26`

## Example
`hello` with pad `XMCKL` → `EQNVZ`

## Security
**Unconditionally secure (perfect secrecy):** every plaintext of the same length is equally likely, so the ciphertext reveals nothing.
Practical problems: generating truly random pads and distributing them securely. Reusing a pad breaks the security.
"""
    params = [Param("key", "Pad", "text", "XMCKL",
                    help="Letters; must be at least as long as the message",
                    random=lambda n: "".join(random.choice(ALPHABET) for _ in range(max(n, 1))))]
    crack_params = [Param("guess", "Guessed plaintext", "text", "", help="Same length as the ciphertext")]
    examples = [
        {"label": 'Encrypt: hello (pad XMCKL)', "mode": 'encrypt', "text": 'hello', "params": {'key': 'XMCKL'}},
        {"label": 'Decrypt: EQNVZ (pad XMCKL)', "mode": 'decrypt', "text": 'EQNVZ', "params": {'key': 'XMCKL'}},
    ]

    def key_stream(self, letters, key, mode, result):
        if len(key) < len(letters):
            raise CipherError(f"One-time pad must be at least as long as the message "
                              f"({len(letters)} letters); it has {len(key)}.")
        return key[:len(letters)]

    def stream_explanation(self, k, ks, enc):
        return f"The pad is the key stream (one letter per message letter, never reused):\n{ks}"

    def crack(self, letters, ctx, guess="", **_):
        res = CrackResult()
        res.log.append("A one-time pad cannot be broken by analysis: for every possible plaintext of the "
                       "same length there is a pad that produces this ciphertext, and all pads are equally "
                       "likely. Brute force just lists every message of that length.\n")
        res.log.append(f"Ciphertext IoC = {index_of_coincidence(letters):.4f} (random ≈ {RANDOM_IOC:.4f}): "
                       "no language statistics survive.")
        g = clean(guess)
        if g:
            if len(g) != len(letters):
                raise CipherError(f"The guess must have exactly {len(letters)} letters (it has {len(g)}).")
            pad = to_text(c - p for c, p in zip(to_nums(letters), to_nums(g)))
            res.log.append(f"\nPad = C − guess mod 26 = {pad}\nWith this pad the ciphertext 'decrypts' to "
                           f"“{g}”. Any other guess gives another valid pad.")
            res.candidates.append(Candidate(pad, {"key": pad}, g, 1.0, "pad that yields your guess"))
        else:
            res.log.append("\nTip: type a guessed plaintext in the crack options to compute the pad that "
                           "would produce it.")
        return res
