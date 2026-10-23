"""Enigma I / M3: three rotors with double stepping, ring settings, a reflector and a plugboard."""
from __future__ import annotations

import heapq
import itertools
import random
import re
import time
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from ..analysis import ENGLISH_IOC, RANDOM_IOC, get_scorer, nums_array
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..text import ALPHABET, CipherError, clean
from ..trace import Arrow, Cell, Chart, Grid, Row, Step, Trace, limit, stream_grid

# Historical wirings (entry contact A..Z → exit letter) and turnover letters: when the rotor's window shows a
# turnover letter, the next key press also turns the rotor to its left.
ROTORS = {
    "I": ("EKMFLGDQVZNTOWYHXUSPAIBRCJ", "Q"),
    "II": ("AJDKSIRUXBLHWTMCQGZNPYFVOE", "E"),
    "III": ("BDFHJLCPRTXVZNYEIWGAKMUSQO", "V"),
    "IV": ("ESOVPZJAYQUIRHXLNFTGKDCMWB", "J"),
    "V": ("VZBRGITYUPSDNHLXAWMJQOFECK", "Z"),
    "VI": ("JPGVOUMFYQBENHZRDKASXLICTW", "ZM"),
    "VII": ("NZJHGRCXMYSWBOUFAIVLPEKQDT", "ZM"),
    "VIII": ("FKQHTLXOCBJSPDZRAMEWNIUYGV", "ZM"),
}
REFLECTORS = {"B": "YRUHQSLDPXNGOKMIEBFZCWVJAT", "C": "FVPJIAOYEDRZXWGCTKUQSBNMHL",
              "A": "EJMZALYXVBWFCRQUONTSPIKHGD"}

FWD = {k: [ord(c) - 65 for c in w] for k, (w, _) in ROTORS.items()}
BWD = {k: [w.index(c) for c in range(26)] for k, w in FWD.items()}
NOTCH = {k: {ord(c) - 65 for c in n} for k, (_, n) in ROTORS.items()}
REF = {k: [ord(c) - 65 for c in w] for k, w in REFLECTORS.items()}
POS = ("left", "middle", "right")


@dataclass(frozen=True)
class Settings:
    rotors: tuple[str, str, str]  # left, middle, right
    reflector: str
    rings: tuple[int, int, int]   # Ringstellung, 0 = A (01)
    start: tuple[int, int, int]   # window letters before the first key press
    plugs: tuple[int, ...]        # plugboard as a permutation of 0..25 (pairs swapped)


def parse_rotors(text: str) -> tuple[str, str, str]:
    names = [n for n in re.split(r"[\s,;/-]+", text.strip().upper()) if n]
    if len(names) != 3:
        raise CipherError("Rotors: enter three rotors from left to right, e.g. I II III.")
    for n in names:
        if n not in ROTORS:
            raise CipherError(f"Rotors: unknown rotor “{n}” — use I to VIII.")
    if len(set(names)) < 3:
        raise CipherError("Rotors: each rotor can be used only once.")
    return tuple(names)


def parse_three(text: str, what: str) -> tuple[int, int, int]:
    """'AAA', 'A A A', '01 01 01' or '1 1 1' → (0, 0, 0)."""
    if re.search(r"\d", text):
        nums = [int(x) for x in re.findall(r"\d+", text)]
        if len(nums) != 3 or not all(1 <= x <= 26 for x in nums):
            raise CipherError(f"{what}: enter three letters (e.g. AAA) or three numbers 1–26 (e.g. 01 01 01).")
        return tuple(x - 1 for x in nums)
    s = clean(text)
    if len(s) != 3:
        raise CipherError(f"{what}: enter three letters, e.g. AAA.")
    return tuple(ord(c) - 65 for c in s)


def parse_plugboard(text: str) -> tuple[int, ...]:
    perm = list(range(26))
    for pair in (p for p in re.split(r"[\s,;]+", text) if p):
        s = clean(pair)
        if len(s) != 2 or s[0] == s[1]:
            raise CipherError(f"Plugboard: “{pair}” should be two different letters, e.g. AV.")
        a, b = ord(s[0]) - 65, ord(s[1]) - 65
        for x in (a, b):
            if perm[x] != x:
                raise CipherError(f"Plugboard: {ALPHABET[x]} is used by two cables.")
        perm[a], perm[b] = b, a
    return tuple(perm)


def format_plugboard(perm) -> str:
    return " ".join(ALPHABET[a] + ALPHABET[b] for a, b in enumerate(perm) if a < b)


def letters3(t) -> str:
    return "".join(ALPHABET[x] for x in t)


def settings(rotors="I II III", reflector="B", rings="AAA", positions="AAA", plugboard="", **_) -> Settings:
    ref = clean(str(reflector)).replace("UKW", "")
    if ref not in REFLECTORS:
        raise CipherError(f"Reflector: choose one of {', '.join(REFLECTORS)}.")
    return Settings(parse_rotors(rotors), ref, parse_three(rings, "Ring settings"),
                    parse_three(positions, "Start position"), parse_plugboard(plugboard))


def step(rotors: tuple[str, str, str], pos: tuple[int, int, int]):
    """Turn the rotors before a key press. Returns (new positions, which rotors turned)."""
    l, m, r = pos
    if m in NOTCH[rotors[1]]:  # double step: the middle rotor turns itself and the left rotor
        return ((l + 1) % 26, (m + 1) % 26, (r + 1) % 26), (True, True, True)
    if r in NOTCH[rotors[2]]:
        return (l, (m + 1) % 26, (r + 1) % 26), (False, True, True)
    return (l, m, (r + 1) % 26), (False, False, True)


def through(x: int, rotor: str, pos: int, ring: int, forward: bool = True) -> int:
    s = pos - ring  # the wiring core is turned by (window − ring) against the fixed contacts
    return ((FWD if forward else BWD)[rotor][(x + s) % 26] - s) % 26


def signal(st: Settings, pos, x: int) -> list[int]:
    """Contacts the current passes for key x: key, plugboard, R, M, L, reflector, L, M, R, plugboard (lamp)."""
    path = [x, st.plugs[x]]
    for k in (2, 1, 0):
        path.append(through(path[-1], st.rotors[k], pos[k], st.rings[k]))
    path.append(REF[st.reflector][path[-1]])
    for k in (0, 1, 2):
        path.append(through(path[-1], st.rotors[k], pos[k], st.rings[k], False))
    path.append(st.plugs[path[-1]])
    return path


@lru_cache(maxsize=128)
def next_state(rotors: tuple[str, str, str]) -> tuple[np.ndarray, list[int]]:
    """The stepping rule as a table: state (l·26 + m)·26 + r → state after one key press (array and list)."""
    S = np.arange(26 ** 3)
    l, m, r = S // 676, (S // 26) % 26, S % 26
    mstep = np.isin(m, list(NOTCH[rotors[1]]))
    rstep = np.isin(r, list(NOTCH[rotors[2]]))
    nxt = (((l + mstep) % 26) * 26 + (m + (mstep | rstep)) % 26) * 26 + (r + 1) % 26
    return nxt, nxt.tolist()


def scrambler(rotors, reflector: str, rings, start, n: int) -> np.ndarray:
    """(n, 26): what rotors + reflector (no plugboard) do to every letter at each of n key presses."""
    nxt = next_state(tuple(rotors))[1]
    seq, state = [], (start[0] * 26 + start[1]) * 26 + start[2]
    for _ in range(n):  # only the stepping is sequential (a table lookup); the wiring runs on all presses at once
        state = nxt[state]
        seq.append(state)
    states = np.array(seq, dtype=np.int64)
    pos = np.stack([states // 676, (states // 26) % 26, states % 26], axis=1)
    x = np.broadcast_to(np.arange(26), (n, 26))
    for k in (2, 1, 0):
        s = (pos[:, k] - rings[k])[:, None]
        x = (np.asarray(FWD[rotors[k]])[(x + s) % 26] - s) % 26
    x = np.asarray(REF[reflector])[x]
    for k in (0, 1, 2):
        s = (pos[:, k] - rings[k])[:, None]
        x = (np.asarray(BWD[rotors[k]])[(x + s) % 26] - s) % 26
    return x


def _random_rotors(_n: int) -> str:
    return " ".join(random.sample(["I", "II", "III", "IV", "V"], 3))


def _random_plugboard(_n: int) -> str:
    letters = random.sample(ALPHABET, 12)
    return " ".join(letters[i] + letters[i + 1] for i in range(0, 12, 2))


@register
class Enigma(Cipher):
    id = "enigma"
    name = "Enigma (I / M3)"
    family = "Rotor machine"
    order = 10
    summary = "The German rotor machine of WWII: three turning rotors, a reflector and a plugboard."
    description = ("Each key press first <b>turns the rotors</b> (right rotor always, the others like an odometer), "
                   "then sends current through the <b>plugboard</b>, three <b>rotors</b>, the <b>reflector</b>, back "
                   "through the rotors and the plugboard to a <b>lamp</b>. Because the rotors move, every letter is "
                   "encrypted with a different alphabet.<br>"
                   "<b>Encrypt = decrypt</b> with the same settings, and no letter ever encrypts to itself.")
    crack_hint = ("Ciphertext-only attack (Gillogly): try every rotor order and all 17,576 start positions without "
                  "the plugboard and keep the decryptions with the highest index of coincidence; then search the "
                  "ring settings of the right and middle rotors, and finally build the plugboard by hill climbing "
                  "(IoC, then English quadgrams). Works on ~500 letters with up to ~6 cables; the historical 10 cables "
                  "need well over 1,000 letters.")
    help = """## The machine
Enigma I (army and air force) and M3 (navy) machines have, from the keyboard inwards:

1. **Plugboard** (Steckerbrett): cables swap pairs of letters, e.g. `AV BS CG`. Usually 10 cables.
2. **Three rotors** chosen from I–V (I–VIII on the M3), placed left, middle, right. Each rotor is a fixed scrambled wiring.
3. **Reflector** (UKW-B usually) sends the current back through the rotors along a different path.

The current goes key → plugboard → right, middle, left rotor → reflector → left, middle, right rotor → plugboard → **lamp**.

## Rotor stepping
**Before** every key press the rotors turn like an odometer:
- the **right** rotor always turns one step;
- when the right rotor's window shows its **turnover letter** (I: Q, II: E, III: V, IV: J, V: Z), the middle rotor turns too;
- when the **middle** rotor shows its turnover letter, it turns *again* on the next press together with the left rotor: the famous **double step** (e.g. `ADU → ADV → AEW → BFX` with rotors I II III).

## Settings (the daily key)
| Setting | Example | Meaning |
|---|---|---|
| Rotors | `II IV V` | which rotors, left to right |
| Reflector | B | which reflector |
| Ring settings | `02 21 12` or `BUL` | turns each rotor's wiring against its letter ring |
| Start position | `BLA` | letters in the windows before the first key press |
| Plugboard | `AV BS CG DL FU HZ IN KM OW RX` | swapped letter pairs |

## Properties
- **Reciprocal:** if A encrypts to Y at some position, Y encrypts to A there. So decrypting = typing the ciphertext with the same start position.
- **No letter encrypts to itself.** This flaw let the codebreakers at Bletchley Park place *cribs* (guessed plaintext) and build the bombe.
- Key space with 3 of 5 rotors, 10 cables: about 1.6 × 10²⁰ settings — but the plugboard does not change which positions give which *rotor* alphabets, so the rotors can be attacked first.

## Visualizer
Each key press takes three steps:
1. **Rotors turn:** the windows before and after, and why each rotor moved.
2. **The current goes in:** keyboard → plugboard → right, middle, left rotor → reflector (top row of the path table).
3. **Back to the lamp:** reflector → left, middle, right rotor → plugboard → lamp (bottom row).
"""
    key_help = """## Key shape (the daily key)
- **Rotors:** 3 of I–V (I–VIII on the M3), left to right
- **Ring settings:** 3 letters, or numbers 01–26
- **Start position:** 3 window letters
- **Plugboard:** up to 13 letter pairs (10 historically)
- **Reflector:** usually B

## Key space
**≈ 1.6 × 10²⁰** with 3 of 5 rotors and 10 cables (60 rotor orders × 17,576 start positions × 1.5 × 10¹⁴ plugboards). The ring settings add a little more.

## Weaknesses
- **No letter ever encrypts to itself**, so a guessed word (crib) can be slid along the text and checked. This is the basis of Turing's bombe.
- The plugboard doesn't change which rotor positions give English-like text, so the rotors can be attacked first (the IoC attack in the Crack tab).
- Operator habits: predictable phrases, and lazy or reused start positions.
"""
    params = [
        Param("rotors", "Rotors (L M R)", "text", "I II III", help="Three rotors from I–VIII, left to right",
              random=_random_rotors),
        Param("reflector", "Reflector", "choice", "B", list(REFLECTORS), help="UKW-B was the standard reflector"),
        Param("rings", "Ring settings", "text", "AAA", help="Ringstellung: three letters (AAA) or numbers (01 01 01)",
              random=lambda n: "".join(random.choices(ALPHABET, k=3))),
        Param("positions", "Start position", "text", "AAA", help="Window letters before the first key press",
              random=lambda n: "".join(random.choices(ALPHABET, k=3))),
        Param("plugboard", "Plugboard", "text", "", help="Swapped pairs, e.g. AV BS CG (up to 13 cables)",
              random=_random_plugboard),
    ]
    crack_params = [
        Param("rotor_set", "Rotors to try", "text", "I II III IV V",
              help="Rotors the operator could have used; every order of three is tried"),
        Param("reflector", "Reflector", "choice", "B", list(REFLECTORS)),
        Param("seconds", "Time limit (s)", "int", 180, minimum=10, maximum=1200),
    ]
    examples = [
        {"label": "Encrypt: AAAAA (standard test: BDZGO)", "mode": "encrypt", "text": "AAAAA", "params": {}},
        {"label": "Encrypt: double step (start ADU)", "mode": "encrypt", "text": "hello world",
         "params": {"positions": "ADU"}},
        {"label": "Decrypt: Operation Barbarossa, 1941", "mode": "decrypt",
         "text": "EDPUD NRGYS ZRCXN UYTPO MRMBO FKTBZ REZKM LXLVE FGUEY SIOZV EQMIK UBPMM YLKLT TDEIS MDICA "
                 "GYKUA CTCDO MOHWX MUUIA UBSTS LRNBZ SZWNR FXWFY SSXJZ VIJHI DISHP RKLKA YUPAD TXQSP INQMA "
                 "TLPIF SVKDA SCTAC DPBOP VHJK",
         "params": {"rotors": "II IV V", "reflector": "B", "rings": "02 21 12", "positions": "BLA",
                    "plugboard": "AV BS CG DL FU HZ IN KM OW RX"}},
        {"label": "Encrypt: full settings with plugboard", "mode": "encrypt", "text": "attack at dawn",
         "params": {"rotors": "IV I V", "reflector": "C", "rings": "KEY", "positions": "WAR",
                    "plugboard": "PO ML IU KJ NH YT GB VF RE DC"}},
    ]

    def encrypt(self, letters, **p):
        st = settings(**p)
        pos, out = st.start, []
        for c in letters:
            pos, _ = step(st.rotors, pos)
            out.append(ALPHABET[signal(st, pos, ord(c) - 65)[-1]])
        return "".join(out)

    def decrypt(self, letters, **p):
        return self.encrypt(letters, **p)  # Enigma is reciprocal

    # ----- visualization ------------------------------------------------------------------------
    def trace(self, letters, mode, **p):
        st = settings(**p)
        enc = mode == "encrypt"
        notes: list[str] = []
        src = limit(letters, notes)
        presses, pos = [], st.start
        for c in src:
            before = pos
            pos, turned = step(st.rotors, pos)
            presses.append((before, pos, turned, signal(st, pos, ord(c) - 65)))
        out = "".join(ALPHABET[pr[3][-1]] for pr in presses)
        L, M, R = st.rotors
        a, b = ("P.T", "C.T") if enc else ("C.T", "P.T")
        rows = [Row(a, list(src), "input", given=True, id="in"),
                Row("Windows", [letters3(pr[1]) for pr in presses], "key", id="ro"),
                Row(b, list(out), "result", id="out")]
        plugs = format_plugboard(st.plugs)
        # The chain of parts the current passes, as seen on the machine: in along the top row, back along the bottom.
        parts = ["Keyboard", "Plugboard", f"Right · {R}", f"Middle · {M}", f"Left · {L}", f"Reflector {st.reflector}"]

        def text(i: int | None, hide_out: bool = False) -> Grid:
            g = stream_grid(rows, i, label_min=74)
            if hide_out and i is not None and i >= 0:
                g.cells[2][i] = Cell("", "empty", "", f"out{i}")
            return g

        def windows(before, after=None, turned=(False, False, False)) -> Grid:
            names = [f"{side} · {n}" for side, n in zip(("Left", "Middle", "Right"), st.rotors)]
            notch = ["".join(ALPHABET[x] for x in sorted(NOTCH[n])) for n in st.rotors]
            cells = [[Cell(n, "header") for n in names],
                     [Cell(ALPHABET[before[k]], "key", "", f"bw{k}") for k in range(3)],
                     [Cell(ALPHABET[after[k]] if after else "", ("current" if turned[k] else "key") if after else "empty",
                           "", f"aw{k}") for k in range(3)],
                     [Cell(notch[k], "hl" if k and before[k] in NOTCH[st.rotors[k]] else "dim") for k in range(3)]]
            return Grid(cells, "Rotor windows", ["Rotor", "Before", "After", "Turnover at"], id="wins")

        def chain(path: list[int] | None, upto: int = -1) -> Grid:
            """Top row: the current going in (keyboard → reflector); bottom row: coming back (reflector → lamp).

            Ids f"f{j}" / f"b{j}" for column j. ``upto`` = how many of the 12 contacts are shown (in path order).
            """
            top, bottom = [], []
            for j in range(6):
                fi, bi = j, 11 - j  # index in the 12-cell sequence: going in / coming back
                show_f = path is not None and fi < upto
                show_b = path is not None and bi < upto
                top.append(Cell(ALPHABET[path[fi]] if show_f else "", "active" if show_f else "empty", "", f"f{j}"))
                bottom.append(Cell(ALPHABET[path[bi]] if show_b else "", ("result" if j == 0 else "current")
                                   if show_b else "empty", "", f"b{j}"))
            return Grid([[Cell(t, "header") for t in parts], top, bottom], "Path of the current",
                        ["", "in →", "← back"], id="chain")

        def scene(i, win, ch, hide_out=False):
            return [[text(i, hide_out)], [win, ch]]

        intro = (f"Settings: rotors {L} {M} {R} (left → right), reflector {st.reflector}, ring settings "
                 f"{letters3(st.rings)}, start position {letters3(st.start)}, plugboard {plugs or '(no cables)'}.\n"
                 "Every key press has three stages:\n"
                 "① the rotors turn (like a car's odometer),\n"
                 "② the current goes in: keyboard → plugboard → right, middle, left rotor → reflector,\n"
                 "③ it comes back the other way through the rotors and the plugboard and lights a lamp.")
        steps = [Step("How the Enigma works", intro, scene(-1, windows(st.start), chain(None)))]
        for i, (before, now, turned, P) in enumerate(presses):
            c, y = src[i], out[i]
            n = len(src)
            # P = key, plugboard, R, M, L, reflector, L, M, R, plugboard (lamp). The chain shows 12 cells: the
            # top row f0..f5 (the reflector column gets the letter that arrives), the bottom row b5..b0.
            seq = [P[0], P[1], P[2], P[3], P[4], P[4], P[5], P[6], P[7], P[8], P[9], P[9]]
            # ---- ① rotors turn
            why = [f"The right rotor ({R}) always turns: {ALPHABET[before[2]]} → {ALPHABET[now[2]]}."]
            if turned[0]:
                why.append(f"The middle rotor ({M}) was showing its turnover letter {ALPHABET[before[1]]}, so it turns "
                           f"again and pushes the left rotor ({L}) too: the double step.")
            elif turned[1]:
                why.append(f"The right rotor was showing its turnover letter {ALPHABET[before[2]]}, so it pushes the "
                           f"middle rotor ({M}) one step.")
            else:
                why.append("No rotor was at its turnover letter, so the others stay.")
            arrows = [Arrow(f"bw{k}", f"aw{k}", "+1" if turned[k] else "stays", 0, reveal=True,
                            kind="key" if turned[k] else "muted", curve="straight") for k in range(3)]
            arrows.append(Arrow("wins", f"ro{i}", "windows", 1, carry=letters3(now), reveal=True, kind="key"))
            steps.append(Step(f"Letter {i + 1}/{n}: {c} — ① rotors turn {letters3(before)} → {letters3(now)}",
                              "\n".join(why), scene(i, windows(before, now, turned), chain(None), True), arrows))
            # ---- ② current goes in
            lines = [f"Press {c}.",
                     f"Plugboard: {self._plug_text(st, P[0], P[1])}",
                     f"Right rotor {R} (window {ALPHABET[now[2]]}): {ALPHABET[P[1]]} → {ALPHABET[P[2]]}",
                     f"Middle rotor {M} (window {ALPHABET[now[1]]}): {ALPHABET[P[2]]} → {ALPHABET[P[3]]}",
                     f"Left rotor {L} (window {ALPHABET[now[0]]}): {ALPHABET[P[3]]} → {ALPHABET[P[4]]}",
                     f"The current reaches the reflector at {ALPHABET[P[4]]}."]
            arrows = [Arrow(f"in{i}", "f0", f"press {c}", 0, reveal=True)]
            # the column headers name the parts, so the hops stay unlabeled and the letters readable
            arrows += [Arrow(f"f{j}", f"f{j + 1}", "", j + 1, reveal=True, curve="straight") for j in range(5)]
            steps.append(Step(f"Letter {i + 1}/{n}: {c} — ② the current goes in", "\n".join(lines),
                              scene(i, windows(before, now, turned), chain(seq, 6), True), arrows))
            # ---- ③ reflected and back to a lamp
            lines = [f"Reflector {st.reflector}: {ALPHABET[P[4]]} is wired to {ALPHABET[P[5]]}, so the current "
                     "turns around.",
                     f"Back through the left rotor {L}: {ALPHABET[P[5]]} → {ALPHABET[P[6]]}",
                     f"Back through the middle rotor {M}: {ALPHABET[P[6]]} → {ALPHABET[P[7]]}",
                     f"Back through the right rotor {R}: {ALPHABET[P[7]]} → {ALPHABET[P[8]]}",
                     f"Plugboard: {self._plug_text(st, P[8], P[9])}",
                     f"Lamp {y} lights up: {c} → {y}."]
            arrows = [Arrow("f5", "b5", f"reflect {ALPHABET[P[4]]}↔{ALPHABET[P[5]]}", 0, reveal=True, kind="result",
                            curve="straight")]
            arrows += [Arrow(f"b{j}", f"b{j - 1}", "", 6 - j, reveal=True, kind="result", curve="straight")
                       for j in range(5, 0, -1)]
            arrows.append(Arrow("b0", f"out{i}", f"lamp {y}", 6, reveal=True, kind="result"))
            steps.append(Step(f"Letter {i + 1}/{n}: {c} — ③ back to the lamp: {y}", "\n".join(lines),
                              scene(i, windows(before, now, turned), chain(seq, 12)), arrows))
        last = presses[-1][1] if presses else st.start
        steps.append(Step("Done", f"Result: {out}\nEnigma is reciprocal: typing the result with the same start "
                                  f"position {letters3(st.start)} gives the input back. Notice that no letter became "
                                  "itself — the reflector always sends the current back on a different wire. "
                                  "Codebreakers used this to place cribs (guessed words).",
                          scene(None, windows(last), chain(None))))
        return Trace(steps, out, notes)

    @staticmethod
    def _plug_text(st: Settings, x: int, y: int) -> str:
        if x == y:
            return f"{ALPHABET[x]} has no cable, it stays {ALPHABET[x]}"
        return f"cable {ALPHABET[x]}–{ALPHABET[y]} swaps {ALPHABET[x]} → {ALPHABET[y]}"

    # ----- cracking (Gillogly's ciphertext-only attack) ---------------------------------------
    @staticmethod
    def _ioc_all_starts(order, reflector: str, ct: np.ndarray) -> np.ndarray:
        """IoC of the plugboard-free decryption for all 26³ start positions (rings AAA).

        Both the stepping and the scrambling only depend on the rotor state (l, m, r), so they are tabulated
        once for all 17,576 states; each letter then costs two table lookups for all start positions at once.
        """
        S = np.arange(26 ** 3)
        l, m, r = S // 676, (S // 26) % 26, S % 26
        nxt = next_state(tuple(order))[0]
        x = np.broadcast_to(np.arange(26), (S.size, 26))
        for k, p in ((2, r), (1, m), (0, l)):
            x = (np.asarray(FWD[order[k]])[(x + p[:, None]) % 26] - p[:, None]) % 26
        x = np.asarray(REF[reflector])[x]
        for k, p in ((0, l), (1, m), (2, r)):
            x = (np.asarray(BWD[order[k]])[(x + p[:, None]) % 26] - p[:, None]) % 26
        scr = np.ascontiguousarray(x.T)  # scr[letter][state]
        state, base = S.copy(), S * 26
        counts = np.zeros(S.size * 26, dtype=np.int32)
        for c in ct:
            state = nxt[state]
            counts[base + scr[c][state]] += 1
        counts = counts.reshape(-1, 26)
        n = len(ct)
        return (counts * (counts - 1)).sum(axis=1) / (n * (n - 1))

    def crack(self, letters, ctx, rotor_set="I II III IV V", reflector="B", seconds=180, **_):
        n = len(letters)
        if n < 100:
            raise CipherError("Need at least 100 letters (300+ works much better, more with many plugboard cables).")
        names = [r for r in re.split(r"[\s,;/-]+", rotor_set.strip().upper()) if r]
        bad = [r for r in names if r not in ROTORS]
        if bad or len(set(names)) < 3:
            raise CipherError("Rotors to try: list at least three different rotors from I–VIII, e.g. I II III IV V.")
        names = list(dict.fromkeys(names))
        ref = clean(str(reflector)) or "B"
        sc = get_scorer()
        res = CrackResult()
        ct = nums_array(letters)
        ar = np.arange(n)
        start = time.monotonic()
        seconds = int(seconds)
        orders = list(itertools.permutations(names, 3))

        def ioc(x: np.ndarray) -> float:
            c = np.bincount(x, minlength=26)
            return float((c * (c - 1)).sum()) / (n * (n - 1))

        # Step 1: rotor order and start position, without plugboard, rings AAA.
        res.log.append(f"Step 1 — Rotor order and start position. The plugboard is ignored for now: with the right "
                       f"rotors the text is already partly English, so its index of coincidence rises above random "
                       f"({RANDOM_IOC:.3f}; English ≈ {ENGLISH_IOC:.3f}). Trying {len(orders)} rotor orders × "
                       "17,576 start positions with reflector " + ref + ".")
        best_per_order: dict[str, float] = {}
        top: list[tuple[float, tuple, tuple]] = []
        for k, order in enumerate(orders):
            if ctx.cancelled or time.monotonic() - start > 0.5 * seconds:
                res.log.append(f"  time limit: stopped after {k} of {len(orders)} orders")
                break
            vals = self._ioc_all_starts(order, ref, ct)
            for i in np.argpartition(vals, -50)[-50:]:  # keep many per order: short texts give noisy IoC
                item = (float(vals[i]), order, (int(i) // 676, (int(i) // 26) % 26, int(i) % 26))
                if len(top) < 3000:
                    heapq.heappush(top, item)
                else:
                    heapq.heappushpop(top, item)
            best_per_order["-".join(order)] = float(vals.max())
            ctx.progress(0.5 * (k + 1) / len(orders), f"rotors {' '.join(order)}: best IoC {vals.max():.4f}")
        top.sort(reverse=True)
        for v, order, pos in top[:6]:
            res.log.append(f"  {' '.join(order):<12} start {letters3(pos)}  IoC {v:.4f}")

        # Steps 2-3 for each candidate, best IoC first, until the time is up or the text reads as English.
        res.log.append("\nStep 2 — Ring settings. Changing the right ring together with the right start letter keeps "
                       "the wiring offset but moves the point where the middle rotor turns; keep the best IoC. Then "
                       "the same for the middle rotor.")
        res.log.append("Step 3 — Plugboard by hill climbing: try connecting / disconnecting every pair of letters, "
                       "keep changes that raise the IoC, then refine with English quadgrams. With the plugboard in "
                       "place, the rings are checked again with quadgrams and the plugboard refined once more.")
        found: list[tuple[float, Settings]] = []

        def ring_search(order, rings, st_pos, score) -> tuple[list[int], list[int]]:
            for k in (2, 1):
                best = None
                for d in range(26):
                    r2, p2 = rings.copy(), st_pos.copy()
                    r2[k], p2[k] = d, (st_pos[k] - rings[k] + d) % 26  # same wiring offset, new turnover point
                    s = score(scrambler(order, ref, r2, p2, n))
                    if best is None or s > best[0]:
                        best = (s, r2, p2)
                _s, rings, st_pos = best
            return rings, st_pos

        def plain(table: np.ndarray, P: np.ndarray) -> np.ndarray:
            return P[table[ar, P[ct]]]

        tried = 0
        for _v, order, pos in top:
            if ctx.cancelled or time.monotonic() - start > seconds:
                break
            tried += 1
            rings, st_pos = ring_search(order, [0, 0, 0], list(pos), lambda tb: ioc(tb[ar, ct]))
            table = scrambler(order, ref, rings, st_pos, n)
            P = self._plug_climb(np.arange(26), lambda Q: ioc(plain(table, Q)), ctx)
            P = self._plug_climb(P, lambda Q: sc.score_nums(plain(table, Q)), ctx)
            rings, st_pos = ring_search(order, rings, st_pos, lambda tb: sc.score_nums(plain(tb, P)))
            table = scrambler(order, ref, rings, st_pos, n)
            P = self._plug_climb(P, lambda Q: sc.score_nums(plain(table, Q)), ctx)
            st = Settings(order, ref, tuple(rings), tuple(st_pos), tuple(int(x) for x in P))
            pt = "".join(ALPHABET[x] for x in plain(table, P))
            like = sc.english_likeness(pt)
            found.append((like, st))
            if tried <= 5 or like > 0.6:
                res.log.append(f"  candidate {tried}: {' '.join(order)}, rings {letters3(rings)}, start "
                               f"{letters3(st_pos)}, plugs {format_plugboard(P) or '-'} → {pt[:50]}")
            best_like = max(f[0] for f in found)
            ctx.progress(0.5 + 0.5 * (time.monotonic() - start - 0.5 * seconds) / (0.5 * seconds),
                         f"candidate {tried}, best English likeness {100 * best_like:.0f}%: {pt[:30]}")
            if like > 0.9:
                break
        res.log.append(f"  ({tried} candidate{'s' if tried != 1 else ''} refined)")
        found = sorted(found, key=lambda f: -f[0])[:8]
        for like, st in found:
            params = {"rotors": " ".join(st.rotors), "reflector": st.reflector, "rings": letters3(st.rings),
                      "positions": letters3(st.start), "plugboard": format_plugboard(st.plugs)}
            key = f"{params['rotors']} | {st.reflector} | rings {params['rings']} | start {params['positions']}"
            pt = self.encrypt(letters, **params)
            res.candidates.append(Candidate(key, params, pt, like, f"plugs {params['plugboard'] or '-'}"))
        if res.candidates:
            res.log.append(f"\nBest: {res.candidates[0].key}, plugboard {res.candidates[0].params['plugboard']}")
            res.log.append("(Equivalent settings exist: shifting a ring and its start letter together, or the left "
                           "ring, gives the same decryption.)")
        if best_per_order:
            labels = sorted(best_per_order, key=lambda k: -best_per_order[k])[:20]
            res.charts.append(Chart("Best IoC per rotor order (no plugboard)", labels,
                                    {"IoC": [best_per_order[k] for k in labels]}, "IoC",
                                    {"English": ENGLISH_IOC, "random": RANDOM_IOC}, [0]))
        return res

    @staticmethod
    def _plug_climb(P: np.ndarray, score, ctx) -> np.ndarray:
        best = score(P)
        improved = True
        while improved and not ctx.cancelled:
            improved = False
            for a in range(26):
                for b in range(a + 1, 26):
                    Q = P.copy()
                    if Q[a] == b:  # connected to each other: try removing the cable
                        Q[a], Q[b] = a, b
                    else:  # free both letters, then connect them
                        for x in (a, b):
                            y = Q[x]
                            Q[x], Q[y] = x, y
                        Q[a], Q[b] = b, a
                    s = score(Q)
                    if s > best:
                        P, best, improved = Q, s, True
        return P
