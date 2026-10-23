"""Monoalphabetic substitution: any permutation of the alphabet."""
from __future__ import annotations

import random

import numpy as np

from ..analysis import ENGLISH_FREQ, ENGLISH_ORDER, counts, get_scorer, nums_array
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import ALPHABET, CipherError, clean, keyed_alphabet, unique_letters
from ..trace import Arrow, Chart, Row, Step, Trace, fan, letters_grid, limit, mapping_strip, stream_grid

DEFAULT_KEY = "QWERTYUIOPASDFGHJKLZXCVBNM"  # keyboard order


def parse_key(key: str) -> tuple[str, str | None]:
    """Return (cipher alphabet, keyword or None). Accepts a 26-letter permutation or a keyword."""
    k = clean(key)
    if not k:
        raise CipherError("Enter a 26-letter permutation or a keyword.")
    if len(k) == 26 and len(set(k)) == 26:
        return k, None
    return keyed_alphabet(k), unique_letters(k)


def _random_key(_n: int) -> str:
    letters = list(ALPHABET)
    random.shuffle(letters)
    return "".join(letters)


@register
class Monoalphabetic(Cipher):
    id = "monoalphabetic"
    name = "Monoalphabetic"
    family = "Monoalphabetic substitution"
    order = 20
    summary = "Replace each letter using a fixed permutation of the alphabet."
    description = ("The key is any permutation of the 26 letters: plain letter <i>i</i> is replaced by the "
                   "<i>i</i>-th letter of the key. You can also type a <b>keyword</b>: its letters (duplicates "
                   "removed) start the cipher alphabet, followed by the unused letters in order.<br>"
                   "<b>Key space:</b> 26! ≈ 4 × 10<sup>26</sup> keys, but it does <b>not</b> change relative "
                   "letter frequencies, so frequency analysis breaks it.")
    crack_hint = ("Frequency analysis gives a first guess; hill climbing with English quadgram statistics "
                  "refines it. Use the Manual solver tab to finish by hand. Needs ~100+ letters.")
    manual_solver = "substitution"
    help = """## Idea
The key is any **permutation** of the alphabet: plain letter *i* is replaced by the *i*-th letter of the key.

## Key
- A 26-letter cipher alphabet, e.g. `QWERTYUIOPASDFGHJKLZXCVBNM`
- or a **keyword**: its letters (duplicates removed) followed by the unused letters.
  `ZEBRAS` → `ZEBRASCDFGHIJKLMNOPQTUVWXY`

## Steps
- **Encrypt:** find the plain letter in the top row of the table, take the letter below it.
- **Decrypt:** find the cipher letter in the bottom row, take the letter above it.

## Security
26! ≈ 4 × 10²⁶ keys, but it **does not change letter frequencies**: the most common cipher letter is probably E, then T, A, O… so frequency analysis breaks it.
"""
    key_help = """## Key shape
A **permutation of the 26 letters** (a → 1st key letter, b → 2nd, …), or a **keyword** that starts the cipher alphabet: `ZEBRAS` → `ZEBRASCDFGH…`.

## Key space
**26! ≈ 4 × 10²⁶**, far too many to brute force. Keyword keys are far fewer, and they leave the end of the alphabet in order (…VWXY).

## Weaknesses
- A plain letter always becomes the same cipher letter, so **letter, pair and word frequencies survive**.
- Frequency analysis plus hill climbing breaks about 100+ letters.
"""
    params = [Param("key", "Key", "text", DEFAULT_KEY,
                    help="26-letter cipher alphabet (a→1st letter, b→2nd, …) or a keyword", random=_random_key)]
    crack_params = [Param("restarts", "Random restarts", "int", 8, minimum=1, maximum=50)]
    examples = [
        {"label": 'Encrypt: keyboard-order key', "mode": 'encrypt', "text": 'meet me at the usual place', "params": {'key': 'QWERTYUIOPASDFGHJKLZXCVBNM'}},
        {"label": 'Encrypt: keyword ZEBRAS', "mode": 'encrypt', "text": 'flee at once we are discovered', "params": {'key': 'ZEBRAS'}},
        {"label": 'Decrypt: keyboard-order key', "mode": 'decrypt', "text": 'ZITZKTQLXKTOLWXKOTRXFRTKZITGSRGQAZKTT', "params": {'key': 'QWERTYUIOPASDFGHJKLZXCVBNM'}},
    ]

    def encrypt(self, letters, key=DEFAULT_KEY, **_):
        alpha, _kw = parse_key(key)
        return letters.translate(str.maketrans(ALPHABET, alpha))

    def decrypt(self, letters, key=DEFAULT_KEY, **_):
        alpha, _kw = parse_key(key)
        return letters.translate(str.maketrans(alpha, ALPHABET))

    def trace(self, letters, mode, key=DEFAULT_KEY, **_):
        alpha, kw = parse_key(key)
        enc = mode == "encrypt"
        notes: list[str] = []
        src = limit(letters, notes)
        out = self.encrypt(src, key) if enc else self.decrypt(src, key)
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        rows_in = [Row(a, list(src), "input", given=True, id="in")]
        rows_out = [Row(b, list(out), "result", id="out")]
        key_cols = set(range(len(kw))) if kw else set()
        LM = 60

        def strip(col):
            return mapping_strip("Plain", ALPHABET, "Cipher", alpha, col, enc, "Substitution table (the key)",
                                 key_cols, label_min=LM)

        def scene(i, col):
            return [[stream_grid(rows_in, i, label_min=LM)], [strip(col)], [stream_grid(rows_out, i, label_min=LM)]]

        steps = []
        if kw:
            steps.append(Step("Build the cipher alphabet",
                              f"Keyword “{kw}” (duplicates removed) is written first, then the unused letters in "
                              f"alphabetical order:\n{alpha}",
                              [[letters_grid(kw, "kw", "Keyword", "key")], [strip(None)]],
                              fan(((f"kw{j}", f"mapb{j}") for j in range(len(kw))), 0, "keyword first", "key")
                              + fan(((f"mapt{ALPHABET.index(c)}", f"mapb{j}") for j, c in enumerate(alpha)
                                     if j >= len(kw)), 1, "then the rest", "muted")))
        intro = f"Key permutation: {alpha}\n" + (
            "Encrypt: find the plain letter in the top row, take the letter below it." if enc else
            "Decrypt: find the cipher letter in the bottom row, take the letter above it.")
        steps.append(Step("The key is a substitution table", intro, scene(-1, None)))
        for i, c in enumerate(src):
            col = ALPHABET.index(c) if enc else alpha.index(c)
            s1, s2 = (f"mapt{col}", f"mapb{col}") if enc else (f"mapb{col}", f"mapt{col}")
            res = out[i].upper()
            how = (f"① find {c} in the plain row (column {col})\n② the letter below it is {res}\n③ write {res}"
                   if enc else
                   f"① find {c} in the cipher row (column {col})\n② the plain letter above it is {res}\n"
                   f"③ write {res}")
            arrows = [Arrow(f"in{i}", s1, f"find {c}", 0),
                      Arrow(s1, s2, "substitute" if enc else "look up", 1, kind="key", curve="straight"),
                      Arrow(s2, f"out{i}", f"write {res}", 2, reveal=True, kind="result")]
            steps.append(Step(f"Letter {i + 1}/{len(src)}: {c} → {out[i]}", how, scene(i, col), arrows))
        steps.append(Step("Done", f"Result: {out}", scene(None, None)))
        return Trace(steps, out, notes)

    # ----- cracking ---------------------------------------------------------------------------
    @staticmethod
    def frequency_guess(letters: str) -> str:
        """Decryption guess: i-th most frequent cipher letter ↦ i-th most frequent English letter.

        Returned as a cipher alphabet (encryption key), like the key parameter.
        """
        c = counts(letters)
        ranked = sorted(ALPHABET, key=lambda ch: (-c[ch], ch))
        enc = {p: cch for cch, p in zip(ranked, ENGLISH_ORDER)}
        return "".join(enc[p] for p in ALPHABET)

    def crack(self, letters, ctx, restarts=8, **_):
        if len(letters) < 20:
            raise CipherError("Need at least 20 letters of ciphertext (100+ works much better).")
        sc = get_scorer()
        res = CrackResult()
        c = counts(letters)
        n = len(letters)
        ranked = sorted(ALPHABET, key=lambda ch: (-c[ch], ch))
        res.log.append("Step 1 — Frequency analysis (substitution keeps letter frequencies):")
        res.log.append("  cipher by frequency : " + " ".join(ranked))
        res.log.append("  English by frequency: " + " ".join(ENGLISH_ORDER))
        res.log.append("  Top: " + ", ".join(f"{ch}={100 * c[ch] / n:.1f}%" for ch in ranked[:8]))
        guess = self.frequency_guess(letters)
        res.log.append(f"  First guess key: {guess} → {self.decrypt(letters, guess)[:70]}\n")
        res.log.append("Step 2 — Hill climbing: swap two letters of the key, keep the swap if the text "
                       "looks more like English (quadgram score), repeat until no swap helps.")
        ct = nums_array(letters)

        def score(dec: np.ndarray) -> float:
            return sc.score_nums(dec[ct])

        found: dict[str, float] = {}
        rng = random.Random(1)
        restarts = int(restarts)
        for r in range(restarts):
            if ctx.cancelled:
                break
            if r == 0:  # start from the frequency guess
                enc = np.array([ord(ch) - 65 for ch in guess])
                dec = np.argsort(enc)
            else:
                dec = np.array(rng.sample(range(26), 26))
            best = score(dec)
            improved = True
            while improved and not ctx.cancelled:  # sweep all 325 swaps until none helps
                improved = False
                for i in range(25):
                    for j in range(i + 1, 26):
                        dec[i], dec[j] = dec[j], dec[i]
                        s = score(dec)
                        if s > best:
                            best, improved = s, True
                        else:
                            dec[i], dec[j] = dec[j], dec[i]
            key = "".join(ALPHABET[x] for x in np.argsort(dec))
            found[key] = best
            pt = self.decrypt(letters, key)
            res.log.append(f"  restart {r + 1}: score {best / max(1, n - 3):.3f}/quadgram → {pt[:60]}")
            ctx.progress((r + 1) / restarts, f"restart {r + 1}/{restarts}: {pt[:40]}")
        for key, s in sorted(found.items(), key=lambda kv: -kv[1]):
            pt = self.decrypt(letters, key)
            res.candidates.append(Candidate(key, {"key": key}, pt, sc.english_likeness(pt)))
        fg = self.decrypt(letters, guess)
        res.candidates.append(Candidate(guess, {"key": guess}, fg, sc.english_likeness(fg), "frequency guess"))
        eng = [c[ch] * 100 / n for ch in ranked]
        res.charts.append(Chart("Ciphertext letters (sorted) vs English letters (sorted)",
                                [f"{a}/{b}" for a, b in zip(ranked, ENGLISH_ORDER)],
                                {"ciphertext %": eng, "English %": [ENGLISH_FREQ[ch] for ch in ENGLISH_ORDER]},
                                "%"))
        return res
