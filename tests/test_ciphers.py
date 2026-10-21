"""Known-answer tests from the lectures and the Stallings textbook."""
import pytest

from cryptoknife.core.cipher import CrackContext, all_ciphers, get_cipher
from cryptoknife.core.ciphers.hill import COL
from cryptoknife.core.text import CipherError

LECTURE_KEY = "DQEPRSFTAWXUGOBVHNCMIZLYJK"  # monoalphabetic permutation from the course slides


def run(cid, text, mode="encrypt", keep=False, **params):
    return get_cipher(cid).run(text, mode, params, keep)


@pytest.mark.parametrize("cid,text,mode,params,expected", [
    # Lecture 1 / Section 1
    ("caesar", "computer", "encrypt", {"shift": 8}, "KWUXCBMZ"),
    ("caesar", "Secrecy", "encrypt", {"shift": 8}, "AMKZMKG"),
    ("caesar", "BGROJGZOUT", "decrypt", {"shift": 6}, "validation"),
    ("caesar", "meet me after the toga party", "encrypt", {"shift": 3}, "PHHWPHDIWHUWKHWRJDSDUWB"),
    ("monoalphabetic", "Secrecy", "encrypt", {"key": LECTURE_KEY}, "CRENREJ"),
    ("monoalphabetic", "computer", "encrypt", {"key": LECTURE_KEY}, "EBGVIMRN"),
    ("vigenere", "Secrecy", "encrypt", {"key": "easy"}, "WEUPICQ"),
    ("vigenere", "rolferv", "decrypt", {"key": "easy"}, "nothard"),
    ("autokey", "Secrecy", "encrypt", {"key": "easy"}, "WEUPWGA"),
    ("autokey", "zadgyaeqrn", "decrypt", {"key": "easy"}, "validation"),
    ("otp", "Computer", "encrypt", {"key": "hilmotry"}, "JWXBIMVP"),
    # Stallings
    ("vigenere", "wearediscoveredsaveyourself", "encrypt", {"key": "deceptive"}, "ZICVTWQNGRZGVTWAVZHCQYGLMGJ"),
    ("autokey", "wearediscoveredsaveyourself", "encrypt", {"key": "deceptive"}, "ZICVTWQNGKZEIIGASXSTSLVVWLA"),
    ("hill", "paymoremoney", "encrypt", {"key": "17 17 5; 21 18 21; 2 2 19"}, "RRLMWBKASPDH"),
    ("columnar", "attackpostponeduntiltwoamxyz", "encrypt", {"key": "4 3 1 2 5 6 7"},
     "TTNAAPTMTSUOAODWCOIXKNLYPETZ"),
    ("railfence", "meet me after the toga party", "encrypt", {"rails": 2}, "MEMATRHTGPRYETEFETEOAAT"),
    ("columnar", "wearediscoveredfleeatonce", "encrypt", {"key": "ZEBRAS", "pad": False},
     "EVLNACDTESEAROFODEECWIREE"),
    ("railfence", "wearediscoveredfleeatonce", "encrypt", {"rails": 3}, "WECRLTEERDSOEEFEAOCAIVDEN"),
    # Lecture 1, "To increase the immunity of monoalphabetic cipher"
    ("homophonic", "aaa bbb ccc", "encrypt", {}, "D-?Q2TE7&"),       # a=D,-,? b=Q,2,T c=E,7,&
    ("homophonic", "D-?Q2TE7&", "decrypt", {}, "aaabbbccc"),
    ("polyalphabetic", "aa bb cc", "encrypt", {}, "DOQLEV"),         # a→D,O b→Q,L c→E,V
    ("polyalphabetic", "DOQLEV", "decrypt", {}, "aabbcc"),
    ("digraph", "aa ab ac", "encrypt", {}, "DSCGHH"),                # aa→DS ab→CG ac→HH
    ("digraph", "DSCGHH", "decrypt", {}, "aaabac"),
])
def test_known_answers(cid, text, mode, params, expected):
    assert run(cid, text, mode, **params) == expected


def test_playfair_rules():
    pf = get_cipher("playfair")
    assert pf.encrypt("AR", key="MONARCHY") == "RM"   # same row
    assert pf.encrypt("MU", key="MONARCHY") == "CM"   # same column
    assert pf.encrypt("HS", key="MONARCHY") == "BP"   # rectangle
    assert pf.encrypt("EA", key="MONARCHY") == "IM"
    assert pf.encrypt("BALLOON", key="MONARCHY") == "IBSUPMNA"  # BA LX LO ON
    assert pf.encrypt("HIDETHEGOLDINTHETREESTUMP", key="PLAYFAIREXAMPLE") == "BMODZBXDNABEKUDMUIXMMOUVIF"


def test_hill_column_convention_and_inverse():
    assert run("hill", "help", key="3 3; 2 5", convention=COL) == "HIAT"
    assert run("hill", "HIAT", "decrypt", key="3 3; 2 5", convention=COL) == "help"
    with pytest.raises(CipherError):
        run("hill", "abcd", key="2 4; 6 8")  # det even → not invertible


@pytest.mark.parametrize("cipher", all_ciphers(), ids=lambda c: c.id)
def test_roundtrip_and_trace(cipher):
    text = "THEQUICKBROWNFOXJUMPSOVERTHELAZYDOGTWICEOVER"
    p = cipher.defaults()
    if cipher.id == "otp":
        p["key"] = "Q" * len(text)
    ct = cipher.encrypt(text, **p)
    pt = cipher.decrypt(ct, **p)
    if cipher.id == "playfair":
        assert pt.startswith("THEQUICKBROWNFOXIUMPSOVERTHELAZYDOGTWICEOVER")
    else:
        assert pt[:len(text)] == text
    for mode, src in (("encrypt", text), ("decrypt", ct)):
        tr = cipher.trace(src, mode, **p)
        assert tr.steps and tr.result[:20] == (ct if mode == "encrypt" else pt)[:20]


def test_keep_format():
    assert run("caesar", "Hello, World!", keep=True, shift=3) == "Khoor, Zruog!"
    assert run("vigenere", "Hi there", keep=True, key="b") == "Ij uifsf"
    # ciphers that move letters keep spaces/punctuation but use the default case
    assert run("railfence", "We are, discovered!", keep=True, rails=3) == run("railfence", "wearediscovered", rails=3)[:2] + " " \
        + run("railfence", "wearediscovered", rails=3)[2:5] + ", " + run("railfence", "wearediscovered", rails=3)[5:] + "!"
    pf = run("playfair", "Hello, world", keep=True)
    assert pf.count(",") == 1 and pf.index(",") == 5 and pf.replace(",", "").replace(" ", "") == run("playfair", "Hello world")



def test_homophonic_key_and_choices():
    h = get_cipher("homophonic")
    with pytest.raises(CipherError):
        run("homophonic", "ab", key="a=DQ b=Q")  # Q stands for two letters
    with pytest.raises(CipherError):
        run("homophonic", "abz", key="a=D b=Q")  # no symbols for z
    random_choice = run("homophonic", "attack at dawn", pick="At random")
    assert random_choice == run("homophonic", "attack at dawn", pick="At random")  # reproducible
    assert run("homophonic", random_choice, "decrypt") == "attackatdawn"
    # keep format: spaces and ordinary punctuation stay; punctuation that is a cipher symbol (? and !) is dropped
    ct = run("homophonic", "Hello, world? yes!", keep=True)
    assert ct.count(" ") == 2 and ct.count(",") == 1 and "?" not in ct[-4:]
    assert run("homophonic", ct, "decrypt", keep=True) == "hello, world yes"
    assert h.trace(h.symbols(ct, "decrypt"), "decrypt").result == "HELLOWORLDYES"


def test_polyalphabetic_generalizes_mono_and_vigenere():
    text = "WEAREDISCOVEREDSAVEYOURSELF"
    assert run("polyalphabetic", text, key=LECTURE_KEY) == run("monoalphabetic", text, key=LECTURE_KEY)
    shifted = " ".join("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i:] + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[:i] for i in (3, 4, 2))
    assert run("polyalphabetic", text, key=shifted) == run("vigenere", text, key="DEC")


def test_digraph_table_is_a_permutation():
    from cryptoknife.core.ciphers.digraph import PAIRS, build_table
    table = build_table("AA=DS AB=CG AC=HH", "LECTURE")
    assert sorted(table) == PAIRS and sorted(table.values()) == PAIRS
    assert build_table("", "LECTURE") != build_table("", "OTHER")
    assert run("digraph", "attack at dawn", keep=True).count(" ") == 2
    with pytest.raises(CipherError):
        run("digraph", "ab", fixed="AA=DS AB=DS")  # DS used twice
    with pytest.raises(CipherError):
        run("digraph", "ABC", "decrypt")  # odd ciphertext


LETTER = ("Cdzq Rstcdmsr, Sghr vddj gzr addm z khsskd cheedqdms eqnl zkk sgd nsgdqr xnt'ud dwodqhdmbdc adenqd. "
          "Hs gzr addm xntq kzrs ehqrs vddj ne tmhudqrhsx")
SAMPLE = ("It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of "
          "foolishness, it was the epoch of belief, it was the epoch of incredulity, it was the season of Light, "
          "it was the season of Darkness, it was the spring of hope, it was the winter of despair, we had "
          "everything before us, we had nothing before us, we were all going direct to Heaven, we were all "
          "going direct the other way")


def crack(cid, ct, **kw):
    return get_cipher(cid).crack(ct, CrackContext(), **kw)


def test_crack_lecture_letter():
    from cryptoknife.core.text import clean
    best = crack("caesar", clean(LETTER)).candidates[0]
    assert best.key == "25" and best.plaintext.startswith("DEARSTUDENTS")


def test_crack_vigenere_and_autokey():
    from cryptoknife.core.text import clean
    pt = clean(SAMPLE)
    assert crack("vigenere", get_cipher("vigenere").encrypt(pt, key="LEMON")).candidates[0].key == "LEMON"
    assert crack("autokey", get_cipher("autokey").encrypt(pt, key="QUEEN")).candidates[0].key == "QUEEN"


def test_crack_mono_columnar_rail_hill():
    from cryptoknife.core.text import clean
    pt = clean(SAMPLE)
    mono = get_cipher("monoalphabetic")
    assert crack("monoalphabetic", mono.encrypt(pt, key="ZEBRAS"), restarts=4).candidates[0].plaintext == pt
    ct = get_cipher("columnar").encrypt(pt, key="3 1 4 2 6 5", pad=False)
    assert crack("columnar", ct, max_len=7).candidates[0].plaintext == pt
    assert crack("railfence", get_cipher("railfence").encrypt(pt, rails=5)).candidates[0].key == "5"
    hill = get_cipher("hill")
    ct = hill.encrypt(pt, key="5 17; 8 3")
    assert crack("hill", ct, size=2).candidates[0].key == "5 17; 8 3"
    assert crack("hill", ct, size=2, known="itwasthe").candidates[0].key == "5 17; 8 3"


def test_crack_polyalphabetic_and_homophonic():
    from cryptoknife.core.text import clean
    pt = clean(SAMPLE)
    ct = get_cipher("polyalphabetic").encrypt(pt, key="ZEBRAS QUICK")
    best = crack("polyalphabetic", ct).candidates[0]
    assert len(best.key.split()) == 2 and sum(a == b for a, b in zip(best.plaintext, pt)) > 0.9 * len(pt)
    ct = get_cipher("homophonic").encrypt(pt)
    best = crack("homophonic", ct, seconds=60).candidates[0]
    assert sum(a == b for a, b in zip(best.plaintext, pt)) > 0.9 * len(pt)


@pytest.mark.parametrize("cipher", all_ciphers(), ids=lambda c: c.id)
def test_arrows_point_at_existing_cells(cipher):
    from cryptoknife.core.trace import Grid, Stack, Wheel
    p = cipher.defaults()
    text = "MEETMEATTHEBRIDGEATNOON"
    if cipher.id == "otp":
        p["key"] = "Q" * len(text)
    ct = cipher.encrypt(text, **p)
    for mode, src in (("encrypt", text), ("decrypt", ct)):
        steps = cipher.trace(src, mode, **p).steps
        assert sum(len(s.arrows) for s in steps) > 0
        for st in steps:
            ids = set()

            def collect(panel):
                if isinstance(panel, Stack):
                    for c in panel.panels:
                        collect(c)
                    return
                if isinstance(panel, Wheel):
                    ids.update({f"{panel.id}o{i}" for i in range(26)} | {f"{panel.id}i{i}" for i in range(26)})
                    return
                ids.add(panel.id)
                if isinstance(panel, Grid):
                    ids.update(c.id for r in panel.cells for c in r)
                    if panel.id and panel.row_labels:
                        ids.update(f"{panel.id}:row{i}" for i in range(len(panel.row_labels)))

            for row in st.rows:
                for panel in row:
                    collect(panel)
            for a in st.arrows:
                assert a.src in ids and a.dst in ids, (mode, st.title, a)


def test_columnar_short_text_has_empty_columns():
    # a key longer than the text leaves empty columns; the trace must still build
    c = get_cipher("columnar")
    for key in ("zz", "abc def"):
        for mode in ("encrypt", "decrypt"):
            assert c.trace("x", mode, **{**c.defaults(), "key": key}).steps


def test_caesar_negative_and_large_shifts():
    for k, same in ((-3, 23), (29, 3), (-29, 23), (26, 0)):
        assert run("caesar", "Attack at dawn", keep=True, shift=k) == run("caesar", "Attack at dawn", keep=True, shift=same)
        ct = run("caesar", "attackatdawn", shift=k)
        assert run("caesar", ct, "decrypt", shift=k) == "attackatdawn"
    c = get_cipher("caesar")
    steps = c.trace("ATTACKATDAWN", "encrypt", shift=-3).steps
    assert steps[1].title.startswith("Shift the alphabet left")
    assert steps[-1].detail.endswith("XQQXZHXQAXTK")
