"""Hill cipher: blocks of n letters multiplied by an invertible n×n key matrix mod 26."""
from __future__ import annotations

import itertools
import math
import random
import re

import numpy as np

from ..analysis import ENGLISH_FREQ, get_scorer
from ..cipher import Candidate, Cipher, CrackResult, Param, register
from ..modmath import Matrix, adjugate, det, egcd_steps, is_invertible, mat_inv, mat_mul, modinv, transpose
from ..text import ALPHABET, CipherError, chunks, clean, to_nums, to_text
from ..trace import Arrow, Cell, Grid, Label, Row, Step, Trace, fan, letters_grid, limit, stream_grid

ROW = "Row vector: C = P·K"
COL = "Column vector: C = K·P"


def parse_matrix(key: str) -> Matrix:
    """'17 17 5; 21 18 21; 2 2 19', one row per line, n² numbers, or n² letters ('HILL')."""
    key = key.strip()
    if not key:
        raise CipherError("Enter a key matrix, e.g. “3 3; 2 5” or a keyword like HILL.")
    if re.search(r"\d", key):
        rows = [r for r in re.split(r"[;\n]|\]\s*,?\s*\[", key) if re.search(r"\d", r)]
        nums = [[int(x) for x in re.findall(r"-?\d+", r)] for r in rows]
        if len(nums) == 1:
            flat = nums[0]
            n = math.isqrt(len(flat))
            if n * n != len(flat):
                raise CipherError(f"{len(flat)} numbers is not a square matrix (need 4, 9, 16…).")
            nums = [flat[i * n:(i + 1) * n] for i in range(n)]
    else:
        letters = to_nums(clean(key))
        n = math.isqrt(len(letters))
        if n * n != len(letters) or n < 1:
            raise CipherError(f"A letter key needs a square number of letters (4, 9, 16…); got {len(letters)}.")
        nums = [letters[i * n:(i + 1) * n] for i in range(n)]
    n = len(nums)
    if any(len(r) != n for r in nums):
        raise CipherError("The key matrix must be square (every row with the same number of entries).")
    M = [[x % 26 for x in r] for r in nums]
    d = det(M) % 26
    if math.gcd(d, 26) != 1:
        raise CipherError(f"Key matrix is not invertible mod 26: det = {d}, gcd({d}, 26) = {math.gcd(d, 26)}. "
                          "The determinant must be odd and not divisible by 13.")
    return M


def format_matrix(M: Matrix) -> str:
    return "; ".join(" ".join(str(x) for x in r) for r in M)


def _random_key(_n: int) -> str:
    while True:
        M = [[random.randrange(26) for _ in range(2)] for _ in range(2)]
        if is_invertible(M):
            return format_matrix(M)


def matrix_grid(M: Matrix, title: str = "", hl_col: int | None = None, hl_row: int | None = None,
                letters: bool = False, style: str = "key", id: str = "") -> Grid:
    """Matrix grid; cell ids f"{id}{i}_{j}", whole-grid id ``id``."""
    cells = []
    for i, r in enumerate(M):
        line = []
        for j, x in enumerate(r):
            st = "active" if (j == hl_col or i == hl_row) else style
            line.append(Cell(str(x), st, ALPHABET[x % 26] if letters else "", f"{id}{i}_{j}" if id else ""))
        cells.append(line)
    return Grid(cells, title, id=id)


def vector_grid(v: list, title: str = "", column: bool = False, style: str = "input", sub=None, id: str = "",
                styles: dict[int, str] | None = None) -> Grid:
    """Vector as a row or column; cell ids f"{id}{i}", whole-grid id ``id``."""
    styles = styles or {}
    cells = [Cell(str(x), styles.get(i, style), sub[i] if sub else "", f"{id}{i}" if id else "")
             for i, x in enumerate(v)]
    return Grid([[c] for c in cells] if column else [cells], title, id=id)


@register
class Hill(Cipher):
    id = "hill"
    name = "Hill"
    family = "Polygraphic substitution"
    order = 20
    preserves_layout = False
    summary = "Multiply blocks of n letters by an invertible key matrix mod 26."
    description = ("Split the plaintext into blocks of n letters (pad with X). Each block is a vector "
                   "multiplied by the n×n key matrix K mod 26. Decryption uses K⁻¹ = det(K)⁻¹ · adj(K) mod 26, "
                   "which exists only if gcd(det K, 26) = 1.<br>Choose the <b>convention</b> your course uses: "
                   "row vectors (C = P·K) or column vectors (C = K·P).")
    crack_hint = ("Known-plaintext attack: with n blocks of matching plaintext/ciphertext, K = P⁻¹·C. "
                  "Ciphertext-only (n = 2 or 3): every column of K⁻¹ is searched separately by letter "
                  "frequencies, then the best columns are combined.")
    help = """## Idea
Split the text into blocks of **n** letters and multiply each block by an invertible **n × n key matrix** mod 26.

## Formulas
- Row vectors: `C = P · K mod 26`
- Column vectors: `C = K · P mod 26`

Choose the convention your textbook uses in the key settings.

## Valid keys
K must be invertible mod 26: **gcd(det K, 26) = 1**, so det K must be odd and not a multiple of 13.

## Decryption
`K⁻¹ = (det K)⁻¹ · adj(K) mod 26`
1. det K mod 26
2. its inverse mod 26 (extended Euclidean algorithm)
3. adjugate — for 2 × 2 `[[a b] [c d]]` it is `[[d −b] [−c a]]`
4. multiply and reduce mod 26

## Example
K = `[[3 3] [2 5]]`: det = 9, 9⁻¹ ≡ 3 (mod 26), K⁻¹ = `[[15 17] [20 9]]`.

## Security
Hides single-letter frequencies, but is **linear**: a few known plaintext/ciphertext blocks reveal the key (K = P⁻¹ · C).
"""
    params = [
        Param("key", "Key matrix", "text", "3 3; 2 5",
              help="Rows separated by ';' (e.g. '3 3; 2 5'; negative entries are fine, taken mod 26), "
                   "or a keyword with n² letters (e.g. HILL)",
              random=_random_key),
        Param("convention", "Convention", "choice", ROW, choices=[ROW, COL]),
        Param("filler", "Padding letter", "text", "X"),
    ]
    crack_params = [
        Param("size", "Matrix size n", "int", 2, minimum=2, maximum=4),
        Param("known", "Known plaintext", "text", "",
              help="Optional: the start of the message, enables the known-plaintext attack"),
        Param("convention", "Convention", "choice", ROW, choices=[ROW, COL]),
    ]
    examples = [
        {"label": 'Encrypt: 3×3 key, paymoremoney', "mode": 'encrypt', "text": 'paymoremoney', "params": {'key': '17 17 5; 21 18 21; 2 2 19', 'convention': 'Row vector: C = P·K'}},
        {"label": 'Encrypt: 2×2 key, short example', "mode": 'encrypt', "text": 'short example', "params": {'key': '3 3; 2 5', 'convention': 'Row vector: C = P·K'}},
        {"label": 'Encrypt: column convention, help', "mode": 'encrypt', "text": 'help', "params": {'key': '3 3; 2 5', 'convention': 'Column vector: C = K·P'}},
        {"label": 'Decrypt: 2×2 key 3 3; 2 5', "mode": 'decrypt', "text": 'QLYXNZRROHPB', "params": {'key': '3 3; 2 5', 'convention': 'Row vector: C = P·K'}},
    ]

    @staticmethod
    def _row_matrix(key: str, convention: str) -> tuple[Matrix, Matrix]:
        """(K as typed, matrix M used with row vectors: c = p·M)."""
        K = parse_matrix(key)
        return K, (K if convention != COL else transpose(K))

    @staticmethod
    def _apply(letters: str, M: Matrix) -> str:
        n = len(M)
        out = []
        for blk in chunks(to_nums(letters), n):
            out.extend(sum(blk[i] * M[i][j] for i in range(n)) % 26 for j in range(n))
        return to_text(out)

    @staticmethod
    def _pad(letters: str, n: int, filler: str) -> str:
        f = (clean(filler) or "X")[0]
        return letters + f * (-len(letters) % n)

    def encrypt(self, letters, key="", convention=ROW, filler="X", **_):
        _, M = self._row_matrix(key, convention)
        return self._apply(self._pad(letters, len(M), filler), M)

    def decrypt(self, letters, key="", convention=ROW, filler="X", **_):
        _, M = self._row_matrix(key, convention)
        if len(letters) % len(M):
            raise CipherError(f"Ciphertext length must be a multiple of {len(M)}.")
        return self._apply(letters, mat_inv(M))

    def trace(self, letters, mode, key="", convention=ROW, filler="X", **_):
        enc = mode == "encrypt"
        col = convention == COL
        K, _ = self._row_matrix(key, convention)
        n = len(K)
        notes: list[str] = []
        src = limit(letters, notes)
        src = src[:len(src) - len(src) % n] if (not enc and len(src) % n) else src
        steps = []
        d = det(K)
        steps.append(Step("Key matrix", f"K is {n}×{n}. det(K) = {d} ≡ {d % 26} (mod 26); gcd({d % 26}, 26) = "
                          f"{math.gcd(d % 26, 26)} → invertible, so decryption is possible.\n"
                          f"Convention: {convention}.", [[matrix_grid(K, "K", letters=True, id="K")]]))
        if enc:
            A = K
            padded = self._pad(src, n, filler)
            fill = set(range(len(src), len(padded)))
        else:
            dm = d % 26
            dinv = modinv(dm)
            adj = adjugate(K)
            adjm = [[x % 26 for x in r] for r in adj]
            A = mat_inv(K)
            euclid = "\n".join(f"  {a} = {q}·{b} + {r}" for a, b, q, r in egcd_steps(dm, 26))
            steps.append(Step("Inverse of the determinant",
                              f"Need d⁻¹ with d·d⁻¹ ≡ 1 (mod 26), d = det K mod 26 = {dm}.\nEuclid:\n{euclid}\n"
                              f"→ {dm}⁻¹ ≡ {dinv} (mod 26)  check: {dm}·{dinv} = {dm * dinv} ≡ 1",
                              [[matrix_grid(K, "K", id="K"), Label("det →"),
                                vector_grid([dm], "det K mod 26", style="normal", id="det"), Label("inverse →"),
                                vector_grid([dinv], "d⁻¹", style="current", id="dinv")]],
                              [Arrow("K", "det", f"det = {d}", 0, carry=str(dm), reveal=True),
                               Arrow("det", "dinv", "Euclid", 1, carry=str(dinv), reveal=True, kind="result")]))
            steps.append(Step("Adjugate matrix", "adj(K) = transpose of the cofactor matrix "
                              "(for 2×2: swap the diagonal, negate the other two), then reduce mod 26.",
                              [[matrix_grid(K, "K", id="K"), Label("→"),
                                matrix_grid(adj, "adj(K)", style="normal", id="adj"), Label("→"),
                                matrix_grid(adjm, "adj(K) mod 26", style="normal", id="adjm")]],
                              [Arrow("K", "adj", "cofactors", 0, carry="adj", reveal=True),
                               Arrow("adj", "adjm", "mod 26", 1, carry="mod", reveal=True)]))
            steps.append(Step("Inverse key matrix", f"K⁻¹ = d⁻¹ · adj(K) mod 26 = {dinv} · adj(K) mod 26.\n"
                              "Check: K · K⁻¹ ≡ I (identity).",
                              [[vector_grid([dinv], "d⁻¹", style="current", id="dinv"), Label("·"),
                                matrix_grid(adjm, "adj(K)", style="normal", id="adjm"),
                                Label("="), matrix_grid(A, "K⁻¹", letters=True, id="Kinv"),
                                Label("check  K·K⁻¹ ="), matrix_grid(mat_mul(K, A), "I", style="result", id="I")]],
                              [Arrow("dinv", "Kinv", f"× {dinv}", 0, carry=f"×{dinv}", reveal=True, kind="key"),
                               Arrow("adjm", "Kinv", "mod 26", 0, reveal=True),
                               Arrow("Kinv", "I", "K·K⁻¹", 1, carry="I", reveal=True, kind="result")]))
            padded, fill = src, set()
        blocks = chunks(padded, n)
        a, b = ("P.T blocks", "C.T blocks") if enc else ("C.T blocks", "P.T blocks")
        out_blocks = []
        for blk in blocks:
            v = to_nums(blk)
            if col:
                out_blocks.append(to_text(sum(A[i][j] * v[j] for j in range(n)) % 26 for i in range(n)))
            else:
                out_blocks.append(to_text(sum(v[i] * A[i][j] for i in range(n)) % 26 for j in range(n)))
        rows = [Row(a, blocks, "input", given=True, id="bin"), Row(b, out_blocks, "result", id="bout")]
        if enc:
            steps.append(Step("Split into blocks", f"Blocks of {n} letters"
                              + (f", padded with {filler or 'X'}" if fill else "") + f": {' '.join(blocks)}",
                              [[letters_grid(padded, "pt", "Prepared text", "input", {j: "filler" for j in fill})],
                               [stream_grid(rows, -1)]],
                              fan(((f"pt{j}", f"bin{j // n}") for j in range(min(len(padded), 60))), 0,
                                  f"groups of {n}", reveal=False)))
        name = "K" if enc else "K⁻¹"
        pc = "c" if enc else "p"
        for bi, blk in enumerate(blocks):
            v = to_nums(blk)
            terms_all, raw = [], []
            for j in range(n):
                terms = [(A[j][i], v[i]) for i in range(n)] if col else [(v[i], A[i][j]) for i in range(n)]
                terms_all.append(terms)
                raw.append(sum(x * y for x, y in terms))
            res = [r % 26 for r in raw]

            def scene(j: int | None, done: int):
                """j = component being computed (None = conversion step); done = components finished."""
                vin = vector_grid(v, f"{blk} as numbers", column=col, sub=list(blk), id="v")
                mat = matrix_grid(A, name, hl_col=None if col else j, hl_row=j if col else None, id="M")
                sums = vector_grid([raw[k] if k < done or k == j else "" for k in range(n)], "sum", column=col,
                                   style="normal", id="s", styles={k: "empty" for k in range(n) if k > (j if j is not None else done - 1)})
                mods = vector_grid([res[k] if k < done or k == j else "" for k in range(n)], "mod 26", column=col,
                                   style="current", sub=[out_blocks[bi][k] if k < done or k == j else "" for k in range(n)],
                                   id="r", styles={k: "empty" for k in range(n) if k > (j if j is not None else done - 1)})
                panels = ([mat, Label("·"), vin] if col else [vin, Label("·"), mat]) + \
                    [Label("="), sums, Label("mod 26 →"), mods]
                hide = done < n  # output block appears only once every component is done
                rows_now = rows if not hide else [rows[0], Row(b, out_blocks, "result", id="bout",
                                                               reveal=[k if k != bi else 10 ** 6 for k in range(len(blocks))])]
                return [panels, [stream_grid(rows_now, bi)]]

            steps.append(Step(f"Block {bi + 1}/{len(blocks)}: {blk} → numbers",
                              f"Convert the block to numbers (A=0 … Z=25): {blk} → {v}",
                              scene(None, 0), [Arrow(f"bin{bi}", "v", "letters → numbers", 0, carry=blk, reveal=True)]))
            for j in range(n):
                terms = terms_all[j]
                expr = " + ".join(f"{x}·{y}" for x, y in terms)
                if col:
                    mul = [Arrow(f"v{i}", f"M{j}_{i}", f"× {A[j][i]}" if i == 0 else "", 0, carry=str(v[i]))
                           for i in range(n)]
                    gather = [Arrow(f"M{j}_{i}", f"s{j}", f"Σ = {raw[j]}" if i == 0 else "", 1,
                                    carry=str(A[j][i] * v[i]), reveal=True, kind="key") for i in range(n)]
                    lane = f"row {j + 1} of {name}"
                else:
                    mul = [Arrow(f"v{i}", f"M{i}_{j}", f"× {A[i][j]}" if i == 0 else "", 0, carry=str(v[i]))
                           for i in range(n)]
                    gather = [Arrow(f"M{i}_{j}", f"s{j}", f"Σ = {raw[j]}" if i == 0 else "", 1,
                                    carry=str(v[i] * A[i][j]), reveal=True, kind="key") for i in range(n)]
                    lane = f"column {j + 1} of {name}"
                arrows = mul + gather + [Arrow(f"s{j}", f"r{j}", f"mod 26 = {res[j]}", 2, reveal=True, kind="result")]
                steps.append(Step(f"Block {bi + 1}, letter {j + 1}/{n}: {pc}{j + 1} = {res[j]} → {out_blocks[bi][j]}",
                                  f"① multiply the vector by {lane}: {expr}\n② add: {pc}{j + 1} = {raw[j]}\n"
                                  f"③ reduce: {raw[j]} mod 26 = {res[j]} → {out_blocks[bi][j]}",
                                  scene(j, j), arrows))
            steps.append(Step(f"Block {bi + 1}/{len(blocks)}: {blk} → {out_blocks[bi]}",
                              f"Numbers back to letters: {res} → {out_blocks[bi]}",
                              scene(None, n), [Arrow("r", f"bout{bi}", "numbers → letters", 0,
                                                     carry=out_blocks[bi], reveal=True, kind="result")]))
        result = "".join(out_blocks)
        steps.append(Step("Done", f"Result: {result}", [[matrix_grid(A, name)], [stream_grid(rows, None)]]))
        return Trace(steps, result, notes)

    # ----- cracking ---------------------------------------------------------------------------
    def crack(self, letters, ctx, size=2, known="", convention=ROW, **_):
        n = int(size)
        res = CrackResult()
        sc = get_scorer()
        ct = letters[:len(letters) - len(letters) % n]
        if len(ct) < n * n:
            raise CipherError(f"Need at least {n * n} ciphertext letters for a {n}×{n} key.")
        kp = clean(known)
        if kp:
            M = self._known_plaintext(ct, kp, n, res)
        else:
            M = None
            if n > 3:
                raise CipherError("Ciphertext-only search supports n = 2 or 3. For bigger keys, give known plaintext.")
            self._ciphertext_only(ct, n, res, ctx, convention)
            return res
        if M is not None:
            K = M if convention != COL else transpose(M)
            pt = self._apply(ct, mat_inv(M))
            res.candidates.append(Candidate(format_matrix(K), {"key": format_matrix(K), "convention": convention},
                                            pt, sc.english_likeness(pt), "known-plaintext attack"))
        return res

    def _known_plaintext(self, ct: str, kp: str, n: int, res: CrackResult) -> Matrix | None:
        m = min(len(kp), len(ct)) // n
        P_blocks = [to_nums(kp[i * n:(i + 1) * n]) for i in range(m)]
        C_blocks = [to_nums(ct[i * n:(i + 1) * n]) for i in range(m)]
        res.log.append("Known-plaintext attack (row vectors): stack n plaintext blocks as rows of P and the "
                       "matching ciphertext blocks as rows of C. Then C = P·K, so K = P⁻¹·C (mod 26).\n")
        for combo in itertools.combinations(range(m), n):
            P = [P_blocks[i] for i in combo]
            if is_invertible(P):
                C = [C_blocks[i] for i in combo]
                Pinv = mat_inv(P)
                M = mat_mul(Pinv, C)
                res.log.append(f"Using blocks {[i + 1 for i in combo]}:")
                res.log.append(f"  P = {P}\n  C = {C}\n  det(P) = {det(P) % 26} (invertible)\n"
                               f"  P⁻¹ = {Pinv}\n  K = P⁻¹·C = {M}  (row convention)")
                res.log.append(f"  Column-convention key (transpose): {transpose(M)}")
                return M
        res.log.append(f"No set of {n} known blocks gives an invertible P matrix — supply more known plaintext "
                       f"(have {m} block(s)).")
        return None

    def _ciphertext_only(self, ct: str, n: int, res: CrackResult, ctx, convention: str) -> None:
        sc = get_scorer()
        C = np.array(to_nums(ct)).reshape(-1, n)
        res.log.append("Ciphertext-only attack. With row vectors, plaintext letter j of each block is "
                       "p_j = Σ c_i·D[i][j], where D = K⁻¹. So each column of D can be guessed on its own: try "
                       f"all 26^{n} = {26 ** n} columns, keep those whose output letters have English-like "
                       "frequencies (lowest chi²), then try combinations and score with quadgrams.\n")
        cands = np.array(list(itertools.product(range(26), repeat=n)))
        out = (C @ cands.T) % 26  # blocks × candidates
        expected = np.array([ENGLISH_FREQ[ch] / 100 for ch in ALPHABET]) * C.shape[0]
        counts = np.zeros((cands.shape[0], 26))
        for letter in range(26):
            counts[:, letter] = (out == letter).sum(axis=0)
        chi = ((counts - expected) ** 2 / expected).sum(axis=1)
        top = np.argsort(chi)[:14 if n == 2 else 10]
        res.log.append("Best columns by chi²: " + ", ".join(f"{list(cands[i])} ({chi[i]:.0f})" for i in top[:8]))
        scored = []
        perms = list(itertools.permutations(top, n))
        for t, combo in enumerate(perms):
            if ctx.cancelled:
                break
            D = [[int(cands[c][i]) for c in combo] for i in range(n)]
            if not is_invertible(D):
                continue
            pt = self._apply(ct, D)
            scored.append((sc.score(pt), D, pt))
            ctx.progress(t / len(perms), "combining columns")
        scored.sort(key=lambda x: -x[0])
        seen = set()
        for s, D, pt in scored[:10]:
            M = mat_inv(D)
            K = M if convention != COL else transpose(M)
            k = format_matrix(K)
            if k in seen:
                continue
            seen.add(k)
            res.candidates.append(Candidate(k, {"key": k, "convention": convention}, pt, sc.english_likeness(pt)))
        if res.candidates:
            res.log.append(f"\nBest key: {res.candidates[0].key} → {res.candidates[0].plaintext[:60]}")
