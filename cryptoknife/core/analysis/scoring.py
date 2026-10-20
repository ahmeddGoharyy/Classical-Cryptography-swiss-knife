"""English fitness scoring with quadgram log-probabilities.

The table (cryptoknife/data/quadgrams.txt) is built by tools/build_ngrams.py
from public-domain books. A higher (less negative) score means "more English".
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..text import clean

DATA = Path(__file__).resolve().parents[2] / "data" / "quadgrams.txt"


class QuadgramScorer:
    def __init__(self, path: Path = DATA):
        lines = path.read_text().splitlines()
        total = int(lines[0].split()[-1]) if lines[0].startswith("#") else None
        pairs = [ln.split() for ln in lines if ln and not ln.startswith("#")]
        total = total or sum(int(n) for _, n in pairs)
        self.floor = math.log10(0.01 / total)
        self.table = np.full(26 ** 4, self.floor)
        for q, n in pairs:
            a, b, c, d = (ord(ch) - 65 for ch in q)
            self.table[((a * 26 + b) * 26 + c) * 26 + d] = math.log10(int(n) / total)

    def score_nums(self, p: np.ndarray) -> float:
        """Total log-probability of an int array of letters 0..25."""
        if len(p) < 4:
            return self.floor * max(1, len(p))
        i = ((p[:-3] * 26 + p[1:-2]) * 26 + p[2:-1]) * 26 + p[3:]
        return float(self.table[i].sum())

    def score(self, text: str) -> float:
        return self.score_nums(np.frombuffer(clean(text).encode(), dtype=np.uint8).astype(np.int64) - 65)

    def per_quadgram(self, text: str) -> float:
        s = clean(text)
        return self.score(s) / max(1, len(s) - 3)

    def english_likeness(self, text: str) -> float:
        """0 = random letters, 1 = typical English (clamped)."""
        s = clean(text)
        if len(s) < 4:
            return 0.0
        v = self.per_quadgram(s)
        return max(0.0, min(1.0, (v - RANDOM_PQ) / (ENGLISH_PQ - RANDOM_PQ)))


# Typical per-quadgram scores for this table (measured on held-out English and random text).
ENGLISH_PQ = -4.2
RANDOM_PQ = -8.4


@lru_cache(maxsize=1)
def get_scorer() -> QuadgramScorer:
    return QuadgramScorer()


def nums_array(letters: str) -> np.ndarray:
    return np.frombuffer(letters.encode(), dtype=np.uint8).astype(np.int64) - 65
