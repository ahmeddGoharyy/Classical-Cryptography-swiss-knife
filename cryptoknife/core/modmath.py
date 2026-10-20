"""Modular arithmetic and small integer matrices (used by Affine-style math and Hill)."""
from __future__ import annotations

from math import gcd

from .text import CipherError

Matrix = list[list[int]]


def egcd(a: int, b: int) -> tuple[int, int, int]:
    """Return (g, x, y) with a*x + b*y = g = gcd(a, b)."""
    x0, y0, x1, y1 = 1, 0, 0, 1
    while b:
        q, a, b = a // b, b, a % b
        x0, x1 = x1, x0 - q * x1
        y0, y1 = y1, y0 - q * y1
    return a, x0, y0


def egcd_steps(a: int, m: int) -> list[tuple[int, int, int, int]]:
    """Euclid's algorithm rows (a, b, q, r) for showing how an inverse is found."""
    rows = []
    while m:
        q, r = divmod(a, m)
        rows.append((a, m, q, r))
        a, m = m, r
    return rows


def modinv(a: int, m: int = 26) -> int:
    g, x, _ = egcd(a % m, m)
    if g != 1:
        raise CipherError(f"{a % m} has no inverse mod {m} (gcd = {g}).")
    return x % m


def det(M: Matrix) -> int:
    n = len(M)
    if n == 1:
        return M[0][0]
    if n == 2:
        return M[0][0] * M[1][1] - M[0][1] * M[1][0]
    return sum((-1) ** j * M[0][j] * det(minor(M, 0, j)) for j in range(n))


def minor(M: Matrix, i: int, j: int) -> Matrix:
    return [row[:j] + row[j + 1:] for k, row in enumerate(M) if k != i]


def adjugate(M: Matrix) -> Matrix:
    n = len(M)
    if n == 1:
        return [[1]]
    cof = [[(-1) ** (i + j) * det(minor(M, i, j)) for j in range(n)] for i in range(n)]
    return [[cof[j][i] for j in range(n)] for i in range(n)]  # transpose


def mat_mod(M: Matrix, m: int = 26) -> Matrix:
    return [[x % m for x in row] for row in M]


def mat_mul(A: Matrix, B: Matrix, m: int | None = 26) -> Matrix:
    R = [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))] for i in range(len(A))]
    return mat_mod(R, m) if m else R


def transpose(M: Matrix) -> Matrix:
    return [list(r) for r in zip(*M)]


def is_invertible(M: Matrix, m: int = 26) -> bool:
    return gcd(det(M) % m, m) == 1


def mat_inv(M: Matrix, m: int = 26) -> Matrix:
    d = det(M) % m
    if gcd(d, m) != 1:
        raise CipherError(f"Matrix is not invertible mod {m}: det = {d}, gcd(det, {m}) = {gcd(d, m)}.")
    di = modinv(d, m)
    return [[(di * x) % m for x in row] for row in adjugate(M)]
