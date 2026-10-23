"""Standalone frequency analysis tool."""
from __future__ import annotations

from collections import Counter

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QBoxLayout, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QPushButton, QSlider,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ..core.analysis import (ENGLISH_FREQ, ENGLISH_IOC, RANDOM_IOC, best_caesar_shift, chi_squared, counts,
                             get_scorer, index_of_coincidence, ngrams, periodic_ioc)
from ..core.analysis.frequency import COMMON_BIGRAMS, COMMON_TRIGRAMS
from ..core.text import ALPHABET, clean
from ..core.trace import Chart
from .samples import ENGLISH_SAMPLE, example_ciphertext
from .widgets import (Card, ChartView, FlowLayout, HelpButton, MonoText, Responsive, SegmentedTabs, label, mono_font,
                      vscroll)

HELP = f"""
## What is frequency analysis?
Every language uses some letters far more than others. In English, **E T A O I N S H R** cover about 70 % of
all letters. Many classical ciphers leave traces of these statistics in the ciphertext.

## What the tool shows
- **Letter frequencies** — the text's letters (blue) next to English (orange).
- **Shift English by k** — slides the English bars by k places. If the text is a Caesar cipher, one shift
  makes the bars line up (lowest chi²). **Best shift** finds it.
- **IoC by period** — splits the text into m columns and averages their IoC. A peak at m (and its multiples)
  reveals a Vigenère key length.
- **N-grams** — the most common pairs, triples and doubled letters. Compare with English:
  {' '.join(COMMON_BIGRAMS)} / {' '.join(COMMON_TRIGRAMS)}.

## The numbers
- **Index of coincidence (IoC)** = Σ fᵢ(fᵢ−1) / (N(N−1)) — the probability that two random letters of the
  text are equal. English ≈ {ENGLISH_IOC:.4f}, random letters ≈ {RANDOM_IOC:.4f}.
- **Chi² vs English** = Σ (observed − expected)² / expected — lower means closer to English letter counts.
- **English likeness** — how English the text reads, from 4-letter-group (quadgram) statistics.

## Which cipher is it?
| Observation | Likely cipher |
|---|---|
| IoC ≈ 0.066 and frequencies match English | Transposition (columnar, rail fence) |
| IoC ≈ 0.066 but the frequency shape is relabelled | Monoalphabetic substitution (Caesar, keyword…) |
| IoC well below 0.06, flat bars | Polyalphabetic (Vigenère) or Enigma |
| In between | Polygraphic (Playfair, Hill) or a short-key Vigenère |
"""


class FrequencyPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(label("Frequency analysis", "h1"))
        row.addWidget(label("Tool", "chip"), 0, Qt.AlignVCenter)
        row.addWidget(HelpButton("Frequency analysis", HELP), 0, Qt.AlignVCenter)
        row.addStretch(1)
        titles.addLayout(row)
        titles.addWidget(label("Compare the letter statistics of any text with English.", "muted"))
        head.addLayout(titles, 1)
        lay.addLayout(head)

        split = QWidget()
        body = QVBoxLayout(split)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        top = QWidget()
        tl = QBoxLayout(QBoxLayout.LeftToRight, top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(14)
        inp = Card("Text")
        self.input = MonoText("Paste any text or ciphertext…")
        self.input.textChanged.connect(lambda: self._timer.start())
        inp.add(self.input, 1)
        btn_box = QWidget()
        btns = FlowLayout(btn_box, spacing=8)
        for text, fn in (("Load example ciphertext", example_ciphertext), ("Load English text", lambda: ENGLISH_SAMPLE),
                         ("Clear", lambda: "")):
            b = QPushButton(text)
            b.setObjectName("ghost")
            b.clicked.connect(lambda _=False, fn=fn: self.input.setPlainText(fn()))
            btns.addWidget(b)
        inp.add(btn_box)
        tl.addWidget(inp, 3)
        stats = Card("Statistics", "Frequency analysis", HELP)
        self.stats = label("", wrap=True)
        self.stats.setTextFormat(Qt.RichText)
        self.stats.setAlignment(Qt.AlignTop)
        stats.add(self.stats, 1)
        tl.addWidget(stats, 2)
        body.addWidget(top)

        charts = Card("Charts")
        tabs = SegmentedTabs()
        charts.header.addWidget(tabs.bar)
        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.setContentsMargins(0, 0, 0, 0)
        ctl_box = QWidget()
        ctl = FlowLayout(ctl_box, spacing=10)
        ctl.addWidget(label("Order", "muted"))
        self.order = QComboBox()
        self.order.addItems(["A → Z", "Most frequent first"])
        self.order.currentIndexChanged.connect(self.refresh)
        ctl.addWidget(self.order)
        ctl.addWidget(label("   Shift English by k", "muted"))
        self.shift = QSlider(Qt.Horizontal)
        self.shift.setRange(0, 25)
        self.shift.setFixedWidth(200)
        self.shift.valueChanged.connect(self.refresh)
        ctl.addWidget(self.shift)
        self.shift_lbl = label("chi² at k=0: 0000.0", "muted")
        self.shift_lbl.setFont(mono_font(10))
        self.shift_lbl.setMinimumWidth(self.shift_lbl.sizeHint().width())
        ctl.addWidget(self.shift_lbl)
        best = QPushButton("Best shift")
        best.setObjectName("ghost")
        best.clicked.connect(self._best_shift)
        ctl.addWidget(best)
        ll.addWidget(ctl_box)
        self.chart = ChartView(height=2.6)
        ll.addWidget(self.chart, 1)
        tabs.addTab(lw, "Letter frequencies")
        self.ioc_chart = ChartView(height=2.6)
        tabs.addTab(self.ioc_chart, "IoC by period")
        ng = QWidget()
        ngl = QGridLayout(ng)
        ngl.setContentsMargins(0, 0, 0, 0)
        self.tables = []
        for col, (title, n) in enumerate((("Bigrams", 2), ("Trigrams", 3), ("Doubled letters", 0))):
            ngl.addWidget(label(title, "h2"), 0, col)
            tw = QTableWidget(0, 2)
            tw.setHorizontalHeaderLabels(["n-gram", "count"])
            tw.verticalHeader().setVisible(False)
            tw.setShowGrid(False)
            tw.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            ngl.addWidget(tw, 1, col)
            self.tables.append((tw, n))
        tabs.addTab(ng, "N-grams")
        charts.add(tabs.stack, 1)
        charts.setMinimumHeight(380)
        body.addWidget(charts, 1)
        lay.addWidget(vscroll(split), 1)
        Responsive(self, 860, layouts=[tl])
        self._timer = QTimer(self, singleShot=True, interval=250)
        self._timer.timeout.connect(self.refresh)
        self.refresh()

    def _best_shift(self) -> None:
        s = clean(self.input.toPlainText())
        if s:
            self.shift.setValue(best_caesar_shift(s)[0])

    def refresh(self) -> None:
        s = clean(self.input.toPlainText())
        n = len(s)
        c = counts(s)
        k = self.shift.value()
        obs = {ch: 100 * c[ch] / (n or 1) for ch in ALPHABET}
        eng = {ALPHABET[(i + k) % 26]: ENGLISH_FREQ[ALPHABET[i]] for i in range(26)}  # English shifted by k
        letters = list(ALPHABET) if self.order.currentIndex() == 0 else sorted(ALPHABET, key=lambda ch: -c[ch])
        title = "Text vs English" + (f" shifted by k = {k}" if k else "")
        self.chart.show_chart(Chart(title, letters, {"text %": [obs[ch] for ch in letters],
                                                      "English %": [eng[ch] for ch in letters]}, "%"))
        self.shift_lbl.setText(f"chi² at k={k}: {best_caesar_shift(s)[1][k]:.1f}" if n else "")
        ioc = index_of_coincidence(s)
        chi = chi_squared(s) if n else 0.0
        eng_like = get_scorer().english_likeness(s) if n >= 4 else 0
        if n == 0:
            verdict = "Paste or load a text to analyse it."
        elif n < 20:
            verdict = "Too short for reliable statistics."
        elif eng_like > 0.75:
            verdict = "Reads like English plaintext."
        elif ioc > 0.058 and chi < 150:
            verdict = "English letter frequencies but scrambled order → probably a <b>transposition</b> cipher."
        elif ioc > 0.058:
            verdict = "Uneven like English but relabelled → probably <b>monoalphabetic substitution</b>."
        elif ioc < 0.047:
            verdict = "Flat distribution → probably <b>polyalphabetic</b> (Vigenère) or a rotor machine."
        else:
            verdict = "In between → maybe polygraphic (Playfair/Hill) or a short-key Vigenère."
        rows = [("Letters", f"{n}"), ("Index of coincidence", f"{ioc:.4f}"), ("Chi² vs English", f"{chi:.1f}"),
                ("English likeness", f"{eng_like * 100:.0f}%"),
                ("Distinct letters", f"{sum(1 for v in c.values() if v)}")]
        table = "".join(f"<tr><td style='padding:3px 18px 3px 0; vertical-align:middle'>{a}</td>"
                        f"<td style='vertical-align:middle'><b>{b}</b></td></tr>" for a, b in rows)
        self.stats.setText(f"<table>{table}</table><p style='margin-top:10px'>{verdict}</p>")
        iocs = periodic_ioc(s, 20) if n > 2 else []
        self.ioc_chart.show_chart(Chart("Average column IoC when the text is split with period m",
                                        [str(i) for i in range(1, len(iocs) + 1)], {"IoC": iocs}, "IoC",
                                        {"English": ENGLISH_IOC, "random": RANDOM_IOC}) if iocs else None)
        for tw, k2 in self.tables:
            data = ngrams(s, k2, 25) if k2 else \
                Counter(s[i] * 2 for i in range(n - 1) if s[i] == s[i + 1]).most_common(25)
            tw.setRowCount(len(data))
            for i, (g, cnt) in enumerate(data):
                tw.setItem(i, 0, QTableWidgetItem(g))
                tw.setItem(i, 1, QTableWidgetItem(str(cnt)))
