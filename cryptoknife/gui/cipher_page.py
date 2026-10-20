"""One page per cipher: step-by-step visualizer + cracker."""
from __future__ import annotations

import html
import traceback

from PySide6.QtCore import QEvent, QObject, QRectF, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QBoxLayout, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QProgressBar, QPushButton, QScrollArea, QSlider, QSplitter,
                               QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from ..core.analysis import ENGLISH_FREQ, ENGLISH_ORDER, counts
from ..core.cipher import Cipher, CrackContext, CrackResult
from ..core.text import ALPHABET, CipherError, clean
from ..core.trace import Chart, Trace
from .scene_view import SceneView
from .sidebar import split_name
from .loading import LoadingOverlay
from .step_player import StepPlayer
from .theme import theme
from .widgets import (Card, ChartView, FlowLayout, HelpButton, MonoText, ParamForm, Responsive, SegmentedTabs,
                      WrapCheckBox, label, mono_font, params_help, status_label, vscroll)

LEGEND = [
    ("active", "Being processed right now (the input letter, key cell or block)"),
    ("current", "Value just produced in this step"),
    ("result", "Output produced in earlier steps"),
    ("key", "Key material (key letters, keyword cells, key matrix)"),
    ("hl", "Highlighted lane: the row, column or region used by the rule"),
    ("filler", "Padding / filler letters added by the cipher"),
    ("header", "Labels and headers"),
    ("empty", "Not computed yet"),
]


def visualization_help() -> str:
    rows = []
    for style, meaning in LEGEND:
        bg, fg, border = theme().cell(style)
        sw = (f"<span style='background:{bg or 'transparent'}; color:{fg}; border:1px solid {border or fg};'>"
              f"&nbsp;&nbsp;A&nbsp;&nbsp;</span>")
        rows.append(f"<tr><td>{sw}</td><td>{meaning}</td></tr>")
    return (
        "<h2>How the visualization works</h2>"
        "<p>Press <b>Encrypt</b> or <b>Decrypt</b>. With <b>Visualize step by step</b> on, the process is "
        "animated from the first step to the last and the output appears when it finishes. Turn it off to get "
        "the result instantly.</p>"
        "<h3>Controls</h3><ul>"
        "<li><b>▶ / ❚❚</b> play or pause (Space)</li>"
        "<li><b>◀ ▶</b> previous / next step (← →), <b>⏮ ⏭</b> first / last step (Home / End)</li>"
        "<li>The keys work while the visualization has focus — click the diagram first if needed.</li>"
        "<li>Drag the slider to scrub, choose a speed, or press <b>Skip to result</b>.</li>"
        "<li>Drag the diagram to pan it; Ctrl + mouse wheel zooms.</li>"
        "<li>Zoom the diagram with the zoom slider.</li></ul>"
        "<h3>Arrows — what goes where</h3><p>Each step plays as a short animation: arrows draw themselves "
        "in order (①, ②, ③…), a token carrying the value travels along each one, and the destination cell "
        "fills in when the token lands. Labels on the arrows show the operation (e.g. <b>+3 mod 26</b>, "
        "<b>row K</b>, <b>swap columns</b>).</p><ul>"
        f"<li><b style='color:{theme().ui['accent']}'>Blue</b> — a value moving to its next stage</li>"
        "<li><b style='color:#f5b84b'>Amber</b> — the key acting (shift, tableau row, matrix entry)</li>"
        f"<li><b style='color:{theme().ui['button']}'>Green</b> — the result being written</li>"
        "<li><b>Dashed grey</b> — a lookup</li></ul>"
        "<h3>Colour legend</h3><table cellspacing='6'>" + "".join(rows) + "</table>"
        "<p>The text above the diagram explains the arithmetic of the current step.</p>"
        "<p>Long messages: the first 120 letters are animated; the output always contains the full result.</p>"
    )


class PanZoom(QObject):
    """Drag the diagram to pan it; Ctrl + mouse wheel zooms it (plain wheel scrolls as usual)."""

    def __init__(self, scroll: QScrollArea, scene: QWidget, zoom: QSlider, on_manual_zoom):
        super().__init__(scene)
        self.scroll, self.scene, self.zoom, self.on_manual_zoom = scroll, scene, zoom, on_manual_zoom
        self._last = None
        scene.setCursor(Qt.OpenHandCursor)
        scene.installEventFilter(self)

    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.MouseButtonPress and ev.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.scene.setFocus(Qt.MouseFocusReason)  # so the player's keyboard shortcuts work afterwards
            self._last = ev.globalPosition().toPoint()
            self.scene.setCursor(Qt.ClosedHandCursor)
            return True
        if t == QEvent.MouseMove and self._last is not None:
            pos = ev.globalPosition().toPoint()
            d = pos - self._last
            self._last = pos
            h, v = self.scroll.horizontalScrollBar(), self.scroll.verticalScrollBar()
            h.setValue(h.value() - d.x())
            v.setValue(v.value() - d.y())
            return True
        if t == QEvent.MouseButtonRelease and self._last is not None:
            self._last = None
            self.scene.setCursor(Qt.OpenHandCursor)
            return True
        if t == QEvent.Wheel and ev.modifiers() & Qt.ControlModifier:
            step = 8 if ev.angleDelta().y() > 0 else -8
            self.on_manual_zoom()
            self.zoom.setValue(self.zoom.value() + step)
            return True
        return False


class VizWindow(QWidget):
    """Separate, freely resizable window that hosts the visualization card while it is popped out."""
    closed = Signal()

    def __init__(self, parent: QWidget, title: str):
        super().__init__(parent, Qt.Window)
        self.setObjectName("content")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setWindowTitle(title)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 16, 16, 16)

    def closeEvent(self, ev) -> None:
        self.closed.emit()
        super().closeEvent(ev)


class CipherPage(QWidget):
    def __init__(self, cipher: Cipher, parent=None):
        super().__init__(parent)
        self.cipher = cipher
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 28, 20)
        lay.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(10)
        name, sub = split_name(cipher.name)
        title = label(name.replace("-", "\u2011"), "h1", wrap=True)  # non-breaking hyphen: no "One-/time"
        title.setMinimumWidth(120)
        row.addWidget(title)
        chip = label(cipher.family, "chip")
        row.addWidget(chip, 0, Qt.AlignVCenter)
        row.addWidget(HelpButton(cipher.name, f"{cipher.help}\n\n## How it is cracked\n{cipher.crack_hint}"),
                      0, Qt.AlignVCenter)
        row.addStretch(1)
        titles.addLayout(row)
        summary = label((f"<b>{html.escape(sub)}</b> · " if sub else "") + html.escape(cipher.summary), "muted", wrap=True)
        summary.setTextFormat(Qt.RichText)
        titles.addWidget(summary)
        head.addLayout(titles, 1)
        self.tabs = SegmentedTabs()
        head.addWidget(self.tabs.bar, 0, Qt.AlignVCenter)
        lay.addLayout(head)
        self.visual = VisualizeTab(cipher)
        self.tabs.addTab(self.visual, "Encrypt / Decrypt")
        if cipher.crackable:
            self.crack = CrackTab(cipher)
            self.tabs.addTab(vscroll(self.crack, 640), "Crack")
            self.crack.useKey.connect(self._use_key)
        lay.addWidget(self.tabs.stack, 1)

    def _use_key(self, params: dict, ciphertext: str) -> None:
        self.visual.load("decrypt", ciphertext, params)
        self.tabs.setCurrentIndex(0)
        self.visual.run("decrypt")


# ---------------------------------------------------------------------------------------------
class VisualizeTab(QWidget):
    """Input + key → press Encrypt/Decrypt → (optional) animated step-by-step playback → output."""

    def __init__(self, cipher: Cipher, parent=None):
        super().__init__(parent)
        self.cipher = cipher
        self.trace: Trace | None = None
        self.mode = "encrypt"
        self._pending = ""
        self._revealed = True
        self._last_step = -1

        # Two panes: controls (own scroll area) | visualization (full height, own scroll area).
        # On narrow windows the panes stack vertically instead.
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(12)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(split)

        top = QWidget()
        grid = QGridLayout(top)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        # Input card
        inp = Card("Input")
        self.examples = QComboBox()
        self.examples.addItem("Load example…")
        for ex in cipher.examples:
            self.examples.addItem(ex["label"])
        self.examples.setEnabled(bool(cipher.examples))
        self.examples.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.examples.setMinimumContentsLength(14)
        self.examples.setToolTip("Fill the input and key with a ready-made example")
        self.examples.activated.connect(self._load_example)
        inp.header.addWidget(self.examples)
        self.input = MonoText("Type the plaintext to encrypt, or the ciphertext to decrypt…")
        self.input.setMinimumHeight(56)
        inp.add(self.input, 1)

        # Key card
        keep_text = ("Keep spaces, punctuation and letter case" if cipher.preserves_layout
                     else "Keep spaces and punctuation")
        key = Card("Key", f"{cipher.name} — key settings",
                   params_help(cipher.params) + f"\n\n**{keep_text}** — spaces and punctuation stay where they were "
                   "in the input. " + ("Each letter also keeps its upper/lower case." if cipher.preserves_layout else
                   "Letter case is not kept because this cipher moves letters: ciphertext is UPPERCASE, plaintext "
                   "lowercase; padding letters are added after the last letter.") + " Turn it off to get letters "
                   "only.")
        self.form = ParamForm(cipher.params, lambda: max(1, len(clean(self.input.toPlainText()))))
        key.add(self.form)
        self.keep = WrapCheckBox(keep_text)
        self.keep.setChecked(True)  # on by default
        key.add(self.keep)
        key.body.addStretch(1)

        # Actions (wrap onto two lines when narrow)
        act = QWidget()
        act_lay = QVBoxLayout(act)
        act_lay.setContentsMargins(0, 0, 0, 0)
        act_lay.setSpacing(6)
        btn_box = QWidget()
        act_lay.addWidget(btn_box)
        actions = FlowLayout(btn_box, spacing=10)
        self.enc_btn = QPushButton("🔒  Encrypt")
        self.dec_btn = QPushButton("🔓  Decrypt")
        for b, mode, sc in ((self.enc_btn, "encrypt", "Ctrl+E"), (self.dec_btn, "decrypt", "Ctrl+D")):
            b.setObjectName("big")
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(f"{mode.capitalize()} ({sc})")
            b.setShortcut(sc)
            b.clicked.connect(lambda _=False, m=mode: self.run(m))
            actions.addWidget(b)
        toggle_box = QWidget()
        toggles = QHBoxLayout(toggle_box)
        toggles.setContentsMargins(4, 8, 0, 0)
        self.viz_toggle = WrapCheckBox("Visualize step by step")
        self.viz_toggle.setChecked(QSettings().value("visualize", True, type=bool))
        self.viz_toggle.toggled.connect(self._toggle_viz)
        toggles.addWidget(self.viz_toggle)
        toggles.addWidget(HelpButton("Visualization", visualization_help, markdown=False))
        actions.addWidget(toggle_box)

        # Output card
        outc = Card("Output")
        self.output = MonoText("The result appears here.", read_only=True)
        outc.add(self.output, 1)
        self.output.setMinimumHeight(84)
        self.loading = LoadingOverlay(self.output)
        btns = QHBoxLayout()
        copy = QPushButton("Copy")
        copy.setObjectName("ghost")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.output.toPlainText()))
        swap = QPushButton("↺  Use as input")
        swap.setObjectName("ghost")
        swap.setToolTip("Move the output into the input box (e.g. to decrypt what you just encrypted)")
        swap.clicked.connect(self._swap)
        btns.addWidget(copy)
        btns.addWidget(swap)
        btns.addStretch(1)
        outc.add(btns)
        self.status = status_label("ok")
        self.error = status_label("error")
        self.notes = status_label("muted")
        outc.add(self.status)
        # errors and "inputs changed" notices sit right under the buttons, where the user is looking
        act_lay.addWidget(self.error)
        act_lay.addWidget(self.notes)
        self._run_inputs = None
        self.input.textChanged.connect(self._inputs_changed)
        self.form.changed.connect(self._inputs_changed)
        self.keep.toggled.connect(self._inputs_changed)
        self._top_grid, self._cards = grid, (inp, key, act, outc)
        self.controls = vscroll(top)
        self.controls.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        split.addWidget(self.controls)

        # Visualization card
        self.viz = Card("Visualization", "Visualization", visualization_help, markdown=False)
        self.viz.header.addWidget(label("Zoom", "muted"))
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(50, 200)
        self.zoom.setValue(100)
        self.zoom.setFixedWidth(84)
        self.zoom.setToolTip("Zoom the diagram (or Ctrl + mouse wheel over it)")
        self.zoom.valueChanged.connect(self._zoom_changed)
        self.viz.header.addWidget(self.zoom)
        self.fit = QCheckBox("Fit")
        self.fit.setToolTip("Zoom each run so the whole visualization fits the panel")
        self.fit.setChecked(True)
        self.fit.toggled.connect(lambda on: on and self._fit())
        self.viz.header.addWidget(self.fit)
        self.expand = QPushButton("⤢  Expand")
        self.expand.setObjectName("ghost")
        self.expand.setCheckable(True)
        self.expand.setToolTip("Give the visualization the whole page (hides the input, key and output)")
        self.expand.toggled.connect(self._toggle_expand)
        self.viz.header.addWidget(self.expand)
        self.popout = QPushButton("⧉  Pop out")
        self.popout.setObjectName("ghost")
        self.popout.setCheckable(True)
        self.popout.setToolTip("Open the visualization in its own window (resize or maximise it freely)")
        self.popout.toggled.connect(self._toggle_popout)
        self.viz.header.addWidget(self.popout)
        self._viz_window: VizWindow | None = None
        ctl = QHBoxLayout()
        ctl.setSpacing(10)
        self.player = StepPlayer()
        self.player.stepChanged.connect(self._show_step)
        self.player.bind_keys(self.viz)
        ctl.addWidget(self.player, 1)
        skip = QPushButton("Skip to result")
        skip.setObjectName("ghost")
        skip.clicked.connect(lambda: self.player.go(self.player.count - 1))
        ctl.addWidget(skip)
        self.viz.add(ctl)
        self.explain = QLabel()
        self.explain.setTextFormat(Qt.RichText)
        self.explain.setWordWrap(True)
        self.explain.setMinimumHeight(54)
        self.explain.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.explain.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.viz.add(self.explain)
        self.scene = SceneView()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.scene)
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("sceneScroll")
        self.scene.focusChanged.connect(self._ensure_visible)
        self._pan = PanZoom(self.scroll, self.scene, self.zoom, lambda: self.fit.setChecked(False))
        self.viz.add(self.scroll, 1)
        split.addWidget(self.viz)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        self.split, self.top = split, top
        self._refit = QTimer(self, singleShot=True, interval=150)
        self._refit.timeout.connect(lambda: self.fit.isChecked() and self._fit())
        self.scroll.installEventFilter(self)
        self.viz.setVisible(self.viz_toggle.isChecked())
        Responsive(self, 900, callback=self._arrange)
        self._arrange(True)

    def eventFilter(self, obj, ev):
        if obj is self.scroll and ev.type() == QEvent.Resize:
            self._refit.start()  # keep "Fit" true when the panel or window is resized
        return super().eventFilter(obj, ev)

    def _toggle_expand(self, on: bool) -> None:
        self.controls.setVisible(not on)
        self.expand.setText("⤡  Show inputs" if on else "⤢  Expand")
        self._refit.start()

    def _toggle_popout(self, on: bool) -> None:
        if on:
            if self.expand.isChecked():
                self.expand.setChecked(False)
            self.expand.hide()
            self._viz_window = VizWindow(self, f"{self.cipher.name} — visualization")
            self._viz_window.closed.connect(lambda: self.popout.setChecked(False))
            self._viz_window.body.addWidget(self.viz)
            self.viz.show()
            self._viz_window.resize(max(900, self.viz.width()), max(640, self.viz.height()))
            self._viz_window.show()
            self.popout.setText("⧉  Dock back")
            self.viz_toggle.setEnabled(False)
        else:
            win, self._viz_window = self._viz_window, None
            self.split.addWidget(self.viz)
            self.viz.setVisible(self.viz_toggle.isChecked())
            self.expand.show()
            self.popout.setText("⧉  Pop out")
            self.viz_toggle.setEnabled(True)
            if win:
                win.closed.disconnect()
                win.close()
                win.deleteLater()
        self._arrange(self._wide)
        self._refit.start()

    def _arrange(self, wide: bool) -> None:
        """Wide: one column of cards beside the visualization. Narrow: two columns above it."""
        self._wide = wide
        # A single column only makes sense when the visualization sits beside the cards.
        beside = self.viz_toggle.isChecked() and not self.popout.isChecked()
        grid = self._top_grid
        inp, key, act, outc = self._cards
        for w in self._cards:
            grid.removeWidget(w)
        for i in range(4):
            grid.setColumnStretch(i, 0)
            grid.setRowStretch(i, 0)
        if wide and beside:
            grid.addWidget(inp, 0, 0)
            grid.addWidget(key, 1, 0)
            grid.addWidget(act, 2, 0)
            grid.addWidget(outc, 3, 0)
            grid.setColumnStretch(0, 1)
            grid.setRowStretch(0, 1)
            grid.setRowStretch(3, 1)
            self.split.setOrientation(Qt.Horizontal)
            self.controls.setMinimumSize(330, 0)
            self.controls.setMaximumWidth(16777215)
        else:
            grid.addWidget(inp, 0, 0)
            grid.addWidget(key, 1, 0)
            grid.addWidget(act, 2, 0)
            grid.addWidget(outc, 0, 1, 3, 1)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            grid.setRowStretch(0, 1)
            self.split.setOrientation(Qt.Horizontal if wide else Qt.Vertical)
            self.controls.setMinimumSize(0, 120)
        QTimer.singleShot(0, self._initial_sizes)

    def _initial_sizes(self) -> None:
        if self.split.count() < 2 or not self.viz.isVisible():
            return
        if self._wide:
            total = self.split.width()
            left = max(330, min(430, int(total * 0.32)))
        else:
            total = self.split.height()
            need = self.top.minimumSizeHint().height() + 4
            left = max(120, min(need, int(total * 0.45), total - self.viz.minimumSizeHint().height() - 2))
        self.split.setSizes([left, max(1, total - left)])

    # ---------------------------------------------------------------------------------------
    def load(self, mode: str, text: str, params: dict) -> None:
        self._cancel_run()
        self._run_inputs = None
        self.mode = mode
        self.input.setPlainText(text)
        self.form.set_values(params)
        self.output.clear()
        self.error.clear()
        self.notes.clear()
        self.status.setText(f"Ready — press {'Encrypt' if mode == 'encrypt' else 'Decrypt'}.")

    def _load_example(self, i: int) -> None:
        if i <= 0:
            return
        ex = self.cipher.examples[i - 1]
        self.load(ex["mode"], ex["text"], {**self.cipher.defaults(), **ex["params"]})
        self.examples.setCurrentIndex(0)

    def _swap(self) -> None:
        out = self.output.toPlainText()
        if out:
            self.load("decrypt" if self.mode == "encrypt" else "encrypt", out, self.form.values())

    def _toggle_viz(self, on: bool) -> None:
        QSettings().setValue("visualize", on)
        if not on and self.popout.isChecked():
            self.popout.setChecked(False)
        self.viz.setVisible(on)
        if not on and self.expand.isChecked():
            self.expand.setChecked(False)
        if not on:
            self.player.stop()
            self._reveal()
        self._arrange(self._wide)

    def run(self, mode: str) -> None:
        self._cancel_run()
        self.mode = mode
        text = self.input.toPlainText()
        for lbl in (self.error, self.notes, self.status):
            lbl.clear()
        letters = clean(text)
        if not letters:
            self._fail("Enter some text first — it needs at least one letter A–Z.", [self.input])
            return
        try:
            params = {**self.cipher.defaults(), **self.form.values()}
            out = self.cipher.run(text, mode, params, self.keep.isChecked())
        except CipherError as e:
            self._fail(str(e), self._fields_for(str(e)))
            return
        except Exception as e:  # a bug — keep the app alive and say so plainly
            traceback.print_exc()
            self._fail(f"Something went wrong ({type(e).__name__}: {e}). Check the key and try again.", [])
            return
        trace = None
        if self.viz_toggle.isChecked():
            try:
                trace = self.cipher.trace(letters, mode, **params)
            except Exception as e:  # the result is fine; only the animation failed
                traceback.print_exc()
                self.notes.setText(f"The step-by-step view is not available for this input ({e}). "
                                   "The result is shown directly.")
        self._pending, self._revealed, self.trace = out, False, trace
        self._run_inputs = self._snapshot()
        if trace and trace.steps:
            self.output.clear()
            if trace.notes:
                self.notes.setText(" ".join(trace.notes))
            self.loading.start("Encrypting" if mode == "encrypt" else "Decrypting")
            if self.fit.isChecked():
                self._fit()
            self._last_step = -1
            self.player.set_count(len(trace.steps), start=0)
            self.player.play()
            if QApplication.focusWidget() in (self.enc_btn, self.dec_btn):
                self.scene.setFocus()  # Space / arrow keys now control the animation
        else:
            self._reveal()

    def _cancel_run(self) -> None:
        """Stop whatever the previous run was doing (animation, loading overlay) before anything else."""
        self.player.stop()
        self.loading.stop()
        self._revealed = True
        self._clear_flags()

    def _fail(self, message: str, fields: list) -> None:
        self.trace = None
        self._run_inputs = None
        self.player.set_count(0)
        self.scene.set_step(None)
        self.explain.clear()
        self.output.clear()
        self.error.setText(f"⚠  {message}")
        for w in fields:
            w.setProperty("invalid", True)
            w.style().unpolish(w)
            w.style().polish(w)
        if fields:
            fields[0].setFocus()

    def _fields_for(self, message: str) -> list:
        """The key widgets an error message is about (by parameter name/label); all of them if unclear."""
        msg = message.lower()
        fields = [(p, self.form.widgets[p.name]) for p in self.cipher.params if p.kind != "bool"]
        hits = [w for p, w in fields if p.name.lower() in msg or p.label.lower() in msg]
        if not hits and ("text" in msg or "message" in msg) and "key" not in msg:
            return [self.input]
        return hits or [w for _, w in fields]

    def _clear_flags(self) -> None:
        for w in [self.input, *self.form.widgets.values()]:
            if w.property("invalid"):
                w.setProperty("invalid", False)
                w.style().unpolish(w)
                w.style().polish(w)

    def _snapshot(self) -> tuple:
        return self.input.toPlainText(), repr(self.form.values()), self.keep.isChecked()

    def _inputs_changed(self) -> None:
        """Editing while (or after) a run is fine: the run keeps going, and we say how to refresh it."""
        self._clear_flags()
        if self.error.text():
            self.error.clear()
        if getattr(self, "_run_inputs", None) is None:
            return
        if self._snapshot() != self._run_inputs:
            what = "The animation shows" if not self._revealed else "The output is from"
            self.notes.setText(f"✎  Inputs changed. {what} the previous run — press Encrypt or Decrypt to update.")
        else:
            self.notes.clear()

    def _reveal(self) -> None:
        if self._revealed:
            return
        self._revealed = True
        self.loading.stop()
        self.output.setPlainText(self._pending)
        n = len(clean(self._pending))
        self.status.setText(f"✔  {'Encrypted' if self.mode == 'encrypt' else 'Decrypted'} — {n} letters.")

    def _show_step(self, i: int) -> None:
        if not self.trace or not (0 <= i < len(self.trace.steps)):
            return
        try:
            self._render_step(i)
        except Exception as e:
            traceback.print_exc()
            self.player.stop()
            self._reveal()
            self.notes.setText(f"The step-by-step view stopped at step {i + 1} ({type(e).__name__}). "
                               "The result above is still correct.")

    def _render_step(self, i: int) -> None:
        st = self.trace.steps[i]
        detail = html.escape(st.detail).replace("\n", "<br>")
        ui = theme().ui
        self.explain.setText(f"<span style='font-size:12pt; font-weight:600'>{html.escape(st.title)}</span><br>"
                             f"<span style='color:{ui['muted']}; font-size:10.5pt'>{detail}</span>")
        animate = self.player.timer.isActive() or i == self._last_step + 1
        self._last_step = i
        self.scene.set_step(st, animate=animate, duration=int(self.player.interval * 0.85))
        if not self._revealed:
            self.loading.set_progress(i, len(self.trace.steps), st.title)
        if i == len(self.trace.steps) - 1:
            self._reveal()

    def _zoom_changed(self, v: int) -> None:
        self.scene.set_zoom(v / 100)
        if self.zoom.hasFocus() or self.zoom.isSliderDown():
            self.fit.setChecked(False)

    def _fit(self) -> None:
        """Choose one zoom for the whole trace so every step fits the visible area."""
        if not self.trace:
            return
        area = self.scroll.contentsRect()  # whole area: scrollbars currently shown must not shrink the fit
        vw = max(200, area.width() - 8)
        vh = max(150, area.height() - 8)
        animated = [st for st in self.trace.steps if st.arrows] or self.trace.steps
        sample = animated[:: max(1, len(animated) // 24)] + animated[-1:]
        sizes = self.scene.natural_sizes(sample)
        w = max(1, max(sz[0] for sz in sizes))
        h = max(1, max(sz[1] for sz in sizes))
        z = max(0.6, min(1.25, vw / w, vh / h))
        self.zoom.blockSignals(True)
        self.zoom.setValue(int(z * 100))
        self.zoom.blockSignals(False)
        self.scene.set_zoom(z)

    def _ensure_visible(self, r: QRectF) -> None:
        self.scroll.ensureVisible(int(r.center().x()), int(r.center().y()), int(r.width()) + 80, int(r.height()) + 20)


# ---------------------------------------------------------------------------------------------
class _CrackWorker(QObject):
    progress = Signal(float, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, cipher: Cipher, letters: str, params: dict):
        super().__init__()
        self.cipher, self.letters, self.params = cipher, letters, params
        self.ctx = CrackContext(lambda f, m: self.progress.emit(f, m))

    @Slot()
    def run(self) -> None:
        try:
            self.done.emit(self.cipher.crack(self.letters, self.ctx, **self.params))
        except CipherError as e:
            self.failed.emit(str(e))
        except Exception as e:
            self.failed.emit(f"Unexpected error: {type(e).__name__}: {e}")


CRACK_RESULTS_HELP = """
## Reading the results
- **Candidates** are possible keys, best first. **English** is how much the decrypted text looks like
  English (0–100 %, from 4-letter-group statistics).
- Click a candidate to preview its full plaintext; double-click or press **Visualize decryption** to watch
  the decryption with that key.
- **Analysis log** explains every step of the attack (frequencies, key-length tests, scores…).
- **Charts** plots the statistics the attack used.

## Tips
- Longer ciphertexts crack much more reliably.
- **Load example ciphertext** encrypts a sample English text with a random key so you can practise.
- Randomised searches (hill climbing, annealing) can be run again if the first result is not readable.
"""

SOLVER_HELP = """
## Manual substitution solver
Type the plain letter you think each cipher letter stands for in the box under it.

- The small number under each cipher letter is its frequency in the ciphertext (%).
- The preview shows mapped letters in **lowercase green**; unmapped letters stay UPPERCASE.
- A plain letter used twice turns **red**.
- **Frequency guess** fills the table by matching frequency ranks (E, T, A, O, I, N…).
- Look for short words (THE, AND, A, I), doubled letters (LL, EE, SS) and common endings (-ING, -ED).
- **Use in visualizer** sends the finished key to the Encrypt / Decrypt tab.
"""


class CrackTab(QWidget):
    useKey = Signal(dict, str)

    def __init__(self, cipher: Cipher, parent=None):
        super().__init__(parent)
        self.cipher = cipher
        self.result: CrackResult | None = None
        self.thread: QThread | None = None
        self.worker: _CrackWorker | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        top = Card("Ciphertext", f"How {cipher.name} is cracked", f"## Method\n{cipher.crack_hint}\n"
                   + (f"\n## Options\n{params_help(cipher.crack_params)}\n" if cipher.crack_params else "")
                   + CRACK_RESULTS_HELP)
        row = QBoxLayout(QBoxLayout.LeftToRight)
        row.setSpacing(14)
        self.input = MonoText("Paste a ciphertext to attack…")
        self.input.setMinimumHeight(80)
        self.input.setMaximumHeight(130)
        row.addWidget(self.input, 3)
        side = QVBoxLayout()
        side.setSpacing(10)
        self.form = ParamForm(cipher.crack_params)
        side.addWidget(self.form)
        btn_box = QWidget()
        btns = FlowLayout(btn_box, spacing=8)
        self.go_btn = QPushButton("⚡  Crack")
        self.go_btn.setObjectName("big")
        self.go_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("ghost")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)
        demo = QPushButton("Load example ciphertext")
        demo.setObjectName("ghost")
        demo.setToolTip("Encrypt a sample English text with a random key to practise on")
        demo.clicked.connect(self._demo)
        for b in (self.go_btn, self.stop_btn, demo):
            btns.addWidget(b)
        side.addWidget(btn_box)
        side.addStretch(1)
        row.addLayout(side, 2)
        top.add(row)
        prog = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        prog.addWidget(self.progress, 1)
        self.status = label("", "muted")
        self.status.setMinimumWidth(10)
        prog.addWidget(self.status, 2)
        top.add(prog)
        self.error = status_label("error")
        top.add(self.error)
        lay.addWidget(top)

        split = QSplitter(Qt.Horizontal)
        cand = Card("Candidates", "Crack results", CRACK_RESULTS_HELP)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Key", "English", "Note", "Plaintext"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.itemDoubleClicked.connect(lambda *_: self._use())
        cand.add(self.table, 2)
        self.preview = MonoText("Select a candidate to preview the plaintext.", read_only=True)
        cand.add(self.preview, 1)
        use = QPushButton("Visualize decryption with this key  →")
        use.clicked.connect(self._use)
        cand.add(use)
        split.addWidget(cand)

        details = Card("Details")
        self.side_tabs = SegmentedTabs()
        details.header.addWidget(self.side_tabs.bar)
        self.log = MonoText(read_only=True)
        self.log.setLineWrapMode(MonoText.NoWrap)
        self.log.setPlaceholderText("The attack's reasoning appears here.")
        self.side_tabs.addTab(self.log, "Analysis log")
        self.charts_box = QWidget()
        self.charts_lay = QVBoxLayout(self.charts_box)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.charts_box)
        self.side_tabs.addTab(sc, "Charts")
        self.solver = None
        if cipher.manual_solver == "substitution":
            self.solver = SubstitutionSolver()
            self.solver.useKey.connect(lambda key: self.useKey.emit({"key": key}, self.input.toPlainText()))
            self.input.textChanged.connect(lambda: self.solver.set_ciphertext(self.input.toPlainText()))
            self.side_tabs.addTab(self.solver, "Manual solver")
            details.header.addWidget(HelpButton("Manual solver", SOLVER_HELP))
        details.add(self.side_tabs.stack, 1)
        split.addWidget(details)
        split.setSizes([520, 620])
        lay.addWidget(split, 1)
        Responsive(self, 1150, layouts=[row], splitters=[split])

    def _demo(self) -> None:
        from .samples import ENGLISH_SAMPLE
        params = {**self.cipher.defaults()}
        for p in self.cipher.params:
            if p.random:
                params[p.name] = p.random(len(clean(ENGLISH_SAMPLE)))
        try:
            self.input.setPlainText(self.cipher.run(ENGLISH_SAMPLE, "encrypt", params))
        except CipherError as e:
            self.error.setText(str(e))
            return
        crack_defaults = {p.name: p.default for p in self.cipher.crack_params}
        if "size" in crack_defaults and "key" in params:  # Hill: matrix size of the random key
            self.form.set_values({"size": params["key"].count(";") + 1})
        self.status.setText("Example ciphertext made with a random key — press Crack.")

    def start(self) -> None:
        letters = clean(self.input.toPlainText())
        self.error.clear()
        if not letters:
            self.error.setText("⚠  Enter some ciphertext first.")
            return
        self.table.setRowCount(0)
        self.log.clear()
        self.preview.clear()
        self._clear_charts()
        self.progress.setValue(0)
        self.go_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.thread = QThread(self)
        self.worker = _CrackWorker(self.cipher, letters, self.form.values())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._progress)
        self.worker.done.connect(self._done)
        self.worker.failed.connect(self._failed)
        self.worker.done.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._finished)
        self.thread.finished.connect(self.thread.deleteLater)
        self.status.setText("Working…")
        self.thread.start()

    def stop(self) -> None:
        if self.worker and self.thread is not None and self.thread.isRunning():
            self.worker.ctx.cancel()
            self.stop_btn.setEnabled(False)
            self.status.setText("Stopping…")

    def shutdown(self) -> None:
        """Called when the app closes: stop a running attack and wait for its thread to finish."""
        if self.thread is not None and self.thread.isRunning():
            if self.worker:
                self.worker.ctx.cancel()
            self.thread.quit()
            self.thread.wait(5000)

    def _progress(self, f: float, msg: str) -> None:
        self.progress.setValue(int(f * 1000))
        self.status.setText(msg)

    def _failed(self, msg: str) -> None:
        self.error.setText(f"⚠  {msg}")
        self.status.clear()

    def _finished(self) -> None:
        self.go_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if self.status.text() == "Stopping…":
            self.status.setText("Stopped.")
        if self.worker:
            self.worker.deleteLater()
        self.worker = None
        self.thread = None  # deleted via deleteLater; never touch it again

    def _done(self, res: CrackResult) -> None:
        self.result = res
        self.progress.setValue(1000)
        stopped = self.worker is not None and self.worker.ctx.cancelled
        n = len(res.candidates)
        if stopped:
            self.status.setText(f"Stopped — best {n} candidate(s) found so far." if n else "Stopped.")
        else:
            self.status.setText(f"Done — {n} candidate(s)." if n else "Done — no candidates; see the analysis log.")
        self.log.setPlainText("\n".join(res.log))
        self.table.setRowCount(len(res.candidates))
        for i, c in enumerate(res.candidates):
            for j, v in enumerate([c.key, f"{c.score * 100:.0f}%", c.note, c.plaintext[:120]]):
                it = QTableWidgetItem(v)
                it.setToolTip(v if j != 3 else c.plaintext[:400])
                if j in (0, 3):
                    it.setFont(mono_font(10))
                self.table.setItem(i, j, it)
        self.table.resizeColumnsToContents()
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        for col, cap in ((0, 200), (2, 150)):  # long keys / notes are elided (full text in the tooltip)
            if self.table.columnWidth(col) > cap:
                self.table.setColumnWidth(col, cap)
        if res.candidates:
            self.table.selectRow(0)
        for ch in res.charts:
            v = ChartView()
            v.show_chart(ch)
            self.charts_lay.addWidget(v)
        self.charts_lay.addStretch(1)
        if self.solver and res.candidates:
            self.solver.set_ciphertext(self.input.toPlainText())
            self.solver.set_key(res.candidates[0].key)

    def _clear_charts(self) -> None:
        while self.charts_lay.count():
            w = self.charts_lay.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _current(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or not self.result:
            return None
        return self.result.candidates[rows[0].row()]

    def _selected(self) -> None:
        c = self._current()
        self.preview.setPlainText(c.plaintext if c else "")

    def _use(self) -> None:
        c = self._current()
        if c:
            self.useKey.emit({**self.cipher.defaults(), **c.params}, self.input.toPlainText())


# ---------------------------------------------------------------------------------------------
class SubstitutionSolver(QWidget):
    """Interactive cipher→plain mapping editor with live partial decryption."""
    useKey = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ct = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        row = QHBoxLayout()
        for text, fn, ghost in (("Frequency guess", self._freq_guess, True), ("Clear", self._clear, True),
                                ("Use in visualizer  →", self._emit, False)):
            b = QPushButton(text)
            if ghost:
                b.setObjectName("ghost")
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)
        grid.setRowMinimumHeight(3, 6)
        self.freq_labels, self.edits = [], []
        for i, ch in enumerate(ALPHABET):
            r0, col = (i // 13) * 3, i % 13
            lab = QLabel(f"<b>{ch}</b>")
            lab.setAlignment(Qt.AlignCenter)
            grid.addWidget(lab, r0, col)
            fl = label("", "muted")
            fl.setAlignment(Qt.AlignCenter)
            fl.setStyleSheet("font-size: 7.5pt")
            grid.addWidget(fl, r0 + 1, col)
            self.freq_labels.append(fl)
            e = QLineEdit()
            e.setMaxLength(1)
            e.setAlignment(Qt.AlignCenter)
            e.setFixedWidth(30)
            e.setStyleSheet("padding: 4px 0;")
            e.setFont(mono_font(11))
            e.textEdited.connect(lambda _t: self._render())
            grid.addWidget(e, r0 + 2, col)
            self.edits.append(e)
        lay.addLayout(grid)
        self.chart = ChartView(height=2.0)
        lay.addWidget(self.chart)
        self.view = QTextBrowser()
        self.view.setFont(mono_font(11))
        lay.addWidget(self.view, 1)
        theme().changed.connect(self._render)

    def set_ciphertext(self, text: str) -> None:
        self.ct = text
        c = counts(text)
        n = sum(c.values()) or 1
        for i, ch in enumerate(ALPHABET):
            self.freq_labels[i].setText(f"{100 * c[ch] / n:.1f}")
        ranked = sorted(ALPHABET, key=lambda ch: (-c[ch], ch))
        self.chart.show_chart(Chart("Cipher letters by frequency vs English", list(ranked),
                                    {"cipher %": [100 * c[ch] / n for ch in ranked],
                                     "English %": [ENGLISH_FREQ[ch] for ch in ENGLISH_ORDER]}, "%"))
        self._render()

    def set_key(self, enc_key: str) -> None:
        """enc_key: cipher alphabet (plain i → enc_key[i])."""
        for p, c in zip(ALPHABET, enc_key):
            self.edits[ALPHABET.index(c)].setText(p.lower())
        self._render()

    def _freq_guess(self) -> None:
        from ..core.ciphers.monoalphabetic import Monoalphabetic
        self.set_key(Monoalphabetic.frequency_guess(clean(self.ct)))

    def _clear(self) -> None:
        for e in self.edits:
            e.clear()
        self._render()

    def mapping(self) -> dict[str, str]:
        return {ALPHABET[i]: e.text().upper() for i, e in enumerate(self.edits) if clean(e.text())}

    def _render(self) -> None:
        m = self.mapping()
        ui = theme().ui
        used = list(m.values())
        for i, e in enumerate(self.edits):
            v = m.get(ALPHABET[i])
            dup = v and used.count(v) > 1
            e.setStyleSheet("padding: 4px 0;" + (f"color: {ui['bad']}; border-color: {ui['bad']};" if dup else ""))
        out = []
        for ch in self.ct:
            u = ch.upper()
            if ch.isascii() and ch.isalpha():
                if u in m:
                    out.append(f"<span style='color:{ui['good']}'>{m[u].lower()}</span>")
                else:
                    out.append(f"<span style='color:{ui['muted']}'>{u}</span>")
            else:
                out.append(html.escape(ch).replace("\n", "<br>"))
        self.view.setHtml(f"<div style='font-family:\"{theme().mono_font}\"; font-size:11pt'>{''.join(out)}</div>")

    def _emit(self) -> None:
        m = self.mapping()
        enc = {}
        for c, p in m.items():
            enc.setdefault(p, c)
        free_c = [c for c in ALPHABET if c not in enc.values()]
        key = "".join(enc.get(p) or free_c.pop(0) for p in ALPHABET)
        self.useKey.emit(key)
