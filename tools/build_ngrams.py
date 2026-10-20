"""Build the English quadgram table used by the automatic crackers.

Downloads a few public-domain books from Project Gutenberg, counts letter
quadgrams and writes the most common ones to cryptoknife/data/quadgrams.txt.

    python tools/build_ngrams.py [--top 40000]
"""
import argparse
import collections
import pathlib
import re
import tempfile
import urllib.request

BOOKS = [1342, 11, 1661, 84, 98, 2701, 74, 345, 1260, 174, 768, 1952]  # P&P, Alice, Sherlock, ...
OUT = pathlib.Path(__file__).resolve().parent.parent / "cryptoknife" / "data" / "quadgrams.txt"


def strip_gutenberg(text: str) -> str:
    start = re.search(r"\*\*\* ?START OF.*?\*\*\*", text)
    end = re.search(r"\*\*\* ?END OF", text)
    return text[start.end() if start else 0: end.start() if end else len(text)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=40000)
    args = ap.parse_args()
    counts = collections.Counter()
    with tempfile.TemporaryDirectory() as tmp:
        for book in BOOKS:
            url = f"https://www.gutenberg.org/cache/epub/{book}/pg{book}.txt"
            path = pathlib.Path(tmp) / f"{book}.txt"
            try:
                urllib.request.urlretrieve(url, path)
            except OSError as exc:
                print(f"skip {book}: {exc}")
                continue
            letters = re.sub(r"[^A-Z]", "", strip_gutenberg(path.read_text("utf-8", "ignore")).upper())
            counts.update(letters[i:i + 4] for i in range(len(letters) - 3))
            print(f"book {book}: {len(letters)} letters")
    OUT.write_text(f"# total {sum(counts.values())}\n" + "".join(f"{q} {n}\n" for q, n in counts.most_common(args.top)))
    print(f"wrote {OUT} ({min(args.top, len(counts))} quadgrams, total {sum(counts.values())})")


if __name__ == "__main__":
    main()
