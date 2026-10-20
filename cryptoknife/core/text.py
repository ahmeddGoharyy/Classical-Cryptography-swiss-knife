"""Alphabet helpers and text cleaning.

Convention: A=0, B=1, ..., Z=25 and all arithmetic is mod 26.
"""
from __future__ import annotations

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class CipherError(ValueError):
    """Raised for invalid keys or inputs; the message is shown to the user."""


def is_letter(c: str) -> bool:
    return c.isascii() and c.isalpha()


def clean(text: str) -> str:
    """Keep only A-Z letters, uppercased (default style)."""
    return "".join(c.upper() for c in text if is_letter(c))


def to_nums(letters: str) -> list[int]:
    return [ord(c) - 65 for c in letters]


def to_text(nums) -> str:
    return "".join(ALPHABET[int(n) % 26] for n in nums)


def idx(c: str) -> int:
    return ord(c.upper()) - 65


def restore_format(original: str, letters: str, keep_format: bool, as_ciphertext: bool) -> str:
    """Put cipher output back into the original text's layout.

    Without keep_format the default style is used: ciphertext UPPERCASE,
    plaintext lowercase, letters only. With keep_format, spaces/punctuation
    and the original letter case are preserved (substitution ciphers only).
    """
    if not keep_format:
        return letters.upper() if as_ciphertext else letters.lower()
    out, it = [], iter(letters)
    for c in original:
        if is_letter(c):
            n = next(it, None)
            if n is None:
                break
            out.append(n.lower() if c.islower() else n.upper())
        else:
            out.append(c)
    out.extend(it)  # any extra letters (shouldn't happen for substitution ciphers)
    return "".join(out)


def require_letters(key: str, what: str = "Key") -> str:
    k = clean(key)
    if not k:
        raise CipherError(f"{what} must contain at least one letter A-Z.")
    return k


def unique_letters(s: str) -> str:
    seen: list[str] = []
    for c in s:
        if c not in seen:
            seen.append(c)
    return "".join(seen)


def keyed_alphabet(keyword: str, alphabet: str = ALPHABET) -> str:
    """Keyword letters (duplicates removed) followed by the rest of the alphabet."""
    head = unique_letters(c for c in clean(keyword) if c in alphabet)
    return head + "".join(c for c in alphabet if c not in head)


def chunks(s, n: int) -> list:
    return [s[i:i + n] for i in range(0, len(s), n)]
