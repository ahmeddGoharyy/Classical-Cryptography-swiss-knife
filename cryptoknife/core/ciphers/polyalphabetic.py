"""Polyalphabetic substitution with any cipher alphabets, used in turn (Vigenère is the special case of shifts)."""
from __future__ import annotations

import math
import random
import re
import time

import numpy as np

from ..analysis import ENGLISH_IOC, ENGLISH_ORDER, RANDOM_IOC, counts, get_scorer, nums_array, periodic_ioc
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import ALPHABET, CipherError
from ..trace import Arrow, Chart, Row, Step, Trace, limit, mapping_strip, stream_grid
from .monoalphabetic import parse_key as parse_alphabet

# Alphabet 1 is the lecture's monoalphabetic key (a→D, b→Q, c→E); alphabet 2 starts O L V like the slide.
DEFAULT_KEY = "DQEPRSFTAWXUGOBVHNCMIZLYJK OLV"
MAX_SHOWN = 6  # alphabets drawn at once in the visualizer
SA_T0 = 20.0  # cracker: starting temperature of simulated annealing


def parse_key(key: str) -> list[str]:
    """'DQEP… OLV' → one 26-letter cipher alphabet per word (a permutation or a keyword)."""
    parts = [p for p in re.split(r"[\s,;]+", key) if p]
    if not parts:
        raise CipherError("Key: enter one or more cipher alphabets (26-letter permutations or keywords), "
                          "separated by spaces.")
    return [parse_alphabet(p)[0] for p in parts]


def _random_key(_n: int) -> str:
    return " ".join("".join(random.sample(ALPHABET, 26)) for _ in range(random.randint(2, 3)))


@register
class Polyalphabetic(Cipher):
    id = "polyalphabetic"
    name = "Polyalphabetic (several alphabets)"
    family = "Polyalphabetic substitution"
    order = 5
    summary = "Use several cipher alphabets in turn: letter 1 with alphabet 1, letter 2 with alphabet 2, …"
    description = ("The key is a list of <i>m</i> cipher alphabets (each one a monoalphabetic key). Letter "
                   "<i>i</i> of the message is substituted with alphabet <i>i</i> mod <i>m</i>, so the same plain "
                   "letter becomes different cipher letters.<br>"
                   "<b>Key space:</b> (26!)<sup>m</sup>. Vigenère is the special case where every alphabet is a "
                   "shifted alphabet.")
    crack_hint = ("The index of coincidence of every m-th letter reveals the number of alphabets. Each column is "
                  "then a monoalphabetic cipher: start from frequency analysis per column and improve all columns "
                  "together by simulated annealing with English quadgrams. Needs ~150+ letters per alphabet.")
    help = """## Idea
A monoalphabetic cipher hardened by using **several cipher alphabets in turn**. From the lecture:

| plain | alphabet 1 | alphabet 2 |
|---|---|---|
| a | D | O |
| b | Q | L |
| c | E | V |

Letter 1 of the message uses alphabet 1, letter 2 uses alphabet 2, letter 3 alphabet 1 again, and so on. So `aa` → `DO`: the same plain letter gives different cipher letters.

## Key
Cipher alphabets separated by spaces. Each one is either:
- a 26-letter permutation, e.g. `DQEPRSFTAWXUGOBVHNCMIZLYJK`
- or a **keyword**: its letters (duplicates removed), then the unused letters. `OLV` → `OLVABCDEFGHIJKMNPQRSTUWXYZ`

## Steps
- **Encrypt:** letter *i* uses alphabet *i* mod *m*: find it in the plain row and take the letter below.
- **Decrypt:** find the cipher letter in the bottom row of the same alphabet and take the letter above.

## Relation to Vigenère
Vigenère is this cipher where alphabet *k* is the plain alphabet shifted by key letter *k*. With any alphabets the key space is (26!)ᵐ.

## Security
Letter frequencies are spread over m alphabets, so the text looks flatter. But every m-th letter still uses the same alphabet: find m with the index of coincidence, then solve each column like a monoalphabetic cipher.
"""
    params = [Param("key", "Alphabets", "text", DEFAULT_KEY,
                    help="cipher alphabets separated by spaces (26-letter permutations or keywords)",
                    random=_random_key)]
    crack_params = [Param("max_period", "Max. number of alphabets", "int", 6, minimum=1, maximum=12),
                    Param("seconds", "Time limit (s)", "int", 30, minimum=5, maximum=600)]
    examples = [
        {"label": "Encrypt: lecture alphabets (aa → DO)", "mode": "encrypt", "text": "abc cba", "params": {}},
        {"label": "Encrypt: meet me at the usual place", "mode": "encrypt", "text": "meet me at the usual place",
         "params": {}},
        {"label": "Encrypt: three keyword alphabets", "mode": "encrypt", "text": "flee at once we are discovered",
         "params": {"key": "ZEBRAS CIPHER KNIFE"}},
        {"label": "Decrypt: lecture alphabets", "mode": "decrypt", "text": "GBRSGBDSMERTCTDIVIDVR", "params": {}},
    ]

    def encrypt(self, letters, key=DEFAULT_KEY, **_):
        alphas = parse_key(key)
        m = len(alphas)
        return "".join(alphas[i % m][ord(c) - 65] for i, c in enumerate(letters))

    def decrypt(self, letters, key=DEFAULT_KEY, **_):
        alphas = parse_key(key)
        m = len(alphas)
        return "".join(ALPHABET[alphas[i % m].index(c)] for i, c in enumerate(letters))

    def trace(self, letters, mode, key=DEFAULT_KEY, **_):
        alphas = parse_key(key)
        m = len(alphas)
        enc = mode == "encrypt"
        notes: list[str] = []
        src = limit(letters, notes)
        out = self.encrypt(src, key) if enc else self.decrypt(src, key)
        if m > MAX_SHOWN:
            notes.append(f"The key has {m} alphabets; the visualizer shows the one in use.")
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        LM = 74
        rows_in = [Row(a, list(src), "input", given=True, id="in"),
                   Row("Alphabet", [str(i % m + 1) for i in range(len(src))], "key", given=True, id="al")]
        rows_out = [Row(b, list(out), "result", id="out")]

        def strips(k: int | None, col: int | None):
            shown = range(m) if m <= MAX_SHOWN else [k if k is not None else 0]
            return [[mapping_strip("Plain", ALPHABET, f"Alphabet {j + 1}", alphas[j], col if j == k else None, enc,
                                   f"Alphabet {j + 1}" + (" (in use)" if j == k else ""), id=f"m{j}", label_min=LM)]
                    for j in shown]

        def scene(i, k=None, col=None):
            return [[stream_grid(rows_in, i, label_min=LM)], *strips(k, col), [stream_grid(rows_out, i, label_min=LM)]]

        intro = (f"The key is {m} cipher alphabet{'s' if m > 1 else ''}, used in turn: letter 1 → alphabet 1, "
                 f"letter 2 → alphabet {2 if m > 1 else 1}, … letter {m + 1} → alphabet 1 again.\n"
                 + ("Encrypt: in the alphabet in use, find the plain letter (top row) and take the letter below it."
                    if enc else
                    "Decrypt: in the alphabet in use, find the cipher letter (bottom row) and take the letter above."))
        steps = [Step("Several alphabets, used in turn", intro, scene(-1))]
        for i, c in enumerate(src):
            k = i % m
            col = ALPHABET.index(c) if enc else alphas[k].index(c)
            s1, s2 = (f"m{k}t{col}", f"m{k}b{col}") if enc else (f"m{k}b{col}", f"m{k}t{col}")
            res = out[i].upper()
            how = (f"① letter {i + 1} uses alphabet ({i + 1} − 1) mod {m} + 1 = {k + 1}\n"
                   + (f"② find {c} in the plain row; the letter below it is {res}" if enc else
                      f"② find {c} in alphabet {k + 1}'s row; the plain letter above it is {res}")
                   + f"\n③ write {res}")
            arrows = [Arrow(f"al{i}", f"m{k}", f"alphabet {k + 1}", 0, kind="key"),
                      Arrow(f"in{i}", s1, f"find {c}", 1),
                      Arrow(s1, s2, "substitute" if enc else "look up", 2, kind="key", curve="straight"),
                      Arrow(s2, f"out{i}", f"write {res}", 3, reveal=True, kind="result")]
            steps.append(Step(f"Letter {i + 1}/{len(src)}: {c} with alphabet {k + 1} → {out[i]}", how,
                              scene(i, k, col), arrows))
        same = next(((i, j) for i in range(len(src)) for j in range(i + 1, min(len(src), i + m + 1))
                     if src[i] == src[j] and out[i] != out[j]), None) if m > 1 else None
        done = f"Result: {out}"
        if same:
            i, j = same
            done += (f"\nThe same letter {src[i]} (positions {i + 1} and {j + 1}) became {out[i]} and {out[j]}: "
                     "it went through different alphabets.")
        steps.append(Step("Done", done, scene(None)))
        return Trace(steps, out, notes)

    # ----- cracking ---------------------------------------------------------------------------
    def crack(self, letters, ctx, max_period=6, seconds=30, **_):
        n = len(letters)
        if n < 60:
            raise CipherError("Need at least 60 letters of ciphertext (a few hundred per alphabet is best).")
        sc = get_scorer()
        res = CrackResult()
        max_period = max(1, min(int(max_period), n // 20))
        iocs = periodic_ioc(letters, max_period)
        res.log.append(f"Step 1 — Index of coincidence of every m-th letter (English ≈ {ENGLISH_IOC:.3f}, "
                       f"random ≈ {RANDOM_IOC:.3f}). With the right m, every column uses one alphabet and looks "
                       "like English:")
        for L, v in enumerate(iocs, 1):
            res.log.append(f"  m = {L:>2}: IoC = {v:.4f} {'█' * int(max(0, v - 0.03) * 600)}")
        # Multiples of the right m score as well, so try the shortest few lengths that look English.
        good = [L for L in range(1, max_period + 1) if iocs[L - 1] > (max(iocs) + RANDOM_IOC) / 2]
        lengths = good[:3] or [max(range(1, max_period + 1), key=lambda L: iocs[L - 1])]
        res.log.append(f"  → trying m = {', '.join(map(str, lengths))}\n")
        res.log.append("Step 2 — Each column is a monoalphabetic cipher. Start from per-column frequency analysis, "
                       "then simulated annealing: swap two letters in one column's alphabet; keep better keys, and "
                       "worse ones with probability e^(Δ/T) while T slowly drops. A greedy pass of all swaps "
                       "finishes each run. Score = English quadgrams of the whole text.")
        ct = nums_array(letters)
        rng = random.Random()
        seconds = int(seconds)
        start = time.monotonic()
        found: dict[str, tuple[float, int]] = {}
        for t, m in enumerate(lengths):
            if ctx.cancelled:
                break
            deadline = start + seconds * (t + 1) / len(lengths)
            col = np.arange(n) % m
            first = np.zeros((m, 26), dtype=np.int64)  # first[k][cipher letter] = plain letter
            for k in range(m):
                c = counts(letters[k::m])
                ranked = sorted(ALPHABET, key=lambda ch: (-c[ch], ch))
                for cch, p in zip(ranked, ENGLISH_ORDER):
                    first[k][ord(cch) - 65] = ord(p) - 65
            best_dec, best = first, sc.score_nums(first[col, ct])
            run = agree = 0
            while time.monotonic() < deadline and not ctx.cancelled:
                run += 1
                d = first.copy()
                cur = sc.score_nums(d[col, ct])
                run_dec, run_best = d.copy(), cur
                T = SA_T0
                while T > 0 and time.monotonic() < deadline and not ctx.cancelled:
                    for _ in range(1000):
                        k = rng.randrange(m)
                        i, j = rng.sample(range(26), 2)
                        d[k][i], d[k][j] = d[k][j], d[k][i]
                        s = sc.score_nums(d[col, ct])
                        if s > cur or rng.random() < math.exp((s - cur) / T):
                            cur = s
                            if s > run_best:
                                run_dec, run_best = d.copy(), s
                        else:
                            d[k][i], d[k][j] = d[k][j], d[k][i]
                    T -= SA_T0 / 20
                d, cur = run_dec, run_best
                improved = True
                while improved and not ctx.cancelled:
                    improved = False
                    for k in range(m):
                        for i in range(25):
                            for j in range(i + 1, 26):
                                d[k][i], d[k][j] = d[k][j], d[k][i]
                                s = sc.score_nums(d[col, ct])
                                if s > cur:
                                    cur, improved = s, True
                                else:
                                    d[k][i], d[k][j] = d[k][j], d[k][i]
                if cur > best + 1e-9:
                    best_dec, best, agree = d, cur, 1
                elif cur > best - 1e-9:
                    agree += 1
                pt = "".join(ALPHABET[x] for x in best_dec[col, ct])
                ctx.progress((time.monotonic() - start) / seconds, f"m = {m}, run {run}: {pt[:40]}", force=True)
                if agree >= 2 and sc.english_likeness(pt) > 0.95:  # two runs found the same English-looking key
                    break
            key = " ".join("".join(ALPHABET[x] for x in np.argsort(best_dec[k])) for k in range(m))
            pt = self.decrypt(letters, key)
            found[key] = (sc.english_likeness(pt), m)
            res.log.append(f"  m = {m}: {run} run{'s' if run != 1 else ''}, score {best / max(1, n - 3):.3f}/quadgram "
                           f"→ {pt[:60]}")
            if found[key][0] > 0.95:  # real English: more alphabets would only fit noise
                break
        # More alphabets can always fit the text a little better, so prefer fewer when the fit is about as good.
        top = max((v[0] for v in found.values()), default=0)
        ranked = sorted(found.items(), key=lambda kv: (kv[1][0] < top - 0.05, kv[1][1], -kv[1][0]))
        for key, (like, m) in ranked:
            res.candidates.append(Candidate(key, {"key": key}, self.decrypt(letters, key), like,
                                            f"{m} alphabet{'s' if m > 1 else ''}"))
        best_m = len(res.candidates[0].key.split()) if res.candidates else 0
        if best_m:
            res.log.append(f"\nBest: {best_m} alphabet{'s' if best_m > 1 else ''} (fewer alphabets win when the fit "
                           "is about as good, because more alphabets can also fit noise).")
        res.charts.append(Chart("Index of coincidence by number of alphabets", [str(L) for L in range(1, max_period + 1)],
                                {"IoC": iocs}, "IoC", {"English": ENGLISH_IOC, "random": RANDOM_IOC},
                                [best_m - 1] if best_m else []))
        return res
