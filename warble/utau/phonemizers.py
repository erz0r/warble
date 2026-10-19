"""choosing a classic phonemizer for a bank. the ports themselves live in warble.utau.pz."""

import os

from ..errors import WarbleError
from .pz import REGISTRY as _PZ, load_all

NOT_PORTED_REASONS = {}


def registry():
    load_all()
    return _PZ


def _short(cls):
    """our short name for a port: its openutau tag, lowercased with spaces as underscores."""
    return cls.tag.lower().replace(" ", "_").replace("-", "_")


def names():
    return {_short(c): c for c in registry().values()}


# short names kept stable for scores written earlier
ALIASES = {"default": "default", "ja_vcv": "ja_vcv", "ja_cvvc": "ja_cvvc"}


def resolve(name):
    """a short name, an openutau tag, or an openutau class name -> port class or None."""
    reg = registry()
    n = names()
    if name in n:
        return n[name]
    for c in reg.values():
        if name in (c.tag, c.openutau_class, c.name):
            return c
    return None


FILE_HINTS = [
    ("presamp.ini", "ja_vcv_&_cvvc"),
    ("arpasing.yaml", "en_arpa+"),
    ("envccv.yaml", "en_vccv"),
    ("en-cpv.yaml", "en_c+v"),
    ("en-xsampa.yaml", "en_x_sampa"),
    ("kocv.yaml", "ko_cv"),
    ("zhcvvplus.yaml", "zh_cvv+"),
    ("filipino.yaml", "fil_vcv_&_cvvc"),
]


def _has_kana(bank):
    n = 0
    for oset in bank.oto_sets:
        for o in oset.otos[:400]:
            if any("\u3040" <= c <= "\u30ff" for c in o.alias):
                n += 1
    return n > 10


def choose(bank, reclist_style, requested=None):
    """-> (short name, how it was chosen, warning or None)."""
    if requested:
        cls = resolve(requested)
        if cls is None:
            raise WarbleError("phonemizer_unknown", f"phonemizer '{requested}' is not available", hint=f"available: {sorted(names())}")
        return _short(cls), "requested", None
    warn = None
    dp = bank.character.get("default_phonemizer")
    if dp:
        cls = resolve(dp)
        if cls is not None:
            return _short(cls), f"character.yaml default_phonemizer {dp}", None
        warn = f"bank asks for {dp}, which is not ported yet; picked one from the reclist style instead"
    # files a bank ships for a specific phonemizer
    files = {f.lower() for f in os.listdir(bank.root)}
    for fname, pick in FILE_HINTS:
        if fname in files and resolve(pick):
            return pick, f"bank ships {fname}", warn
    styles = reclist_style.split("+")
    kana = _has_kana(bank)
    if styles[0] in ("cv", "vcv", "cvvc") and kana and resolve("ja_vcv_&_cvvc"):
        # openutau's general japanese phonemizer: handles cv, vcv and cvvc banks (presamp.ini optional)
        return "ja_vcv_&_cvvc", f"reclist style {reclist_style}, kana aliases", warn
    pick = {"vcv": "ja_vcv", "cvvc": "ja_cvvc", "cv": "default", "vccv": "en_vccv", "diphone": "en_arpa+"}.get(styles[0])
    if pick and resolve(pick):
        return pick, f"reclist style {reclist_style}", warn
    raise WarbleError("no_phonemizer", f"no ported phonemizer fits a '{reclist_style}' bank automatically",
                      hint=f"pick one with 'phonemizer <name>' (available: {sorted(names())}), or give aliases in [brackets]")
