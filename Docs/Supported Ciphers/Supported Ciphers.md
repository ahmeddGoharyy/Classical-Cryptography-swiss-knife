# Supported Ciphers

This document lists every algorithm built into **Classical Cryptography Swiss Knife**. For each cipher it gives the encryption and decryption rules, a worked example, what the visualizer shows, and how the cracker attacks it. All worked examples come from the lectures or the textbook (Stallings), and the app's test suite (`tests/test_ciphers.py`) checks each one.

## Conventions

| Item | Convention |
|---|---|
| Letter numbering | A = 0, B = 1, …, Z = 25 |
| Arithmetic | mod 26 |
| Default output | Ciphertext in UPPERCASE, plaintext in lowercase, letters only (lecture style) |
| Keep format option | On by default. Spaces and punctuation stay at their original positions for every cipher. Substitution ciphers (Caesar, Monoalphabetic, Vigenère family) also keep each letter's case; ciphers that move letters or add padding (Playfair, Hill, transpositions) use UPPERCASE ciphertext / lowercase plaintext and put padding letters after the last letter. |
| "English likeness" | A 0–100 % score built from English quadgram (4-letter) statistics. The crackers use it to rank candidates. |

## Overview

| # | Cipher | Family | Key | Key space | Crack method in the app |
|---|---|---|---|---|---|
| 1 | Caesar | Monoalphabetic substitution | shift k (any integer, e.g. −3; used mod 26) | 25 | Brute force over all 26 shifts |
| 2 | Monoalphabetic | Monoalphabetic substitution | permutation of the alphabet, or a keyword | 26! ≈ 4 × 10²⁶ | Frequency analysis, then hill climbing, plus a manual solver |
| 3 | Vigenère (repeating key) | Polyalphabetic substitution | keyword | 26^m | Kasiski + index of coincidence, then a Caesar per column |
| 4 | Vigenère (autokey) | Polyalphabetic substitution | keyword (followed by the plaintext) | 26^m | Per-column chi² for each keyword length |
| 5 | One-time pad | Polyalphabetic substitution | random pad ≥ message length | 26^n | Not breakable; shows the pad for any guessed plaintext |
| 6 | Playfair | Polygraphic substitution | keyword → 5×5 square | 25! ≈ 1.5 × 10²⁵ | Simulated annealing over key squares |
| 7 | Hill | Polygraphic substitution | invertible n×n matrix mod 26 | ≈ 26^(n²) | Known-plaintext K = P⁻¹·C, or a ciphertext-only column search (n = 2, 3) |
| 8 | Columnar transposition | Transposition | column order (numbers or keyword) | L! | Exhaustive search over orders (L ≤ 8), hill climbing beyond |
| 9 | Rail fence | Transposition | number of rails | n − 1 | Brute force over the rail count |
| — | Frequency analysis tool | Analysis | — | — | Letter %, IoC, chi², n-grams, Caesar overlay, periodic IoC |

---

## 1. Caesar cipher

**Idea:** replace every letter with the letter *k* places further down the alphabet. Julius Caesar used k = 3.

**Encrypt:** `C = (P + k) mod 26`
**Decrypt:** `P = (C − k) mod 26`

**Algorithm**
1. Convert each letter to its index (A=0 … Z=25).
2. Add k (encrypt) or subtract k (decrypt), then reduce mod 26.
3. Convert the index back to a letter.

**Examples**

| Plaintext | Key | Ciphertext | Source |
|---|---|---|---|
| computer | k = 8 | KWUXCBMZ | Lecture 1 |
| Secrecy | k = 8 | AMKZMKG | Section 1 |
| validation | k = 6 | BGROJGZOUT | Section 1 (decryption exercise) |
| meet me after the toga party | k = 3 | PHHWPHDIWHUWKHWRJDSDUWB | Lecture 1 |

Worked step from the Section 1 example: S = 18 → (18 + 8) mod 26 = 26 mod 26 = 0 → **A**.

**Visualizer:**
- A **cipher wheel** (outer ring = plain, inner ring = cipher) **rotates one position per step** until it reaches the shift k — to the left for a negative k (k = −3 is the same cipher as k = 23).
- For each letter, **hop arrows count +1, +2, … +k** along the plain alphabet, including the Z → A wrap-around. The shift table below confirms the same pair, and the wheel lights it up.
- The input table (P.T / index) and output table (C.T index / C.T) fill in as each result token lands.

**Cracking (brute force):** there are only 26 keys, so the app decrypts with every shift and ranks the results by English likeness and chi². The lecture's "Let's Play" letter (`Cdzq Rstcdmsr…`) cracks to **k = 25** ("Dear Students…").

---

## 2. Monoalphabetic substitution

**Idea:** the key is any permutation of the alphabet. Plain letter *i* becomes the *i*-th letter of the key.

**Key input:** either a 26-letter permutation, or a **keyword**. A keyword builds the cipher alphabet from its letters (duplicates removed) followed by the unused letters in order. For example, ZEBRAS gives `ZEBRASCDFGHIJKLMNOPQTUVWXY`.

**Encrypt:** look up the plain letter in the top row and take the letter below it.
**Decrypt:** find the cipher letter in the bottom row and take the letter above it.

**Lecture key:**

```
plain : a b c d e f g h i j k l m n o p q r s t u v w x y z
cipher: D Q E P R S F T A W X U G O B V H N C M I Z L Y J K
```

| Plaintext | Ciphertext | Source |
|---|---|---|
| Secrecy | CRENREJ | Section 1 |
| computer | EBGVIMRN | Lecture 1 |

> **Note:** the lecture key was reconstructed from the slides, using the slide examples and the homophone table (a→D, b→Q, c→E). The mapping d→P was inferred because it is the only letter left. If your slide shows a different letter, change it in the app's key box.

**Weakness:** the key space is enormous (26!), but substitution **does not change relative letter frequencies**.

**Visualizer:** the 26-column substitution table with the current letter highlighted. Keyword letters are marked, and the P.T/C.T rows fill in step by step.

**Cracking**
1. **Frequency analysis.** Rank cipher letters by frequency and map them to English order (E T A O I N S H R D L C U M W F G Y P B V K J X Q Z) to get a first guess.
2. **Hill climbing.** Swap two letters of the key and keep the swap if the decrypted text scores better on English quadgrams. Repeat until no swap helps, with several random restarts.
3. **Manual solver tab.** Type the plain letter under each cipher letter and watch the partial decryption update live. The tab shows cipher frequencies next to English, flags duplicate assignments in red, and can send the finished key to the visualizer.

Works reliably on about 100 or more letters of ciphertext.

---

## 3. Vigenère cipher (repeating key)

**Idea:** a polyalphabetic cipher. The keyword is repeated until it matches the plaintext length, and each letter is shifted by its key letter using the **Vigenère tableau**. Row = key letter, column = plain letter, cell = cipher letter.

**Encrypt:** `Cᵢ = (Pᵢ + K_(i mod m)) mod 26`
**Decrypt:** `Pᵢ = (Cᵢ − K_(i mod m)) mod 26`

**Example (Section 1):** keyword `easy`, plaintext `Secrecy`

```
P.T       S  E  C  R  E  C  Y
K-stream  E  A  S  Y  E  A  S
C.T       W  E  U  P  I  C  Q
```

The Section 1 exercise, decrypting `rolferv` with key `easy`, gives **nothard**.
Stallings: `wearediscoveredsaveyourself` with key `deceptive` gives `ZICVTWQNGRZGVTWAVZHCQYGLMGJ`.

**Visualizer:**
- The keyword is first copied repeatedly into the key stream, with arrows showing each copy.
- Every step shows the **full 26×26 tableau** next to the table. Arrows show the key letter selecting its **row** and the plain letter selecting its **column**, run along both lanes to the crossing cell, and carry the result back to the output.
- The index arithmetic `(P + K) mod 26` is checked by an arrow as well.

**Cracking**
1. **Kasiski examination.** Repeated sequences of three or more letters are usually the same plaintext encrypted under the same part of the key, so the distances between them are multiples of the key length *m*. The app lists the repeats, their distances, and how often each factor appears.
2. **Index of coincidence.** For each candidate *m*, split the ciphertext into *m* columns and average their IoC. The right *m* gives about 0.066 (English); wrong values give about 0.038 (random). The app plots this as a chart.
3. **Column solving.** Each column is a Caesar cipher, so the app picks the shift with the lowest chi² against English. The resulting candidate keys are ranked by English likeness.

---

## 4. Vigenère cipher (autokey)

**Idea:** the key stream is the **keyword followed by the plaintext itself**, so the key never repeats.

**Encrypt:** `K = keyword ‖ plaintext`, then `Cᵢ = (Pᵢ + Kᵢ) mod 26`
**Decrypt:** `Pᵢ = (Cᵢ − Kᵢ) mod 26`. Each recovered plaintext letter is appended to the key stream, so decryption runs left to right.

**Example (Section 1):** keyword `easy`, plaintext `Secrecy`

```
P.T       S  E  C  R  E  C  Y
K-stream  E  A  S  Y  S  E  C      (easy + sec)
C.T       W  E  U  P  W  G  A
```

The Section 1 exercise, decrypting `zadgyaeqrn` with key `easy`, gives **validation**.

**Visualizer:** the same table and tableau as Vigenère. During decryption the K-stream row starts with only the keyword. Each plaintext letter appears in the key row *m* steps later, so you can watch the feedback.

**Cracking:** guess the keyword length *m*. Positions j, j+m, j+2m, … form a chain that depends only on key letter *j*: P[j] = C[j] − k, then P[j+m] = C[j+m] − P[j], and so on. Each key letter can therefore be chosen on its own by testing all 26 values and keeping the one whose chain looks most like English (chi²). The app does this for every *m* up to the limit and ranks the results.

---

## 5. One-time pad

**Idea:** Vigenère with a **truly random key that is as long as the message** and is **never reused**. The key stream is the pad itself.

**Encrypt / Decrypt:** the same as Vigenère, with `Kᵢ = padᵢ`.

**Example (Section 1):** pad `hilmotry`, plaintext `Computer` → **JWXBIMVP**.

**Security:** unconditionally secure. Every plaintext of the same length is equally likely, so the ciphertext reveals nothing. Its practical problems are **key generation** and **key distribution**.

**Visualizer:** the table and tableau, with the pad as the K-stream. The 🎲 button generates a random pad of the right length.

**"Crack" tab:** explains why analysis fails (the IoC is at random level). If you type a guessed plaintext, it computes the pad `pad = C − guess (mod 26)` that would produce it. This shows that a valid key exists for *any* guess.

---

## 6. Playfair cipher

**Idea:** encrypt **pairs of letters** (digrams) using a 5×5 key square.

**Key square:** write the keyword's letters (duplicates removed, J merged into I), then the rest of the alphabet. For keyword `MONARCHY`:

```
M O N A R
C H Y B D
E F G I K
L P Q S T
U V W X Z
```

**Preparing the plaintext**
1. Replace J with I.
2. Split the text into pairs. If a pair would contain the same letter twice, insert the filler **X** between them (Q if the doubled letter is X).
3. If one letter is left at the end, pad it with the filler.

**Encryption rules for each pair**

| Case | Rule | Example (MONARCHY) |
|---|---|---|
| Same row | take the letter to the **right** of each (wrapping around) | AR → RM |
| Same column | take the letter **below** each (wrapping around) | MU → CM |
| Rectangle | each letter takes the one in **its own row and the other letter's column** | HS → BP, EA → IM |

**Decryption:** the same rules with **left** and **up**. The fillers stay in the output; turn on "Remove fillers" to drop X between identical letters and at the end.

**Examples**

| Plaintext | Keyword | Ciphertext |
|---|---|---|
| balloon (BA LX LO ON) | MONARCHY | IBSUPMNA |
| instruments (IN ST RU ME NT SX) | MONARCHY | GATLMZCLRQXA |
| hide the gold in the tree stump | PLAYFAIR EXAMPLE | BMODZBXDNABEKUDMUIXMMOUVIF |

**Visualizer:**
1. Build the square, with keyword letters marked.
2. Prepare the digrams, with fillers highlighted.
3. For each pair, the square highlights the input letters, the output letters and the row, column or rectangle involved, and names the rule used.

**Cracking (simulated annealing):** start from a random square and make small changes (swap two letters, swap rows or columns, flip the square). The app always accepts an improvement in English score, and accepts a worse square with probability e^(Δ/T) so the search can escape local maxima. The temperature *T* decreases over time. Needs a long ciphertext (about 200+ letters) and some time; the result is stochastic, so run it again if it doesn't converge.

---

## 7. Hill cipher

**Idea:** split the text into blocks of *n* letters and multiply each block by an invertible n×n key matrix **K** mod 26.

**Conventions:** the app supports both. Choose the one your course uses.
- **Row vector:** `C = P · K mod 26` (Stallings)
- **Column vector:** `C = K · P mod 26`

**Key input:** rows separated by `;` (for example `3 3; 2 5`), or a keyword with n² letters (`HILL` → [[7 8] [11 11]]).

**Key validity:** K is invertible mod 26 only if `gcd(det K, 26) = 1`, which means det K must be odd and not divisible by 13.

**Decryption:** `K⁻¹ = (det K)⁻¹ · adj(K) mod 26`
1. Compute det K mod 26.
2. Find (det K)⁻¹ mod 26 with the extended Euclidean algorithm.
3. Compute the adjugate (the transpose of the cofactor matrix). For a 2×2 matrix [[a b] [c d]] it is [[d −b] [−c a]].
4. Multiply and reduce mod 26, then check that K·K⁻¹ ≡ I.

**Worked inverse:** K = [[3 3] [2 5]]
- det = 15 − 6 = 9, and 9⁻¹ ≡ 3 (mod 26) because 9·3 = 27 ≡ 1.
- adj = [[5 −3] [−2 3]] ≡ [[5 23] [24 3]].
- K⁻¹ = 3 · adj ≡ [[15 17] [20 9]].

**Examples**

| Plaintext | Key | Convention | Ciphertext |
|---|---|---|---|
| paymoremoney | 17 17 5; 21 18 21; 2 2 19 | row (Stallings) | RRLMWBKASPDH |
| help | 3 3; 2 5 | column | HIAT |

**Visualizer:**
- **Key check:** the key matrix, its determinant and the gcd check.
- **Inverse (decryption only):** the inverse of the determinant with the Euclid steps, the adjugate, and K⁻¹ with a K·K⁻¹ = I check.
- **Blocks:** for every block, `vector · matrix = sums → mod 26 → letters`, with the full arithmetic written out (for example `c1 = 15·17 + 0·21 + 24·2 = 303 ≡ 17 → R`).

**Cracking**
- **Known-plaintext attack (any n):** take *n* plaintext blocks that form an invertible matrix **P**, with the matching ciphertext blocks **C**. Then `K = P⁻¹ · C (mod 26)`.
- **Ciphertext-only attack (n = 2 or 3):** each plaintext letter position *j* depends only on column *j* of K⁻¹. The app tries all 26ⁿ possible columns and keeps the ones whose output has English-like letter frequencies (lowest chi²). It then combines the best columns into invertible matrices and ranks the results by quadgram score.

---

## 8. Columnar transposition

**Idea:** letters are rearranged, not replaced. Write the plaintext row by row under the key, then read the **columns** top to bottom in key order.

**Key input:**
- A numeric order such as `4 3 1 2 5 6 7`: the column labelled 1 is read first.
- A **keyword** such as `ZEBRAS`: its letters are ranked alphabetically, with ties broken left to right, which gives Z=6 E=3 B=2 R=4 A=1 S=5.

**Options:**
- Pad the last row with X (on by default). With padding off, the table is irregular.
- **Rounds:** 2 rounds gives a double transposition.

**Decrypt:**
1. Work out the column lengths. When the table is irregular, the first `n mod L` columns are one letter longer.
2. Fill the columns in key order.
3. Read the rows.

**Examples**

| Plaintext | Key | Ciphertext |
|---|---|---|
| attack postponed until two am xyz | 4 3 1 2 5 6 7 | TTNAAPTMTSUOAODWCOIXKNLYPETZ |
| we are discovered flee at once (no pad) | ZEBRAS | EVLNACDTESEAROFODEECWIREE |

**Visualizer:** the key and rank header with the table filling row by row (padding highlighted), then each column highlighted as it is read into the ciphertext. Decryption shows the column lengths, the columns being filled in rank order, and the rows being read.

**Cracking:** a transposition keeps letter frequencies identical to English, which is the tell. For each key length up to 8 the app tries **every** column order; for longer keys it uses hill climbing with column swaps. Candidates are ranked by quadgram score.

---

## 9. Rail fence cipher

**Idea:** write the plaintext in a **zigzag** over *k* rails, then read rail by rail.

**Example:** depth 2, `meet me after the toga party`

```
m . e . m . a . t . r . h . t . g . p . r . y
. e . t . e . f . e . t . e . o . a . a . t .
```

Reading rail 1 then rail 2 gives **MEMATRHTGPRYETEFETEOAAT** (Stallings).
With 3 rails, `we are discovered flee at once` gives `WECRLTEERDSOEEFEAOCAIVDEN`.

**Decrypt:**
1. Draw the zigzag pattern for the message length.
2. Count the letters on each rail.
3. Fill each rail with that many ciphertext letters, in order.
4. Read along the zigzag.

**Visualizer:** the rail grid with a **zigzag guide line** connecting the letters in order.
- **Encryption:** letters drop straight down onto their rail one at a time, then each rail streams into the ciphertext.
- **Decryption:** the zigzag is marked with `?`, each rail is filled with its share of the ciphertext, and the plaintext is read back along the zigzag.

**Cracking:** brute force. The only key is the number of rails (2 to n−1), so the app ranks every option by English likeness.

---

## Frequency analysis tool

A standalone page (Tools → Frequency analysis) for any text:

- **Letter frequency chart:** the text compared with English, sorted A–Z or by frequency.
- **Caesar overlay:** a slider shifts the English distribution by *k* and shows the chi² at that shift; "Best shift" finds the minimum. This is a visual way to crack a Caesar cipher by hand.
- **Statistics:**
  - letter count
  - **index of coincidence**: `IoC = Σ fᵢ(fᵢ−1) / (N(N−1))`, about 0.0667 for English and 0.0385 for random text
  - chi² against English: `χ² = Σ (observedᵢ − expectedᵢ)² / expectedᵢ`
  - English likeness
  - an automatic hint about which cipher family produced the text
- **IoC by period:** the average column IoC for periods 1–20. Peaks reveal a Vigenère key length.
- **N-grams:** the top bigrams, trigrams and doubled letters, next to the most common English ones (TH HE IN ER AN…, THE AND ING…).

**Interpreting the statistics**

| Observation | Likely cipher |
|---|---|
| IoC ≈ 0.066 and letter frequencies match English | Transposition |
| IoC ≈ 0.066 but the frequency shape is relabelled | Monoalphabetic substitution (Caesar, keyword…) |
| IoC well below 0.06 (flat distribution) | Polyalphabetic (Vigenère) or a one-time pad |
| In between | Polygraphic (Playfair / Hill) or a Vigenère with a short key |

---

## Adding a new cipher

1. Create `cryptoknife/core/ciphers/<name>.py`.
2. Subclass `Cipher` and decorate the class with `@register`.
3. Implement `encrypt`, `decrypt` and `trace`. `crack` is optional.
4. Declare `params` (they become the form fields in the GUI) and `examples`.
5. Add a known-answer test to `tests/test_ciphers.py`.
6. Add a section to this document.

The GUI picks the cipher up automatically: it appears in the sidebar under its `family`, and the visualizer draws whatever grids the `trace()` steps describe.
