"""Letter frequency statistics."""
from __future__ import annotations

from collections import Counter

from ..text import ALPHABET, clean

# Relative frequencies of letters in English text (percent).
ENGLISH_FREQ = {
    "A": 8.167, "B": 1.492, "C": 2.782, "D": 4.253, "E": 12.702, "F": 2.228, "G": 2.015,
    "H": 6.094, "I": 6.966, "J": 0.153, "K": 0.772, "L": 4.025, "M": 2.406, "N": 6.749,
    "O": 7.507, "P": 1.929, "Q": 0.095, "R": 5.987, "S": 6.327, "T": 9.056, "U": 2.758,
    "V": 0.978, "W": 2.360, "X": 0.150, "Y": 1.974, "Z": 0.074,
}
ENGLISH_ORDER = "ETAOINSHRDLCUMWFGYPBVKJXQZ"
ENGLISH_IOC = 0.0667
RANDOM_IOC = 1 / 26
COMMON_BIGRAMS = ["TH", "HE", "IN", "ER", "AN", "RE", "ND", "AT", "ON", "NT"]
COMMON_TRIGRAMS = ["THE", "AND", "ING", "ENT", "ION", "HER", "FOR", "THA", "NTH", "INT"]


def counts(text: str) -> dict[str, int]:
    c = Counter(clean(text))
    return {ch: c.get(ch, 0) for ch in ALPHABET}


def percentages(text: str) -> dict[str, float]:
    c = counts(text)
    n = sum(c.values()) or 1
    return {ch: 100 * v / n for ch, v in c.items()}


def chi_squared(text: str) -> float:
    """Chi-squared distance between the text's letter counts and English (lower = more English)."""
    c = counts(text)
    n = sum(c.values())
    if not n:
        return float("inf")
    return sum((c[ch] - n * p / 100) ** 2 / (n * p / 100) for ch, p in ENGLISH_FREQ.items())


def chi_squared_counts(c: list[int]) -> float:
    n = sum(c)
    if not n:
        return float("inf")
    return sum((c[i] - n * ENGLISH_FREQ[ALPHABET[i]] / 100) ** 2 / (n * ENGLISH_FREQ[ALPHABET[i]] / 100)
               for i in range(26))


def index_of_coincidence(text: str) -> float:
    c = counts(text)
    n = sum(c.values())
    if n < 2:
        return 0.0
    return sum(v * (v - 1) for v in c.values()) / (n * (n - 1))


def ngrams(text: str, n: int, top: int = 10) -> list[tuple[str, int]]:
    s = clean(text)
    return Counter(s[i:i + n] for i in range(len(s) - n + 1)).most_common(top)


def periodic_ioc(text: str, max_period: int = 20) -> list[float]:
    """Average IoC of the columns when the text is split with period 1..max_period."""
    s = clean(text)
    out = []
    for p in range(1, max_period + 1):
        cols = [s[i::p] for i in range(p)]
        vals = [index_of_coincidence(c) for c in cols if len(c) > 1]
        out.append(sum(vals) / len(vals) if vals else 0.0)
    return out


def best_caesar_shift(column: str) -> tuple[int, list[float]]:
    """Shift k (the key letter) minimizing chi-squared of column decrypted by k; also all chi² values."""
    nums = [ord(c) - 65 for c in column]
    scores = []
    for k in range(26):
        c = [0] * 26
        for x in nums:
            c[(x - k) % 26] += 1
        scores.append(chi_squared_counts(c))
    return min(range(26), key=scores.__getitem__), scores
