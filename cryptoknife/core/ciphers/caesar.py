"""Caesar cipher: C = (P + k) mod 26."""
from __future__ import annotations

import random

from ..analysis import chi_squared, get_scorer
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import ALPHABET, to_nums, to_text
from ..trace import Arrow, Chart, Row, Stack, Step, Trace, Wheel, limit, mapping_strip, stream_grid


@register
class Caesar(Cipher):
    id = "caesar"
    name = "Caesar"
    family = "Monoalphabetic substitution"
    order = 10
    summary = "Shift every letter k places down the alphabet."
    description = ("Each letter is replaced by the letter <b>k</b> places further down the alphabet "
                   "(Julius Caesar used k = 3).<br><b>Encrypt:</b> C = (P + k) mod 26 &nbsp; "
                   "<b>Decrypt:</b> P = (C − k) mod 26 &nbsp; <b>Key space:</b> 25 useful keys.")
    crack_hint = "Brute force: try all 26 shifts and rank them by how English the result looks."
    help = """## Idea
Replace every letter with the letter **k** places further down the alphabet (Julius Caesar used k = 3).

## Formulas
Number the letters A = 0 … Z = 25.

- **Encrypt:** `C = (P + k) mod 26`
- **Decrypt:** `P = (C − k) mod 26`

## Steps
1. Convert each letter to its number.
2. Add k (encrypt) or subtract k (decrypt).
3. Reduce mod 26 and convert back to a letter.

## Example
`attack at dawn`, k = 3 → `DWWDFNDWGDZQ`
(A = 0 → 0 + 3 = 3 → D)

## Security
Only **25 useful keys**, so it falls to a brute-force attack instantly.
"""
    params = [Param("shift", "Shift k", "int", 3, minimum=0, maximum=25,
                    help="Number of positions to shift (0-25)", random=lambda n: random.randint(1, 25))]
    examples = [
        {"label": 'Encrypt: attack at dawn (shift 3)', "mode": 'encrypt', "text": 'attack at dawn', "params": {'shift': 3}},
        {"label": 'Encrypt: Hello, World! (ROT13)', "mode": 'encrypt', "text": 'Hello, World!', "params": {'shift': 13}},
        {"label": 'Decrypt: a pangram (shift 7)', "mode": 'decrypt', "text": 'AOLXBPJRIYVDUMVEQBTWZVCLYAOLSHGFKVN', "params": {'shift': 7}},
    ]

    @staticmethod
    def _shift(text: str, k: int) -> str:
        return to_text((x + k) % 26 for x in to_nums(text))

    def encrypt(self, letters, shift=3, **_):
        return self._shift(letters, int(shift))

    def decrypt(self, letters, shift=3, **_):
        return self._shift(letters, -int(shift))

    def trace(self, letters, mode, shift=3, **_):
        k = int(shift) % 26
        enc = mode == "encrypt"
        notes: list[str] = []
        src = limit(letters, notes)
        nums = to_nums(src)
        out_nums = [(x + k) % 26 if enc else (x - k) % 26 for x in nums]
        out = to_text(out_nums)
        n = len(src)
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        sign = "+" if enc else "−"
        LM = 92
        rows_in = [Row(a, list(src), "input", given=True, id="in"),
                   Row(f"{a} index", [str(x) for x in nums], given=True, id="ix")]
        rows_out = [Row(f"{b} index", [str(x) for x in out_nums], id="ox"), Row(b, list(out), "result", id="out")]

        def strip(off: int, styles: dict | None = None):
            shifted = ALPHABET[off:] + ALPHABET[:off]
            g = mapping_strip("Plain", ALPHABET, "Cipher", shifted, None, enc,
                              f"Shift table — cipher row = plain row shifted by {off}", label_min=LM)
            for (row, col), st in (styles or {}).items():
                g.cells[row][col].style = st
            return g

        def scene(i, wheel, table):
            flow = Stack([stream_grid(rows_in, i, label_min=LM), table, stream_grid(rows_out, i, label_min=LM)])
            return [[wheel, flow]]

        steps = [Step("The cipher wheel",
                      "Two alphabets on rings: outer = plain letters, inner = cipher letters. Right now they are "
                      f"aligned (shift 0). The key k = {k} says how far to turn the inner ring.",
                      scene(-1, Wheel(0, title="Cipher wheel"), strip(0)))]
        # ---- shifting, one position at a time
        if k:
            if k <= 12:
                for s_ in range(1, k + 1):
                    steps.append(Step(f"Shift the alphabet: {s_} / {k}",
                                      f"Turn the inner ring one more place: plain A now lines up with "
                                      f"{ALPHABET[s_]} (every letter moves {s_} place{'s' if s_ > 1 else ''}).",
                                      scene(-1, Wheel(s_, s_ - 1, {0: "active"}, {s_: "current"}, "Cipher wheel"),
                                            strip(s_, {(0, 0): "active", (1, 0): "current"}))))
            else:
                steps.append(Step(f"Shift the alphabet by {k}",
                                  f"Turn the inner ring {k} places: plain A now lines up with {ALPHABET[k]}. "
                                  f"(Shifting by {k} is the same as shifting back by {26 - k}.)",
                                  scene(-1, Wheel(k, 0, {0: "active"}, {k: "current"}, "Cipher wheel"),
                                        strip(k, {(0, 0): "active", (1, 0): "current"}))))
        steps.append(Step("Read the wheel",
                          "Each plain letter (outer) is replaced by the cipher letter right inside it (inner).\n"
                          + ("Encrypt: outer → inner." if enc else "Decrypt: inner → outer (go back by k)."),
                          scene(-1, Wheel(k, title="Cipher wheel"), strip(k)),
                          [Arrow(f"wo{j}", f"wi{(j + k) % 26}", f"{ALPHABET[j]}→{ALPHABET[(j + k) % 26]}" if j == 0 else "",
                                 0, kind="key") for j in (0, 1, 2)]))
        # ---- letter by letter
        for i in range(n):
            x, y = nums[i], out_nums[i]
            raw = x + k if enc else x - k
            calc = f"({x} {sign} {k}) mod 26 = {raw} mod 26 = {y}" if raw != y else f"({x} {sign} {k}) mod 26 = {y}"
            step_dir = 1 if enc else -1
            hops = [((x + step_dir * h) % 26, (x + step_dir * (h + 1)) % 26) for h in range(k)]
            groups = min(6, max(1, k))
            arrows = [Arrow(f"ix{i}", f"mapt{x}", f"find {src[i]}", 0, carry=src[i])]
            for h, (fr, to) in enumerate(hops):
                wrap = (enc and fr == 25) or (not enc and fr == 0)
                lbl = ("wrap Z→A" if enc else "wrap A→Z") if wrap else (f"{sign}{h + 1}" if k <= 12 or h in (0, k - 1) else "")
                arrows.append(Arrow(f"mapt{fr}", f"mapt{to}", lbl, 1 + h * groups // max(1, k), kind="key"))
            last = 1 + groups
            arrows.append(Arrow(f"mapt{x}", f"mapb{x}", "shift table", last, kind="key", curve="straight") if enc else
                          Arrow(f"mapb{y}", f"mapt{y}", "shift table", last, kind="key", curve="straight"))
            if enc:
                arrows.append(Arrow(f"wo{x}", f"wi{y}", f"{src[i]} → {out[i]}", last, kind="key"))
                wheel = Wheel(k, None, {x: "active"}, {y: "current"}, "Cipher wheel")
                table = strip(k, {(0, x): "active", (1, x): "current", (0, y): "hl"} if k else {(0, x): "active", (1, x): "current"})
            else:
                arrows.append(Arrow(f"wi{x}", f"wo{y}", f"{src[i]} → {out[i].upper()}", last, kind="key"))
                wheel = Wheel(k, None, {y: "current"}, {x: "active"}, "Cipher wheel")
                table = strip(k, {(0, x): "active", (1, y): "active", (0, y): "current"})
            src_cell = f"mapb{x}" if enc else f"mapt{y}"
            arrows += [Arrow(src_cell, f"ox{i}", f"= {y}", last + 1, carry=str(y), reveal=True),
                       Arrow(f"ox{i}", f"out{i}", f"{y} = {out[i].upper()}", last + 2, reveal=True, kind="result",
                             curve="straight")]
            steps.append(Step(f"Letter {i + 1}/{n}: {src[i]} → {out[i]}",
                              f"① find {src[i]} (= {x}) in the plain alphabet\n"
                              f"② count {k} place{'s' if k != 1 else ''} {'forward' if enc else 'back'}"
                              f"{' (wrapping around)' if (x + step_dir * k) % 26 != x + step_dir * k else ''}: {calc}\n"
                              f"③ the wheel shows the same pair: {src[i]} ↔ {out[i].upper()}  →  write {out[i].upper()}",
                              scene(i, wheel, table), arrows))
        steps.append(Step("Done", f"{'Ciphertext' if enc else 'Plaintext'}: {out}",
                          scene(None, Wheel(k, title="Cipher wheel"), strip(k))))
        return Trace(steps, out, notes)

    def crack(self, letters, ctx, **_):
        sc = get_scorer()
        res = CrackResult()
        res.log.append("Brute-force attack: the key space has only 26 keys, so try them all.\n")
        res.log.append(f"{'k':>3}  {'chi²':>8}  {'English':>7}  plaintext")
        chis, cands = [], []
        for k in range(26):
            p = self._shift(letters, -k)
            chi = chi_squared(p)
            chis.append(chi)
            cands.append(Candidate(str(k), {"shift": k}, p, sc.english_likeness(p), f"chi² = {chi:.1f}"))
            res.log.append(f"{k:>3}  {chi:>8.1f}  {cands[-1].score:>7.2f}  {p[:60]}")
        res.candidates = sorted(cands, key=lambda c: -c.score)
        best = int(res.candidates[0].key)
        res.log.append(f"\nBest key: k = {best} → {res.candidates[0].plaintext[:80]}")
        res.charts.append(Chart("Chi-squared vs English for every shift (lower is better)",
                                [str(k) for k in range(26)], {"chi²": chis}, "chi²", highlight=[best]))
        return res
