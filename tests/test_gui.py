"""GUI regression tests (run headless with QT_QPA_PLATFORM=offscreen; skipped if PySide6 is missing)."""
from __future__ import annotations

import os
import sys
import time
import traceback

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import QSettings, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from cryptoknife.core.cipher import all_ciphers  # noqa: E402

ERRORS: list[str] = []


@pytest.fixture(scope="module")
def win():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setOrganizationName("cryptoknife-tests")
    QSettings().clear()
    old_hook = sys.excepthook
    sys.excepthook = lambda t, v, tb: ERRORS.append("".join(traceback.format_exception(t, v, tb)))
    from cryptoknife.gui.main_window import MainWindow
    from cryptoknife.gui.step_player import SPEEDS
    from cryptoknife.gui.theme import theme
    theme().apply(app)
    saved = list(SPEEDS)
    SPEEDS[:] = [(name, 30) for name, _ in SPEEDS]  # fast animations
    w = MainWindow()
    w.resize(1480, 940)
    w.show()
    yield w
    w.close()
    SPEEDS[:] = saved
    sys.excepthook = old_hook


@pytest.fixture(autouse=True)
def no_errors():
    ERRORS.clear()
    yield
    assert not ERRORS, ERRORS[0]


def pump(s: float = 0.05) -> None:
    app = QtWidgets.QApplication.instance()
    end = time.time() + s
    while time.time() < end:
        app.processEvents()
        time.sleep(0.003)


def visual(win, cid):
    win.open_page(f"cipher:{cid}")
    pump()
    return win.pages[f"cipher:{cid}"].visual


@pytest.mark.parametrize("cipher", all_ciphers(), ids=lambda c: c.id)
def test_examples_animate_and_reveal_correct_output(win, cipher):
    v = visual(win, cipher.id)
    for i, ex in enumerate(cipher.examples, 1):
        v._load_example(i)
        v.run(ex["mode"])
        assert not v.error.text()
        v.player.go(v.player.count - 1)
        pump(0.02)
        expected = cipher.run(ex["text"], ex["mode"], {**cipher.defaults(), **ex["params"]}, v.keep.isChecked())
        assert v.output.toPlainText() == expected
        assert not v.loading.isVisible()


@pytest.mark.parametrize("cipher", all_ciphers(), ids=lambda c: c.id)
def test_typing_while_animating_then_running_again(win, cipher):
    v = visual(win, cipher.id)
    v._load_example(1)
    v.run(cipher.examples[0]["mode"])
    pump(0.1)
    QTest.keyClicks(v.input, " more text")
    for le in v.form.findChildren(QtWidgets.QLineEdit):
        QTest.keyClicks(le, "q")
    pump(0.05)
    assert "Inputs changed" in v.notes.text()
    v.enc_btn.click()  # second run, while the first may still be playing
    pump(0.05)
    if v.error.text():  # the edited key may be invalid: then nothing may be left running
        assert not v.loading.isVisible() and not v.player.timer.isActive() and not v.output.toPlainText()
    else:
        v.player.go(v.player.count - 1)
        pump(0.02)
        assert v.output.toPlainText() and not v.loading.isVisible()


def test_failed_second_run_stops_the_first(win):
    v = visual(win, "otp")
    v._load_example(1)
    v.run("encrypt")
    pump(0.05)
    v.input.setPlainText("this text is longer than the pad")
    v.enc_btn.click()
    pump(0.05)
    assert "at least as long" in v.error.text()
    assert not v.loading.isVisible() and not v.player.timer.isActive()
    assert v.form.widgets["key"].property("invalid")
    QTest.keyClicks(v.form.widgets["key"], "A")
    assert not v.form.widgets["key"].property("invalid") and not v.error.text()


def test_empty_input_flags_the_text_box(win):
    v = visual(win, "caesar")
    v.input.setPlainText("  123 ")
    v.enc_btn.click()
    assert v.error.text() and v.input.property("invalid")


def test_popout_and_dock_back(win):
    v = visual(win, "vigenere")
    v._load_example(1)
    v.run("encrypt")
    v.popout.setChecked(True)
    pump(0.1)
    assert v._viz_window is not None and v.viz.window() is v._viz_window
    v._viz_window.close()
    pump(0.1)
    assert not v.popout.isChecked() and v.viz.parent() is v.split


def test_player_keys_do_not_fire_from_other_widgets(win):
    v = visual(win, "caesar")
    v._load_example(1)
    v.run("encrypt")
    v.player.stop()
    v.player.go(2)
    v.keep.box.setFocus()
    before = v.keep.isChecked()
    QTest.keyClick(v.keep.box, Qt.Key_Space)
    pump(0.02)
    assert v.keep.isChecked() != before  # Space toggled the checkbox …
    assert not v.player.timer.isActive() and v.player.index == 2  # … and did not touch the animation


def test_theme_toggle_after_repeated_cracks(win):
    from cryptoknife.gui.theme import theme
    win.open_page("cipher:caesar")
    cr = win.pages["cipher:caesar"].crack
    for _ in range(2):
        cr._demo()
        cr.start()
        end = time.time() + 20
        while cr.worker is not None and time.time() < end:
            pump(0.05)
    assert cr.table.rowCount() == 26
    theme().toggle()
    pump(0.2)
    theme().toggle()
    pump(0.1)


def test_crack_stop_reports_stopped(win):
    win.open_page("cipher:playfair")
    cr = win.pages["cipher:playfair"].crack
    cr.form.set_values({"seconds": 30})
    cr._demo()
    cr.start()
    pump(0.3)
    cr.stop()
    end = time.time() + 20
    while cr.worker is not None and time.time() < end:
        pump(0.05)
    assert cr.status.text().startswith("Stopped")
    assert cr.go_btn.isEnabled() and not cr.stop_btn.isEnabled()


def test_search_enter_opens_first_match(win):
    win.sidebar.search.setText("rail")
    win.sidebar._open_first()
    pump()
    assert win.stack.currentWidget() is win.pages["cipher:railfence"]
    win.sidebar.search.setText("home")
    win.sidebar._open_first()
    pump()
    assert win.stack.currentWidget() is win.pages["home"]
    win.sidebar.search.clear()
