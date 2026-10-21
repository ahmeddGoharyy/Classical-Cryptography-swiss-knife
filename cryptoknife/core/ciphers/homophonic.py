"""Homophonic substitution: each plain letter has several cipher symbols (homophones) that flatten its frequency."""
from __future__ import annotations

import math
import random
import time
import zlib

import numpy as np

from ..analysis import ENGLISH_FREQ, ENGLISH_ORDER, get_scorer
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import ALPHABET, CipherError, clean, is_letter
from ..trace import Arrow, Cell, Chart, Grid, Row, Step, Trace, limit, stream_grid

# Rows a, b, c are the lecture's table. The other letters start with the lecture's monoalphabetic key
# (h→T is taken by b, so h only gets symbols), and frequent letters get extra digits and punctuation.
DEFAULT_KEY = ("a=D-? b=Q2T c=E7& d=P e=R01# f=S g=F h=+= i=A6! j=W k=X l=U: m=G n=O8% o=B5@ p=V q=H "
               "r=N/ s=C9* t=M34 u=I v=Z w=L x=Y y=J z=K")
IN_TURN, AT_RANDOM = "In turn", "At random"
CHI2_WEIGHT = 0.5  # cracker: penalty per unit of chi² distance from English letter frequencies
SA_T0 = 20.0  # cracker: starting temperature of simulated annealing


def parse_key(key: str) -> dict[str, str]:
    """'a=D-? b=Q2T …' → {'A': 'D-?', 'B': 'Q2T', …}. A symbol may stand for one letter only."""
    table: dict[str, str] = {}
    owner: dict[str, str] = {}
    for entry in key.split():
        letter, eq, syms = entry.partition("=")
        if not eq or len(letter) != 1 or not is_letter(letter):
            raise CipherError(f"Key entry “{entry}” should look like a=D-? (a letter, =, then its symbols).")
        letter = letter.upper()
        syms = "".join(s.upper() if is_letter(s) else s for s in syms)
        if letter in table:
            raise CipherError(f"Key lists the letter {letter.lower()} twice.")
        if not syms:
            raise CipherError(f"Key gives no symbols for the letter {letter.lower()}.")
        for s in syms:
            if s in owner:
                raise CipherError(f"Key uses the symbol {s} for both {owner[s].lower()} and {letter.lower()}; "
                                  "each symbol must stand for one letter only.")
            owner[s] = letter
        table[letter] = syms
    if not table:
        raise CipherError("Enter a key like a=D-? b=Q2T c=E7& …")
    return table


def inverse(table: dict[str, str]) -> dict[str, str]:
    return {s: p for p, syms in table.items() for s in syms}


def format_key(table: dict[str, str]) -> str:
    return " ".join(f"{p.lower()}={table[p]}" for p in ALPHABET if table.get(p))


def choose(letters: str, table: dict[str, str], pick: str, key: str) -> list[int]:
    """Which homophone (index into the letter's symbols) encrypts each letter."""
    missing = sorted({c for c in letters if c not in table})
    if missing:
        raise CipherError(f"Key has no symbols for the letter(s) {', '.join(m.lower() for m in missing)}.")
    if pick == AT_RANDOM:
        rng = random.Random(zlib.crc32(f"{key}|{letters}".encode()))  # same text and key → same ciphertext
        return [rng.randrange(len(table[c])) for c in letters]
    used = dict.fromkeys(table, 0)
    out = []
    for c in letters:
        out.append(used[c] % len(table[c]))
        used[c] += 1
    return out


def _random_key(_n: int) -> str:
    pool = list(ALPHABET + "0123456789!@#$%&*+=?/:-")
    random.shuffle(pool)
    sizes = {p: 1 for p in ALPHABET}
    for p in ENGLISH_ORDER:  # hand out the spare symbols to the most frequent letters first
        if sum(sizes.values()) >= len(pool):
            break
        sizes[p] += max(0, round(ENGLISH_FREQ[p] / 3) - 1)
    out, i = {}, 0
    for p in ALPHABET:
        n = min(sizes[p], len(pool) - i - (25 - ALPHABET.index(p)))
        out[p] = "".join(pool[i:i + n])
        i += n
    return format_key(out)


@register
class Homophonic(Cipher):
    id = "homophonic"
    name = "Homophonic substitution"
    family = "Monoalphabetic substitution"
    order = 30
    preserves_layout = False
    summary = "Give each letter several cipher symbols so frequent letters stop standing out."
    description = ("Each plain letter has a list of cipher symbols (<b>homophones</b>): letters, digits or "
                   "punctuation. Every time the letter appears, one of its symbols is used. Frequent letters get "
                   "more symbols, so the ciphertext's symbol frequencies come out flat.<br>"
                   "<b>Decrypt:</b> every symbol belongs to exactly one plain letter, so just look it up.")
    crack_hint = ("Plain frequency analysis fails because the symbols have flat frequencies. The cracker "
                  "searches for the plain letter of every symbol with simulated annealing, scored with English "
                  "quadgram statistics, then polishes the result by hill climbing. Needs ~250+ symbols; rare "
                  "symbols may still come out wrong and can be fixed in the key.")
    help = """## Idea
A monoalphabetic cipher hardened with **homophones**: each plain letter can be written with several symbols, and the symbols can be letters, digits or punctuation. From the lecture:

| plain | cipher symbols |
|---|---|
| a | D , - , ? |
| b | Q , 2 , T |
| c | E , 7 , & |

## Key
One entry per letter: `letter=symbols`, separated by spaces. For example, `a=D-? b=Q2T c=E7&` gives a the symbols D, - and ?.
- Each symbol may belong to **one letter only**, otherwise decryption would be ambiguous.
- Give frequent letters (e, t, a, o…) more symbols so every symbol is about equally common.

## Choosing a symbol
- **In turn:** the 1st a uses the 1st symbol, the 2nd a the 2nd symbol, and so on, wrapping around.
- **At random:** any of the letter's symbols. The choice is fixed by the text and key, so the same input always gives the same ciphertext.

## Steps
- **Encrypt:** find the plain letter's column in the key table and take one of its symbols.
- **Decrypt:** find the symbol in the table and read the plain letter at the top of its column.

## Keep format
Spaces and line breaks are kept. Punctuation is kept too, unless it is one of the key's cipher symbols (like `?` or `-` above). Such punctuation is left out of the ciphertext so it can't be mistaken for a letter.

## Security
Frequency analysis of single symbols no longer works, but letter **pairs and words** still leak: q is still followed by a u symbol, "the" is still common. Hill climbing with n-gram statistics breaks it on a few hundred symbols.
"""
    params = [Param("key", "Key", "text", DEFAULT_KEY,
                    help="letter=symbols for each letter, e.g. a=D-? b=Q2T c=E7&", random=_random_key),
              Param("pick", "Choose a symbol", "choice", IN_TURN, [IN_TURN, AT_RANDOM],
                    help="Which homophone is used each time a letter appears")]
    crack_params = [Param("seconds", "Time limit (s)", "int", 30, minimum=5, maximum=600)]
    examples = [
        {"label": "Encrypt: lecture table (a, b, c)", "mode": "encrypt", "text": "a cab, a baba", "params": {}},
        {"label": "Encrypt: frequent letters get more symbols", "mode": "encrypt",
         "text": "meet me at the usual place", "params": {}},
        {"label": "Encrypt: random symbol choice", "mode": "encrypt", "text": "attack at dawn",
         "params": {"pick": AT_RANDOM}},
        {"label": "Decrypt: the cab is ready", "mode": "decrypt", "text": "M+REDQACN0-PJ", "params": {}},
    ]

    def symbols(self, text, mode):
        if mode == "encrypt":
            return clean(text)
        return "".join(c.upper() if is_letter(c) else c for c in text if not c.isspace())

    def encrypt(self, letters, key=DEFAULT_KEY, pick=IN_TURN, **_):
        table = parse_key(key)
        return "".join(table[c][k] for c, k in zip(letters, choose(letters, table, pick, key)))

    def decrypt(self, letters, key=DEFAULT_KEY, **_):
        inv = inverse(parse_key(key))
        out = "".join(inv[c] for c in letters if c in inv)  # other characters are not part of the ciphertext
        if not out:
            raise CipherError("The text contains none of the key's cipher symbols.")
        return out

    def run(self, text, mode, params, keep_format=False):
        src = self.symbols(text, mode)
        if not src:
            return ""
        p = {**self.defaults(), **params}
        enc = mode == "encrypt"
        out = self.encrypt(src, **p) if enc else self.decrypt(src, **p)
        if not keep_format:
            return out if enc else out.lower()
        used = set(inverse(parse_key(p["key"])))
        res, it = [], iter(out)
        for c in text:
            u = c.upper() if is_letter(c) else c
            if is_letter(c) if enc else u in used:
                res.append(next(it) if enc else next(it).lower())
            elif not (enc and c in used):  # punctuation that is also a cipher symbol would be ambiguous
                res.append(c)
        return "".join(res)

    def trace(self, letters, mode, key=DEFAULT_KEY, pick=IN_TURN, **_):
        enc = mode == "encrypt"
        table = parse_key(key)
        inv = inverse(table)
        notes: list[str] = []
        src = limit(letters if enc else "".join(c for c in letters if c in inv), notes)
        if not src:
            raise CipherError("The text contains none of the key's cipher symbols.")
        if enc:
            ks = choose(src, table, pick, key)
            plain, cipher = src, "".join(table[c][k] for c, k in zip(src, ks))
        else:
            plain = "".join(inv[s] for s in src)
            cipher, ks = src, [table[inv[s]].index(s) for s in src]
        out = cipher if enc else plain
        cols = [p for p in ALPHABET if p in table]
        depth = max(len(table[p]) for p in cols)
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        LM = 74
        rows_in = [Row(a, list(src), "input", given=True, id="in")]
        rows_out = [Row("Homophone", [f"{k + 1}/{len(table[p])}" for p, k in zip(plain, ks)], "key", id="hn"),
                    Row(b, list(out), "result", id="out")]

        def key_grid(p: str | None, k: int | None) -> Grid:
            cells = [[Cell(c, "active" if c == p and enc else ("current" if c == p else "header"), "", f"hp{c}")
                      for c in cols]]
            for r in range(depth):
                line = []
                for c in cols:
                    syms = table[c]
                    if r >= len(syms):
                        line.append(Cell("", "dim"))
                        continue
                    st = "normal"
                    if c == p:
                        st = ("current" if enc else "active") if r == k else "hl"
                    line.append(Cell(syms[r], st, "", f"hs{c}{r}"))
                cells.append(line)
            return Grid(cells, "Key table: the symbols of each plain letter",
                        ["Plain"] + [f"Symbol {r + 1}" for r in range(depth)], label_min=LM)

        def scene(i, p=None, k=None):
            return [[stream_grid(rows_in, i, label_min=LM)], [key_grid(p, k)], [stream_grid(rows_out, i, label_min=LM)]]

        rule = ("each time a letter appears, the next of its symbols is used (wrapping around)" if pick == IN_TURN
                else "one of the letter's symbols is picked at random")
        intro = (f"Every plain letter owns one or more cipher symbols; no symbol is shared.\n"
                 + (f"Encrypt: find the letter's column and take one of its symbols — {rule}." if enc else
                    "Decrypt: find the symbol in the table and read the plain letter at the top of its column."))
        steps = [Step("The key: several symbols per letter", intro, scene(-1))]
        seen: dict[str, int] = {}
        for i, (p, k) in enumerate(zip(plain, ks)):
            s = cipher[i]
            seen[p] = seen.get(p, 0) + 1
            n = len(table[p])
            if enc:
                why = (f"this is {p} number {seen[p]}, so symbol {k + 1} of {n}" if pick == IN_TURN else
                       f"picked at random from its {n} symbol{'s' if n > 1 else ''}")
                how = f"① find {p} in the plain row\n② {why}: {s}\n③ write {s}"
                arrows = [Arrow(f"in{i}", f"hp{p}", f"find {p}", 0),
                          Arrow(f"hp{p}", f"hs{p}{k}", f"symbol {k + 1}/{n}", 1, kind="key", curve="straight"),
                          Arrow(f"hs{p}{k}", f"out{i}", f"write {s}", 2, reveal=True, kind="result"),
                          Arrow(f"hs{p}{k}", f"hn{i}", "", 2, reveal=True, kind="key")]
            else:
                how = (f"① find the symbol {s} in the table (column {p}, symbol {k + 1})\n"
                       f"② the plain letter at the top of that column is {p}\n③ write {p}")
                arrows = [Arrow(f"in{i}", f"hs{p}{k}", f"find {s}", 0),
                          Arrow(f"hs{p}{k}", f"hp{p}", "column header", 1, kind="key", curve="straight"),
                          Arrow(f"hp{p}", f"out{i}", f"= {p}", 2, reveal=True, kind="result"),
                          Arrow(f"hs{p}{k}", f"hn{i}", "", 2, reveal=True, kind="key")]
            steps.append(Step(f"Letter {i + 1}/{len(src)}: {s if not enc else p} → {out[i]}", how, scene(i, p, k),
                              arrows))
        top = max(set(plain), key=plain.count)
        top_sym = max(set(cipher), key=cipher.count)
        steps.append(Step("Done", f"Result: {out}\nThe most common plain letter, {top}, appears {plain.count(top)} "
                                  f"times, but the most common cipher symbol, {top_sym}, only {cipher.count(top_sym)} "
                                  "times: the homophones flatten the frequencies.", scene(None)))
        return Trace(steps, out, notes)

    # ----- cracking ---------------------------------------------------------------------------
    def crack(self, letters, ctx, seconds=30, **_):
        n = len(letters)
        if n < 60:
            raise CipherError("Need at least 60 cipher symbols (300+ works much better).")
        sc = get_scorer()
        res = CrackResult()
        syms = sorted(set(letters), key=lambda s: (-letters.count(s), s))
        S = len(syms)
        ct = np.array([syms.index(c) for c in letters])
        freq = [letters.count(s) for s in syms]
        expected = np.array([ENGLISH_FREQ[p] * n / 100 for p in ALPHABET])
        res.log.append(f"{n} symbols, {S} different symbols (a plain alphabet has at most 26).")
        res.log.append("Most common: " + ", ".join(f"{s}={100 * f / n:.1f}%" for s, f in zip(syms[:10], freq)))
        res.log.append("The frequencies are flat, so mapping 'most common symbol → E' does not work.\n")
        res.log.append("Simulated annealing: give every symbol a random plain letter, then keep changing one "
                       "symbol's letter. Better keys are always kept; worse ones with probability e^(Δ/T), so the "
                       "search can escape dead ends while T slowly drops. Score = English quadgrams minus a penalty "
                       "for letter counts far from English. Each run ends with a greedy pass that tries every "
                       "symbol as every letter.\n")

        def chi2(pt: np.ndarray) -> float:
            return float((((np.bincount(pt, minlength=26) - expected) ** 2) / expected).sum())

        def score(d: np.ndarray) -> float:
            # Quadgrams alone reward texts like "STESETESE…"; the chi² term keeps letter counts English-like.
            pt = d[ct]
            return sc.score_nums(pt) - CHI2_WEIGHT * chi2(pt)

        def polish(d: np.ndarray, cur: float) -> float:
            improved = True
            while improved and not ctx.cancelled:
                improved = False
                for j in range(S):
                    keep = d[j]
                    for p in range(26):
                        d[j] = p
                        s = score(d)
                        if s > cur:
                            cur, keep, improved = s, p, True
                    d[j] = keep
            return cur

        rng = random.Random()
        seconds = int(seconds)
        start = time.monotonic()
        deadline = start + seconds
        found: dict[str, float] = {}
        best_dec, best = None, -1e18
        run = agree = 0
        while time.monotonic() < deadline and not ctx.cancelled:
            run += 1
            d = np.array([rng.randrange(26) for _ in range(S)])
            cur = score(d)
            run_dec, run_best = d.copy(), cur
            T = SA_T0
            while T > 0 and time.monotonic() < deadline and not ctx.cancelled:
                for _ in range(2000):
                    j = rng.randrange(S)
                    old = d[j]
                    d[j] = rng.randrange(26)
                    s = score(d)
                    if s > cur or rng.random() < math.exp((s - cur) / T):
                        cur = s
                        if s > run_best:
                            run_dec, run_best = d.copy(), s
                    else:
                        d[j] = old
                T -= SA_T0 / 20
                ctx.progress((time.monotonic() - start) / seconds, f"run {run}, T={max(T, 0):.1f}")
            run_best = polish(run_dec, run_best)
            found[self._key(syms, run_dec)] = run_best
            if run_best > best + 1e-9:
                best_dec, best, agree = run_dec, run_best, 1
            elif run_best > best - 1e-9:
                agree += 1
            pt = "".join(ALPHABET[x] for x in best_dec[ct])
            res.log.append(f"  run {run}: score {run_best / max(1, n - 3):.3f}/quadgram, best → {pt[:60]}")
            ctx.progress((time.monotonic() - start) / seconds, f"run {run}: {pt[:40]}", force=True)
            if agree >= 2 and sc.english_likeness(pt) > 0.9 and chi2(best_dec[ct]) < 0.3 * n:
                break  # two runs found the same English-looking key
        for key, _s in sorted(found.items(), key=lambda kv: -kv[1])[:8]:
            pt = self.decrypt(letters, key)
            res.candidates.append(Candidate(key, {"key": key, "pick": IN_TURN}, pt, sc.english_likeness(pt)))
        if best_dec is not None:
            res.log.append(f"\nBest key: {self._key(syms, best_dec)}")
        top = min(26, S)
        res.charts.append(Chart("Cipher symbols (sorted) vs English letters (sorted): homophones flatten the peaks",
                                [f"{s}/{p}" for s, p in zip(syms[:top], ENGLISH_ORDER)],
                                {"ciphertext %": [100 * f / n for f in freq[:top]],
                                 "English %": [ENGLISH_FREQ[p] for p in ENGLISH_ORDER[:top]]}, "%"))
        return res

    @staticmethod
    def _key(syms: list[str], dec: np.ndarray) -> str:
        table: dict[str, str] = {}
        for s, p in zip(syms, dec):
            table[ALPHABET[p]] = table.get(ALPHABET[p], "") + s
        return format_key(table)
