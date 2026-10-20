# Classical Cryptography Swiss Knife

A desktop app (Python + PySide6) to **visualize, solve and crack classical ciphers** step by step.

Made by **Ahmed El Gohary**.

- **Ciphers:** Caesar, Monoalphabetic, Vigenère (repeating key / autokey), One-time pad, Playfair, Hill, Columnar transposition, Rail fence
- **Step-by-step animated visualizer** for any plaintext/ciphertext and key (Encrypt / Decrypt buttons, play/pause/step/speed, can be turned off)
- **“?” help windows** explaining every cipher, key setting, visualization legend and attack
- **Quick navigation:** top-bar cipher switcher / command palette (**Ctrl+K**), light & dark themes, responsive layout
- **Crackers:** brute force, frequency analysis with a manual substitution solver, Kasiski + IoC, hill climbing, simulated annealing, and the Hill known-plaintext attack
- **Frequency analysis tool:** letter chart vs English, IoC, chi², n-grams, Caesar overlay, periodic IoC

The details of each algorithm are in [Docs/Supported Ciphers](Docs/Supported%20Ciphers/Supported%20Ciphers.md).

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

## Test

```bash
.venv/bin/python -m pytest -q
```

## Project layout

```
cryptoknife/
  core/                 pure Python, no GUI (unit-tested)
    text.py             A=0..25 helpers, cleaning, keep-format restore
    modmath.py          gcd / modular inverse / matrices mod 26
    trace.py            Step/Grid/Cell scene model the visualizer draws
    cipher.py           Cipher base class, Param, registry
    ciphers/            one module per cipher (auto-discovered)
    analysis/           frequency, IoC, chi², Kasiski, quadgram scoring
  data/quadgrams.txt    English quadgram counts (tools/build_ngrams.py)
  gui/                  PySide6 app (main window, cipher pages, scene renderer)
tests/                  known-answer tests from the lectures + Stallings
```

To add a cipher, drop a new module into `cryptoknife/core/ciphers/`. The "Adding a new cipher" section of the Supported Ciphers document has the steps.
