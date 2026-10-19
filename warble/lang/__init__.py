"""language front-ends, keyed by language code. each module exposes normalize_lyric(lyric) -> list
of candidate spellings to try against a bank's dictionary. add a language by adding a module and
registering it here."""

from . import ja


def _identity(lyric):
    return [lyric]


FRONTENDS = {"ja": ja.normalize_lyric}


def candidates(lang, lyric):
    """spellings to look up, in order; always starts with the lyric itself."""
    fn = FRONTENDS.get(lang or "", _identity)
    out = []
    for c in fn(lyric) + [lyric.lower()]:
        if c not in out:
            out.append(c)
    return out


PHONEME_GUESSES = {"ja": ja.phoneme_guesses}


def phoneme_guesses(lang, lyric):
    """front-end guesses at raw phonemes for lyrics a dictionary doesn't cover."""
    fn = PHONEME_GUESSES.get(lang or "")
    return fn(lyric) if fn else []
