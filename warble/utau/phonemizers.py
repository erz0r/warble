"""choosing a classic phonemizer for a bank. the ports themselves live in warble.utau.pz."""

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
    styles = reclist_style.split("+")
    pick = {"vcv": "ja_vcv", "cvvc": "ja_cvvc", "cv": "default"}.get(styles[0])
    if pick and resolve(pick):
        return pick, f"reclist style {reclist_style}", warn
    raise WarbleError("no_phonemizer", f"no ported phonemizer fits a '{reclist_style}' bank automatically",
                      hint=f"pick one with 'phonemizer <name>' (available: {sorted(names())}), or give aliases in [brackets]")
