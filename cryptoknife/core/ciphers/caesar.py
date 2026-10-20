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

## Negative keys
k can be negative: the alphabet shifts **left** instead of right. Because everything is mod 26,
k = −3 gives exactly the same cipher as k = 23, and k = 29 the same as k = 3.

## Security
Only **25 useful keys**, so it falls to a brute-force attack instantly.
"""
    params = [Param("shift", "Shift k", "int", 3, minimum=-99, maximum=99,
                    help="Places to shift; negative = shift left (k = −3 is the same as 23)",
                    random=lambda n: random.randint(1, 25))]
    examples = [
        {"label": 'Encrypt: attack at dawn (shift 3)', "mode": 'encrypt', "text": 'attack at dawn', "params": {'shift': 3}},
        {"label": 'Encrypt: Hello, World! (ROT13)', "mode": 'encrypt', "text": 'Hello, World!', "params": {'shift': 13}},
        {"label": 'Decrypt: a pangram (shift 7)', "mode": 'decrypt', "text": 'AOLXBPJRIYVDUMVEQBTWZVCLYAOLSHGFKVN', "params": {'shift': 7}},
        {"label": 'Encrypt: negative shift (k = −3)', "mode": 'encrypt', "text": 'attack at dawn', "params": {'shift': -3}},
    ]

    @staticmethod
    def _shift(text: str, k: int) -> str:
        return to_text((x + k) % 26 for x in to_nums(text))

    def encrypt(self, letters, shift=3, **_):
        return self._shift(letters, int(shift))

    def decrypt(self, letters, shift=3, **_):
        return self._shift(letters, -int(shift))

    def trace(self, letters, mode, shift=3, **_):
        k_raw = int(shift)
        k = k_raw % 26                           # the table / wheel position
        d = k_raw - 26 * int(k_raw / 26)         # signed shift in (−26, 26): sign = direction of the turn
        enc = mode == "encrypt"
        notes: list[str] = []
        if k_raw != d:
            notes.append(f"k = {_num(k_raw)} ≡ {_num(d)} (mod 26): whole turns of the wheel change nothing.")
        src = limit(letters, notes)
        nums = to_nums(src)
        out_nums = [(x + k) % 26 if enc else (x - k) % 26 for x in nums]
        out = to_text(out_nums)
        n = len(src)
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        sign = "+" if enc else "−"
        kstr = _num(d) if d >= 0 else f"({_num(d)})"
        move = d if enc else -d                  # places each letter moves (negative = backwards)
        LM = 92
        rows_in = [Row(a, list(src), "input", given=True, id="in"),
                   Row(f"{a} index", [str(x) for x in nums], given=True, id="ix")]
        rows_out = [Row(f"{b} index", [str(x) for x in out_nums], id="ox"), Row(b, list(out), "result", id="out")]

        def strip(off: int, styles: dict | None = None, signed: int | None = None):
            shifted = ALPHABET[off:] + ALPHABET[:off]
            signed = d if signed is None and off == k else signed
            by = f"{_num(signed)} (= {off})" if signed is not None and signed < 0 else str(off)
            g = mapping_strip("Plain", ALPHABET, "Cipher", shifted, None, enc,
                              f"Shift table — cipher row = plain row shifted by {by}", label_min=LM)
            for (row, col), st in (styles or {}).items():
                g.cells[row][col].style = st
            return g

        def scene(i, wheel, table):
            flow = Stack([stream_grid(rows_in, i, label_min=LM), table, stream_grid(rows_out, i, label_min=LM)])
            return [[wheel, flow]]

        neg = (f" A negative key turns the ring the other way: k = {_num(d)} is the same as k = {k}."
               if d < 0 else "")
        steps = [Step("The cipher wheel",
                      "Two alphabets on rings: outer = plain letters, inner = cipher letters. Right now they are "
                      f"aligned (shift 0). The key k = {_num(k_raw)} says how far to turn the inner ring.{neg}",
                      scene(-1, Wheel(0, title="Cipher wheel"), strip(0)))]
        # ---- shifting, one position at a time (backwards for a negative key)
        way = "left" if d < 0 else "right"
        if d:
            unit = 1 if d > 0 else -1
            if abs(d) <= 12:
                for s_ in range(1, abs(d) + 1):
                    off = unit * s_
                    steps.append(Step(f"Shift the alphabet {way}: {s_} / {abs(d)}",
                                      f"Turn the inner ring one more place {way}: plain A now lines up with "
                                      f"{ALPHABET[off % 26]} (every letter moves {s_} place{'s' if s_ > 1 else ''} "
                                      f"{'back' if d < 0 else 'forward'}).",
                                      scene(-1, Wheel(off, off - unit, {0: "active"}, {off % 26: "current"},
                                                      "Cipher wheel"),
                                            strip(off % 26, {(0, 0): "active", (1, 0): "current"}, off))))
            else:
                other = f"shifting {'left' if d > 0 else 'right'} by {26 - abs(d)}"
                steps.append(Step(f"Shift the alphabet {way} by {abs(d)}",
                                  f"Turn the inner ring {abs(d)} places {way}: plain A now lines up with "
                                  f"{ALPHABET[k]}. (The same as {other}.)",
                                  scene(-1, Wheel(d, 0, {0: "active"}, {k: "current"}, "Cipher wheel"),
                                        strip(k, {(0, 0): "active", (1, 0): "current"}))))
        steps.append(Step("Read the wheel",
                          "Each plain letter (outer) is replaced by the cipher letter right inside it (inner).\n"
                          + ("Encrypt: outer → inner." if enc else "Decrypt: inner → outer (go back by k)."),
                          scene(-1, Wheel(d, title="Cipher wheel"), strip(k)),
                          [Arrow(f"wo{j}", f"wi{(j + k) % 26}", f"{ALPHABET[j]}→{ALPHABET[(j + k) % 26]}" if j == 0 else "",
                                 0, kind="key") for j in (0, 1, 2)]))
        # ---- letter by letter
        for i in range(n):
            x, y = nums[i], out_nums[i]
            raw = x + d if enc else x - d
            calc = (f"({x} {sign} {kstr}) mod 26 = {_num(raw)} mod 26 = {y}" if raw != y
                    else f"({x} {sign} {kstr}) mod 26 = {y}")
            step_dir = 1 if move >= 0 else -1
            steps_n = abs(move)
            hops = [((x + step_dir * h) % 26, (x + step_dir * (h + 1)) % 26) for h in range(steps_n)]
            groups = min(6, max(1, steps_n))
            hop_sign = "+" if step_dir > 0 else "−"
            arrows = [Arrow(f"ix{i}", f"mapt{x}", f"find {src[i]}", 0, carry=src[i])]
            for h, (fr, to) in enumerate(hops):
                wrap = (step_dir > 0 and fr == 25) or (step_dir < 0 and fr == 0)
                lbl = ("wrap Z→A" if step_dir > 0 else "wrap A→Z") if wrap else \
                    (f"{hop_sign}{h + 1}" if steps_n <= 12 or h in (0, steps_n - 1) else "")
                arrows.append(Arrow(f"mapt{fr}", f"mapt{to}", lbl, 1 + h * groups // max(1, steps_n), kind="key"))
            last = 1 + groups
            arrows.append(Arrow(f"mapt{x}", f"mapb{x}", "shift table", last, kind="key", curve="straight") if enc else
                          Arrow(f"mapb{y}", f"mapt{y}", "shift table", last, kind="key", curve="straight"))
            if enc:
                arrows.append(Arrow(f"wo{x}", f"wi{y}", f"{src[i]} → {out[i]}", last, kind="key"))
                wheel = Wheel(d, None, {x: "active"}, {y: "current"}, "Cipher wheel")
                table = strip(k, {(0, x): "active", (1, x): "current", (0, y): "hl"} if k else {(0, x): "active", (1, x): "current"})
            else:
                arrows.append(Arrow(f"wi{x}", f"wo{y}", f"{src[i]} → {out[i].upper()}", last, kind="key"))
                wheel = Wheel(d, None, {y: "current"}, {x: "active"}, "Cipher wheel")
                table = strip(k, {(0, x): "active", (1, y): "active", (0, y): "current"})
            src_cell = f"mapb{x}" if enc else f"mapt{y}"
            arrows += [Arrow(src_cell, f"ox{i}", f"= {y}", last + 1, carry=str(y), reveal=True),
                       Arrow(f"ox{i}", f"out{i}", f"{y} = {out[i].upper()}", last + 2, reveal=True, kind="result",
                             curve="straight")]
            steps.append(Step(f"Letter {i + 1}/{n}: {src[i]} → {out[i]}",
                              f"① find {src[i]} (= {x}) in the plain alphabet\n"
                              f"② count {steps_n} place{'s' if steps_n != 1 else ''} "
                              f"{'forward' if step_dir > 0 else 'back'}"
                              f"{' (wrapping around)' if not 0 <= x + move <= 25 else ''}: {calc}\n"
                              f"③ the wheel shows the same pair: {src[i]} ↔ {out[i].upper()}  →  write {out[i].upper()}",
                              scene(i, wheel, table), arrows))
        steps.append(Step("Done", f"{'Ciphertext' if enc else 'Plaintext'}: {out}",
                          scene(None, Wheel(d, title="Cipher wheel"), strip(k))))
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


def _num(v: int) -> str:
    """Integer with a real minus sign (−3, not -3)."""
    return f"−{-v}" if v < 0 else str(v)
