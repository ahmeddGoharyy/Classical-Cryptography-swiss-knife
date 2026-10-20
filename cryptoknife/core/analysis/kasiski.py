"""Kasiski examination: repeated sequences reveal the Vigenère key length."""
from __future__ import annotations

from collections import Counter, defaultdict

from ..text import clean


def repeated_sequences(text: str, min_len: int = 3, max_len: int = 5) -> dict[str, list[int]]:
    """Map each repeated substring to the positions where it occurs (longest kept first)."""
    s = clean(text)
    found: dict[str, list[int]] = {}
    for n in range(max_len, min_len - 1, -1):
        pos = defaultdict(list)
        for i in range(len(s) - n + 1):
            pos[s[i:i + n]].append(i)
        for seq, p in pos.items():
            if len(p) > 1 and not any(seq in longer for longer in found):
                found[seq] = p
    return found


def kasiski(text: str, max_factor: int = 20) -> tuple[list[tuple[str, list[int], list[int]]], Counter]:
    """Return ([(sequence, positions, distances)], factor_counts)."""
    reps = []
    factors: Counter = Counter()
    for seq, pos in sorted(repeated_sequences(text).items(), key=lambda kv: (-len(kv[0]), kv[1][0])):
        dists = [b - a for a, b in zip(pos, pos[1:])]
        reps.append((seq, pos, dists))
        for d in dists:
            for f in range(2, max_factor + 1):
                if d % f == 0:
                    factors[f] += 1
    return reps, factors
