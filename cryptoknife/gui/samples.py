"""Sample texts for demos and the frequency analysis tool."""

ENGLISH_SAMPLE = (
    "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of "
    "foolishness, it was the epoch of belief, it was the epoch of incredulity, it was the season of Light, "
    "it was the season of Darkness, it was the spring of hope, it was the winter of despair, we had everything "
    "before us, we had nothing before us, we were all going direct to Heaven, we were all going direct the "
    "other way. In short, the period was so far like the present period, that some of its noisiest "
    "authorities insisted on its being received, for good or for evil, in the superlative degree of "
    "comparison only."
)

_SECRET = (
    "To Sherlock Holmes she is always the woman. I have seldom heard him mention her under any other name. "
    "In his eyes she eclipses and predominates the whole of her sex. It was not that he felt any emotion akin "
    "to love for Irene Adler. All emotions, and that one particularly, were abhorrent to his cold, precise but "
    "admirably balanced mind."
)


def example_ciphertext() -> str:
    """A Caesar-encrypted paragraph (spaces and punctuation kept) to practise frequency analysis on."""
    from ..core.cipher import get_cipher
    return get_cipher("caesar").run(_SECRET, "encrypt", {"shift": 11}, keep_format=True)
