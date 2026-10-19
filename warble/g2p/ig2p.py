"""ported from openutau (MIT, Copyright (c) 2014 StAkira): OpenUtau.Core/Api/IG2p.cs, OpenUtau.Core/Api/IG2pSymbols.cs"""


class IG2p:
    """grapheme to phoneme converter. query() returns a new list of symbols, or None when it has no answer."""

    def is_valid_symbol(self, symbol):
        raise NotImplementedError

    def is_vowel(self, symbol):
        raise NotImplementedError

    def is_glide(self, symbol):
        """true if the symbol is a semivowel or liquid phoneme, like y, w, l, r in english."""
        raise NotImplementedError

    def query(self, grapheme):
        """produces a list of phonemes from grapheme."""
        raise NotImplementedError

    def unpack_hint(self, hint, separator=" "):
        """produces a list of phonemes from hint, removing invalid symbols."""
        raise NotImplementedError


class IG2pSymbols:
    """a phonemizer that can tell the symbols of a note (PhonemeBasedPhonemizer implements it)."""

    def get_symbols(self, note):
        raise NotImplementedError
