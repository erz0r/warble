"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/G2pRemapper.cs"""

from .ig2p import IG2p


class G2pRemapper(IG2p):
    def __init__(self, mapped, phoneme_symbols, replacements, glide_symbols=None):
        self.mapped = mapped
        self.phoneme_symbols = phoneme_symbols  # (phoneme, isVowel)
        self.replacements = replacements
        self.glide_symbols = glide_symbols if glide_symbols is not None else set()

    def is_valid_symbol(self, symbol):
        return symbol in self.phoneme_symbols

    def is_vowel(self, symbol):
        return self.phoneme_symbols.get(symbol, False)

    def is_glide(self, symbol):
        return symbol in self.glide_symbols

    def query(self, grapheme):
        phonemes = self.mapped.query(grapheme)
        if phonemes is None:
            return None
        return [self.replacements.get(p, p) for p in phonemes]

    def unpack_hint(self, hint, separator=" "):
        return [s for s in hint.split(separator) if s in self.phoneme_symbols]

    # warble helpers (not in the c#)
    def symbols(self):
        return dict(self.phoneme_symbols)

    def glides(self):
        return set(self.glide_symbols)
