"""Cipher plugin base class and registry.

To add a cipher: create ``core/ciphers/<name>.py`` with a subclass of
:class:`Cipher` decorated with ``@register``. It is discovered automatically
and appears in the GUI with its parameters, visualization and cracker.
"""
from __future__ import annotations

import importlib
import pkgutil
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .text import CipherError, clean, restore_format
from .trace import Chart, Trace

FAMILIES = [
    "Monoalphabetic substitution",
    "Polyalphabetic substitution",
    "Polygraphic substitution",
    "Transposition",
]


@dataclass
class Param:
    name: str
    label: str
    kind: str = "text"  # text | int | choice | bool | multiline
    default: Any = ""
    choices: list[str] | None = None
    minimum: int = 0
    maximum: int = 999
    help: str = ""
    random: Callable[[int], Any] | None = None  # random value given the message length


@dataclass
class Candidate:
    key: str              # human-readable key
    params: dict          # values to load into the cipher's parameter form
    plaintext: str
    score: float          # English likeness 0..1 (higher is better)
    note: str = ""


@dataclass
class CrackResult:
    candidates: list[Candidate] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)


class CrackContext:
    """Passed to ``crack()`` for progress reporting and cancellation."""

    def __init__(self, on_progress: Callable[[float, str], None] | None = None):
        self._on_progress = on_progress
        self._cancel = threading.Event()
        self._last = 0.0

    def progress(self, fraction: float, message: str = "", force: bool = False) -> None:
        now = time.monotonic()
        if self._on_progress and (force or now - self._last > 0.1):
            self._last = now
            self._on_progress(max(0.0, min(1.0, fraction)), message)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()


class Cipher:
    id = ""
    name = ""
    family = FAMILIES[0]
    order = 100
    summary = ""          # one line
    description = ""      # short HTML summary
    help = ""             # Markdown shown in the "?" help window
    params: list[Param] = []
    crack_params: list[Param] = []
    preserves_layout = True   # output letter i depends only on input letter i (keep spaces/case possible)
    crackable = True
    crack_hint = ""
    manual_solver: str | None = None  # "substitution" adds the interactive mapping editor
    examples: list[dict] = []  # {"label", "mode", "text", "params"}

    def defaults(self) -> dict:
        return {p.name: p.default for p in self.params}

    def encrypt(self, letters: str, **params) -> str:
        raise NotImplementedError

    def decrypt(self, letters: str, **params) -> str:
        raise NotImplementedError

    def trace(self, letters: str, mode: str, **params) -> Trace:
        raise NotImplementedError

    def crack(self, letters: str, ctx: CrackContext, **params) -> CrackResult:
        raise CipherError("No automatic cracker for this cipher.")

    def run(self, text: str, mode: str, params: dict, keep_format: bool = False) -> str:
        letters = clean(text)
        if not letters:
            return ""
        p = {**self.defaults(), **params}
        out = self.encrypt(letters, **p) if mode == "encrypt" else self.decrypt(letters, **p)
        return restore_format(text, out, keep_format and self.preserves_layout, mode == "encrypt")


_REGISTRY: dict[str, Cipher] = {}
_loaded = False


def register(cls: type[Cipher]) -> type[Cipher]:
    _REGISTRY[cls.id] = cls()
    return cls


def _load() -> None:
    global _loaded
    _loaded = True
    from . import ciphers
    for m in pkgutil.iter_modules(ciphers.__path__):
        if not m.name.startswith("_"):
            importlib.import_module(f"{ciphers.__name__}.{m.name}")


def all_ciphers() -> list[Cipher]:
    if not _loaded:
        _load()
    fam = {f: i for i, f in enumerate(FAMILIES)}
    return sorted(_REGISTRY.values(), key=lambda c: (fam.get(c.family, 99), c.order, c.name))


def get_cipher(cipher_id: str) -> Cipher:
    all_ciphers()
    return _REGISTRY[cipher_id]
